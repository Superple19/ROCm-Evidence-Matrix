import unittest

from rocm_evidence_matrix.legacy import build_legacy_candidates, parse_hip_sdk_gpu_support, parse_hip_sdk_release_versions, parse_legacy_artifact, parse_pytorch_windows_support


class LegacyWindowsTests(unittest.TestCase):
    def test_builds_common_candidate_from_direct_wheels(self):
        document = {
            "pytorch_windows_support": [{"rocm_version": "7.2.1", "gfx_targets": ["gfx1201"]}],
            "artifact_releases": [{
                "release_id": "7.2.1",
                "artifacts": [
                    {"package": "torch", "version": "2.9.1+rocm7.2.1", "python_tag": "cp312", "filename": "torch.whl", "url": "https://example.test/torch.whl"},
                    {"package": "torchvision", "version": "0.24.1+rocm7.2.1", "python_tag": "cp312", "filename": "torchvision.whl", "url": "https://example.test/torchvision.whl"},
                    {"package": "torchaudio", "version": "2.9.1+rocm7.2.1", "python_tag": "cp312", "filename": "torchaudio.whl", "url": "https://example.test/torchaudio.whl"},
                ],
            }],
        }
        candidates = build_legacy_candidates(document)
        self.assertEqual(candidates[0]["distribution_family"], "legacy")
        self.assertEqual(candidates[0]["platform"], "windows")
        self.assertEqual(len(candidates[0]["wheel_urls"]), 3)
        self.assertEqual(set(candidates[0]["evidence_status"]), {"artifact", "documentation", "ci", "resolver", "runtime", "hardware"})

    def test_parses_joint_hip_sdk_releases(self):
        html = """
        <table><tr><th>ROCm version</th><th>Linux support</th><th>Windows support</th></tr>
        <tr><td>5.5</td><td>✅</td><td>✅</td></tr><tr><td>5.6</td><td>✅</td><td>❌</td></tr></table>
        """

        releases = parse_hip_sdk_release_versions(html, "versions")

        self.assertTrue(releases[0]["windows_support"])
        self.assertFalse(releases[1]["windows_support"])

    def test_parses_runtime_and_sdk_status_separately(self):
        html = """
        <table><tr><th>Name</th><th>Architecture</th><th>LLVM target</th><th>Runtime</th><th>HIP SDK</th></tr>
        <tr><td>AMD Radeon RX 6600</td><td>RDNA2</td><td>gfx1032</td><td>✅</td><td>❌</td></tr></table>
        """

        products = parse_hip_sdk_gpu_support(html, "6.1", "gpus")

        self.assertEqual(products[0]["runtime_status"], "supported")
        self.assertEqual(products[0]["hip_sdk_status"], "unsupported")

    def test_parses_pytorch_support_without_inferring_artifacts(self):
        html = """
        <table><tr><th>ROCm Version</th><th>Supported Architectures</th><th>Supported AMD Radeon™ Hardware</th></tr>
        <tr><td>7.2.1*</td><td>gfx1201gfx1100</td><td>AMD Radeon RX 9070 XT AMD Radeon RX 7900 XTX</td></tr></table>
        <table><tr><th>PyTorch Version</th><th>ROCm Version</th><th>Python Version</th><th>Comments</th></tr>
        <tr><td>2.9.1</td><td>7.2.1*</td><td>3.12</td><td>Official support.</td></tr></table>
        """

        release = parse_pytorch_windows_support(html, "radeon", "support")

        self.assertEqual(release["gfx_targets"], ["gfx1100", "gfx1201"])
        self.assertEqual(len(release["products"]), 2)

    def test_parses_legacy_wheel(self):
        artifact = parse_legacy_artifact(
            "torch-2.9.1+rocm7.2.1-cp312-cp312-win_amd64.whl",
            "https://example.test/torch.whl",
        )

        self.assertEqual(artifact["package"], "torch")
        self.assertEqual(artifact["python_tag"], "cp312")


if __name__ == "__main__":
    unittest.main()
