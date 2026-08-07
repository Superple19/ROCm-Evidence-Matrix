import unittest

from windows_rocm_matrix.verify import merge_verification, normalized_command, resolved_packages


class VerificationTests(unittest.TestCase):
    def test_builds_safe_dry_run_command(self):
        candidate = {
            "id": "candidate",
            "source_id": "packages-stable",
            "rocm_version": "7.14.0",
            "torch_version": "2.12.0+rocm7.14.0",
            "torchvision_version": "0.27.0+rocm7.14.0",
            "torchaudio_version": "2.11.0+rocm7.14.0",
        }

        command = normalized_command(candidate, "gfx1201")

        self.assertIn("--dry-run", command)
        self.assertIn("--ignore-installed", command)
        self.assertIn("torch[device-gfx1201]==2.12.0+rocm7.14.0", command)

    def test_normalizes_pip_report(self):
        report = {
            "install": [
                {
                    "metadata": {"name": "torch", "version": "2.12.0+rocm7.14.0"},
                    "download_info": {
                        "url": "https://example.test/torch.whl",
                        "archive_info": {"hashes": {"sha256": "abc"}},
                    },
                }
            ]
        }

        packages = resolved_packages(report)

        self.assertEqual(packages[0]["name"], "torch")
        self.assertEqual(packages[0]["sha256"], "abc")

    def test_appends_verification_evidence(self):
        record = {"id": "one", "observed_at": "2026-08-07T00:00:00Z"}

        document = merge_verification(None, record)

        self.assertEqual(document["verifications"], [record])


if __name__ == "__main__":
    unittest.main()
