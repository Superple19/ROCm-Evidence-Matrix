import types
import unittest

from windows_rocm_matrix.hardware import collect_hardware, merge_hardware
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

    def test_rejects_legacy_os_name(self):
        record = collect_hardware(types.SimpleNamespace(__version__="2.12.0", version=types.SimpleNamespace(hip=None), cuda=types.SimpleNamespace(is_available=lambda: False, device_count=lambda: 0)), "2026-08-08T00:00:00Z")
        record["os"] = "nt"
        with self.assertRaisesRegex(ValueError, "operating system"):
            validate_hardware_verifications({"schema_version": 1, "generated_at": record["observed_at"], "verifications": [record]})

    def test_merge_deduplicates_ids_and_keeps_generated_time_monotonic(self):
        record = collect_hardware(
            types.SimpleNamespace(__version__="2.12.0", version=types.SimpleNamespace(hip=None), cuda=types.SimpleNamespace(is_available=lambda: False, device_count=lambda: 0)),
            "2026-08-07T00:00:00Z",
        )
        existing = {"schema_version": 1, "generated_at": "2026-08-08T00:00:00Z", "verifications": [record]}
        merged = merge_hardware(existing, record)
        self.assertEqual(len(merged["verifications"]), 1)
        self.assertEqual(merged["generated_at"], "2026-08-08T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
