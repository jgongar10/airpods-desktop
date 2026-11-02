"""Enlace con los AirPods: canal L2CAP clásico en el PSM 0x1001.

Expone "bytes recibidos / enviar bytes / se cortó". Sin root.
"""

import socket
import threading

from . import aap


class Link:
    def __init__(self, address, on_rx, on_closed, on_tx=None, timeout=10.0,
                 socket_factory=None):
        self.address = address
        self._on_rx = on_rx
        self._on_closed = on_closed
        self._on_tx = on_tx
        self._timeout = timeout
        self._socket_factory = socket_factory or self._default_socket
        self._sock = None
        self._closing = False

    @staticmethod
    def _default_socket():
        return socket.socket(
            socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP
        )

    def open(self):
        """Conecta, espera el saludo y pide notificaciones. Lanza OSError si falla."""
        sock = self._socket_factory()
        sock.settimeout(self._timeout)
        self._sock = sock
        try:
            sock.connect((self.address, aap.PSM))
            self.send(aap.HANDSHAKE)
            while True:
                data = sock.recv(4096)
                if not data:
                    raise OSError("Canal cerrado durante el saludo")
                self._on_rx(data)
                if data.startswith(aap.HANDSHAKE_ACK_PREFIX):
                    break
            for packet in aap.POST_HANDSHAKE_PACKETS:
                self.send(packet)
        except OSError:
            self._sock = None
            sock.close()
            raise
        sock.settimeout(None)
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
