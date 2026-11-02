"""Control local por socket Unix con líneas JSON."""

import json
import os
import socket
import threading


def default_socket_path():
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return os.path.join(runtime_dir, "airpods.sock")


class ControlServer:
    def __init__(self, core, socket_path=None):
        self._core = core
        self.socket_path = socket_path or default_socket_path()
        self._sock = None
        self._clients = set()
        self._lock = threading.Lock()

    def start(self):
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen()
        self._sock = sock
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        with self._lock:
            clients = list(self._clients)
            self._clients.clear()
        for c in clients:
            try:
                c.close()
            except OSError:
                pass
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass

    def _accept_loop(self):
        while self._sock is not None:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                break
            with self._lock:
                self._clients.add(conn)
            threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()

    def _handle_client(self, conn):
        send_lock = threading.Lock()
        closed = threading.Event()

        def send_state(state):
            line = (json.dumps(state) + "\n").encode("utf-8")
            with send_lock:
                try:
                    conn.sendall(line)
                except OSError:
                    closed.set()

        try:
            f = conn.makefile("r", encoding="utf-8")
            line = f.readline()
            if not line:
                return
            req = json.loads(line)
            if req.get("cmd") == "watch":
                self._core.subscribe(send_state)
                try:
                    while not closed.is_set():
                        if not conn.recv(1):
                            break
                except OSError:
                    pass
                finally:
                    self._core.unsubscribe(send_state)
        except (OSError, ValueError):
            pass
        finally:
            with self._lock:
                self._clients.discard(conn)
            try:
                conn.close()
            except OSError:
                pass
