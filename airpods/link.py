"""Enlace con los AirPods: canal L2CAP clásico en el PSM 0x1001.

Expone "bytes recibidos / enviar bytes / se cortó". Sin root.
"""

import socket
import threading

from . import aap


class Link:
    def __init__(self, address, on_rx, on_closed, on_tx=None, timeout=10.0):
        self.address = address
        self._on_rx = on_rx
        self._on_closed = on_closed
        self._on_tx = on_tx
        self._timeout = timeout
        self._sock = None
        self._closing = False

    def open(self):
        """Conecta y hace el saludo inicial. Lanza OSError si falla."""
        sock = socket.socket(
            socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP
        )
        sock.settimeout(self._timeout)
        try:
            sock.connect((self.address, aap.PSM))
        except OSError:
            sock.close()
            raise
        sock.settimeout(None)
        self._sock = sock
        for packet in aap.INITIAL_PACKETS:
            self.send(packet)
        threading.Thread(target=self._read_loop, daemon=True).start()

    def send(self, data):
        self._sock.send(data)
        if self._on_tx:
            self._on_tx(data)

    def close(self):
        self._closing = True
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._sock.close()

    def _read_loop(self):
        try:
            while True:
                data = self._sock.recv(4096)
                if not data:
                    break
                self._on_rx(data)
        except OSError:
            pass
        finally:
            if not self._closing:
                self._on_closed()
