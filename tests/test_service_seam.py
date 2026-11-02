import io
import json
import os
import tempfile
import threading
import unittest

from airpods import cli
from airpods.core import Core
from airpods.server import ControlServer


def load_capture_rx(name):
    path = os.path.join("docs", "captures", f"{name}.jsonl")
    packets = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("dir") == "rx":
                packets.append(bytes.fromhex(entry["hex"]))
    return packets


class FakeLink:
    def __init__(self, on_rx, on_closed):
        self._on_rx = on_rx
        self._on_closed = on_closed

    def open(self):
        pass

    def close(self):
        pass

    def receive(self, packet):
        self._on_rx(packet)


class FakeAirPods:
    def __init__(self):
        self._on_connected = None
        self._on_disconnected = None
        self.link = None

    def bind(self, on_connected, on_disconnected):
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected

    def make_link(self, _address, on_rx, on_closed):
        self.link = FakeLink(on_rx, on_closed)
        return self.link

    def connect(self, address="AA:BB:CC:DD:EE:FF"):
        self._on_connected(address)

    def disconnect(self, address="AA:BB:CC:DD:EE:FF"):
        self._on_disconnected(address)

    def replay(self, capture_name):
        for packet in load_capture_rx(capture_name):
            self.link.receive(packet)


class WatchBatteryTest(unittest.TestCase):
    def test_watch_emits_initial_state_on_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            sock_path = os.path.join(tmp, "airpods.sock")
            fake = FakeAirPods()
            core = Core(link_factory=fake.make_link)
            fake.bind(core.on_connected, core.on_disconnected)
            server = ControlServer(core, sock_path)
            server.start()
            self.addCleanup(server.close)

            lines = []
            got_first = threading.Event()
            stop = threading.Event()

            def on_line(line):
                lines.append(json.loads(line))
                got_first.set()
                stop.set()

            t = threading.Thread(
                target=cli.main,
                args=(["watch"],),
                kwargs={"socket_path": sock_path, "out": on_line, "stop_event": stop},
                daemon=True,
            )
            t.start()
            self.assertTrue(got_first.wait(timeout=2.0))
            t.join(timeout=2.0)

            self.assertEqual(lines, [{
                "connected": False,
                "communicating": False,
                "battery": {
                    "left": {"level": None, "charging": False},
                    "right": {"level": None, "charging": False},
                    "case": {"level": None, "charging": False},
                },
                "noise_mode": None,
                "in_ear": {"left": None, "right": None},
                "ear_detection": True,
            }])

    def test_watch_updates_battery_across_real_captures(self):
        with tempfile.TemporaryDirectory() as tmp:
            sock_path = os.path.join(tmp, "airpods.sock")
            fake = FakeAirPods()
            core = Core(link_factory=fake.make_link)
            fake.bind(core.on_connected, core.on_disconnected)
            server = ControlServer(core, sock_path)
            server.start()
            self.addCleanup(server.close)

            lines = []
            cond = threading.Condition()
            stop = threading.Event()

            def on_line(line):
                with cond:
                    lines.append(json.loads(line))
                    cond.notify_all()

            def wait_for(count):
                with cond:
                    self.assertTrue(
                        cond.wait_for(lambda: len(lines) >= count, timeout=2.0),
                        f"Esperaba al menos {count} líneas, recibidas {len(lines)}",
                    )

            t = threading.Thread(
                target=cli.main,
                args=(["watch"],),
                kwargs={"socket_path": sock_path, "out": on_line, "stop_event": stop},
                daemon=True,
            )
            t.start()
            wait_for(1)

            fake.connect()
            wait_for(2)
            self.assertEqual(lines[1]["connected"], True)
            self.assertEqual(lines[1]["communicating"], True)

            # 1) Estuche cerrado: izquierdo y derecho al 100 % sin cargar, estuche desconocido (null, nunca 0)
            fake.replay("bateria-estuche-cerrado")
            wait_for(3)
            self.assertEqual(lines[2]["battery"], {
                "left": {"level": 100, "charging": False},
                "right": {"level": 100, "charging": False},
                "case": {"level": None, "charging": False},
            })

            # 2) Auricular derecho en el estuche cargando, estuche sigue desconocido (0xff / status 04 -> null)
            fake.replay("auricular-cargando")
            wait_for(4)
            self.assertEqual(lines[3]["battery"], {
                "left": {"level": 100, "charging": False},
                "right": {"level": 100, "charging": True},
                "case": {"level": None, "charging": False},
            })

            # 3) Estuche abierto con ambos auriculares dentro:
            #    primero llega un paquete transitorio con ambos cargando y estuche desconocido,
            #    y luego el paquete con el estuche al 36 % (y duplicados que no deben reemitirse).
            fake.replay("bateria-estuche-abierto")
            wait_for(6)
            self.assertEqual(lines[4]["battery"], {
                "left": {"level": 100, "charging": True},
                "right": {"level": 100, "charging": True},
                "case": {"level": None, "charging": False},
            })
            self.assertEqual(lines[5]["battery"], {
                "left": {"level": 100, "charging": True},
                "right": {"level": 100, "charging": True},
                "case": {"level": 36, "charging": False},
            })
            self.assertEqual(len(lines), 6)

            # 4) Sesión con niveles intermedios distintos (izquierdo 89 %, derecho 96 % y luego 95 %)
            fake.replay("sesion-oido")
            wait_for(8)
            self.assertEqual(lines[6]["battery"], {
                "left": {"level": 89, "charging": False},
                "right": {"level": 96, "charging": False},
                "case": {"level": None, "charging": False},
            })
            self.assertEqual(lines[7]["battery"], {
                "left": {"level": 89, "charging": False},
                "right": {"level": 95, "charging": False},
                "case": {"level": None, "charging": False},
            })
            self.assertEqual(len(lines), 8)

            stop.set()
            fake.disconnect()
            t.join(timeout=2.0)

    def test_watch_fails_with_clear_message_when_service_not_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_sock = os.path.join(tmp, "no-service.sock")
            err = io.StringIO()
            code = cli.main(["watch"], socket_path=missing_sock, err=err)
            self.assertNotEqual(code, 0)
            self.assertIn("servicio", err.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
