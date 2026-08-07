import types
import unittest

from windows_rocm_matrix.runtime import collect_runtime
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
        self.assertEqual(record["devices"][0]["gcnArchName"], "gfx1201")
        validate_runtime_verifications({"schema_version": 1, "generated_at": record["observed_at"], "verifications": [record]})

    def test_records_unavailable_runtime_as_failure(self):
        torch = types.SimpleNamespace(__version__="2.12.0", version=types.SimpleNamespace(hip=None), cuda=types.SimpleNamespace(is_available=lambda: False, device_count=lambda: 0))
        record = collect_runtime(torch, "2026-08-08T00:00:00Z")
        self.assertEqual(record["result"], "failed")


if __name__ == "__main__":
    unittest.main()
