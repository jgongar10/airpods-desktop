"""Servicio en segundo plano: detecta AirPods, abre el enlace AAP, mantiene el
estado en el núcleo y expone el control local por socket Unix."""

import argparse
import logging
import os
import signal
import sys
import threading
import time

from gi.repository import GLib

from . import guided
from .bluez import AirPodsWatcher
from .capture import CaptureWriter
from .core import Core
from .link import Link
from .server import ControlServer

log = logging.getLogger("airpods")


class Service:
    def __init__(self, capture=None, socket_path=None):
        self._capture = capture
        self.core = Core(link_factory=self._make_link)
        self.server = ControlServer(self.core, socket_path=socket_path)
        self._watcher = AirPodsWatcher(self._connected, self._disconnected)

    def start(self):
        self.server.start()
        self._watcher.start()

    def close(self):
        self.server.close()

    def _connected(self, address):
        log.info("AirPods conectados: %s", address)
        # La conexión L2CAP bloquea: fuera del hilo principal de GLib.
        threading.Thread(
            target=self.core.on_connected, args=(address,), daemon=True
        ).start()

    def _disconnected(self, address):
        log.info("AirPods desconectados: %s", address)
        self.core.on_disconnected(address)

    def _make_link(self, address, on_rx, on_closed):
        cap_rx = self._capture.rx if self._capture else None
        cap_tx = self._capture.tx if self._capture else None

        def handle_rx(data):
            log.debug("rx %s", data.hex())
            if cap_rx:
                cap_rx(data)
            on_rx(data)

        def handle_closed():
            log.warning("Canal L2CAP cerrado")
            on_closed()

        return Link(
            address,
            on_rx=handle_rx,
            on_closed=handle_closed,
            on_tx=cap_tx,
        )


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
    try:
        loop.run()
    finally:
        service.close()
        if capture and not args.guided:
            capture.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
