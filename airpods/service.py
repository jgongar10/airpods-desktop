"""Servicio en segundo plano (primer contacto): detecta, conecta y captura.

Uso: python -m airpods.service [--capture ARCHIVO]
"""

import argparse
import logging
import os
import signal
import sys
import threading
import time

from gi.repository import GLib

from .bluez import AirPodsWatcher
from . import guided
from .capture import CaptureWriter
from .link import Link

log = logging.getLogger("airpods")


class Service:
    def __init__(self, capture=None):
        self._capture = capture
        self._link = None
        self._watcher = AirPodsWatcher(self._connected, self._disconnected)

    def start(self):
        self._watcher.start()

    def _connected(self, address):
        log.info("AirPods conectados: %s", address)
        # La conexión L2CAP bloquea: fuera del hilo principal de GLib.
        threading.Thread(target=self._open_link, args=(address,), daemon=True).start()

    def _disconnected(self, address):
        log.info("AirPods desconectados: %s", address)
        if self._link:
            self._link.close()
            self._link = None

    def _open_link(self, address):
        rx = self._capture.rx if self._capture else (lambda d: None)
        tx = self._capture.tx if self._capture else None
        link = Link(address, on_rx=lambda d: self._on_rx(d, rx),
                    on_closed=lambda: log.warning("Canal L2CAP cerrado"), on_tx=tx)
        try:
            link.open()
        except OSError as exc:
            log.error("No se pudo abrir L2CAP 0x1001: %s", exc)
            return
        self._link = link
        log.info("Canal L2CAP abierto y saludo enviado")

    @staticmethod
    def _on_rx(data, rx):
        log.debug("rx %s", data.hex())
        rx(data)


def _mark_from_stdin(capture):
    label = sys.stdin.readline().strip()
    if label:
        capture.mark(label)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(prog="airpods-service")
    parser.add_argument("--capture", metavar="ARCHIVO",
                        help="vuelca los paquetes crudos (JSON Lines)")
    parser.add_argument("--guided", metavar="DIRECTORIO",
                        help="captura guiada: una situación tras otra, "
                             "guarda un archivo por situación en DIRECTORIO")
    parser.add_argument("--only", metavar="A,B",
                        help="con --guided, solo estas situaciones (separadas por comas)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.guided:
        os.makedirs(args.guided, exist_ok=True)
        args.capture = os.path.join(args.guided, f"sesion-{int(time.time())}.jsonl")
    capture = CaptureWriter(args.capture) if args.capture else None
    service = Service(capture)
    service.start()
    loop = GLib.MainLoop()
    if args.guided:
        def guide():
            guided.run(capture, only=args.only.split(',') if args.only else None)
            capture.close()
            for path in guided.split(args.capture, args.guided):
                print("Guardado", path)
            GLib.idle_add(loop.quit)
        threading.Thread(target=guide, daemon=True).start()
    elif capture and sys.stdin.isatty():
        print("Captura activa. Escribe una etiqueta y pulsa Enter para marcarla.")
        GLib.io_add_watch(sys.stdin.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN,
                          lambda *_: _mark_from_stdin(capture))
    for sig in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, loop.quit)
    loop.run()
    if capture and not args.guided:
        capture.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
