import unittest

from airpods import aap
from airpods.link import Link


class _FakeSocket:
    def __init__(self, incoming):
        self._incoming = list(incoming)
        self.events = []

    def settimeout(self, _):
        pass

    def connect(self, addr):
        self.events.append(("connect", addr))

    def send(self, data):
        self.events.append(("tx", data))

    def recv(self, _):
        if not self._incoming:
            return b""
        pkt = self._incoming.pop(0)
        self.events.append(("rx", pkt))
        return pkt

    def shutdown(self, _):
        pass

    def close(self):
        pass


class LinkTest(unittest.TestCase):
    def test_requests_notifications_only_after_handshake_ack(self):
        ack = bytes.fromhex("010004000000010003000000000000000000")
        fake = _FakeSocket([ack])
        rx_log = []
        link = Link(
            "AA:BB:CC:DD:EE:FF",
            on_rx=rx_log.append,
            on_closed=lambda: None,
            socket_factory=lambda: fake,
        )
        link.open()
        link.close()
        self.assertEqual(fake.events[:5], [
            ("connect", ("AA:BB:CC:DD:EE:FF", aap.PSM)),
            ("tx", aap.HANDSHAKE),
            ("rx", ack),
            ("tx", aap.SET_SPECIFIC_FEATURES),
            ("tx", aap.REQUEST_NOTIFICATIONS),
        ])
        self.assertEqual(rx_log, [ack])


if __name__ == "__main__":
    unittest.main()
