import unittest
from unittest.mock import patch

from pathlib import Path
import json
import tempfile

from windows_rocm_matrix.verify import candidate_hash, combined_process_output, default_platform_tag, error_summary, install_arguments_for_candidate, merge_verification, normalized_command, resolved_packages, update_history_evidence, virtualenv_python
from windows_rocm_matrix.verify_matrix import DEFAULT_CHANNELS, completed_job_keys, matrix_exit_code, matrix_job_key, matrix_jobs, parse_args as matrix_parse_args
from windows_rocm_matrix.resolve import parse_args


class VerificationTests(unittest.TestCase):
    def test_resolver_defaults_to_host_platform(self):
        with patch("windows_rocm_matrix.resolve.host_platform", return_value="linux"):
            self.assertEqual(parse_args([]).platform, "linux")
        with patch("windows_rocm_matrix.verify_matrix.host_platform", return_value="windows"):
            self.assertEqual(matrix_parse_args([]).platform, "windows")

    def test_single_verifier_supports_family_and_failed_retries(self):
        from windows_rocm_matrix.verify import parse_args as verify_parse_args

        args = verify_parse_args(["--distribution-family", "legacy", "--include-failed"])
        self.assertEqual(args.distribution_family, "legacy")
        self.assertTrue(args.include_failed)

    def test_matrix_exit_code_distinguishes_failed_and_not_applicable(self):
        self.assertEqual(matrix_exit_code([{"result": "passed"}, {"result": "not_applicable"}]), 0)
        self.assertEqual(matrix_exit_code([{"result": "not_applicable"}, {"result": "failed"}]), 1)

    def test_matrix_rejects_nonpositive_worker_count(self):
        self.assertEqual(matrix_parse_args(["--workers", "0"]).workers, 0)

    def test_matrix_defaults_to_all_channels(self):
        self.assertEqual(DEFAULT_CHANNELS, ("stable", "nightly", "staging"))
        self.assertTrue(matrix_parse_args(["--resume"]).resume)
        self.assertEqual(matrix_parse_args(["--cache-dir", "cache"]).cache_dir, "cache")
        self.assertEqual(matrix_parse_args(["--workers", "3"]).workers, 3)

    def test_resume_skips_existing_candidate_hash(self):
        candidate = {"id": "candidate", "distribution_family": "therock", "platform": "windows", "source_id": "packages-stable", "rocm_version": "7.14.0", "torch_version": "2.12.0", "torchvision_version": "0.27.0", "torchaudio_version": "2.11.0"}
        job = (candidate, "gfx1201", "cp312", "win_amd64")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resolver.json"
            path.write_text(json.dumps({"verifications": [{"candidate_hash": matrix_job_key(job)[0], "gfx": "gfx1201", "python_tag": "cp312", "platform_tag": "win_amd64"}]}), encoding="utf-8")
            self.assertIn(matrix_job_key(job)[0], {item[0] for item in completed_job_keys(path)})

    def test_resume_reads_tracked_history_evidence(self):
        candidate = {"id": "candidate", "distribution_family": "therock", "platform": "windows", "source_id": "packages-stable", "rocm_version": "7.14.0", "torch_version": "2.12.0", "torchvision_version": "0.27.0", "torchaudio_version": "2.11.0"}
        job = (candidate, "gfx1201", "cp312", "win_amd64")
        history = {"candidates": [{"resolver_results": [{"candidate_hash": matrix_job_key(job)[0], "gfx": "gfx1201", "python_tag": "cp312", "platform_tag": "win_amd64"}]}]}
        with tempfile.TemporaryDirectory() as directory:
            self.assertIn(matrix_job_key(job)[0], {item[0] for item in completed_job_keys(Path(directory) / "missing.json", history)})

    def test_matrix_includes_candidates_with_previous_failed_status(self):
        candidate = {
            "id": "failed", "distribution_family": "therock", "platform": "linux", "channel": "stable", "evidence_status": {"resolver": "resolver_failed"},
            "available_gfx_targets": ["gfx1201"], "gfx_targets": ["gfx1201"], "python_tags": ["cp312"], "rocm_version": "7.14.0", "torch_version": "2.12.0", "torchvision_version": "0.27.0", "torchaudio_version": "2.11.0",
        }
        self.assertEqual(len(matrix_jobs({"candidates": [candidate]}, "linux", ["stable"], gfx="gfx1201", python_tag="cp312")), 1)

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
            "framework_compatibility": "verified",
        }
        jobs = matrix_jobs({"candidates": [candidate]}, "linux", ["stable"], python_tag="cp312")

        self.assertEqual(jobs, [(candidate, None, "cp312", "manylinux_2_28_x86_64")])

    def test_matrix_filters_distribution_family(self):
        candidate = {
            "id": "legacy:linux:stable:7.2:torch:vision:audio:cp312",
            "distribution_family": "legacy", "platform": "linux", "channel": "stable",
            "rocm_version": "7.2", "torch_version": "2.10.0", "torchvision_version": "0.25.0", "torchaudio_version": "2.9.0",
            "python_tags": ["cp312"], "gfx_targets": [], "available_gfx_targets": [], "framework_compatibility": "verified",
        }
        self.assertEqual(len(matrix_jobs({"candidates": [candidate]}, "linux", ["stable"], distribution_family="legacy")), 1)

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

    def test_normalizes_timeout_output_bytes(self):
        output = combined_process_output(b"first", "second")
        self.assertEqual(error_summary(output), "first\nsecond")

    def test_appends_verification_evidence(self):
        record = {"id": "one", "observed_at": "2026-08-07T00:00:00Z"}

        document = merge_verification(None, record)

        self.assertEqual(document["verifications"], [record])

    def test_keeps_legacy_resolver_direct_wheels_separate(self):
        candidate = {"distribution_family": "legacy", "wheel_urls": ["https://example.test/torch.whl"]}
        self.assertEqual(install_arguments_for_candidate(candidate, "gfx1201"), ["install", "--index-url", "https://pypi.org/simple", "https://example.test/torch.whl"])

    def test_candidate_hash_is_stable(self):
        candidate = {"id": "candidate", "source_id": "packages-stable", "torch_version": "2.12.0"}
        self.assertEqual(candidate_hash(candidate, "gfx1201", "cp312"), candidate_hash(candidate, "gfx1201", "cp312"))

    def test_uses_candidate_platform_for_cross_platform_dry_run(self):
        candidate = {"id": "candidate", "platform": "linux", "source_id": "packages-stable-linux", "torch_version": "2.12.0", "torchvision_version": "0.27.0", "torchaudio_version": "2.11.0", "rocm_version": "7.14.0"}
        self.assertEqual(default_platform_tag(candidate), "manylinux_2_28_x86_64")

    def test_cross_platform_resolver_uses_target_platform_tag(self):
        candidate = {"id": "candidate", "distribution_family": "legacy", "platform": "linux", "source_id": "legacy-linux-artifacts", "wheel_urls": ["https://example.test/torch.whl"], "torch_version": "2.12.0", "torchvision_version": "0.27.0", "torchaudio_version": "2.11.0", "rocm_version": "7.14.0"}
        self.assertEqual(default_platform_tag(candidate), "manylinux_2_28_x86_64")
        command = normalized_command(candidate, None, "cp312", "manylinux_2_28_x86_64")
        self.assertIn("manylinux_2_28_x86_64", command)

        linux_wheel = {**candidate, "wheel_urls": ["https://example.test/torch-cp312-cp312-linux_x86_64.whl"]}
        self.assertEqual(default_platform_tag(linux_wheel), "linux_x86_64")

    def test_uses_host_virtualenv_layout(self):
        self.assertEqual(virtualenv_python("/tmp/env", "nt").as_posix(), "/tmp/env/Scripts/python.exe")
        self.assertEqual(virtualenv_python("/tmp/env", "posix").as_posix(), "/tmp/env/bin/python")

    def test_repeated_resolver_attempts_are_append_only(self):
        passed = {"id": "candidate:attempt-a", "observed_at": "2026-08-08T00:00:00Z", "result": "passed"}
        failed = {"id": "candidate:attempt-b", "observed_at": "2026-08-08T00:01:00Z", "result": "failed"}
        document = merge_verification({"verifications": [passed]}, failed)
        self.assertEqual([item["result"] for item in document["verifications"]], ["passed", "failed"])

    def test_candidate_resolver_results_are_append_only_for_same_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            path.write_text(json.dumps({"schema_version": 2, "generated_at": "2026-08-08T00:00:00Z", "sources": {"packages-stable": {}}, "candidates": [{
                "id": "candidate", "distribution_family": "therock", "platform": "linux", "lifecycle": "current", "channel": "stable",
                "rocm_version": "7.14.0", "torch_version": "2.12.0", "torchvision_version": "0.27.0", "torchaudio_version": "2.11.0",
                "python_tags": ["cp312"], "gfx_support": "known", "gfx_targets": ["gfx1201"], "available_gfx_targets": ["gfx1201"],
                "artifact_available": True, "source_id": "packages-stable", "first_observed_at": "2026-08-08T00:00:00Z", "last_observed_at": "2026-08-08T00:00:00Z"
            }]}), encoding="utf-8")
            update_history_evidence(path, "candidate", "failed", "gfx1201", "cp312", "manylinux_2_28_x86_64", "attempt-a", "2026-08-08T00:00:00Z", "failure", "linux", ["python", "-m", "pip", "install"], 1)
            update_history_evidence(path, "candidate", "passed", "gfx1201", "cp312", "manylinux_2_28_x86_64", "attempt-b", "2026-08-08T00:01:00Z")
            history = json.loads(path.read_text(encoding="utf-8"))
            results = history["candidates"][0]["resolver_results"]
            self.assertEqual([item["verification_id"] for item in results], ["attempt-a", "attempt-b"])
            self.assertTrue(all(len(item["candidate_hash"]) == 64 for item in results))
            self.assertEqual(results[0]["candidate_id"], "candidate")
            self.assertEqual(results[0]["platform"], "linux")
            self.assertEqual(results[0]["host_platform"], "linux")
            self.assertEqual(results[0]["command"], ["python", "-m", "pip", "install"])
            self.assertEqual(results[0]["exit_code"], 1)
            self.assertEqual(history["candidates"][0]["evidence_status"]["resolver"], "partial")

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
            self.assertEqual(history["candidates"][0]["evidence_status"]["resolver"], "resolver_failed")
            self.assertEqual(history["candidates"][0]["evidence_status"]["artifact"], "artifact_available")
            self.assertEqual(history["candidates"][0]["resolver_results"][0]["gfx"], "gfx1201")

    def test_status_promotion_requires_verification_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            path.write_text(json.dumps({"schema_version": 2, "generated_at": "2026-08-08T00:00:00Z", "sources": {}, "candidates": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                update_history_evidence(path, "missing", "passed")

    def test_not_applicable_does_not_clear_stale_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            path.write_text(json.dumps({"schema_version": 2, "generated_at": "2026-08-08T00:00:00Z", "sources": {"packages-stable": {}}, "candidates": [{
                "id": "candidate", "distribution_family": "therock", "platform": "linux", "lifecycle": "current", "channel": "stable",
                "rocm_version": "7.14.0", "torch_version": "2.12.0", "torchvision_version": "0.27.0", "torchaudio_version": "2.11.0",
                "python_tags": ["cp312"], "gfx_support": "known", "gfx_targets": ["gfx1201"], "available_gfx_targets": ["gfx1201"],
                "artifact_available": True, "source_id": "packages-stable", "first_observed_at": "2026-08-08T00:00:00Z", "last_observed_at": "2026-08-08T00:00:00Z"
            }]}), encoding="utf-8")
            update_history_evidence(path, "candidate", "failed", "gfx1201", "cp312", "manylinux_2_28_x86_64", "failed", "2026-08-08T00:00:00Z")
            update_history_evidence(path, "candidate", "not_applicable", "gfx1201", "cp312", "manylinux_2_28_x86_64", "n/a", "2026-08-08T00:01:00Z")
            history = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(history["candidates"][0]["evidence_status"]["artifact"], "artifact_available")

    def test_linux_matrix_selects_known_gfx_targets(self):
        history = {"candidates": [{
            "id": "linux-candidate", "platform": "linux", "channel": "nightly",
            "distribution_family": "therock", "available_gfx_targets": ["gfx1201"],
            "python_tags": ["cp312"], "rocm_version": "7.14.0", "torch_version": "2.12.0",
            "torchvision_version": "0.27.0", "torchaudio_version": "2.11.0",
        }]}
        jobs = matrix_jobs(history, "linux", ["nightly"], gfx="gfx1201", python_tag="cp312")
        self.assertEqual([(job[1], job[2], job[3]) for job in jobs], [("gfx1201", "cp312", "manylinux_2_28_x86_64")])

    def test_matrix_uses_one_representative_candidate_by_default(self):
        candidates = []
        for rocm, torch in (("7.14.0", "2.12.0"), ("7.13.0", "2.11.0")):
            candidates.append({
                "id": rocm, "platform": "linux", "channel": "stable", "distribution_family": "therock",
                "available_gfx_targets": ["gfx1201", "gfx1100"], "python_tags": ["cp312"],
                "rocm_version": rocm, "torch_version": torch, "torchvision_version": "0.27.0", "torchaudio_version": "2.11.0",
            })
        jobs = matrix_jobs({"candidates": candidates}, "linux", ["stable"])
        self.assertEqual([(job[0]["rocm_version"], job[1]) for job in jobs], [("7.14.0", "gfx1201"), ("7.14.0", "gfx1100")])

    def test_matrix_deduplicates_same_package_identity_across_candidates(self):
        candidates = []
        for python_tags in (("cp310", "cp311"), ("cp310",)):
            candidates.append({
                "id": f"candidate:{','.join(python_tags)}", "platform": "linux", "channel": "nightly",
                "distribution_family": "therock", "source_id": "packages-nightly-linux",
                "available_gfx_targets": ["gfx1201"], "python_tags": list(python_tags),
                "rocm_version": "7.14.0a20260527", "torch_version": "2.12.0+rocm7.14.0a20260527",
                "torchvision_version": "0.27.0+rocm7.14.0a20260527", "torchaudio_version": "2.11.0+rocm7.14.0a20260527",
            })
        jobs = matrix_jobs({"candidates": candidates}, "linux", ["nightly"], gfx="gfx1201", all_candidates=True)
        self.assertEqual([(job[2]) for job in jobs], ["cp310", "cp311"])


if __name__ == "__main__":
    unittest.main()
