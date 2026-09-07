import unittest

from rocm_evidence_matrix.validation import validate_legacy_windows, validate_snapshot
from rocm_evidence_matrix.validation import validate_compatibility_matrix


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
        "source": {
            "id": "nightly",
            "distribution_family": "therock",
            "channel": "nightly",
            "url": "https://example.test/",
            "platform": "windows",
        },
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
    def test_linux_only_compatibility_matrix_does_not_require_windows_aliases(self):
        matrix = {
            "schema_version": 1,
            "generated_at": "2026-08-08T00:00:00Z",
            "sources": {"packages-stable-linux": {"id": "packages-stable-linux"}},
            "targets": [
                {
                    "gfx": "gfx1100",
                    "products": [],
                    "platforms": {
                        "linux": {
                            "package_channels": {
                                "stable": {
                                    "source_id": "packages-stable-linux",
                                }
                            }
                        }
                    },
                }
            ],
        }

        validate_compatibility_matrix(matrix)

    def test_accepts_valid_snapshot(self):
        validate_snapshot(valid_snapshot())

    def test_rejects_snapshot_without_platform(self):
        snapshot = valid_snapshot()
        snapshot["source"].pop("platform")

        with self.assertRaisesRegex(ValueError, "platform"):
            validate_snapshot(snapshot)

    def test_rejects_linux_snapshot_with_windows_wheel(self):
        snapshot = valid_snapshot()
        snapshot["source"]["platform"] = "linux"

        with self.assertRaisesRegex(ValueError, "not applicable to Linux"):
            validate_snapshot(snapshot)

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

    def test_rejects_legacy_artifact_outside_release_index(self):
        document = {
            "schema_version": 1,
            "generated_at": "2026-08-07T00:00:00Z",
            "sources": {"legacy": {}},
            "hip_sdk_releases": [],
            "hip_sdk_gpu_support": [],
            "pytorch_windows_support": [],
            "artifact_releases": [
                {
                    "release_id": "7.2.1",
                    "url": "https://example.test/7.2.1/",
                    "source_id": "legacy",
                    "artifacts": [{"url": "https://other.test/torch.whl"}],
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "outside legacy release index"):
            validate_legacy_windows(document)


if __name__ == "__main__":
    unittest.main()
