import unittest

from windows_rocm_matrix.history import attach_therock_ci_evidence, build_history_observations, candidate_id_for, execution_evidence_errors, merge_history, render_history
from windows_rocm_matrix.resolve import install_command, resolve_candidates


def artifact(package, version, python_tag="cp312"):
    normalized = package.replace("-", "_")
    return {
        "filename": f"{normalized}-{version}-{python_tag}-{python_tag}-win_amd64.whl",
        "version": version,
        "python_tag": python_tag,
        "abi_tag": python_tag,
        "platform_tag": "win_amd64",
        "url": f"https://example.test/{package}/{version}.whl",
    }


class HistoryTests(unittest.TestCase):
    def test_builds_candidate_from_matching_rocm_versions(self):
        packages = {
            "rocm": [artifact("rocm", "10.1.0a20260807", "source")],
            "rocm-sdk-core": [artifact("rocm-sdk-core", "10.1.0a20260807", "py3")],
            "rocm-sdk-libraries": [artifact("rocm-sdk-libraries", "10.1.0a20260807", "py3")],
            "torch": [artifact("torch", "2.14.0a0+rocm10.1.0a20260807")],
            "torchvision": [artifact("torchvision", "0.29.0a0+rocm10.1.0a20260807")],
            "torchaudio": [artifact("torchaudio", "2.11.0+rocm10.1.0a20260807")],
            "triton": [artifact("triton", "3.6.0+rocm10.1.0a20260807")],
            "rocm-sdk-device-gfx1201": [artifact("rocm-sdk-device-gfx1201", "10.1.0a20260807", "py3")],
            "amd-torch-device-gfx1201": [artifact("amd-torch-device-gfx1201", "2.14.0a0+rocm10.1.0a20260807")],
            "amd-torchvision-device-gfx1201": [artifact("amd-torchvision-device-gfx1201", "0.29.0a0+rocm10.1.0a20260807")],
        }
        rules = [{"torch_series": "2.14", "torchaudio_series": "2.11", "torchvision_series": "0.29"}]

        candidates = build_history_observations(
            {"id": "nightly", "channel": "nightly"}, ["gfx1201"], packages, rules, "therock"
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["distribution_family"], "therock")
        self.assertEqual(candidates[0]["python_tags"], ["cp312"])
        self.assertIsNone(candidates[0]["triton_version"])

    def test_retains_candidate_when_artifact_disappears(self):
        observation = {
            "id": "candidate",
            "distribution_family": "therock",
            "channel": "stable",
            "rocm_version": "7.14.0",
            "torch_version": "2.12.0+rocm7.14.0",
            "torchvision_version": "0.27.0+rocm7.14.0",
            "torchaudio_version": "2.11.0+rocm7.14.0",
            "python_tags": ["cp312"],
            "gfx_targets": ["gfx1201"],
            "source_id": "packages-stable",
        }
        first = merge_history(None, [observation], {"packages-stable": {}}, "2026-08-07T00:00:00Z", {"packages-stable"})
        second = merge_history(first, [], {"packages-stable": {}}, "2026-08-08T00:00:00Z", {"packages-stable"})

        self.assertFalse(second["candidates"][0]["artifact_available"])
        self.assertEqual(second["candidates"][0]["gfx_targets"], ["gfx1201"])

    def test_generated_at_does_not_regress_during_offline_merge(self):
        existing = {"schema_version": 2, "generated_at": "2026-08-08T14:13:02Z", "sources": {}, "candidates": []}
        merged = merge_history(existing, [], {}, "2026-08-08T10:15:14Z", set())
        self.assertEqual(merged["generated_at"], "2026-08-08T14:13:02Z")

    def test_scoped_gfx_merge_preserves_other_available_targets(self):
        observation = {
            "id": "candidate",
            "distribution_family": "therock",
            "platform": "windows",
            "channel": "stable",
            "rocm_version": "7.14.0",
            "torch_version": "2.12.0+rocm7.14.0",
            "torchvision_version": "0.27.0+rocm7.14.0",
            "torchaudio_version": "2.11.0+rocm7.14.0",
            "python_tags": ["cp312"],
            "gfx_targets": ["gfx1100", "gfx1201"],
            "source_id": "packages-stable",
        }
        observation["id"] = candidate_id_for(
            observation["distribution_family"], observation["platform"], observation["channel"],
            observation["rocm_version"], observation["torch_version"], observation["torchvision_version"],
            observation["torchaudio_version"], observation["python_tags"],
        )
        first = merge_history(None, [observation], {"packages-stable": {}}, "2026-08-07T00:00:00Z", {"packages-stable"})
        scoped = {**observation, "gfx_targets": ["gfx1201"]}
        second = merge_history(first, [scoped], {"packages-stable": {}}, "2026-08-08T00:00:00Z", {"packages-stable"}, ["gfx1201"])
        self.assertEqual(second["candidates"][0]["available_gfx_targets"], ["gfx1100", "gfx1201"])

    def test_computes_lifecycle_within_distribution_and_channel(self):
        base = {
            "distribution_family": "therock",
            "channel": "nightly",
            "torch_version": "2.14.0",
            "torchvision_version": "0.29.0",
            "torchaudio_version": "2.11.0",
            "python_tags": ["cp312"],
            "gfx_targets": ["gfx1201"],
            "source_id": "packages-nightly",
        }
        older = {**base, "id": "older", "rocm_version": "10.0.0"}
        newer = {**base, "id": "newer", "rocm_version": "10.1.0"}

        history = merge_history(None, [older, newer], {"packages-nightly": {}}, "2026-08-07T00:00:00Z", {"packages-nightly"})
        by_version = {candidate["rocm_version"]: candidate for candidate in history["candidates"]}

        self.assertEqual(by_version["10.0.0"]["lifecycle"], "historical")
        self.assertEqual(by_version["10.1.0"]["lifecycle"], "current")

    def test_lifecycle_is_scoped_to_platform(self):
        base = {
            "distribution_family": "therock",
            "channel": "stable",
            "torch_version": "2.12.0",
            "torchvision_version": "0.27.0",
            "torchaudio_version": "2.11.0",
            "python_tags": ["cp312"],
            "gfx_targets": ["gfx1201"],
            "source_id": "packages-stable",
        }
        observations = [
            {**base, "id": "windows", "platform": "windows", "rocm_version": "7.14.0"},
            {**base, "id": "linux", "platform": "linux", "rocm_version": "7.2.4"},
        ]

        history = merge_history(None, observations, {"packages-stable": {}}, "2026-08-07T00:00:00Z", {"packages-stable"})
        self.assertEqual({item["platform"]: item["lifecycle"] for item in history["candidates"]}, {"windows": "current", "linux": "current"})

    def test_migrates_existing_therock_history(self):
        existing = {
            "schema_version": 1,
            "sources": {},
            "candidates": [
                {
                    "id": "nightly:10.0.0:2.14.0:0.29.0:2.11.0:cp312",
                    "channel": "nightly",
                    "rocm_version": "10.0.0",
                    "torch_version": "2.14.0",
                    "torchvision_version": "0.29.0",
                    "torchaudio_version": "2.11.0",
                    "python_tags": ["cp312"],
                    "gfx_targets": ["gfx1201"],
                    "available_gfx_targets": ["gfx1201"],
                    "artifact_available": True,
                    "source_id": "packages-nightly",
                    "first_observed_at": "2026-08-07T00:00:00Z",
                    "last_observed_at": "2026-08-07T00:00:00Z",
                }
            ],
        }

        history = merge_history(existing, [], {}, "2026-08-08T00:00:00Z", set())

        self.assertEqual(history["schema_version"], 2)
        self.assertEqual(history["candidates"][0]["distribution_family"], "therock")
        self.assertEqual(history["candidates"][0]["lifecycle"], "current")
        self.assertTrue(history["candidates"][0]["id"].startswith("therock:"))

    def test_resolves_and_formats_install_command(self):
        candidate = {
            "distribution_family": "therock",
            "lifecycle": "current",
            "channel": "stable",
            "rocm_version": "7.14.0",
            "torch_version": "2.12.0+rocm7.14.0",
            "torchvision_version": "0.27.0+rocm7.14.0",
            "torchaudio_version": "2.11.0+rocm7.14.0",
            "python_tags": ["cp312"],
            "gfx_targets": ["gfx1201"],
            "available_gfx_targets": ["gfx1201"],
            "source_id": "packages-stable",
        }
        history = {"candidates": [candidate]}

        matches = resolve_candidates(history, "gfx1201", channel="stable", python_tag="3.12")

        self.assertEqual(matches, [candidate])
        self.assertIn('"torch[device-gfx1201]==2.12.0+rocm7.14.0"', install_command(candidate, "gfx1201"))

    def test_excludes_failed_and_stale_candidates_by_default(self):
        base = {
            "distribution_family": "therock", "platform": "linux", "channel": "stable",
            "rocm_version": "7.14.0", "torch_version": "2.12.0", "torchvision_version": "0.27.0", "torchaudio_version": "2.11.0",
            "python_tags": ["cp312"], "gfx_targets": ["gfx1201"], "available_gfx_targets": ["gfx1201"],
        }
        failed = {**base, "id": "failed", "evidence_status": {"artifact": "artifact_available", "resolver": "resolver_failed"}}
        stale = {**base, "id": "stale", "evidence_status": {"artifact": "artifact_stale", "resolver": "not_collected"}}
        history = {"candidates": [failed, stale]}

        self.assertEqual(resolve_candidates(history, "gfx1201"), [])
        self.assertEqual(len(resolve_candidates(history, "gfx1201", include_failed=True)), 2)

    def test_history_render_labels_unknown_gfx_support(self):
        candidate = {
            "distribution_family": "legacy", "platform": "linux", "channel": "stable", "lifecycle": "current",
            "rocm_version": "7.2.4", "gfx_support": "unknown", "gfx_targets": [], "available_gfx_targets": [],
            "python_tags": ["cp312"], "evidence_status": {"artifact": "artifact_available"},
        }
        document = render_history({"candidates": [candidate]})
        self.assertIn("| legacy | linux | stable | current | `7.2.4` | not observed | 1 | unknown |", document)

    def test_execution_evidence_requires_candidate_match(self):
        candidate = {
            "platform": "windows", "gfx_support": "known", "gfx_targets": ["gfx1201"],
            "torch_version": "2.12.0", "hip_version": None,
        }
        record = {
            "os": "windows", "gfx": "gfx1201", "torch_version": "2.12.0", "hip_version": None,
            "result": "passed", "devices": [{"gfx": "gfx1201"}],
        }
        self.assertEqual(execution_evidence_errors(candidate, record, "runtime"), [])
        self.assertTrue(execution_evidence_errors(candidate, {**record, "torch_version": "2.13.0"}, "runtime"))
        self.assertTrue(execution_evidence_errors(candidate, {**record, "os": "linux"}, "runtime"))

    def test_attaches_ci_evidence_with_gfx_platform_scope(self):
        candidate = {
            "id": "therock:stable:candidate",
            "distribution_family": "therock",
            "platform": "windows",
            "lifecycle": "current",
            "gfx_targets": ["gfx1201"],
            "evidence_status": {"artifact": "artifact_available", "resolver": "not_collected", "runtime": "not_collected", "hardware": "not_collected"},
        }
        evidence = {"executions": [{"id": "github:1", "platform": "windows", "targets": ["gfx1201"], "observations": [{"state": "success"}]}]}

        attach_therock_ci_evidence({"candidates": [candidate]}, evidence)

        self.assertEqual(candidate["evidence_status"]["ci"], "ci_verified")
        self.assertEqual(candidate["ci_evidence_refs"], ["github:1"])
        self.assertEqual(candidate["ci_evidence_scope"], "gfx_platform")

    def test_configured_or_non_windows_coverage_does_not_verify_candidate(self):
        candidate = {
            "id": "therock:stable:candidate",
            "distribution_family": "therock",
            "platform": "windows",
            "lifecycle": "current",
            "gfx_targets": ["gfx1201"],
            "evidence_status": {"artifact": "artifact_available", "resolver": "not_collected", "runtime": "not_collected", "hardware": "not_collected", "ci": "not_collected"},
        }
        coverage_only = {"entries": [{"configured_targets": ["gfx1201"], "platform": "windows"}]}
        attach_therock_ci_evidence({"candidates": [candidate]}, coverage_only)
        self.assertEqual(candidate["evidence_status"]["ci"], "not_collected")

        linux_execution = {"executions": [{"id": "linux:1", "platform": "linux", "targets": ["gfx1201"], "observations": [{"state": "success"}]}]}
        attach_therock_ci_evidence({"candidates": [candidate]}, linux_execution)
        self.assertEqual(candidate["evidence_status"]["ci"], "not_collected")


if __name__ == "__main__":
    unittest.main()
