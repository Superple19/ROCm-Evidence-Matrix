import unittest

from windows_rocm_matrix.validation import validate_snapshot


def valid_snapshot():
    package_names = [
        "rocm-sdk-device-gfx1201",
        "amd-torch-device-gfx1201",
        "amd-torchvision-device-gfx1201",
    ]
    artifact = {
        "filename": "package-1.0.0-cp312-cp312-win_amd64.whl",
        "version": "1.0.0",
        "python_tag": "cp312",
        "abi_tag": "cp312",
        "platform_tag": "win_amd64",
        "url": "https://example.test/package.whl",
    }
    return {
        "schema_version": 1,
        "last_observed_at": "2026-08-07T00:00:00Z",
        "source": {"id": "nightly", "channel": "nightly", "url": "https://example.test/"},
        "gfx_targets": [
            {
                "gfx": "gfx1201",
                "device_packages": package_names,
                "all_device_packages_available": True,
            }
        ],
        "packages": {name: [artifact.copy()] for name in package_names},
    }


class ValidationTests(unittest.TestCase):
    def test_accepts_valid_snapshot(self):
        validate_snapshot(valid_snapshot())

    def test_rejects_incorrect_availability(self):
        snapshot = valid_snapshot()
        snapshot["packages"]["amd-torch-device-gfx1201"] = []

        with self.assertRaisesRegex(ValueError, "Incorrect device package availability"):
            validate_snapshot(snapshot)

    def test_rejects_multiple_versions_per_package(self):
        snapshot = valid_snapshot()
        second = snapshot["packages"]["rocm-sdk-device-gfx1201"][0].copy()
        second["version"] = "2.0.0"
        snapshot["packages"]["rocm-sdk-device-gfx1201"].append(second)

        with self.assertRaisesRegex(ValueError, "multiple versions"):
            validate_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()
