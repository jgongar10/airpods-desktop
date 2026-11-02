import json
import os
import tempfile
import unittest

from airpods.capture import CaptureWriter


class CaptureWriterTest(unittest.TestCase):
    def test_dumps_rx_tx_and_marks_with_timestamp_and_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cap.jsonl")
            ticks = iter([1.0, 2.0, 3.0])
            writer = CaptureWriter(path, clock=lambda: next(ticks))
            writer.tx(b"\x00\x01")
            writer.rx(b"\x04\x00\xff")
            writer.mark("estuche abierto")
            writer.close()
            with open(path) as f:
                lines = [json.loads(line) for line in f]
        self.assertEqual(lines, [
            {"ts": 1.0, "dir": "tx", "hex": "0001"},
            {"ts": 2.0, "dir": "rx", "hex": "0400ff"},
            {"ts": 3.0, "dir": "mark", "label": "estuche abierto"},
        ])


if __name__ == "__main__":
    unittest.main()
