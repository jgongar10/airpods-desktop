"""Adaptador de reproductores MPRIS por D-Bus (sesión de usuario)."""

from gi.repository import Gio

DBUS_NAME = "org.freedesktop.DBus"
DBUS_PATH = "/org/freedesktop/DBus"
DBUS_IFACE = "org.freedesktop.DBus"
MPRIS_PREFIX = "org.mpris.MediaPlayer2."
MPRIS_PATH = "/org/mpris/MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
PROPS_IFACE = "org.freedesktop.DBus.Properties"


class MprisPlayers:
    def __init__(self, on_changed=None):
        self._on_changed = on_changed
        self._bus = Gio.bus_get_sync(Gio.BusType.SESSION)

    def start(self):
        self._bus.signal_subscribe(
            None,
            PROPS_IFACE,
            "PropertiesChanged",
            MPRIS_PATH,
            PLAYER_IFACE,
            Gio.DBusSignalFlags.NONE,
            self._properties_changed,
        )

    def _list_names(self):
        reply = self._bus.call_sync(
            DBUS_NAME,
            DBUS_PATH,
            DBUS_IFACE,
            "ListNames",
            None,
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        names = reply.unpack()[0]
        return [n for n in names if n.startswith(MPRIS_PREFIX)]

    def _playback_status(self, bus_name):
        try:
            reply = self._bus.call_sync(
                bus_name,
                MPRIS_PATH,
                PROPS_IFACE,
                "Get",
                Gio.GLib.Variant("(ss)", (PLAYER_IFACE, "PlaybackStatus")),
                None,
                Gio.DBusCallFlags.NONE,
                1000,
                None,
            )
            return reply.unpack()[0]
        except Exception:
            return None

    def playing_players(self):
        return [
            name for name in self._list_names()
            if self._playback_status(name) == "Playing"
        ]

    def paused_players(self):
        return [
            name for name in self._list_names()
            if self._playback_status(name) == "Paused"
        ]

    def pause(self, bus_name):
        self._call_player(bus_name, "Pause")

    def play(self, bus_name):
        self._call_player(bus_name, "Play")

    def _call_player(self, bus_name, method):
        try:
            self._bus.call_sync(
                bus_name,
                MPRIS_PATH,
                PLAYER_IFACE,
                method,
                None,
                None,
                Gio.DBusCallFlags.NONE,
                1000,
                None,
            )
        except Exception:
            pass

    def _properties_changed(self, _conn, sender, _path, _iface, _signal, params):
        if self._on_changed is None or not sender:
            return
        _iface_name, changed, _invalidated = params.unpack()
        status = changed.get("PlaybackStatus")
        if status in ("Playing", "Paused", "Stopped"):
            self._on_changed(sender, status)
