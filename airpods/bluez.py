"""Detección de conexión de AirPods a través de BlueZ por D-Bus.

Identifica el dispositivo por el fabricante Apple (0x004C), sin configurar
su dirección. Usa Gio (PyGObject del sistema).
"""

import re

from gi.repository import Gio, GLib

from . import aap

BLUEZ = "org.bluez"
DEVICE_IFACE = "org.bluez.Device1"
PROPS_IFACE = "org.freedesktop.DBus.Properties"
_MODALIAS_RE = re.compile(r"^bluetooth:v([0-9A-Fa-f]{4})p", re.IGNORECASE)


def is_apple(props):
    """True si las propiedades de Device1 indican fabricante Apple."""
    match = _MODALIAS_RE.match(props.get("Modalias", ""))
    if match and int(match.group(1), 16) == aap.APPLE_VENDOR_ID:
        return True
    return aap.APPLE_VENDOR_ID in props.get("ManufacturerData", {})


class AirPodsWatcher:
    """Llama a on_connected(address) / on_disconnected(address)."""

    def __init__(self, on_connected, on_disconnected):
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        self._devices = {}  # object path -> props conocidas
        self._connected = set()

    def start(self):
        self._bus.signal_subscribe(
            BLUEZ, PROPS_IFACE, "PropertiesChanged", None, DEVICE_IFACE,
            Gio.DBusSignalFlags.NONE, self._properties_changed,
        )
        self._bus.signal_subscribe(
            BLUEZ, "org.freedesktop.DBus.ObjectManager", "InterfacesAdded",
            None, None, Gio.DBusSignalFlags.NONE, self._interfaces_added,
        )
        reply = self._bus.call_sync(
            BLUEZ, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
            None, None, Gio.DBusCallFlags.NONE, -1, None,
        )
        for path, ifaces in reply.unpack()[0].items():
            if DEVICE_IFACE in ifaces:
                self._update(path, ifaces[DEVICE_IFACE])

    def _interfaces_added(self, _c, _s, _p, _i, _m, params):
        path, ifaces = params.unpack()
        if DEVICE_IFACE in ifaces:
            self._update(path, ifaces[DEVICE_IFACE])

    def _properties_changed(self, _c, _s, path, _i, _m, params):
        _iface, changed, _invalidated = params.unpack()
        self._update(path, changed)

    def _update(self, path, changed):
        props = self._devices.setdefault(path, {})
        props.update(changed)
        if not is_apple(props):
            return
        connected = bool(props.get("Connected"))
        address = props.get("Address") or self._address_from_path(path)
        if connected and path not in self._connected:
            self._connected.add(path)
            self._on_connected(address)
        elif not connected and path in self._connected:
            self._connected.discard(path)
            self._on_disconnected(address)

    @staticmethod
    def _address_from_path(path):
        return path.rsplit("dev_", 1)[-1].replace("_", ":")
