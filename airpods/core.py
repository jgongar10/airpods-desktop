"""Núcleo del servicio: mantiene el estado de los AirPods."""

import copy
import threading

from . import aap


def _empty_battery():
    return {
        "left": {"level": None, "charging": False},
        "right": {"level": None, "charging": False},
        "case": {"level": None, "charging": False},
    }


def _initial_state():
    return {
        "connected": False,
        "communicating": False,
        "battery": _empty_battery(),
        "noise_mode": None,
        "in_ear": {"left": None, "right": None},
        "ear_detection": True,
    }


class Core:
    def __init__(self, link_factory):
        self._link_factory = link_factory
        self._lock = threading.Lock()
        self._state = _initial_state()
        self._subscribers = []
        self._link = None

    def get_state(self):
        with self._lock:
            return copy.deepcopy(self._state)

    def subscribe(self, callback):
        with self._lock:
            self._subscribers.append(callback)
            initial = copy.deepcopy(self._state)
        callback(initial)

    def unsubscribe(self, callback):
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def on_connected(self, address):
        link = self._link_factory(address, self._on_rx, self._on_link_closed)
        try:
            link.open()
        except OSError:
            self._set_state(connected=True, communicating=False)
            return
        self._link = link
        self._set_state(connected=True, communicating=True)

    def on_disconnected(self, _address):
        link = self._link
        self._link = None
        if link is not None:
            link.close()
        self._set_state(
            connected=False,
            communicating=False,
            battery=_empty_battery(),
            noise_mode=None,
            in_ear={"left": None, "right": None},
        )

    def _on_link_closed(self):
        with self._lock:
            if not self._state["connected"]:
                return
        self._set_state(communicating=False)

    def _on_rx(self, packet):
        battery_update = aap.parse_battery(packet)
        if battery_update is None:
            return
        with self._lock:
            new_battery = copy.deepcopy(self._state["battery"])
            new_battery.update(battery_update)
        self._set_state(battery=new_battery)

    def _set_state(self, **changes):
        with self._lock:
            next_state = copy.deepcopy(self._state)
            next_state.update(changes)
            if next_state == self._state:
                return
            self._state = next_state
            snapshot = copy.deepcopy(self._state)
            subs = list(self._subscribers)
        for cb in subs:
            cb(snapshot)
