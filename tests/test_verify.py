import unittest

from windows_rocm_matrix.verify import candidate_hash, install_arguments_for_candidate, merge_verification, normalized_command, resolved_packages
from windows_rocm_matrix.verify_matrix import matrix_jobs


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

    def test_keeps_legacy_resolver_direct_wheels_separate(self):
        candidate = {"distribution_family": "legacy", "wheel_urls": ["https://example.test/torch.whl"]}
        self.assertEqual(install_arguments_for_candidate(candidate, "gfx1201"), ["install", "--no-index", "https://example.test/torch.whl"])

    def test_candidate_hash_is_stable(self):
        candidate = {"id": "candidate", "source_id": "packages-stable", "torch_version": "2.12.0"}
        self.assertEqual(candidate_hash(candidate, "gfx1201", "cp312"), candidate_hash(candidate, "gfx1201", "cp312"))

    def test_linux_matrix_selects_known_gfx_targets(self):
        history = {"candidates": [{
            "id": "linux-candidate", "platform": "linux", "channel": "nightly",
            "distribution_family": "therock", "available_gfx_targets": ["gfx1201"],
            "python_tags": ["cp312"], "rocm_version": "7.14.0", "torch_version": "2.12.0",
            "torchvision_version": "0.27.0", "torchaudio_version": "2.11.0",
        }]}
        jobs = matrix_jobs(history, "linux", ["nightly"], gfx="gfx1201", python_tag="cp312")
        self.assertEqual([(job[1], job[2], job[3]) for job in jobs], [("gfx1201", "cp312", "manylinux_2_28_x86_64")])


if __name__ == "__main__":
    unittest.main()
