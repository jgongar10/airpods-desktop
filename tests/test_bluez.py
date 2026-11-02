import unittest

from airpods.bluez import is_apple


class IsAppleTest(unittest.TestCase):
    def test_modalias_with_apple_vendor(self):
        self.assertTrue(is_apple({"Modalias": "bluetooth:v004Cp201Bd215C"}))

    def test_manufacturer_data_with_apple_id(self):
        self.assertTrue(is_apple({"ManufacturerData": {0x004C: b"\x07"}}))

    def test_other_vendor(self):
        self.assertFalse(is_apple({"Modalias": "bluetooth:v005Dp0001d0001"}))

    def test_no_info(self):
        self.assertFalse(is_apple({}))


if __name__ == "__main__":
    unittest.main()
