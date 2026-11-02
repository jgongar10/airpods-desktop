"""Constantes del protocolo AAP necesarias para el primer contacto.

Referencia del formato: LibrePods / librepods-rs (ver ADR 0001).
La interpretación de los paquetes recibidos llega en tickets posteriores.
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
