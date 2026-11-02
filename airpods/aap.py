"""Protocolo AAP (Apple Accessory Protocol).

Módulo puro, sin E/S: traduce entre bytes de paquetes AAP y conceptos del dominio.
Referencia del formato: LibrePods / librepods-rs (ver ADR 0001).
"""

PSM = 0x1001
APPLE_VENDOR_ID = 0x004C

HANDSHAKE = bytes.fromhex("00000400010002000000000000000000")
HANDSHAKE_ACK_PREFIX = bytes.fromhex("01000400")
SET_SPECIFIC_FEATURES = bytes.fromhex("040004004d00d700000000000000")
REQUEST_NOTIFICATIONS = bytes.fromhex("040004000f00ffffffff")

# Se envían solo después de recibir la confirmación del saludo; si salen antes
# (p. ej. recién reconectados, cuando el saludo tarda ~400 ms), los AirPods
# los descartan y no activan notificaciones de batería ni de oído.
POST_HANDSHAKE_PACKETS = (SET_SPECIFIC_FEATURES, REQUEST_NOTIFICATIONS)

_BATTERY_PREFIX = bytes.fromhex("040004000400")
_EAR_DETECTION_PREFIX = bytes.fromhex("040004000600")
_PRIMARY_POD_PREFIX = bytes.fromhex("040004000800")
_NOISE_MODE_PREFIX = bytes.fromhex("0400040009000d")

_BATTERY_COMPONENTS = {
    0x02: "right",
    0x04: "left",
    0x08: "case",
}

_STATUS_CHARGING = 0x01
_STATUS_DISCONNECTED = 0x04

NOISE_MODES = ("cancelacion", "transparencia", "adaptativo", "desactivado")

_CODE_TO_NOISE_MODE = {
    0x01: "desactivado",
    0x02: "cancelacion",
    0x03: "transparencia",
    0x04: "adaptativo",
}

_NOISE_MODE_TO_CODE = {v: k for k, v in _CODE_TO_NOISE_MODE.items()}

_PRIMARY_POD_ROLES = {
    0x01: "left",
    0x02: "right",
}


def parse_battery(packet):
    """Extrae la batería por pieza de un paquete AAP, o devuelve None si no es de batería."""
    raw = bytes(packet)
    if not raw.startswith(_BATTERY_PREFIX) or len(raw) < 7:
        return None
    count = raw[6]
    offset = 7
    result = {}
    for _ in range(count):
        if offset + 5 > len(raw):
            break
        comp_id, _pad, level, status, _end = raw[offset:offset + 5]
        offset += 5
        piece = _BATTERY_COMPONENTS.get(comp_id)
        if piece is None:
            continue
        if status == _STATUS_DISCONNECTED or level > 100:
            result[piece] = {"level": None, "charging": False}
        else:
            result[piece] = {
                "level": int(level),
                "charging": status == _STATUS_CHARGING,
            }
    return result or None


def parse_noise_mode(packet):
    """Extrae el modo de ruido de un paquete AAP, o devuelve None si no aplica."""
    raw = bytes(packet)
    if not raw.startswith(_NOISE_MODE_PREFIX) or len(raw) < 8:
        return None
    return _CODE_TO_NOISE_MODE.get(raw[7])


def encode_noise_mode(mode):
    """Codifica la orden AAP para cambiar al modo de ruido indicado."""
    code = _NOISE_MODE_TO_CODE.get(mode)
    if code is None:
        raise ValueError(f"Modo de ruido no válido: {mode}")
    return _NOISE_MODE_PREFIX + bytes([code, 0x00, 0x00, 0x00])


def parse_primary_pod(packet):
    """Extrae qué auricular es el primario ('left' o 'right') de un paquete 0x08."""
    raw = bytes(packet)
    if not raw.startswith(_PRIMARY_POD_PREFIX) or len(raw) < 7:
        return None
    return _PRIMARY_POD_ROLES.get(raw[6])


def parse_ear_detection(packet, primary_pod="left"):
    """Extrae {'left': bool, 'right': bool} de un paquete 0x06 según el auricular primario."""
    raw = bytes(packet)
    if not raw.startswith(_EAR_DETECTION_PREFIX) or len(raw) < 8:
        return None
    primary_in_ear = raw[6] == 0x00
    secondary_in_ear = raw[7] == 0x00
    if primary_pod == "right":
        return {"left": secondary_in_ear, "right": primary_in_ear}
    return {"left": primary_in_ear, "right": secondary_in_ear}
