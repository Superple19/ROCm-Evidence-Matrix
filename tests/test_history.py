import unittest

from rocm_evidence_matrix.history import build_history_observations, merge_history, render_history


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
            "rocm-sdk-device-gfx1201": [artifact("rocm-sdk-device-gfx1201", "10.1.0a20260807", "py3")],
            "amd-torch-device-gfx1201": [artifact("amd-torch-device-gfx1201", "2.14.0a0+rocm10.1.0a20260807")],
            "amd-torchvision-device-gfx1201": [artifact("amd-torchvision-device-gfx1201", "0.29.0a0+rocm10.1.0a20260807")],
        }
        rules = [{"torch_series": "2.14", "torchaudio_series": "2.11", "torchvision_series": "0.29"}]

        candidates = build_history_observations(
            {"id": "nightly", "channel": "nightly", "platform": "windows"},
            ["gfx1201"],
            packages,
            rules,
            "therock",
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["python_tags"], ["cp312"])

    def test_rolling_source_replaces_previous_candidates(self):
        old = {
            "id": "old-nightly",
            "distribution_family": "therock",
            "channel": "nightly",
            "rocm_version": "10.1.0a20260807",
            "torch_version": "2.14.0",
            "torchvision_version": "0.29.0",
            "torchaudio_version": "2.11.0",
            "python_tags": ["cp312"],
            "gfx_targets": ["gfx1201"],
            "source_id": "packages-nightly",
        }
        new = {**old, "id": "new-nightly", "rocm_version": "10.1.0a20260808"}
        history = merge_history(None, [old], {"packages-nightly": {}}, "2026-08-07T00:00:00Z", {"packages-nightly"})
        history = merge_history(
            history,
            [new],
            {"packages-nightly": {}},
            "2026-08-08T00:00:00Z",
            {"packages-nightly"},
            replace_source_ids={"packages-nightly"},
        )

        self.assertEqual([item["id"] for item in history["candidates"]], ["new-nightly"])

    def test_lifecycle_is_scoped_to_channel(self):
        base = {
            "distribution_family": "therock",
            "platform": "windows",
            "channel": "stable",
            "torch_version": "2.12.0",
            "torchvision_version": "0.27.0",
            "torchaudio_version": "2.11.0",
            "python_tags": ["cp312"],
            "gfx_targets": ["gfx1201"],
            "source_id": "packages-stable",
        }
        history = merge_history(
            None,
            [{**base, "id": "old", "rocm_version": "7.13.0"}, {**base, "id": "new", "rocm_version": "7.14.0"}],
            {"packages-stable": {}},
            "2026-08-08T00:00:00Z",
            {"packages-stable"},
        )

        lifecycle = {item["id"]: item["lifecycle"] for item in history["candidates"]}
        self.assertEqual(lifecycle, {"old": "historical", "new": "current"})

    def test_render_labels_unknown_gfx_support(self):
        document = render_history(
            {
                "candidates": [
                    {
                        "distribution_family": "legacy",
                        "platform": "linux",
                        "channel": "stable",
                        "lifecycle": "current",
                        "rocm_version": "7.2.4",
                        "gfx_support": "unknown",
                        "gfx_targets": [],
                        "available_gfx_targets": [],
                        "python_tags": ["cp312"],
                        "evidence_status": {"artifact": "artifact_available"},
                    }
                ]
            }
        )

        self.assertIn("| legacy | linux | stable | current | `7.2.4` |", document)


if __name__ == "__main__":
    unittest.main()
