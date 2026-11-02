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

_BATTERY_COMPONENTS = {
    0x02: "right",
    0x04: "left",
    0x08: "case",
}

_STATUS_CHARGING = 0x01
_STATUS_DISCONNECTED = 0x04


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
