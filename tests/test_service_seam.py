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
    def __init__(self, on_rx, on_closed, fail_open=False):
        self._on_rx = on_rx
        self._on_closed = on_closed
        self._fail_open = fail_open
        self.sent = []

    def open(self):
        if self._fail_open:
            raise OSError("L2CAP connection refused")

    def send(self, data):
        self.sent.append(bytes(data))

    def close(self):
        pass

    def drop(self):
        self._on_closed()

    def receive(self, packet):
        self._on_rx(packet)


class FakeAirPods:
    def __init__(self):
        self._on_connected = None
        self._on_disconnected = None
        self.link = None
        self.fail_next_open = 0
        self.open_attempts = 0

    def bind(self, on_connected, on_disconnected):
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected

    def make_link(self, _address, on_rx, on_closed):
        self.open_attempts += 1
        fail = self.fail_next_open > 0
        if fail:
            self.fail_next_open -= 1
        self.link = FakeLink(on_rx, on_closed, fail_open=fail)
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

            def wait_for(predicate, msg=""):
                with cond:
                    self.assertTrue(
                        cond.wait_for(predicate, timeout=2.0),
                        msg or f"Estado actual: {lines[-1] if lines else None}",
                    )

            t = threading.Thread(
                target=cli.main,
                args=(["watch"],),
                kwargs={"socket_path": sock_path, "out": on_line, "stop_event": stop},
                daemon=True,
            )
            t.start()
            wait_for(lambda: len(lines) >= 1)

            fake.connect()
            wait_for(lambda: lines[-1]["connected"] is True)
            self.assertEqual(lines[-1]["communicating"], True)

            # 1) Estuche cerrado: izquierdo y derecho al 100 % sin cargar, estuche desconocido (null, nunca 0)
            fake.replay("bateria-estuche-cerrado")
            wait_for(lambda: lines[-1]["battery"] == {
                "left": {"level": 100, "charging": False},
                "right": {"level": 100, "charging": False},
                "case": {"level": None, "charging": False},
            })

            # 2) Auricular derecho en el estuche cargando, estuche sigue desconocido (0xff / status 04 -> null)
            fake.replay("auricular-cargando")
            wait_for(lambda: lines[-1]["battery"] == {
                "left": {"level": 100, "charging": False},
                "right": {"level": 100, "charging": True},
                "case": {"level": None, "charging": False},
            })

            # 3) Estuche abierto con ambos auriculares dentro:
            #    primero llega un paquete transitorio con ambos cargando y estuche desconocido,
            #    y luego el paquete con el estuche al 36 %.
            fake.replay("bateria-estuche-abierto")
            wait_for(lambda: lines[-1]["battery"] == {
                "left": {"level": 100, "charging": True},
                "right": {"level": 100, "charging": True},
                "case": {"level": 36, "charging": False},
            })
            self.assertIn(
                {
                    "left": {"level": 100, "charging": True},
                    "right": {"level": 100, "charging": True},
                    "case": {"level": None, "charging": False},
                },
                [l["battery"] for l in lines],
            )

            # 4) Sesión con niveles intermedios distintos (izquierdo 89 %, derecho 96 % y luego 95 %)
            fake.replay("sesion-oido")
            wait_for(lambda: lines[-1]["battery"] == {
                "left": {"level": 89, "charging": False},
                "right": {"level": 95, "charging": False},
                "case": {"level": None, "charging": False},
            })
            self.assertIn(
                {
                    "left": {"level": 89, "charging": False},
                    "right": {"level": 96, "charging": False},
                    "case": {"level": None, "charging": False},
                },
                [l["battery"] for l in lines],
            )

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


class NoiseModeTest(unittest.TestCase):
    def test_watch_reflects_noise_mode_on_connect_and_stem_changes(self):
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

            def wait_for_mode(expected):
                with cond:
                    self.assertTrue(
                        cond.wait_for(
                            lambda: bool(lines) and lines[-1]["noise_mode"] == expected,
                            timeout=2.0,
                        ),
                        f"Esperaba noise_mode={expected!r}, recibido {[l['noise_mode'] for l in lines]}",
                    )

            t = threading.Thread(
                target=cli.main,
                args=(["watch"],),
                kwargs={"socket_path": sock_path, "out": on_line, "stop_event": stop},
                daemon=True,
            )
            t.start()
            fake.connect()

            # Al conectar (volcado inicial en bateria-estuche-cerrado trae 0x01 -> desactivado)
            fake.replay("bateria-estuche-cerrado")
            wait_for_mode("desactivado")
            self.assertEqual(lines[-1]["noise_mode"], "desactivado")

            # Pulsaciones del tallo / cambios capturados en los ejemplos reales:
            for capture, expected in [
                ("modo-cancelacion", "cancelacion"),
                ("modo-transparencia", "transparencia"),
                ("modo-adaptativo", "adaptativo"),
                ("modo-desactivado", "desactivado"),
            ]:
                fake.replay(capture)
                wait_for_mode(expected)
                self.assertEqual(lines[-1]["noise_mode"], expected)

            stop.set()
            fake.disconnect()
            t.join(timeout=2.0)

    def test_mode_command_sends_correct_aap_bytes_for_each_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            sock_path = os.path.join(tmp, "airpods.sock")
            fake = FakeAirPods()
            core = Core(link_factory=fake.make_link)
            fake.bind(core.on_connected, core.on_disconnected)
            server = ControlServer(core, sock_path)
            server.start()
            self.addCleanup(server.close)

            fake.connect()

            expected_packets = [
                ("desactivado", bytes.fromhex("0400040009000d01000000")),
                ("cancelacion", bytes.fromhex("0400040009000d02000000")),
                ("transparencia", bytes.fromhex("0400040009000d03000000")),
                ("adaptativo", bytes.fromhex("0400040009000d04000000")),
            ]
            for mode_name, raw in expected_packets:
                err = io.StringIO()
                code = cli.main(["mode", mode_name], socket_path=sock_path, err=err)
                self.assertEqual(code, 0, err.getvalue())
                self.assertEqual(fake.link.sent[-1], raw)
                self.assertEqual(core.get_state()["noise_mode"], mode_name)

    def test_mode_command_with_invalid_mode_lists_valid_modes_and_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            sock_path = os.path.join(tmp, "airpods.sock")
            err = io.StringIO()
            code = cli.main(["mode", "invalido"], socket_path=sock_path, err=err)
            self.assertNotEqual(code, 0)
            msg = err.getvalue()
            for valid in ("cancelacion", "transparencia", "adaptativo", "desactivado"):
                self.assertIn(valid, msg)

    def test_mode_command_fails_when_disconnected_or_not_communicating(self):
        with tempfile.TemporaryDirectory() as tmp:
            sock_path = os.path.join(tmp, "airpods.sock")
            fake = FakeAirPods()
            core = Core(link_factory=fake.make_link)
            fake.bind(core.on_connected, core.on_disconnected)
            server = ControlServer(core, sock_path)
            server.start()
            self.addCleanup(server.close)

            # Sin AirPods conectados
            err = io.StringIO()
            code = cli.main(["mode", "cancelacion"], socket_path=sock_path, err=err)
            self.assertNotEqual(code, 0)
            self.assertIn("conectados", err.getvalue().lower())

            # Conectados pero sin comunicación
            fake.connect()
            fake.link._on_closed()
            err_no_comm = io.StringIO()
            code_no_comm = cli.main(
                ["mode", "cancelacion"], socket_path=sock_path, err=err_no_comm
            )
            self.assertNotEqual(code_no_comm, 0)
            self.assertIn("comunicación", err_no_comm.getvalue().lower())


class FakePlayers:
    def __init__(self, initial=None):
        self._players = dict(initial or {})
        self.events = []
        self._on_changed = None

    def bind(self, on_changed):
        self._on_changed = on_changed

    def playing_players(self):
        return [pid for pid, status in self._players.items() if status == "Playing"]

    def paused_players(self):
        return [pid for pid, status in self._players.items() if status == "Paused"]

    def pause(self, player_id):
        if self._players.get(player_id) == "Playing":
            self._players[player_id] = "Paused"
            self.events.append(("pause", player_id))

    def play(self, player_id):
        if self._players.get(player_id) == "Paused":
            self._players[player_id] = "Playing"
            self.events.append(("play", player_id))

    def user_pause(self, player_id):
        self._players[player_id] = "Paused"
        if self._on_changed:
            self._on_changed(player_id, "Paused")

    def user_play(self, player_id):
        self._players[player_id] = "Playing"
        if self._on_changed:
            self._on_changed(player_id, "Playing")


class EarDetectionAndAutoPauseTest(unittest.TestCase):
    def _setup_service(self, tmp, players=None):
        sock_path = os.path.join(tmp, "airpods.sock")
        cfg_path = os.path.join(tmp, "config.json")
        fake = FakeAirPods()
        fake_players = players or FakePlayers()
        core = Core(
            link_factory=fake.make_link,
            players=fake_players,
            config_path=cfg_path,
        )
        fake.bind(core.on_connected, core.on_disconnected)
        fake_players.bind(core.on_player_state_changed)
        server = ControlServer(core, sock_path)
        server.start()
        self.addCleanup(server.close)
        return sock_path, cfg_path, fake, fake_players, core

    def test_watch_reflects_in_ear_across_real_captures(self):
        with tempfile.TemporaryDirectory() as tmp:
            sock_path, _, fake, _, _ = self._setup_service(tmp)
            lines = []
            cond = threading.Condition()
            stop = threading.Event()

            def on_line(line):
                with cond:
                    lines.append(json.loads(line))
                    cond.notify_all()

            def wait_for_in_ear(expected):
                with cond:
                    self.assertTrue(
                        cond.wait_for(
                            lambda: bool(lines) and lines[-1]["in_ear"] == expected,
                            timeout=2.0,
                        ),
                        f"Esperaba in_ear={expected}, último={lines[-1]['in_ear'] if lines else None}",
                    )

            t = threading.Thread(
                target=cli.main,
                args=(["watch"],),
                kwargs={"socket_path": sock_path, "out": on_line, "stop_event": stop},
                daemon=True,
            )
            t.start()
            fake.connect()

            # Con estuche cerrado (primario = izquierdo 01) y ambos puestos (00 00)
            fake.replay("bateria-estuche-cerrado")
            wait_for_in_ear({"left": True, "right": True})

            # En auricular-cargando el secundario (derecho) pasa al estuche (00 02)
            fake.replay("auricular-cargando")
            wait_for_in_ear({"left": True, "right": False})

            # En bateria-estuche-abierto ambos están en el estuche (02 02)
            fake.replay("bateria-estuche-abierto")
            wait_for_in_ear({"left": False, "right": False})

            # En sesion-oido el primario pasa a ser el derecho (040004000800 02 00 01 00):
            # primero inyectamos el paquete de rol primario=derecho y ambos puestos:
            fake.link.receive(bytes.fromhex("04000400080002000100"))
            fake.link.receive(bytes.fromhex("0400040006000000"))
            wait_for_in_ear({"left": True, "right": True})

            fake.replay("quitar-izquierdo")
            wait_for_in_ear({"left": False, "right": True})

            fake.replay("poner-izquierdo")
            wait_for_in_ear({"left": True, "right": True})

            fake.replay("quitar-derecho")
            wait_for_in_ear({"left": True, "right": False})

            fake.replay("poner-derecho")
            wait_for_in_ear({"left": True, "right": True})

            fake.replay("quitar-ambos")
            wait_for_in_ear({"left": False, "right": False})

            stop.set()
            fake.disconnect()
            t.join(timeout=2.0)

    def test_auto_pause_pauses_only_playing_players_and_resumes_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            players = FakePlayers({
                "spotify": "Playing",
                "firefox": "Playing",
                "vlc": "Paused",
            })
            _, _, fake, _, _ = self._setup_service(tmp, players=players)
            fake.connect()
            # Primario = derecho, ambos puestos (como al inicio de sesion-oido)
            fake.link.receive(bytes.fromhex("04000400080002000100"))
            fake.link.receive(bytes.fromhex("0400040006000000"))
            self.assertEqual(players.events, [])

            # Quitarse el izquierdo pausa spotify y firefox, pero no toca vlc
            fake.replay("quitar-izquierdo")
            self.assertEqual(players.events, [("pause", "spotify"), ("pause", "firefox")])

            # Volver a ponerse el izquierdo reanuda solo spotify y firefox
            fake.replay("poner-izquierdo")
            self.assertEqual(players.events, [
                ("pause", "spotify"),
                ("pause", "firefox"),
                ("play", "spotify"),
                ("play", "firefox"),
            ])
            self.assertEqual(players._players["vlc"], "Paused")

    def test_manual_pause_Is_never_resumed_and_manual_action_during_autopause_drops_player(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Caso A: usuario había pausado antes -> quitar y poner un auricular no reanuda nada
            players = FakePlayers({"spotify": "Paused"})
            _, _, fake, _, _ = self._setup_service(tmp, players=players)
            fake.connect()
            fake.link.receive(bytes.fromhex("04000400080002000100"))
            fake.link.receive(bytes.fromhex("0400040006000000"))
            fake.replay("quitar-izquierdo")
            fake.replay("poner-izquierdo")
            self.assertEqual(players.events, [])

            # Caso B: durante una pausa automática el usuario interactúa a mano (reproduce y pausa)
            players.user_play("spotify")
            fake.replay("quitar-derecho")
            self.assertEqual(players.events, [("pause", "spotify")])
            players.user_play("spotify")
            players.user_pause("spotify")
            fake.replay("poner-derecho")
            # No se reanuda porque el usuario lo pausó a mano mientras tanto
            self.assertEqual(players.events, [("pause", "spotify")])

    def test_removing_both_earbuds_pauses_and_does_not_resume_when_put_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            players = FakePlayers({"spotify": "Playing"})
            _, _, fake, _, _ = self._setup_service(tmp, players=players)
            fake.connect()
            fake.link.receive(bytes.fromhex("04000400080002000100"))
            fake.link.receive(bytes.fromhex("0400040006000000"))

            fake.replay("quitar-ambos")
            self.assertEqual(players.events, [("pause", "spotify")])

            # Volver a ponerse uno y luego el otro no debe reanudar
            fake.link.receive(bytes.fromhex("0400040006000001"))
            fake.replay("poner-izquierdo")
            self.assertEqual(players.events, [("pause", "spotify")])

    def test_ear_detection_disabled_does_not_pause_or_resume_and_persists_across_restarts(self):
        with tempfile.TemporaryDirectory() as tmp:
            players = FakePlayers({"spotify": "Playing"})
            sock_path, cfg_path, fake, _, _ = self._setup_service(tmp, players=players)

            err = io.StringIO()
            code = cli.main(["ear-detection", "off"], socket_path=sock_path, err=err)
            self.assertEqual(code, 0, err.getvalue())

            fake.connect()
            fake.link.receive(bytes.fromhex("04000400080002000100"))
            fake.link.receive(bytes.fromhex("0400040006000000"))
            fake.replay("quitar-izquierdo")
            fake.replay("poner-izquierdo")
            self.assertEqual(players.events, [])

            # Reiniciar el núcleo leyendo el mismo archivo de configuración conserva ear_detection=False
            restarted = Core(link_factory=fake.make_link, players=players, config_path=cfg_path)
            self.assertEqual(restarted.get_state()["ear_detection"], False)


class DesktopAppClientTest(unittest.TestCase):
    def test_app_controller_receives_live_state_and_sends_commands(self):
        from airpods.gui import AppController

        with tempfile.TemporaryDirectory() as tmp:
            sock_path = os.path.join(tmp, "airpods.sock")
            fake = FakeAirPods()
            core = Core(
                link_factory=fake.make_link,
                config_path=os.path.join(tmp, "config.json"),
            )
            fake.bind(core.on_connected, core.on_disconnected)
            server = ControlServer(core, sock_path)
            server.start()
            self.addCleanup(server.close)
            self.addCleanup(core.close)

            states = []
            cond = threading.Condition()

            def on_state(st):
                with cond:
                    states.append(st)
                    cond.notify_all()

            ctrl = AppController(socket_path=sock_path, on_state=on_state, dispatch=lambda fn: fn())
            ctrl.start()
            self.addCleanup(ctrl.stop)

            with cond:
                self.assertTrue(cond.wait_for(lambda: len(states) >= 1, timeout=2.0))
            self.assertEqual(states[-1]["connected"], False)

            fake.connect()
            fake.replay("bateria-estuche-cerrado")
            with cond:
                self.assertTrue(
                    cond.wait_for(
                        lambda: states[-1]["connected"] is True
                        and states[-1]["battery"]["left"]["level"] == 100,
                        timeout=2.0,
                    )
                )

            ok, err = ctrl.set_noise_mode("cancelacion")
            self.assertTrue(ok, err)
            self.assertEqual(fake.link.sent[-1], bytes.fromhex("0400040009000d02000000"))

            ok, err = ctrl.set_ear_detection(False)
            self.assertTrue(ok, err)
            with cond:
                self.assertTrue(
                    cond.wait_for(lambda: states[-1]["ear_detection"] is False, timeout=2.0)
                )

    def test_render_airpods_3d_svg_handles_disconnected_closed_and_open_states(self):
        from airpods.gui import render_airpods_3d_svg

        gray_svg = render_airpods_3d_svg(connected=False, open_progress=0.0, spin_angle=0.0)
        closed_svg = render_airpods_3d_svg(connected=True, open_progress=0.0, spin_angle=0.0)
        opened_svg = render_airpods_3d_svg(connected=True, open_progress=1.0, spin_angle=0.4)

        self.assertIn(b"<svg", gray_svg)
        self.assertNotEqual(gray_svg, closed_svg)
        self.assertNotEqual(closed_svg, opened_svg)


class CommunicationRetryAndReconnectionTest(unittest.TestCase):
    def test_channel_failure_emits_communicating_false_and_recovers_on_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            sock_path = os.path.join(tmp, "airpods.sock")
            fake = FakeAirPods()
            core = Core(
                link_factory=fake.make_link,
                config_path=os.path.join(tmp, "config.json"),
                retry_interval=0.02,
            )
            fake.bind(core.on_connected, core.on_disconnected)
            server = ControlServer(core, sock_path)
            server.start()
            self.addCleanup(server.close)
            self.addCleanup(core.close)

            lines = []
            cond = threading.Condition()
            stop = threading.Event()

            def on_line(line):
                with cond:
                    lines.append(json.loads(line))
                    cond.notify_all()

            def wait_for(pred, desc=""):
                with cond:
                    self.assertTrue(
                        cond.wait_for(pred, timeout=2.0),
                        desc or f"Líneas: {lines}",
                    )

            t = threading.Thread(
                target=cli.main,
                args=(["watch"],),
                kwargs={"socket_path": sock_path, "out": on_line, "stop_event": stop},
                daemon=True,
            )
            t.start()
            wait_for(lambda: len(lines) >= 1)

            # Los dos primeros intentos de abrir L2CAP fallan; el tercero tendrá éxito
            fake.fail_next_open = 2
            fake.connect()

            # Primero se emite connected=True, communicating=False
            wait_for(
                lambda: any(l["connected"] is True and l["communicating"] is False for l in lines),
                "Esperaba connected=True y communicating=False al fallar la apertura",
            )

            # Tras los reintentos periódicos se recupera solo a communicating=True
            wait_for(
                lambda: lines[-1]["connected"] is True and lines[-1]["communicating"] is True,
                "Esperaba recuperación automática a communicating=True",
            )
            self.assertGreaterEqual(fake.open_attempts, 3)

            # Si el canal se cae en mitad de la sesión, pasa a communicating=False y se recupera solo
            fake.fail_next_open = 1
            fake.link.drop()
            wait_for(
                lambda: lines[-1]["connected"] is True and lines[-1]["communicating"] is False,
                "Esperaba communicating=False al cortarse el canal",
            )
            wait_for(
                lambda: lines[-1]["connected"] is True and lines[-1]["communicating"] is True,
                "Esperaba reconexión del canal tras el corte",
            )

            # Tras recuperarse recibe paquetes normalmente
            fake.replay("bateria-estuche-cerrado")
            wait_for(lambda: lines[-1]["battery"]["left"]["level"] == 100)

            stop.set()
            fake.disconnect()
            t.join(timeout=2.0)

    def test_watch_continues_across_airpods_disconnect_and_reconnect(self):
        with tempfile.TemporaryDirectory() as tmp:
            sock_path = os.path.join(tmp, "airpods.sock")
            fake = FakeAirPods()
            core = Core(
                link_factory=fake.make_link,
                config_path=os.path.join(tmp, "config.json"),
            )
            fake.bind(core.on_connected, core.on_disconnected)
            server = ControlServer(core, sock_path)
            server.start()
            self.addCleanup(server.close)
            self.addCleanup(core.close)

            lines = []
            cond = threading.Condition()
            stop = threading.Event()

            def on_line(line):
                with cond:
                    lines.append(json.loads(line))
                    cond.notify_all()

            def wait_for(pred):
                with cond:
                    self.assertTrue(cond.wait_for(pred, timeout=2.0))

            t = threading.Thread(
                target=cli.main,
                args=(["watch"],),
                kwargs={"socket_path": sock_path, "out": on_line, "stop_event": stop},
                daemon=True,
            )
            t.start()
            wait_for(lambda: len(lines) >= 1)

            fake.connect()
            fake.replay("bateria-estuche-cerrado")
            wait_for(lambda: lines[-1]["connected"] is True and lines[-1]["battery"]["left"]["level"] == 100)

            fake.disconnect()
            wait_for(lambda: lines[-1]["connected"] is False and lines[-1]["battery"]["left"]["level"] is None)

            fake.connect()
            fake.replay("sesion-oido")
            wait_for(lambda: lines[-1]["connected"] is True and lines[-1]["battery"]["left"]["level"] == 89)
            self.assertTrue(t.is_alive())

            stop.set()
            fake.disconnect()
            t.join(timeout=2.0)


if __name__ == "__main__":
    unittest.main()
