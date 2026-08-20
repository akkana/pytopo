"""Tiny line-delimited JSON protocol for talking between the map and plot
processes. Both processes import this module; one side runs as a server,
the other connects as a client, and messages flow in either direction
after that.
"""
import json
import threading

DEFAULT_PORT = 8765


def send_message(sock, msg: dict):
    """Send a single JSON message, newline-terminated."""
    data = (json.dumps(msg) + "\n").encode("utf-8")
    sock.sendall(data)


def recv_loop(sock, on_message, on_close=None):
    """Run in a background thread: read newline-delimited JSON messages
    from sock and call on_message(msg_dict) for each one. Call on_close()
    when the connection ends.

    This does NOT touch any GUI toolkit directly - callers must marshal
    on_message onto their GUI thread themselves (GLib.idle_add for GTK,
    a Qt signal for Qt). Calling GUI methods directly from this thread
    will crash or corrupt the UI.
    """
    buf = b""
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if line.strip():
                    on_message(json.loads(line.decode("utf-8")))
    except OSError:
        pass
    finally:
        if on_close:
            on_close()


def start_recv_thread(sock, on_message, on_close=None):
    t = threading.Thread(target=recv_loop, args=(sock, on_message, on_close),
                         daemon=True)
    t.start()
    return t
