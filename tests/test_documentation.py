import unittest
from pathlib import Path

from rocm_evidence_matrix.documentation import collect_documentation_sources, parse_compatibility_matrix, parse_framework_compatibility, parse_gpu_specifications, parse_gpu_specifications_rst, parse_pytorch_version_compatibility, parse_therock_windows_status
from rocm_evidence_matrix.validation import validate_documentation_snapshot


FIXTURES = Path(__file__).parent / "fixtures"


class DocumentationTests(unittest.TestCase):
    def test_parses_product_to_gfx_mapping(self):
        html = (FIXTURES / "gpu-specifications.html").read_text(encoding="utf-8")
        products = parse_gpu_specifications(html, "specs")

        self.assertEqual(products[0]["gfx"], "gfx1152")
        self.assertEqual(products[0]["graphics_model"], "Radeon 860M")
        self.assertEqual(products[1]["name"], "Radeon RX 9070 XT")

    def test_parses_product_categories_from_rst_table_identity(self):
        rst = (FIXTURES / "gpu-specifications.rst").read_text(encoding="utf-8")
        products = parse_gpu_specifications_rst(rst, "specs")
        by_name = {product["name"]: product for product in products}

        self.assertEqual(by_name["MI300X"]["category"], "instinct")
        self.assertEqual(by_name["Radeon AI PRO R9700"]["category"], "radeon_pro")
        self.assertEqual(by_name["Radeon RX 9070 XT"]["category"], "radeon")
        self.assertEqual(by_name["AMD Ryzen AI 7 350"]["graphics_model"], "Radeon 860M")

    def test_falls_back_to_rendered_gpu_specifications(self):
        html = (FIXTURES / "gpu-specifications.html").read_text(encoding="utf-8")
        source = {
            "id": "amd-gpu-specifications",
            "url": "https://example.test/gpu-specifications.rst",
            "parser": "gpu-specifications-rst",
            "fallback": {
                "url": "https://example.test/gpu-specifications.html",
                "parser": "gpu-specifications-html",
            },
        }

        document, results = collect_documentation_sources(
            [source],
            lambda url: "invalid" if url.endswith(".rst") else html,
            observed_at="2026-08-07T00:00:00Z",
        )

        self.assertEqual(results[0]["url"], source["fallback"]["url"])
        self.assertTrue(document["sources"][source["id"]]["fallback_used"])
        self.assertEqual(document["sources"][source["id"]]["preferred_url"], source["url"])
        self.assertIn("windows", document["platforms"])
        self.assertIn("linux", document["platforms"])
        self.assertEqual(document["platforms"]["linux"]["release_support"], [])
        validate_documentation_snapshot(document)

    def test_prefers_rst_gpu_specifications(self):
        rst = (FIXTURES / "gpu-specifications.rst").read_text(encoding="utf-8")
        source = {
            "id": "amd-gpu-specifications",
            "url": "https://example.test/gpu-specifications.rst",
            "parser": "gpu-specifications-rst",
            "fallback": {
                "url": "https://example.test/gpu-specifications.html",
                "parser": "gpu-specifications-html",
            },
        }

        document, results = collect_documentation_sources(
            [source],
            lambda url: rst if url.endswith(".rst") else self.fail("fallback should not be fetched"),
            observed_at="2026-08-07T00:00:00Z",
        )

        self.assertEqual(results[0]["url"], source["url"])
        self.assertFalse(document["sources"][source["id"]]["fallback_used"])
        validate_documentation_snapshot(document)

    def test_parses_windows_release_support_conditions(self):
        html = (FIXTURES / "compatibility-matrix.html").read_text(encoding="utf-8")
        support = parse_compatibility_matrix(html, "compatibility")

        self.assertEqual([item["gfx"] for item in support], ["gfx1200", "gfx1201"])
        self.assertEqual(support[1]["selector_ids"], ["rx-9070", "rx-9070-xt"])
        self.assertEqual(support[1]["rocm_version"], "7.14.0")

    def test_parses_therock_windows_status(self):
        markdown = (FIXTURES / "supported-gpus.md").read_text(encoding="utf-8")
        status = parse_therock_windows_status(markdown, "therock")
        by_gfx = {item["gfx"]: item for item in status}

        self.assertTrue(by_gfx["gfx1201"]["build_passing"])
        self.assertFalse(by_gfx["gfx1201"]["sanity_tested"])
        self.assertTrue(by_gfx["gfx1152"]["release_ready"])

    def test_rejects_changed_therock_status_headers(self):
        markdown = (FIXTURES / "supported-gpus.md").read_text(encoding="utf-8")
        markdown = markdown.replace("| Architecture | LLVM target | Build Passing | Sanity Tested | Release Ready |", "| Architecture | LLVM target | Build Status | Sanity Tested | Release Ready |")

        with self.assertRaisesRegex(ValueError, "unexpected headers"):
            parse_therock_windows_status(markdown, "therock")

    def test_parses_framework_compatibility(self):
        markdown = (FIXTURES / "supported-gpus.md").read_text(encoding="utf-8")
        compatibility = parse_framework_compatibility(markdown, "releases")

        self.assertEqual(compatibility[-1]["torch_series"], "2.14")
        self.assertEqual(compatibility[-1]["torchvision_series"], "0.29")

    def test_parses_pytorch_version_compatibility(self):
        markdown = (FIXTURES / "supported-gpus.md").read_text(encoding="utf-8")
        compatibility = parse_pytorch_version_compatibility(markdown, "pytorch")

        self.assertEqual(compatibility[-1]["torch_series"], "2.10")
        self.assertEqual(compatibility[-1]["torchaudio_series"], "2.10")


if __name__ == "__main__":
    unittest.main()
