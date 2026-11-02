"""Modo de captura: vuelca los paquetes crudos a un archivo JSON Lines.

Una línea por paquete: {"ts": <epoch s>, "dir": "rx"|"tx", "hex": "<bytes>"}.
Las etiquetas de situación (para los ejemplos de las pruebas) son líneas
{"ts": ..., "dir": "mark", "label": "..."} que se añaden con `mark`.
"""

import json
import threading
import time


class CaptureWriter:
    def __init__(self, path, clock=time.time):
        self._file = open(path, "a", encoding="utf-8")
        self._clock = clock
        self._lock = threading.Lock()
        self.rx_packets = []

    def _write(self, entry):
        with self._lock:
            self._file.write(json.dumps(entry) + "\n")
            self._file.flush()

    def rx(self, data):
        raw = bytes(data)
        with self._lock:
            self.rx_packets.append(raw)
        self._write({"ts": self._clock(), "dir": "rx", "hex": raw.hex()})

    def tx(self, data):
        self._write({"ts": self._clock(), "dir": "tx", "hex": bytes(data).hex()})

    def mark(self, label):
        self._write({"ts": self._clock(), "dir": "mark", "label": label})

    def close(self):
        with self._lock:
            self._file.close()
