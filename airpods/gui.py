"""Aplicación de escritorio (GTK4 + Libadwaita) para configurar y ver los AirPods.

Incluye:
- Vista desconectada con los AirPods sombreados en gris 3D.
- Tarjeta emergente al estilo Apple cuando los AirPods están conectados, con
  animación 3D del estuche cerrado que se abre, los auriculares emergiendo,
  porcentajes de batería y el botón azul «Continuar».
- Panel completo de configuración (batería por pieza, modo de ruido y detección de oído).
"""

import json
import math
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


def _ease_out_cubic(t):
    t = max(0.0, min(1.0, float(t)))
    return 1.0 - (1.0 - t) ** 3


def _ease_in_out_cubic(t):
    t = max(0.0, min(1.0, float(t)))
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - ((-2.0 * t + 2.0) ** 3) / 2.0


def _ease_out_back(t, overshoot=1.08):
    t = max(0.0, min(1.0, float(t)))
    c1 = overshoot
    c3 = c1 + 1.0
    return 1.0 + c3 * ((t - 1.0) ** 3) + c1 * ((t - 1.0) ** 2)


def render_airpods_3d_svg(
    connected=True,
    open_progress=1.0,
    spin_angle=0.0,
    approach_progress=1.0,
):
    """Genera un SVG con iluminación y perspectiva 3D de unos AirPods 4 y su estuche.

    - connected=False: AirPods y estuche sombreados en gris mate (estado desconectado).
    - connected=True:
      * `approach_progress` (0.0 -> 1.0): el estuche cerrado llega desde el fondo
        (escala pequeña, elevado, girando y emergiendo hacia el primer plano).
      * `open_progress` (0.0 -> 1.0): una vez delante, la tapa se abre en 3D y
        los dos auriculares emergen con rotación suave (`spin_angle`).
    """
    p = _ease_in_out_cubic(open_progress if connected else 0.35)
    ap_raw = max(0.0, min(1.0, float(approach_progress if connected else 1.0)))
    ap = _ease_out_cubic(ap_raw)
    ap_scale = 0.22 + 0.78 * _ease_out_back(ap_raw, overshoot=0.95) if connected else 1.0
    ap_offset_y = (1.0 - ap) * (-78.0) if connected else 0.0
    ap_roll = (1.0 - ap) * (-16.0) if connected else 0.0

    # Mientras viene desde lo lejos gira con más amplitud en perspectiva 3D
    approach_yaw_boost = (1.0 - ap) * 26.0 if connected else 0.0
    yaw = math.sin(spin_angle) * (10.0 if connected else 4.0) + approach_yaw_boost
    tilt_y = math.cos(spin_angle * 0.7) * (3.0 if connected else 1.5) + (1.0 - ap) * 8.0
    side_shift = yaw * 1.15
    extrude_x = -yaw * 0.55

    if connected:
        shell_top = "#ffffff"
        shell_mid = "#f2f5fa"
        shell_bot = "#c9d2e0"
        shell_edge = "#aeb8c8"
        inner_well = "#cfd6e2"
        inner_dark = "#98a2b3"
        bud_top = "#ffffff"
        bud_mid = "#eef2f8"
        bud_bot = "#bfc9d9"
        mesh_fill = "#232730"
        led_color = "#32d74b"
        led_glow = "rgba(50, 215, 75, 0.55)"
        ambient_glow = "rgba(137, 180, 250, 0.24)"
        overall_opacity = f"{0.20 + 0.80 * ap:.2f}"
    else:
        # Sombreado en gris apagado cuando están desconectados
        shell_top = "#6e7380"
        shell_mid = "#505461"
        shell_bot = "#343741"
        shell_edge = "#262932"
        inner_well = "#3d404c"
        inner_dark = "#252830"
        bud_top = "#787d8a"
        bud_mid = "#585c69"
        bud_bot = "#393c47"
        mesh_fill = "#1d1f26"
        led_color = "#454954"
        led_glow = "rgba(0, 0, 0, 0.0)"
        ambient_glow = "rgba(90, 95, 110, 0.10)"
        overall_opacity = "0.78"

    # Geometría de los auriculares emergiendo al abrirse la tapa
    bud_rise = p * 38.0 if connected else 18.0
    bud_visible_opacity = max(0.0, min(1.0, (p - 0.08) / 0.55)) if connected else 0.85
    bud_y = 148.0 - bud_rise + tilt_y * 0.4

    # Geometría 3D de la tapa superior:
    # p = 0.0 -> tapa cerrada hacia abajo cubriendo los auriculares
    # p = 1.0 -> tapa abatida hacia atrás dejando ver el interior cóncavo 3D
    lid_open_angle = p * 1.0
    lid_Pivot_y = 142.0 + tilt_y
    lid_height = 54.0 * (1.0 - 0.55 * math.sin(lid_open_angle * math.pi * 0.5))
    lid_top_y = lid_Pivot_y - lid_height - (p * 34.0)
    lid_back_shift = p * (-8.0)

    # Cavidad interior de la tapa cuando está abierta (se ve a partir de p > 0.35)
    inside_lid_opacity = max(0.0, min(1.0, (p - 0.30) / 0.45))

    cx = 170.0 + side_shift * 0.35
    base_y = 140.0 + tilt_y
    shadow_rx = (86.0 + abs(yaw) * 0.5) * (0.28 + 0.72 * ap)
    shadow_ry = 14.0 * (0.28 + 0.72 * ap)
    shadow_opacity = 0.15 + 0.85 * ap

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="340" height="270" viewBox="0 0 340 270">
  <defs>
    <radialGradient id="ambientGlow" cx="50%" cy="54%" r="48%">
      <stop offset="0%" stop-color="{ambient_glow}"/>
      <stop offset="100%" stop-color="rgba(0,0,0,0)"/>
    </radialGradient>

    <radialGradient id="floorShadow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="rgba(0,0,0,0.48)"/>
      <stop offset="65%" stop-color="rgba(0,0,0,0.18)"/>
      <stop offset="100%" stop-color="rgba(0,0,0,0)"/>
    </radialGradient>

    <linearGradient id="caseSide3D" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{shell_mid}"/>
      <stop offset="50%" stop-color="{shell_bot}"/>
      <stop offset="100%" stop-color="{shell_edge}"/>
    </linearGradient>

    <radialGradient id="caseBodyGrad" cx="{36 - yaw * 0.4:.1f}%" cy="24%" r="78%">
      <stop offset="0%" stop-color="{shell_top}"/>
      <stop offset="48%" stop-color="{shell_mid}"/>
      <stop offset="86%" stop-color="{shell_bot}"/>
      <stop offset="100%" stop-color="{shell_edge}"/>
    </radialGradient>

    <radialGradient id="lidGrad" cx="{38 - yaw * 0.4:.1f}%" cy="22%" r="75%">
      <stop offset="0%" stop-color="{shell_top}"/>
      <stop offset="55%" stop-color="{shell_mid}"/>
      <stop offset="100%" stop-color="{shell_bot}"/>
    </radialGradient>

    <linearGradient id="wellGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="{inner_dark}"/>
      <stop offset="55%" stop-color="{inner_well}"/>
      <stop offset="100%" stop-color="{shell_bot}"/>
    </linearGradient>

    <radialGradient id="budGradL" cx="35%" cy="28%" r="72%">
      <stop offset="0%" stop-color="{bud_top}"/>
      <stop offset="58%" stop-color="{bud_mid}"/>
      <stop offset="100%" stop-color="{bud_bot}"/>
    </radialGradient>

    <radialGradient id="budGradR" cx="65%" cy="28%" r="72%">
      <stop offset="0%" stop-color="{bud_top}"/>
      <stop offset="58%" stop-color="{bud_mid}"/>
      <stop offset="100%" stop-color="{bud_bot}"/>
    </radialGradient>

    <linearGradient id="specHighlight" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="rgba(255,255,255,{0.75 if connected else 0.22})"/>
      <stop offset="100%" stop-color="rgba(255,255,255,0.0)"/>
    </linearGradient>
  </defs>

  <g opacity="{overall_opacity}">
    <!-- Halo ambiental y sombra proyectada en suelo (crece al acercarse) -->
    <ellipse cx="170" cy="142" rx="{135 * (0.4 + 0.6 * ap):.1f}" ry="{105 * (0.4 + 0.6 * ap):.1f}" fill="url(#ambientGlow)"/>
    <ellipse cx="{cx:.1f}" cy="242" rx="{shadow_rx:.1f}" ry="{shadow_ry:.1f}" opacity="{shadow_opacity:.2f}" fill="url(#floorShadow)"/>

    <!-- Grupo 3D con transformación de llegada desde lo lejos (escala + traslación Z/Y + alabeo) -->
    <g transform="translate(170, {155 + ap_offset_y:.1f}) scale({ap_scale:.3f}) rotate({ap_roll:.2f}) translate(-170, -155)">

    <!-- Tapa abierta vista desde atrás (cuando p > 0) -->
    <g opacity="{inside_lid_opacity:.2f}" transform="translate({extrude_x * 0.4:.1f}, {lid_back_shift:.1f})">
      <rect x="{cx - 82:.1f}" y="{lid_top_y - 12:.1f}" width="164" height="58" rx="28"
            fill="url(#caseSide3D)" stroke="{shell_edge}" stroke-width="1"/>
      <rect x="{cx - 76:.1f}" y="{lid_top_y - 6:.1f}" width="152" height="46" rx="23"
            fill="url(#wellGrad)"/>
      <ellipse cx="{cx - 34:.1f}" cy="{lid_top_y + 17:.1f}" rx="28" ry="13" fill="{inner_dark}" opacity="0.55"/>
      <ellipse cx="{cx + 34:.1f}" cy="{lid_top_y + 17:.1f}" rx="28" ry="13" fill="{inner_dark}" opacity="0.55"/>
    </g>

    <!-- Auriculares izquierdo y derecho en 3D dentro del estuche -->
    <g opacity="{bud_visible_opacity:.2f}">
      <!-- Auricular Izquierdo -->
      <g transform="translate({cx - 38 + extrude_x * 0.25:.1f}, {bud_y:.1f}) rotate({-8 - yaw * 0.15:.1f})">
        <!-- Tallo -->
        <rect x="-11" y="6" width="15" height="44" rx="7.5" fill="url(#budGradL)" stroke="{shell_edge}" stroke-width="0.8"/>
        <!-- Cabeza ergonómica 3D -->
        <ellipse cx="4" cy="0" rx="26" ry="20" fill="url(#budGradL)" stroke="{shell_edge}" stroke-width="0.9"/>
        <!-- Brillo especular -->
        <ellipse cx="-2" cy="-7" rx="15" ry="7" fill="url(#specHighlight)"/>
        <!-- Rejilla acústica negra -->
        <ellipse cx="14" cy="2" rx="6.5" ry="9.5" transform="rotate(14 14 2)" fill="{mesh_fill}"/>
        <ellipse cx="-5" cy="4" rx="3.2" ry="1.8" fill="{mesh_fill}" opacity="0.75"/>
      </g>

      <!-- Auricular Derecho -->
      <g transform="translate({cx + 38 + extrude_x * 0.25:.1f}, {bud_y:.1f}) rotate({8 - yaw * 0.15:.1f})">
        <!-- Tallo -->
        <rect x="-4" y="6" width="15" height="44" rx="7.5" fill="url(#budGradR)" stroke="{shell_edge}" stroke-width="0.8"/>
        <!-- Cabeza ergonómica 3D -->
        <ellipse cx="-4" cy="0" rx="26" ry="20" fill="url(#budGradR)" stroke="{shell_edge}" stroke-width="0.9"/>
        <!-- Brillo especular -->
        <ellipse cx="2" cy="-7" rx="15" ry="7" fill="url(#specHighlight)"/>
        <!-- Rejilla acústica negra -->
        <ellipse cx="-14" cy="2" rx="6.5" ry="9.5" transform="rotate(-14 -14 2)" fill="{mesh_fill}"/>
        <ellipse cx="5" cy="4" rx="3.2" ry="1.8" fill="{mesh_fill}" opacity="0.75"/>
      </g>
    </g>

    <!-- Boca / cuna interior del estuche -->
    <ellipse cx="{cx:.1f}" cy="{base_y + 2:.1f}" rx="82" ry="14" fill="url(#wellGrad)" stroke="{shell_edge}" stroke-width="1"/>
    <ellipse cx="{cx - 34:.1f}" cy="{base_y + 2:.1f}" rx="28" ry="8" fill="{inner_dark}" opacity="0.65"/>
    <ellipse cx="{cx + 34:.1f}" cy="{base_y + 2:.1f}" rx="28" ry="8" fill="{inner_dark}" opacity="0.65"/>

    <!-- Volumen lateral 3D del cuerpo del estuche (extrusión según rotación) -->
    <rect x="{cx - 84 + extrude_x:.1f}" y="{base_y - 2:.1f}" width="168" height="92" rx="42"
          fill="url(#caseSide3D)"/>

    <!-- Cuerpo frontal principal del estuche -->
    <rect x="{cx - 84:.1f}" y="{base_y - 4:.1f}" width="168" height="92" rx="42"
          fill="url(#caseBodyGrad)" stroke="{shell_edge}" stroke-width="1.1"/>

    <!-- Reflejo curvo frontal estilo cerámica Apple -->
    <path d="M {cx - 66:.1f} {base_y + 10:.1f} Q {cx:.1f} {base_y + 2:.1f} {cx + 66:.1f} {base_y + 10:.1f}"
          fill="none" stroke="url(#specHighlight)" stroke-width="5" stroke-linecap="round"/>

    <!-- Ranura de apertura con bisel metálico sutil -->
    <line x1="{cx - 82:.1f}" y1="{base_y:.1f}" x2="{cx + 82:.1f}" y2="{base_y:.1f}"
          stroke="{inner_dark}" stroke-width="1.6"/>

    <!-- LED frontal del estuche -->
    <circle cx="{cx + side_shift * 0.2:.1f}" cy="{base_y + 34:.1f}" r="6.5" fill="{led_glow}"/>
    <circle cx="{cx + side_shift * 0.2:.1f}" cy="{base_y + 34:.1f}" r="3.0" fill="{led_color}"/>

    <!-- Tapa frontal cuando está cerrada o abriéndose (se pliega al llegar a p=1) -->
    <g opacity="{max(0.0, 1.0 - p * 1.15):.2f}">
      <rect x="{cx - 84 + extrude_x * 0.6:.1f}" y="{base_y - lid_height:.1f}" width="168" height="{lid_height + 6:.1f}" rx="38"
            fill="url(#caseSide3D)"/>
      <rect x="{cx - 84:.1f}" y="{base_y - lid_height:.1f}" width="168" height="{lid_height + 6:.1f}" rx="38"
            fill="url(#lidGrad)" stroke="{shell_edge}" stroke-width="1.1"/>
      <ellipse cx="{cx - 12:.1f}" cy="{base_y - lid_height + 14:.1f}" rx="52" ry="10"
               fill="url(#specHighlight)"/>
    </g>
    </g>
  </g>
</svg>"""
    return svg.encode("utf-8")


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
    from gi.repository import Adw, Gdk, GLib, Gtk

    app = Adw.Application(application_id="org.gonzavz.AirPods")

    css = Gtk.CssProvider()
    css.load_from_string(
        """
        .apple-sheet {
            background: linear-gradient(180deg, rgba(42, 45, 58, 0.95) 0%, rgba(26, 28, 36, 0.98) 100%);
            border-radius: 28px;
            border: 1px solid rgba(255, 255, 255, 0.10);
            padding: 24px 22px 22px 22px;
        }
        .apple-sheet-disconnected {
            background: linear-gradient(180deg, rgba(34, 36, 44, 0.85) 0%, rgba(22, 23, 29, 0.92) 100%);
            border-radius: 28px;
            border: 1px solid rgba(255, 255, 255, 0.06);
            padding: 28px 22px 26px 22px;
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

    def _svg_to_texture(svg_bytes):
        return Gdk.Texture.new_from_bytes(GLib.Bytes.new(svg_bytes))

    def on_activate(application):
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

        win = Adw.ApplicationWindow(application=application)
        win.set_title("AirPods")
        win.set_default_size(460, 650)

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        toast_overlay = Adw.ToastOverlay()
        toolbar_view.set_content(toast_overlay)

        # Stack principal:
        # 1) "disconnected": AirPods sombreados en gris 3D cuando están desconectados.
        # 2) "welcome": Tarjeta estilo Apple con animación 3D de estuche cerrado -> abierto + botón Continuar.
        # 3) "controls": Panel completo de configuración y estado.
        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        stack.set_transition_duration(260)
        toast_overlay.set_child(stack)

        # =====================================================================
        # VISTA 1: DESCONECTADOS (AirPods sombreados en gris)
        # =====================================================================
        disc_clamp = Adw.Clamp(maximum_size=400)
        disc_clamp.set_margin_top(28)
        disc_clamp.set_margin_bottom(28)
        disc_clamp.set_margin_start(20)
        disc_clamp.set_margin_end(20)
        disc_clamp.set_valign(Gtk.Align.CENTER)

        disc_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        disc_card.add_css_class("apple-sheet-disconnected")
        disc_clamp.set_child(disc_card)

        disc_picture = Gtk.Picture()
        disc_picture.set_size_request(320, 250)
        disc_picture.set_can_shrink(True)
        disc_picture.set_paintable(
            _svg_to_texture(render_airpods_3d_svg(connected=False, open_progress=0.35, spin_angle=0.0))
        )
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
        # VISTA 2: BIENVENIDA ESTILO APPLE (Animación 3D cerrados -> se abren + Continuar)
        # =====================================================================
        welcome_clamp = Adw.Clamp(maximum_size=400)
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

        anim_picture = Gtk.Picture()
        anim_picture.set_size_request(330, 260)
        anim_picture.set_can_shrink(True)
        welcome_card.append(anim_picture)

        # Pastillas de batería debajo de la animación 3D (Izquierdo · Estuche · Derecho)
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

        # Cabecera visual 3D compacta en la vista de controles
        hero_picture = Gtk.Picture()
        hero_picture.set_size_request(240, 175)
        hero_picture.set_can_shrink(True)
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
            "anim_start": time.monotonic(),
            "anim_timer_id": None,
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

        # --- Animación 3D en tiempo real (llega desde lo lejos cerrado -> se abre + rotación 3D) ---
        def update_3d_frame():
            elapsed = time.monotonic() - ui_state["anim_start"]
            # Fase 1 (0.0s .. 0.85s): el estuche cerrado llega desde lo lejos hacia el primer plano
            approach_t = max(0.0, min(1.0, elapsed / 0.85))
            # Fase 2 (0.75s .. 1.85s): al llegar delante se abre la tapa y emergen los auriculares
            open_t = max(0.0, min(1.0, (elapsed - 0.75) / 1.10))
            spin = elapsed * 1.65
            tex = _svg_to_texture(
                render_airpods_3d_svg(
                    connected=True,
                    open_progress=open_t,
                    spin_angle=spin,
                    approach_progress=approach_t,
                )
            )
            anim_picture.set_paintable(tex)
            hero_picture.set_paintable(tex)
            return True

        def start_opening_animation():
            ui_state["anim_start"] = time.monotonic()
            update_3d_frame()
            if ui_state["anim_timer_id"] is None:
                ui_state["anim_timer_id"] = GLib.timeout_add(33, update_3d_frame)

        def stop_animation():
            if ui_state["anim_timer_id"] is not None:
                GLib.source_remove(ui_state["anim_timer_id"])
                ui_state["anim_timer_id"] = None

        def on_continue_clicked(_btn):
            ui_state["dismissed_welcome"] = True
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
                    stop_animation()
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
                    disc_picture.set_paintable(
                        _svg_to_texture(
                            render_airpods_3d_svg(
                                connected=False, open_progress=0.35, spin_angle=0.0
                            )
                        )
                    )
                    stack.set_visible_child_name("disconnected")
                    return False

                # Conectados: si acaban de conectarse (o al abrir la app conectados),
                # mostramos la tarjeta estilo Apple con la animación 3D cerrados -> abiertos
                if not ui_state["was_connected"]:
                    ui_state["was_connected"] = True
                    ui_state["dismissed_welcome"] = False
                    start_opening_animation()

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
            lambda *_: (stop_animation(), controller.stop(), False)[2],
        )

        win.set_content(toolbar_view)
        win.present()

    app.connect("activate", on_activate)
    return app.run([])


def main(argv=None):
    return run_app()


if __name__ == "__main__":
    sys.exit(main())
