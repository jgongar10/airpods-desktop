"""Aplicación de escritorio (GTK4 + Libadwaita) para configurar y ver los AirPods."""

import json
import os
import socket
import sys
import threading
import time

from .server import default_socket_path


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
        .status-pill {
            padding: 6px 12px;
            border-radius: 999px;
            font-weight: 600;
        }
        .mode-btn {
            padding: 10px 14px;
            font-weight: 600;
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
        win.set_default_size(460, 620)

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        toast_overlay = Adw.ToastOverlay()
        toolbar_view.set_content(toast_overlay)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        toast_overlay.set_child(scroll)

        clamp = Adw.Clamp(maximum_size=440)
        clamp.set_margin_top(16)
        clamp.set_margin_bottom(24)
        clamp.set_margin_start(16)
        clamp.set_margin_end(16)
        scroll.set_child(clamp)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        clamp.set_child(main_box)

        # --- Banner de estado ---
        status_group = Adw.PreferencesGroup()
        status_row = Adw.ActionRow(
            title="AirPods 4",
            subtitle="Comprobando estado del servicio…",
        )
        status_row.add_prefix(
            Gtk.Image.new_from_icon_name("audio-headphones-symbolic")
        )
        min_badge = Gtk.Label(label="—")
        min_badge.add_css_class("title-2")
        status_row.add_suffix(min_badge)
        status_group.add(status_row)
        main_box.append(status_group)

        # --- Grupo Batería ---
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

        # --- Grupo Modo de ruido ---
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
        updating_state = {"busy": False}

        def on_mode_clicked(_btn, mode_value):
            if updating_state["busy"]:
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

        # --- Grupo Detección de oído ---
        ear_group = Adw.PreferencesGroup(title="Detección de oído")
        ear_switch_row = Adw.SwitchRow(
            title="Detección de oído",
            subtitle="Pausa automática al quitarte un auricular",
            active=True,
        )

        def on_ear_toggled(row_widget, _pspec):
            if updating_state["busy"]:
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

        def apply_state(state):
            updating_state["busy"] = True
            try:
                svc = state.get("service_running", True)
                connected = bool(state.get("connected"))
                comm = bool(state.get("communicating"))
                battery = state.get("battery") or {}

                if not svc:
                    status_row.set_subtitle("El servicio de AirPods no está en marcha")
                    min_badge.set_label("—")
                elif not connected:
                    status_row.set_subtitle("Desconectados")
                    min_badge.set_label("—")
                elif not comm:
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
                updating_state["busy"] = False
            return False

        controller = AppController(socket_path=socket_path, on_state=apply_state)
        controller.start()
        win.connect("close-request", lambda *_: (controller.stop(), False)[1])

        win.set_content(toolbar_view)
        win.present()

    app.connect("activate", on_activate)
    return app.run([])


def main(argv=None):
    return run_app()


if __name__ == "__main__":
    sys.exit(main())
