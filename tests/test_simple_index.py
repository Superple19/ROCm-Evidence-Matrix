import unittest
from pathlib import Path

from rocm_evidence_matrix.simple_index import discover_gfx_targets, discover_packages, latest_artifacts, latest_version, parse_linux_wheels, parse_source_distributions, parse_windows_wheels, version_key


FIXTURES = Path(__file__).parent / "fixtures"


class SimpleIndexTests(unittest.TestCase):
    def test_discovers_packages_and_exact_targets(self):
        html = (FIXTURES / "root-index.html").read_text(encoding="utf-8")
        packages = discover_packages(html, "https://example.test/simple/")

        self.assertEqual(discover_gfx_targets(packages), ["gfx1100", "gfx1201"])

    def test_discovers_alias_packages_without_treating_them_as_exact_targets(self):
        html = (FIXTURES / "root-index-aliases.html").read_text(encoding="utf-8")
        packages = discover_packages(html, "https://example.test/simple/")

        self.assertIn("amd-torch-device-gfx12-0", packages)
        self.assertIn("amd-torch-device-gfx110x", packages)
        self.assertEqual(discover_gfx_targets(packages), ["gfx1201"])

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

    def test_orders_pep440_local_and_post_versions(self):
        self.assertLess(version_key("7.14.0a20260806"), version_key("7.14.0"))
        self.assertLess(version_key("2.12.0+rocm7.14.0"), version_key("2.12.0+rocm7.14.0.post1"))
        self.assertGreater(version_key("2.14.0+rocm10.1.0a20260806"), version_key("2.13.0+rocm10.1.0a20260806"))

    def test_parses_source_distribution(self):
        html = '<a href="rocm-7.14.0.tar.gz">rocm-7.14.0.tar.gz</a>'

        artifacts = parse_source_distributions(html, "https://example.test/simple/rocm/", "rocm")

        self.assertEqual(artifacts[0]["version"], "7.14.0")
        self.assertEqual(artifacts[0]["platform_tag"], "source")

    def test_parses_linux_wheels_without_accepting_windows_wheels(self):
        html = '<a href="torch-2.12.0+rocm7.14-cp312-cp312-manylinux_2_28_x86_64.whl">torch</a><a href="torch-2.12.0+rocm7.14-cp312-cp312-win_amd64.whl">torch</a>'
        artifacts = parse_linux_wheels(html, "https://example.test/", "torch")
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["platform_tag"], "manylinux_2_28_x86_64")

    def test_parses_fixture_for_platform_independent_package(self):
        html = (FIXTURES / "package-index-linux-any.html").read_text(encoding="utf-8")
        artifacts = parse_linux_wheels(html, "https://example.test/rocm-bootstrap/", "rocm-bootstrap")
        self.assertEqual([item["platform_tag"] for item in artifacts], ["any"])


if __name__ == "__main__":
    unittest.main()
