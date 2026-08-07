import unittest
from pathlib import Path

from windows_rocm_matrix.documentation import parse_compatibility_matrix, parse_framework_compatibility, parse_gpu_specifications, parse_pytorch_version_compatibility, parse_therock_windows_status


FIXTURES = Path(__file__).parent / "fixtures"


class DocumentationTests(unittest.TestCase):
    def test_parses_product_to_gfx_mapping(self):
        html = (FIXTURES / "gpu-specifications.html").read_text(encoding="utf-8")
        products = parse_gpu_specifications(html, "specs")

        self.assertEqual(products[0]["gfx"], "gfx1152")
        self.assertEqual(products[0]["graphics_model"], "Radeon 860M")
        self.assertEqual(products[1]["name"], "Radeon RX 9070 XT")

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
