import unittest

from windows_rocm_matrix.legacy_linux import build_legacy_linux_candidates, classify_legacy_linux_framework
from windows_rocm_matrix.resolve import resolve_candidates


class LegacyLinuxTests(unittest.TestCase):
    def test_builds_candidate_without_inventing_gfx_support(self):
        document = {
            "artifact_releases": [{
                "release_id": "7.2.1",
                "artifacts": [
                    {"filename": "torch-2.8.0+rocm7.2.1-cp311-cp311-manylinux_2_28_x86_64.whl", "url": "https://example.test/torch.whl"},
                    {"filename": "torchvision-0.23.0+rocm7.2.1-cp311-cp311-manylinux_2_28_x86_64.whl", "url": "https://example.test/torchvision.whl"},
                    {"filename": "torchaudio-2.8.0+rocm7.2.1-cp311-cp311-manylinux_2_28_x86_64.whl", "url": "https://example.test/torchaudio.whl"},
                ],
            }]
        }
        candidate = build_legacy_linux_candidates(document, [{"torch_series": "2.8", "torchvision_series": "0.23", "torchaudio_series": "2.8"}])[0]
        self.assertEqual(candidate["platform"], "linux")
        self.assertEqual(candidate["gfx_support"], "unknown")
        self.assertEqual(candidate["gfx_targets"], [])
        self.assertEqual(set(candidate["evidence_status"]), {"artifact", "documentation", "ci", "resolver", "runtime", "hardware"})

    def test_rejects_incompatible_framework_versions(self):
        document = {
            "artifact_releases": [{
                "release_id": "6.2.4",
                "artifacts": [
                    {"filename": "torch-1.13.1+rocm6.2.4-cp39-cp39-manylinux_2_28_x86_64.whl", "url": "https://example.test/torch.whl"},
                    {"filename": "torchvision-0.20.0+rocm6.2.4-cp39-cp39-manylinux_2_28_x86_64.whl", "url": "https://example.test/torchvision.whl"},
                    {"filename": "torchaudio-2.5.0+rocm6.2.4-cp39-cp39-manylinux_2_28_x86_64.whl", "url": "https://example.test/torchaudio.whl"},
                ],
            }]
        }
        compatibility = [{"torch_series": "1.13", "torchvision_series": "0.14", "torchaudio_series": "0.13"}]
        self.assertEqual(build_legacy_linux_candidates(document, compatibility), [])

    def test_quarantines_stale_incompatible_candidates(self):
        history = {"candidates": [{
            "distribution_family": "legacy", "platform": "linux",
            "torch_version": "1.13.1+rocm6.2.4", "torchvision_version": "0.20.0+rocm6.2.4", "torchaudio_version": "2.5.0+rocm6.2.4",
        }]}
        classify_legacy_linux_framework(history, [{"torch_series": "1.13", "torchvision_series": "0.14", "torchaudio_series": "0.13"}])
        self.assertEqual(history["candidates"][0]["framework_compatibility"], "incompatible")

    def test_resolves_linux_candidate_without_gfx_filter(self):
        candidate = {
            "id": "legacy:linux:stable:7.2.1:torch:vision:audio:cp311",
            "distribution_family": "legacy",
            "platform": "linux",
            "channel": "stable",
            "rocm_version": "7.2.1",
            "torch_version": "2.8.0+rocm7.2.1",
            "torchvision_version": "0.23.0+rocm7.2.1",
            "torchaudio_version": "2.8.0+rocm7.2.1",
            "python_tags": ["cp311"],
            "gfx_support": "unknown",
            "gfx_targets": [],
            "available_gfx_targets": [],
            "artifact_available": True,
            "source_id": "legacy-linux-artifacts",
            "framework_compatibility": "verified",
        }
        self.assertEqual(resolve_candidates({"candidates": [candidate]}, None, platform="linux"), [candidate])


if __name__ == "__main__":
    unittest.main()
