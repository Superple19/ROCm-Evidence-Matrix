import unittest
from pathlib import Path

from windows_rocm_matrix.simple_index import discover_gfx_targets, discover_packages, latest_artifacts, latest_version, parse_windows_wheels, version_key


FIXTURES = Path(__file__).parent / "fixtures"


class SimpleIndexTests(unittest.TestCase):
    def test_discovers_packages_and_exact_targets(self):
        html = (FIXTURES / "root-index.html").read_text(encoding="utf-8")
        packages = discover_packages(html, "https://example.test/simple/")

        self.assertEqual(discover_gfx_targets(packages), ["gfx1100", "gfx1201"])

    def test_parses_only_matching_windows_wheels(self):
        html = (FIXTURES / "package-index.html").read_text(encoding="utf-8")
        artifacts = parse_windows_wheels(
            html,
            "https://example.test/simple/amd-torch-device-gfx1201/",
            "amd-torch-device-gfx1201",
        )

        self.assertEqual(len(artifacts), 2)
        self.assertEqual(artifacts[0]["platform_tag"], "win_amd64")
        self.assertEqual(latest_version(artifacts), "2.14.0a0+rocm10.1.0a20260806")
        self.assertEqual(len(latest_artifacts(artifacts)), 1)

    def test_orders_prereleases_before_final_release(self):
        self.assertLess(version_key("2.14.0a0"), version_key("2.14.0"))


if __name__ == "__main__":
    unittest.main()
