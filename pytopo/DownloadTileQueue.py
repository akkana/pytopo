# Copyright (C) 2009-2016 by Akkana Peck.
# You are free to use, share or modify this program under
# the terms of the GPLv2 or, at your option, any later GPL.

'''DownloadTileQueue: maintain a list of tiles being downloaded.
'''

from __future__ import print_function

import sys
import os

try:
    # Python 3:
    from urllib.request import urlopen, Request
except ImportError:
    # Python 2:
    from urllib2 import urlopen, Request

import gobject

import threading

# The only way I can find to have a module-wide user_agent variable
# is to import pytopo and have it be pytopo.user_agent.
# Things like from pytopo import user_agent makes a copy of
# the variable and doesn't see later changes.
import pytopo

# If we download files, we'll try to use the magic library to make
# sure we got the right file type. But no need to import it
# if we're not downloading anything.
magic_parser = None

Debug = False    # XXX move this into a class

class DownloadTileQueue:
    def __init__(self):
        self.queue = []    # Will be a list
        gobject.threads_init()

    def __len__(self):
        return len(self.queue)

    # XXX we should perhaps use a set, for faster existence checking,
    # but then we wouldn't retain order.
    def push(self, url, path):
        """Push details for a new tile onto the queue if not already there.
        """
        for q in self.queue:
            if q[1] == path:  # Are paths the same? Already queued.
                return
        if path:
            self.queue.insert(0, [url, path])

    def pop(self):
        return self.queue.pop()

    def peek(self):
        return self.queue[-1]

    # A relatively clean way of downloading files in a separate thread.
    # http://code.activestate.com/recipes/577129-run-asynchronous-tasks-using-coroutines/
    #
    @staticmethod
    def start_job(generator):
        """Start a job (a coroutine that yield generic tasks)."""
        def _task_return(result):
            """Function to be sent to tasks to be used as task_return."""
            def _advance_generator():
                try:
                    new_task = generator.send(result)
                except StopIteration:
                    return
                new_task(_task_return)
            # make sure the generator is advanced in the main thread
            gobject.idle_add(_advance_generator)
        _task_return(None)
        return generator

    @staticmethod
    def threaded_task(function, *args, **kwargs):
        """Run function inside a thread, return the result."""
        def _task(task_return):
            def _thread():
                result = function(*args, **kwargs)
                gobject.idle_add(task_return, result)
            thread = threading.Thread(target=_thread, args=())
            thread.setDaemon(True)
            thread.start()
        return _task

    @staticmethod
    def download_job(url, localpath, callback):
        def download(url, localpath, callback):
            global magic_parser
            if Debug:
                print("Downloading", url)
                print("  to", localpath)
            try:

                if pytopo.user_agent:
                    headers = { 'User-Agent': pytopo.user_agent }
                    response = urlopen(Request(url, headers=headers))
                else:
                    headers = {}
                    response = urlopen(Request(url))
                data = response.read()
                with open(localpath, "wb") as localfile:
                    localfile.write(data)

            except IOError as e:
                print("Couldn't download", url, ":")
                print(e)
                return None

            # Sometimes there's no error but we still didn't download anything.
            # Don't try to MIME parse that: magic gets confused by empty files.
            if not os.path.exists(localpath):
                print("Failed to download", url, "to", localpath)
                return None

            if magic_parser is None:
                try:
                    import magic
                    magic_parser = magic.open(magic.MAGIC_MIME)
                    magic_parser.load()
                except:
                    magic_parser = False
            if magic_parser:
                mimetype = magic_parser.file(localpath)
                if not mimetype.startswith("image/"):
                    print("Problem downloading'%s' to '%s'" % (url, localpath))
                    print("Type:", mimetype)
                    # Opencyclemap, at least, sometimes serves text files
                    # that say "tile not available". Other servers may serve
                    # HTML files.
                    # If it's text, give the user a chance to see it.
                    if mimetype.startswith("text/"):
                        with open(localpath, 'r') as errfile:
                            errstr = errfile.read()
                        # Don't show >3 full lines of error message:
                        if len(errstr) > 240:
                            errstr = errstr[0:100]
                        print('File contents: "%s"' % errstr.strip())
                    else:
                        print("File type is", mimetype)

                    # Return no path, so it can be deleted if appropriate.
                    return None

            return localpath

        path = yield DownloadTileQueue.threaded_task(download, url,
                                                     localpath, callback)
        if Debug:
            print("[downloaded %s]" % (localpath), file=sys.stderr)
        callback(path)
