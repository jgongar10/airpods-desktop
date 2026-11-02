import json
import os
import tempfile
import unittest

from airpods import guided
from airpods.capture import CaptureWriter


class GuidedTest(unittest.TestCase):
    def test_splits_session_by_situation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sesion.jsonl")
            cap = CaptureWriter(path)
            cap.rx(b"\x01")  # fuera de cualquier situación
            guided.run(cap, input_fn=lambda _="": (cap.rx(b"\x02"), "")[1],
                       print_fn=lambda *_: None,
                       situations=[("a", "x"), ("b", "y")])
            cap.close()
            files = guided.split(path, tmp)
            self.assertEqual(sorted(os.path.basename(f) for f in files), ["a.jsonl", "b.jsonl"])
            with open(os.path.join(tmp, "a.jsonl")) as f:
                entries = [json.loads(l) for l in f]
            self.assertEqual([e["dir"] for e in entries], ["mark", "rx", "mark"])


if __name__ == "__main__":
    unittest.main()
