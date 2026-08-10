import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from rocm_evidence_matrix.render import render_snapshots


class RenderTests(unittest.TestCase):
    def test_reports_non_candidate_packages_separately(self):
        snapshot = {
            "source": {"channel": "stable", "platform": "linux", "url": "https://example.test/"},
            "last_observed_at": "2026-08-08T00:00:00Z",
            "gfx_targets": [
                {
                    "gfx": "gfx1201",
                    "device_packages": [
                        "rocm-sdk-device-gfx1201",
                        "amd-torch-device-gfx1201",
                        "amd-torchvision-device-gfx1201",
                    ],
                    "all_device_packages_available": True,
                }
            ],
            "packages": {
                "rocm-sdk-device-gfx1201": [{"version": "7.14.0"}],
                "amd-torch-device-gfx1201": [{"version": "2.12.0"}],
                "amd-torchvision-device-gfx1201": [{"version": "0.27.0"}],
                "apex": [{"version": "1.13.0+rocm7.14.0"}],
                "amd-torch-device-gfx12-0": [{"version": "2.12.0+rocm7.14.0"}],
            },
        }

        with TemporaryDirectory() as directory:
            path = Path(directory) / "stable-linux.json"
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            document = render_snapshots([path])

        self.assertIn("### Other observed packages", document)
        self.assertIn("| `apex` | `1.13.0+rocm7.14.0` | 1 |", document)
        self.assertIn("| `amd-torch-device-gfx12-0` | `2.12.0+rocm7.14.0` | 1 |", document)

if __name__ == "__main__":
    unittest.main()
