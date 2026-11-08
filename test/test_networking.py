#!/usr/bin/env python3

import unittest
from unittest import mock

# import requests
import subprocess
import signal
import time
import sys

sys.path.insert(0, '..')


class TestTimeout(unittest.TestCase):
    def setUp(self):
        pass
        # p = mock.patch.object(requests.Session, "send", slow_timeout_send)
        # p.start()
        # self.addCleanup(p.stop)                  # runs last
        # self.addCleanup(self.drain_pool)         # runs first

    # def drain_pool(self):
    #     # however your class exposes its session/executor:
    #     self.obj.session.executor.shutdown(wait=True)

    def test_exit_with_pending_requests(self):
        WAIT_BEFORE_QUITTING = 3     # seconds
        WAIT_FOR_EXIT = 30           # seconds
        # Use Popen as a context manager, to make sure the proc.stdout
        # pipe gets closed
        with subprocess.Popen(
            [sys.executable, "-m", "test.timeout_runner"],
            stdout=subprocess.PIPE, text=True) as proc:
            try:
                print("Waiting for the window to come up...")
                time.sleep(WAIT_BEFORE_QUITTING)
                t0 = time.monotonic()
                print("Sending an exit signal")
                proc.send_signal(signal.SIGUSR1)
                print("Waiting for process to exit...")
                rc = proc.wait(timeout=WAIT_FOR_EXIT)
                print("Process exited")
                self.assertEqual(rc, 0)
                self.assertLess(time.monotonic() - t0, WAIT_FOR_EXIT)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()

if __name__ == "__main__":
    unittest.main()
