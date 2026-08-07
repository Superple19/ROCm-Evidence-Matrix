import unittest

from windows_rocm_matrix.integration import build_compatibility_matrix


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
            "source": {"id": "nightly", "channel": "nightly", "url": "https://example.test/packages"},
            "gfx_targets": [{"gfx": "gfx1201", "all_device_packages_available": False}],
            "packages": {},
        }

        matrix = build_compatibility_matrix(documentation, [package_snapshot])
        target = matrix["targets"][0]

        self.assertIsNotNone(target["windows_release_support"])
        self.assertFalse(target["package_channels"]["nightly"]["all_device_packages_available"])
        self.assertIsNone(target["package_channels"]["nightly"]["torch_device_version"])


if __name__ == "__main__":
    unittest.main()
