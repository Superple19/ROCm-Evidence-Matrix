import unittest

from windows_rocm_matrix.history import build_history_observations, merge_history
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
            "rocm-sdk-device-gfx1201": [artifact("rocm-sdk-device-gfx1201", "10.1.0a20260807", "py3")],
            "amd-torch-device-gfx1201": [artifact("amd-torch-device-gfx1201", "2.14.0a0+rocm10.1.0a20260807")],
            "amd-torchvision-device-gfx1201": [artifact("amd-torchvision-device-gfx1201", "0.29.0a0+rocm10.1.0a20260807")],
        }
        rules = [{"torch_series": "2.14", "torchaudio_series": "2.11", "torchvision_series": "0.29"}]

        candidates = build_history_observations(
            {"id": "nightly", "channel": "nightly"}, ["gfx1201"], packages, rules
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["python_tags"], ["cp312"])

    def test_retains_candidate_when_artifact_disappears(self):
        observation = {
            "id": "candidate",
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

    def test_resolves_and_formats_install_command(self):
        candidate = {
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


if __name__ == "__main__":
    unittest.main()
