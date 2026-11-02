"""Aplicación de escritorio (GTK4 + Libadwaita) para configurar y ver los AirPods.

Incluye:
- Vista desconectada con los AirPods sombreados en gris.
- Tarjeta emergente al estilo Apple cuando los AirPods están conectados, que
  reproduce la animación en vídeo `.mp4` de apertura del estuche junto con las
  pastillas de batería y el botón azul «Continuar».
- Panel completo de configuración (batería por pieza, modo de ruido y detección de oído).
"""

import json
import os
import socket
import sys
import threading
import time

from .server import default_socket_path


PACKAGE_DIR = os.path.dirname(os.path.realpath(__file__))
REPO_DIR = os.path.dirname(PACKAGE_DIR)
ASSETS_DIR = os.path.join(PACKAGE_DIR, "assets")

OPENING_VIDEO_PATH = os.path.join(
    REPO_DIR, "Wireless_earbuds_case_opening_7125f54c_1080p.mp4"
)
DISCONNECTED_IMAGE_PATH = os.path.join(ASSETS_DIR, "airpods-disconnected.png")
CONNECTED_IMAGE_PATH = os.path.join(ASSETS_DIR, "airpods-connected.png")


NOISE_MODE_LABELS = [
    ("cancelacion", "Cancelación"),
    ("transparencia", "Transparencia"),
    ("adaptativo", "Adaptativo"),
    ("desactivado", "Desactivado"),
]


def _disconnected_service_state():
    return {
        "service_running": False,
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
    }


class AppController:
    """Conecta con el socket del servicio en segundo plano, emite el estado en vivo
    y envía órdenes de modo de ruido y detección de oído."""

    def __init__(self, socket_path=None, on_state=None, dispatch=None, retry_delay=1.5):
        self._socket_path = (
            socket_path
            or os.environ.get("AIRPODS_SOCKET")
            or default_socket_path()
        )
        self._on_state = on_state or (lambda _s: None)
        self._dispatch = dispatch
        self._retry_delay = retry_delay
        self._stop = threading.Event()
        self._watch_sock = None
        self._thread = None

    def _emit(self, state):
        if self._dispatch is not None:
            self._dispatch(lambda: self._on_state(state))
        else:
            from gi.repository import GLib

            GLib.idle_add(self._on_state, state)

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        sock = self._watch_sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _watch_loop(self):
        while not self._stop.is_set():
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.connect(self._socket_path)
                self._watch_sock = sock
                sock.sendall(b'{"cmd": "watch"}\n')
                f = sock.makefile("r", encoding="utf-8")
                for line in f:
                    if self._stop.is_set():
                        break
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    data["service_running"] = True
                    self._emit(data)
            except (OSError, ValueError):
                if not self._stop.is_set():
                    self._emit(_disconnected_service_state())
            finally:
                self._watch_sock = None
                try:
                    sock.close()
                except OSError:
                    pass
            if not self._stop.is_set():
                time.sleep(self._retry_delay)

    def _send(self, payload):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self._socket_path)
            sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            f = sock.makefile("r", encoding="utf-8")
            line = f.readline()
            if not line:
                return False, "Sin respuesta del servicio."
            resp = json.loads(line)
            return bool(resp.get("ok")), resp.get("error")
        except OSError:
            return False, "El servicio de AirPods no está en marcha."
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def set_noise_mode(self, mode):
        return self._send({"cmd": "mode", "mode": mode})

    def set_ear_detection(self, enabled):
        return self._send({"cmd": "ear-detection", "enabled": bool(enabled)})


def _format_battery_text(piece):
    if not piece or piece.get("level") is None:
        return "Desconocida"
    txt = f"{piece['level']} %"
    if piece.get("charging"):
        txt += " · Cargando"
    return txt


def _format_pill_battery(piece):
    if not piece or piece.get("level") is None:
        return "—"
    prefix = "⚡ " if piece.get("charging") else ""
    return f"{prefix}{piece['level']} %"


def _format_in_ear(val):
    if val is True:
        return "Puesto"
    if val is False:
        return "Fuera"
    return "Desconocido"


def run_app(socket_path=None):
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, Gtk

    app = Adw.Application(application_id="org.gonzavz.AirPods")

    css = Gtk.CssProvider()
    css.load_from_string(
        """
        .apple-sheet {
            background: linear-gradient(180deg, rgba(42, 45, 58, 0.96) 0%, rgba(24, 26, 34, 0.99) 100%);
            border-radius: 28px;
            border: 1px solid rgba(255, 255, 255, 0.10);
            padding: 24px 22px 22px 22px;
        }
        .apple-sheet-disconnected {
            background: linear-gradient(180deg, rgba(34, 36, 44, 0.90) 0%, rgba(20, 21, 27, 0.96) 100%);
            border-radius: 28px;
            border: 1px solid rgba(255, 255, 255, 0.06);
            padding: 26px 22px 24px 22px;
        }
        .media-frame {
            border-radius: 20px;
        }
        .apple-title {
            font-size: 22px;
            font-weight: 700;
            letter-spacing: -0.3px;
        }
        .apple-subtitle {
            font-size: 13px;
            opacity: 0.68;
        }
        .apple-pill {
            background: rgba(255, 255, 255, 0.07);
            border-radius: 16px;
            padding: 10px 14px;
            border: 1px solid rgba(255, 255, 255, 0.06);
        }
        .apple-pill-title {
            font-size: 11px;
            opacity: 0.65;
            font-weight: 600;
        }
        .apple-pill-value {
            font-size: 16px;
            font-weight: 700;
        }
        .apple-continue-btn {
            background: #007aff;
            color: #ffffff;
            border-radius: 999px;
            padding: 12px 28px;
            font-size: 15px;
            font-weight: 700;
            border: none;
        }
        .apple-continue-btn:hover {
            background: #1485ff;
        }
        .mode-btn {
            padding: 10px 14px;
            font-weight: 600;
            border-radius: 12px;
        }
        """
    )

    def on_activate(application):
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

        win = Adw.ApplicationWindow(application=application)
        win.set_title("AirPods")
        win.set_default_size(480, 660)

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        toast_overlay = Adw.ToastOverlay()
        toolbar_view.set_content(toast_overlay)

        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        stack.set_transition_duration(260)
        toast_overlay.set_child(stack)

        # =====================================================================
        # VISTA 1: DESCONECTADOS (AirPods sombreados en gris)
        # =====================================================================
        disc_clamp = Adw.Clamp(maximum_size=420)
        disc_clamp.set_margin_top(24)
        disc_clamp.set_margin_bottom(24)
        disc_clamp.set_margin_start(20)
        disc_clamp.set_margin_end(20)
        disc_clamp.set_valign(Gtk.Align.CENTER)

        disc_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        disc_card.add_css_class("apple-sheet-disconnected")
        disc_clamp.set_child(disc_card)

        disc_picture = Gtk.Picture.new_for_filename(DISCONNECTED_IMAGE_PATH)
        disc_picture.set_size_request(360, 202)
        disc_picture.set_can_shrink(True)
        disc_picture.set_content_fit(Gtk.ContentFit.COVER)
        disc_picture.set_overflow(Gtk.Overflow.HIDDEN)
        disc_picture.add_css_class("media-frame")
        disc_card.append(disc_picture)

        disc_title = Gtk.Label(label="AirPods desconectados")
        disc_title.add_css_class("apple-title")
        disc_card.append(disc_title)

        disc_sub = Gtk.Label(
            label="Abre el estuche o conecta tus AirPods por Bluetooth para ver su batería y configurarlos."
        )
        disc_sub.add_css_class("apple-subtitle")
        disc_sub.set_wrap(True)
        disc_sub.set_justify(Gtk.Justification.CENTER)
        disc_card.append(disc_sub)

        stack.add_named(disc_clamp, "disconnected")

        # =====================================================================
        # VISTA 2: BIENVENIDA ESTILO APPLE (Vídeo .mp4 de apertura + Continuar)
        # =====================================================================
        welcome_clamp = Adw.Clamp(maximum_size=420)
        welcome_clamp.set_margin_top(20)
        welcome_clamp.set_margin_bottom(24)
        welcome_clamp.set_margin_start(20)
        welcome_clamp.set_margin_end(20)
        welcome_clamp.set_valign(Gtk.Align.CENTER)

        welcome_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        welcome_card.add_css_class("apple-sheet")
        welcome_clamp.set_child(welcome_card)

        welcome_title = Gtk.Label(label="AirPods de Gonzalo")
        welcome_title.add_css_class("apple-title")
        welcome_card.append(welcome_title)

        welcome_sub = Gtk.Label(label="Conectados")
        welcome_sub.add_css_class("apple-subtitle")
        welcome_card.append(welcome_sub)

        media_file = Gtk.MediaFile.new_for_filename(OPENING_VIDEO_PATH)
        media_file.set_muted(True)
        media_file.set_loop(False)

        video_picture = Gtk.Picture.new_for_paintable(media_file)
        video_picture.set_size_request(360, 202)
        video_picture.set_can_shrink(True)
        video_picture.set_content_fit(Gtk.ContentFit.COVER)
        video_picture.set_overflow(Gtk.Overflow.HIDDEN)
        video_picture.add_css_class("media-frame")
        welcome_card.append(video_picture)

        pills_grid = Gtk.Grid(column_spacing=10, column_homogeneous=True)
        welcome_pills = {}
        for idx, (piece_key, piece_title) in enumerate([
            ("left", "Izquierdo"),
            ("case", "Estuche"),
            ("right", "Derecho"),
        ]):
            pbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            pbox.add_css_class("apple-pill")
            t_lbl = Gtk.Label(label=piece_title)
            t_lbl.add_css_class("apple-pill-title")
            v_lbl = Gtk.Label(label="—")
            v_lbl.add_css_class("apple-pill-value")
            pbox.append(t_lbl)
            pbox.append(v_lbl)
            pills_grid.attach(pbox, idx, 0, 1, 1)
            welcome_pills[piece_key] = v_lbl
        welcome_card.append(pills_grid)

        continue_btn = Gtk.Button(label="Continuar")
        continue_btn.add_css_class("apple-continue-btn")
        continue_btn.set_margin_top(6)
        welcome_card.append(continue_btn)

        stack.add_named(welcome_clamp, "welcome")

        # =====================================================================
        # VISTA 3: PANEL DE CONTROL COMPLETO
        # =====================================================================
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        clamp = Adw.Clamp(maximum_size=440)
        clamp.set_margin_top(12)
        clamp.set_margin_bottom(24)
        clamp.set_margin_start(16)
        clamp.set_margin_end(16)
        scroll.set_child(clamp)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        clamp.set_child(main_box)

        hero_picture = Gtk.Picture.new_for_filename(CONNECTED_IMAGE_PATH)
        hero_picture.set_size_request(320, 175)
        hero_picture.set_can_shrink(True)
        hero_picture.set_content_fit(Gtk.ContentFit.COVER)
        hero_picture.set_overflow(Gtk.Overflow.HIDDEN)
        hero_picture.add_css_class("media-frame")
        main_box.append(hero_picture)

        status_group = Adw.PreferencesGroup()
        status_row = Adw.ActionRow(
            title="AirPods 4",
            subtitle="Conectados",
        )
        status_row.add_prefix(
            Gtk.Image.new_from_icon_name("audio-headphones-symbolic")
        )
        min_badge = Gtk.Label(label="—")
        min_badge.add_css_class("title-2")
        status_row.add_suffix(min_badge)
        status_group.add(status_row)
        main_box.append(status_group)

        battery_group = Adw.PreferencesGroup(title="Batería")
        piece_widgets = {}
        for key, label in [
            ("left", "Auricular izquierdo"),
            ("right", "Auricular derecho"),
            ("case", "Estuche"),
        ]:
            row = Adw.ActionRow(title=label, subtitle="Desconocida")
            bar = Gtk.LevelBar()
            bar.set_min_value(0.0)
            bar.set_max_value(100.0)
            bar.set_value(0.0)
            bar.set_size_request(110, 10)
            bar.set_valign(Gtk.Align.CENTER)
            row.add_suffix(bar)
            battery_group.add(row)
            piece_widgets[key] = (row, bar)
        main_box.append(battery_group)

        mode_group = Adw.PreferencesGroup(
            title="Modo de ruido",
            description="Cambia el modo activo en los AirPods",
        )
        mode_grid = Gtk.Grid(
            column_spacing=8,
            row_spacing=8,
            column_homogeneous=True,
        )
        mode_grid.set_margin_top(4)
        mode_buttons = {}
        ui_state = {
            "busy": False,
            "was_connected": None,
            "dismissed_welcome": False,
        }

        def on_mode_clicked(_btn, mode_value):
            if ui_state["busy"]:
                return
            ok, err = controller.set_noise_mode(mode_value)
            if not ok and err:
                toast_overlay.add_toast(Adw.Toast.new(err))

        for idx, (mode_val, mode_label) in enumerate(NOISE_MODE_LABELS):
            btn = Gtk.Button(label=mode_label)
            btn.add_css_class("mode-btn")
            btn.connect("clicked", on_mode_clicked, mode_val)
            mode_grid.attach(btn, idx % 2, idx // 2, 1, 1)
            mode_buttons[mode_val] = btn

        mode_group.add(mode_grid)
        main_box.append(mode_group)

        ear_group = Adw.PreferencesGroup(title="Detección de oído")
        ear_switch_row = Adw.SwitchRow(
            title="Detección de oído",
            subtitle="Pausa automática al quitarte un auricular",
            active=True,
        )

        def on_ear_toggled(row_widget, _pspec):
            if ui_state["busy"]:
                return
            ok, err = controller.set_ear_detection(row_widget.get_active())
            if not ok and err:
                toast_overlay.add_toast(Adw.Toast.new(err))

        ear_switch_row.connect("notify::active", on_ear_toggled)
        ear_group.add(ear_switch_row)

        left_ear_row = Adw.ActionRow(title="Auricular izquierdo")
        left_ear_lbl = Gtk.Label(label="Desconocido")
        left_ear_lbl.add_css_class("dim-label")
        left_ear_row.add_suffix(left_ear_lbl)
        ear_group.add(left_ear_row)

        right_ear_row = Adw.ActionRow(title="Auricular derecho")
        right_ear_lbl = Gtk.Label(label="Desconocido")
        right_ear_lbl.add_css_class("dim-label")
        right_ear_row.add_suffix(right_ear_lbl)
        ear_group.add(right_ear_row)

        main_box.append(ear_group)
        stack.add_named(scroll, "controls")

        def play_opening_video():
            try:
                media_file.seek(0)
            except Exception:
                pass
            media_file.play()

        def stop_opening_video():
            media_file.pause()

        def on_continue_clicked(_btn):
            ui_state["dismissed_welcome"] = True
            stop_opening_video()
            stack.set_visible_child_name("controls")

        continue_btn.connect("clicked", on_continue_clicked)

        def apply_state(state):
            ui_state["busy"] = True
            try:
                svc = state.get("service_running", True)
                connected = bool(state.get("connected"))
                comm = bool(state.get("communicating"))
                battery = state.get("battery") or {}

                if not svc or not connected:
                    stop_opening_video()
                    ui_state["was_connected"] = False
                    ui_state["dismissed_welcome"] = False
                    disc_title.set_label(
                        "Servicio detenido" if not svc else "AirPods desconectados"
                    )
                    disc_sub.set_label(
                        "El servicio en segundo plano no está en marcha."
                        if not svc
                        else "Abre el estuche o conecta tus AirPods por Bluetooth para ver su batería y configurarlos."
                    )
                    stack.set_visible_child_name("disconnected")
                    return False

                if not ui_state["was_connected"]:
                    ui_state["was_connected"] = True
                    ui_state["dismissed_welcome"] = False
                    play_opening_video()

                if not ui_state["dismissed_welcome"]:
                    stack.set_visible_child_name("welcome")
                else:
                    stack.set_visible_child_name("controls")

                welcome_sub.set_label(
                    "Conectados" if comm else "Sin comunicación con los AirPods"
                )
                for key, lbl in welcome_pills.items():
                    lbl.set_label(_format_pill_battery(battery.get(key)))

                if not comm:
                    status_row.set_subtitle("Sin comunicación con los AirPods")
                    min_badge.set_label("—")
                else:
                    status_row.set_subtitle("Conectados")
                    known_earbuds = [
                        battery.get(side, {}).get("level")
                        for side in ("left", "right")
                        if isinstance(battery.get(side, {}).get("level"), int)
                    ]
                    min_badge.set_label(
                        f"{min(known_earbuds)} %" if known_earbuds else "—"
                    )

                for key, (row, bar) in piece_widgets.items():
                    piece = battery.get(key) or {}
                    row.set_subtitle(_format_battery_text(piece))
                    lvl = piece.get("level")
                    bar.set_value(float(lvl) if isinstance(lvl, int) else 0.0)

                active_mode = state.get("noise_mode")
                for mode_val, btn in mode_buttons.items():
                    btn.set_sensitive(connected and comm)
                    if mode_val == active_mode and connected and comm:
                        btn.add_css_class("suggested-action")
                    else:
                        btn.remove_css_class("suggested-action")

                ear_switch_row.set_sensitive(svc)
                ear_switch_row.set_active(bool(state.get("ear_detection", True)))

                in_ear = state.get("in_ear") or {}
                left_ear_lbl.set_label(_format_in_ear(in_ear.get("left")))
                right_ear_lbl.set_label(_format_in_ear(in_ear.get("right")))
            finally:
                ui_state["busy"] = False
            return False

        controller = AppController(socket_path=socket_path, on_state=apply_state)
        controller.start()
        win.connect(
            "close-request",
            lambda *_: (stop_opening_video(), controller.stop(), False)[2],
        )

        win.set_content(toolbar_view)
        win.present()

    app.connect("activate", on_activate)
    return app.run([])


def main(argv=None):
    return run_app()


if __name__ == "__main__":
    sys.exit(main())
