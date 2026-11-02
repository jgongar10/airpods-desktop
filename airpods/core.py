"""Núcleo del servicio: mantiene el estado de los AirPods, aplica la Pausa automática
y gestiona los reintentos de comunicación."""

import copy
import json
import os
import threading

from . import aap


def default_config_path():
    config_home = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(config_home, "airpods", "config.json")


def _empty_battery():
    return {
        "left": {"level": None, "charging": False},
        "right": {"level": None, "charging": False},
        "case": {"level": None, "charging": False},
    }


def _initial_state(ear_detection=True):
    return {
        "connected": False,
        "communicating": False,
        "battery": _empty_battery(),
        "noise_mode": None,
        "in_ear": {"left": None, "right": None},
        "ear_detection": bool(ear_detection),
    }


class Core:
    def __init__(self, link_factory, players=None, config_path=None, retry_interval=3.0):
        self._link_factory = link_factory
        self._players = players
        self._config_path = config_path or default_config_path()
        self._retry_interval = retry_interval
        self._lock = threading.Lock()
        self._state = _initial_state(ear_detection=self._load_ear_detection())
        self._subscribers = []
        self._link = None
        self._address = None
        self._retry_timer = None
        self._closed = False
        self._primary_pod = "left"
        self._auto_paused = []
        self._in_flight_player_ops = set()

    def close(self):
        with self._lock:
            self._closed = True
            timer = self._retry_timer
            self._retry_timer = None
            link = self._link
            self._link = None
        if timer is not None:
            timer.cancel()
        if link is not None:
            link.close()

    def _load_ear_detection(self):
        try:
            with open(self._config_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("ear_detection"), bool):
                return data["ear_detection"]
        except (OSError, ValueError):
            pass
        return True

    def _save_ear_detection(self, enabled):
        try:
            parent = os.path.dirname(self._config_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump({"ear_detection": bool(enabled)}, f)
        except OSError:
            pass

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
        with self._lock:
            self._address = address
            self._cancel_retry_locked()
        self._try_open_link(address)

    def on_disconnected(self, _address):
        with self._lock:
            self._address = None
            self._cancel_retry_locked()
            link = self._link
            self._link = None
            self._auto_paused.clear()
            self._primary_pod = "left"
        if link is not None:
            link.close()
        self._set_state(
            connected=False,
            communicating=False,
            battery=_empty_battery(),
            noise_mode=None,
            in_ear={"left": None, "right": None},
        )

    def _try_open_link(self, address):
        with self._lock:
            if self._closed or self._address != address:
                return
        link = self._link_factory(address, self._on_rx, self._on_link_closed)
        try:
            link.open()
        except OSError:
            with self._lock:
                if self._closed or self._address != address:
                    return
                self._link = None
            self._set_state(connected=True, communicating=False)
            self._schedule_retry(address)
            return
        with self._lock:
            if self._closed or self._address != address:
                link.close()
                return
            self._link = link
            self._cancel_retry_locked()
        self._set_state(connected=True, communicating=True)

    def _schedule_retry(self, address):
        with self._lock:
            if self._closed or self._address != address or self._retry_interval is None:
                return
            self._cancel_retry_locked()
            timer = threading.Timer(
                self._retry_interval, self._try_open_link, args=(address,)
            )
            timer.daemon = True
            self._retry_timer = timer
            timer.start()

    def _cancel_retry_locked(self):
        if self._retry_timer is not None:
            self._retry_timer.cancel()
            self._retry_timer = None

    def set_noise_mode(self, mode):
        if mode not in aap.NOISE_MODES:
            valid = ", ".join(aap.NOISE_MODES)
            return False, f"Modo de ruido no válido '{mode}'. Modos válidos: {valid}."
        with self._lock:
            connected = self._state["connected"]
            communicating = self._state["communicating"]
            link = self._link
        if not connected:
            return False, "Error: los AirPods no están conectados."
        if not communicating or link is None:
            return False, "Error: sin comunicación con los AirPods."
        packet = aap.encode_noise_mode(mode)
        try:
            link.send(packet)
        except OSError:
            self._on_link_closed()
            return False, "Error: sin comunicación con los AirPods."
        self._set_state(noise_mode=mode)
        return True, None

    def set_ear_detection(self, enabled):
        if not isinstance(enabled, bool):
            return False, "Valor de detección de oído no válido (usa 'on' u 'off')."
        with self._lock:
            if not enabled:
                self._auto_paused.clear()
        self._save_ear_detection(enabled)
        self._set_state(ear_detection=enabled)
        return True, None

    def on_player_state_changed(self, player_id, _status):
        with self._lock:
            if player_id in self._in_flight_player_ops:
                return
            if player_id in self._auto_paused:
                self._auto_paused.remove(player_id)

    def _on_link_closed(self):
        with self._lock:
            if self._closed or not self._state["connected"]:
                return
            self._link = None
            address = self._address
        self._set_state(communicating=False)
        if address:
            self._schedule_retry(address)

    def _on_rx(self, packet):
        battery_update = aap.parse_battery(packet)
        if battery_update is not None:
            with self._lock:
                new_battery = copy.deepcopy(self._state["battery"])
                new_battery.update(battery_update)
            self._set_state(battery=new_battery)
            return

        noise_mode = aap.parse_noise_mode(packet)
        if noise_mode is not None:
            self._set_state(noise_mode=noise_mode)
            return

        primary = aap.parse_primary_pod(packet)
        if primary is not None:
            with self._lock:
                self._primary_pod = primary
            return

        with self._lock:
            current_primary = self._primary_pod
        in_ear = aap.parse_ear_detection(packet, primary_pod=current_primary)
        if in_ear is not None:
            self._handle_in_ear(in_ear)

    def _handle_in_ear(self, new_in_ear):
        with self._lock:
            prev_in_ear = copy.deepcopy(self._state["in_ear"])
            ear_detection = self._state["ear_detection"]
        self._set_state(in_ear=new_in_ear)
        if not ear_detection or self._players is None:
            return
        if prev_in_ear["left"] is None or prev_in_ear["right"] is None:
            return

        removed_any = (
            (prev_in_ear["left"] and not new_in_ear["left"])
            or (prev_in_ear["right"] and not new_in_ear["right"])
        )
        both_out = not new_in_ear["left"] and not new_in_ear["right"]
        both_in = new_in_ear["left"] and new_in_ear["right"]
        put_back_any = (
            (not prev_in_ear["left"] and new_in_ear["left"])
            or (not prev_in_ear["right"] and new_in_ear["right"])
        )

        if removed_any:
            playing = list(self._players.playing_players())
            for pid in playing:
                with self._lock:
                    self._in_flight_player_ops.add(pid)
                try:
                    self._players.pause(pid)
                finally:
                    with self._lock:
                        self._in_flight_player_ops.discard(pid)
            with self._lock:
                if both_out:
                    self._auto_paused.clear()
                elif playing:
                    for pid in playing:
                        if pid not in self._auto_paused:
                            self._auto_paused.append(pid)
            return

        if both_out:
            with self._lock:
                self._auto_paused.clear()
            return

        if put_back_any and both_in:
            with self._lock:
                remembered = list(self._auto_paused)
                self._auto_paused.clear()
            if not remembered:
                return
            paused_now = set(self._players.paused_players())
            for pid in remembered:
                if pid in paused_now:
                    with self._lock:
                        self._in_flight_player_ops.add(pid)
                    try:
                        self._players.play(pid)
                    finally:
                        with self._lock:
                            self._in_flight_player_ops.discard(pid)

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
