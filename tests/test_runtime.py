import types
import unittest

from windows_rocm_matrix.runtime import collect_runtime, merge_runtime, normalized_os
from windows_rocm_matrix.validation import validate_runtime_verifications


class RuntimeTests(unittest.TestCase):
    def test_records_device_and_hip_information(self):
        torch = types.SimpleNamespace(
            __version__="2.12.0",
            version=types.SimpleNamespace(hip="7.14.0"),
            cuda=types.SimpleNamespace(
                is_available=lambda: True,
                device_count=lambda: 1,
                get_device_properties=lambda index: types.SimpleNamespace(name="AMD GPU", gcnArchName="gfx1201", multi_processor_count=64, total_memory=1024),
            ),
        )
        record = collect_runtime(torch, "2026-08-08T00:00:00Z")
        self.assertEqual(record["result"], "passed")
        self.assertEqual(record["os"], normalized_os())
        self.assertEqual(record["devices"][0]["gcnArchName"], "gfx1201")
        validate_runtime_verifications({"schema_version": 1, "generated_at": record["observed_at"], "verifications": [record]})

    def test_records_unavailable_runtime_as_failure(self):
        torch = types.SimpleNamespace(__version__="2.12.0", version=types.SimpleNamespace(hip=None), cuda=types.SimpleNamespace(is_available=lambda: False, device_count=lambda: 0))
        record = collect_runtime(torch, "2026-08-08T00:00:00Z")
        self.assertEqual(record["result"], "failed")

    def test_rejects_legacy_os_name(self):
        record = collect_runtime(types.SimpleNamespace(__version__="2.12.0", version=types.SimpleNamespace(hip=None), cuda=types.SimpleNamespace(is_available=lambda: False, device_count=lambda: 0)), "2026-08-08T00:00:00Z")
        record["os"] = "win32"
        with self.assertRaisesRegex(ValueError, "operating system"):
            validate_runtime_verifications({"schema_version": 1, "generated_at": record["observed_at"], "verifications": [record]})

    def test_merge_deduplicates_ids_and_keeps_generated_time_monotonic(self):
        record = collect_runtime(
            types.SimpleNamespace(__version__="2.12.0", version=types.SimpleNamespace(hip=None), cuda=types.SimpleNamespace(is_available=lambda: False, device_count=lambda: 0)),
            "2026-08-07T00:00:00Z",
        )
        existing = {"schema_version": 1, "generated_at": "2026-08-08T00:00:00Z", "verifications": [record]}
        merged = merge_runtime(existing, record)
        self.assertEqual(len(merged["verifications"]), 1)
        self.assertEqual(merged["generated_at"], "2026-08-08T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
