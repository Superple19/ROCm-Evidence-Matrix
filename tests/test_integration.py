import unittest

from rocm_evidence_matrix.integration import build_compatibility_matrix


class IntegrationTests(unittest.TestCase):
    def test_keeps_documentation_and_package_evidence_separate(self):
        documentation = {
            "sources": {"docs": {"id": "docs", "url": "https://example.test/docs", "observed_at": "2026-08-07T00:00:00Z"}},
            "products": [{"name": "Example GPU", "gfx": "gfx1201"}],
            "windows_release_support": [{"gfx": "gfx1201", "source_id": "docs"}],
            "therock_windows_status": [],
        }
        package_snapshot = {
            "last_observed_at": "2026-08-07T00:00:00Z",
            "source": {
                "id": "nightly",
                "channel": "nightly",
                "platform": "windows",
                "url": "https://example.test/packages",
            },
            "gfx_targets": [{"gfx": "gfx1201", "all_device_packages_available": False}],
            "packages": {},
        }

        matrix = build_compatibility_matrix(documentation, [package_snapshot])
        target = matrix["targets"][0]

        self.assertIsNotNone(target["windows_release_support"])
        self.assertIs(target["platforms"]["windows"]["release_support"], target["windows_release_support"])
        self.assertFalse(target["package_channels"]["nightly"]["all_device_packages_available"])
        self.assertIsNone(target["package_channels"]["nightly"]["torch_device_version"])
        self.assertEqual(matrix["generated_at"], "2026-08-07T00:00:00Z")

    def test_rejects_snapshot_without_platform(self):
        documentation = {"sources": {}, "products": []}
        snapshot = {
            "last_observed_at": "2026-08-07T00:00:00Z",
            "source": {"id": "missing-platform", "channel": "stable", "url": "https://example.test/packages"},
            "gfx_targets": [],
            "packages": {},
        }

        with self.assertRaisesRegex(ValueError, "platform"):
            build_compatibility_matrix(documentation, [snapshot])

    def test_keeps_package_channels_separate_by_platform(self):
        documentation = {
            "sources": {},
            "products": [{"name": "Example GPU", "gfx": "gfx1201"}],
            "windows_release_support": [],
            "therock_windows_status": [],
        }
        snapshots = []
        for platform, source_id, rocm in (("windows", "stable", "7.14.0"), ("linux", "stable-linux", "7.2.4")):
            snapshots.append({
                "last_observed_at": "2026-08-07T00:00:00Z",
                "source": {"id": source_id, "channel": "stable", "platform": platform, "url": "https://example.test/packages"},
                "gfx_targets": [{"gfx": "gfx1201", "all_device_packages_available": True}],
                "packages": {
                    "rocm-sdk-device-gfx1201": [{"version": rocm}],
                    "amd-torch-device-gfx1201": [{"version": f"2.0+rocm{rocm}"}],
                    "amd-torchvision-device-gfx1201": [{"version": f"0.1+rocm{rocm}"}],
                },
            })

        target = build_compatibility_matrix(documentation, snapshots)["targets"][0]
        self.assertEqual(target["platforms"]["windows"]["package_channels"]["stable"]["rocm_device_version"], "7.14.0")
        self.assertEqual(target["platforms"]["linux"]["package_channels"]["stable"]["rocm_device_version"], "7.2.4")

    def test_linux_only_target_does_not_invent_windows_aliases(self):
        documentation = {"sources": {}, "products": []}
        snapshot = {
            "last_observed_at": "2026-08-07T00:00:00Z",
            "source": {"id": "stable-linux", "channel": "stable", "platform": "linux", "url": "https://example.test/packages"},
            "gfx_targets": [{"gfx": "gfx1100", "all_device_packages_available": True}],
            "packages": {
                "rocm-sdk-device-gfx1100": [{"version": "7.2.4"}],
                "amd-torch-device-gfx1100": [{"version": "2.0+rocm7.2.4"}],
                "amd-torchvision-device-gfx1100": [{"version": "0.1+rocm7.2.4"}],
            },
        }

        target = build_compatibility_matrix(documentation, [snapshot])["targets"][0]

        self.assertNotIn("windows_release_support", target)
        self.assertNotIn("therock_windows_status", target)
        self.assertNotIn("package_channels", target)
        self.assertEqual(set(target["platforms"]), {"linux"})


if __name__ == "__main__":
    unittest.main()
