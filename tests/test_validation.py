import unittest

from rocm_evidence_matrix.validation import validate_legacy_windows, validate_resolver_verifications, validate_snapshot


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

    def test_accepts_resolver_record_without_runtime_fields(self):
        validate_resolver_verifications({
            "schema_version": 1,
            "generated_at": "2026-08-07T00:00:00Z",
            "verifications": [{
                "id": "resolver:one",
                "candidate_id": "candidate",
                "source_id": "packages-nightly",
                "candidate_hash": "a" * 64,
                "distribution_family": "therock",
                "gfx": "gfx1201",
                "platform": "windows",
                "host_platform": "windows",
                "python_tag": "cp312",
                "python_version": "3.12.10",
                "platform_tag": "win_amd64",
                "packages": {"torch": "2.14.0", "torchvision": "0.29.0", "torchaudio": "2.11.0"},
                "command": ["python", "-m", "pip", "install"],
                "observed_at": "2026-08-07T00:00:00Z",
                "result": "failed",
                "exit_code": 1,
                "pip_version": "25.0.1",
                "resolved_packages": [],
                "error": "No matching distribution found",
            }],
        })


if __name__ == "__main__":
    unittest.main()
