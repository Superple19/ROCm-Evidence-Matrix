import unittest
from pathlib import Path

from windows_rocm_matrix.profile import load_profile, validate_profile


class ProfileTests(unittest.TestCase):
    def test_loads_comfyui_baseline_profile(self):
        profile = load_profile(Path(__file__).parents[1] / "profiles" / "comfyui" / "profile.json")
        self.assertEqual(profile["id"], "comfyui")
        self.assertEqual(profile["metadata"]["domain"], "generation")
        self.assertEqual(
            {item["id"] for item in profile["constraints"]},
            {"rocm-package-candidate", "torch-rocm", "rocm-channel", "supported-platform", "platform-package-layout", "python-tag", "gfx-target"},
        )

    def test_supports_constraint_kinds_and_relationships(self):
        profile = {
            "schema_version": 1,
            "id": "example",
            "name": "Example profile",
            "profile_kind": "application",
            "evidence_refs": ["resolver:one"],
            "constraints": [
                {"id": "torch", "kind": "framework", "relationship": "required", "name": "Torch", "value": ">=2.0", "claim_status": "verified", "evidence_refs": ["resolver:one"]},
                {"id": "extension", "kind": "extension", "relationship": "optional", "name": "AITER", "value": "enabled", "claim_status": "documented", "evidence_refs": []},
                {"id": "option", "kind": "option", "relationship": "conflicting", "name": "legacy backend", "value": "disabled", "claim_status": "unverified", "evidence_refs": []},
            ],
        }
        self.assertIs(validate_profile(profile), profile)

    def test_verified_constraint_requires_evidence(self):
        profile = {"schema_version": 1, "id": "example", "name": "Example", "profile_kind": "runtime", "evidence_refs": [], "constraints": [{"id": "runtime", "kind": "runtime", "relationship": "required", "name": "ROCm", "value": "available", "claim_status": "verified", "evidence_refs": []}]}
        with self.assertRaisesRegex(ValueError, "lacks evidence"):
            validate_profile(profile)


if __name__ == "__main__":
    unittest.main()
