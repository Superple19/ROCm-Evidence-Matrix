import types
import unittest

from windows_rocm_matrix.hardware import collect_hardware
from windows_rocm_matrix.runtime import normalized_os
from windows_rocm_matrix.validation import validate_hardware_verifications


class HardwareTests(unittest.TestCase):
    def test_records_unavailable_hardware_without_claiming_success(self):
        torch = types.SimpleNamespace(__version__="2.12.0", version=types.SimpleNamespace(hip="7.14.0"), cuda=types.SimpleNamespace(is_available=lambda: False, device_count=lambda: 0))
        record = collect_hardware(torch, "2026-08-08T00:00:00Z")
        self.assertEqual(record["result"], "failed")
        self.assertEqual(record["os"], normalized_os())
        self.assertFalse(record["correct"])
        validate_hardware_verifications({"schema_version": 1, "generated_at": record["observed_at"], "verifications": [record]})


if __name__ == "__main__":
    unittest.main()
