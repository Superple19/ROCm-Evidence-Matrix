import unittest

from pathlib import Path
import json
import tempfile

from windows_rocm_matrix.verify import candidate_hash, default_platform_tag, install_arguments_for_candidate, merge_verification, normalized_command, resolved_packages, update_history_evidence
from windows_rocm_matrix.verify_matrix import matrix_jobs


class VerificationTests(unittest.TestCase):
    def test_legacy_linux_matrix_verifies_without_gfx_target(self):
        candidate = {
            "id": "legacy:linux:stable:7.2:torch:vision:audio:cp312",
            "distribution_family": "legacy",
            "platform": "linux",
            "channel": "stable",
            "rocm_version": "7.2",
            "torch_version": "2.10.0",
            "torchvision_version": "0.25.0",
            "torchaudio_version": "2.9.0",
            "python_tags": ["cp312"],
            "gfx_targets": [],
            "available_gfx_targets": [],
        }
        jobs = matrix_jobs({"candidates": [candidate]}, "linux", ["stable"], python_tag="cp312")

        self.assertEqual(jobs, [(candidate, None, "cp312", "manylinux_2_28_x86_64")])

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

    def test_uses_candidate_platform_for_cross_platform_dry_run(self):
        candidate = {"id": "candidate", "platform": "linux", "source_id": "packages-stable-linux", "torch_version": "2.12.0", "torchvision_version": "0.27.0", "torchaudio_version": "2.11.0", "rocm_version": "7.14.0"}
        self.assertEqual(default_platform_tag(candidate), "manylinux_2_28_x86_64")

    def test_records_resolver_failure_on_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            path.write_text(json.dumps({"schema_version": 2, "generated_at": "2026-08-08T00:00:00Z", "sources": {"packages-stable-linux": {}}, "candidates": [{
                "id": "candidate", "distribution_family": "therock", "platform": "linux", "lifecycle": "current", "channel": "stable",
                "rocm_version": "7.14.0", "torch_version": "2.12.0", "torchvision_version": "0.27.0", "torchaudio_version": "2.11.0",
                "python_tags": ["cp312"], "gfx_support": "known", "gfx_targets": ["gfx1201"], "available_gfx_targets": ["gfx1201"],
                "artifact_available": True, "source_id": "packages-stable-linux", "first_observed_at": "2026-08-08T00:00:00Z", "last_observed_at": "2026-08-08T00:00:00Z"
            }]}), encoding="utf-8")
            self.assertTrue(update_history_evidence(path, "candidate", "failed", "gfx1201", "cp312", "manylinux_2_28_x86_64", "verification", "2026-08-08T00:00:00Z"))
            history = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(history["candidates"][0]["evidence_status"]["resolver"], "partial")
            self.assertEqual(history["candidates"][0]["resolver_results"][0]["gfx"], "gfx1201")

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
