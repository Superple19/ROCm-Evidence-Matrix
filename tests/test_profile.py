import unittest
from pathlib import Path

from rocm_evidence_matrix.profile import compatible_extensions, load_profile, separate_profile_results, validate_extension_selection, validate_profile


class ProfileTests(unittest.TestCase):
    def test_loads_comfyui_baseline_profile(self):
        profile = load_profile(Path(__file__).parents[1] / "profiles" / "comfyui" / "profile.json")
        self.assertEqual(profile["id"], "comfyui")
        self.assertEqual(profile["metadata"]["domain"], "generation")
        self.assertEqual(
            {item["id"] for item in profile["constraints"]},
            {"rocm-package-candidate", "torch-rocm", "rocm-channel", "supported-platform", "platform-package-layout", "python-tag", "gfx-target", "disable-cudnn", "pinned-memory"},
        )
        options = {item["id"]: item for item in profile["constraints"] if item["kind"] == "option"}
        self.assertEqual(options["disable-cudnn"]["relationship"], "required")
        self.assertEqual(options["pinned-memory"]["relationship"], "optional")

    def test_comfyui_extensions_are_optional_and_not_auto_verified(self):
        root = Path(__file__).parents[1] / "profiles" / "comfyui" / "extensions"
        profiles = [load_profile(path) for path in sorted(root.glob("*.json"))]
        self.assertEqual({profile["metadata"]["package_name"] for profile in profiles}, {"bitsandbytes", "aiter", "flash-attn", "sageattention", "triton"})
        for profile in profiles:
            constraint = profile["constraints"][0]
            self.assertEqual(constraint["relationship"], "optional")
            self.assertEqual(constraint["claim_status"], "unverified")
            self.assertFalse(profile["metadata"]["core_required"])

        self.assertEqual(compatible_extensions(profiles), [])
        with self.assertRaisesRegex(ValueError, "Unverified extension"):
            validate_extension_selection(profiles)

    def test_extension_results_do_not_change_core_result(self):
        result = separate_profile_results("passed", [{"id": "aiter", "result": "failed"}])
        self.assertEqual(result["core"], "passed")
        self.assertEqual(result["extensions"][0]["result"], "failed")

    def test_conflicting_extensions_are_rejected(self):
        def extension(identifier, conflicts_with):
            return {"metadata": {"domain": "extension"}, "constraints": [{"id": identifier, "kind": "extension", "relationship": "optional", "value": {"conflicts_with": conflicts_with}, "claim_status": "documented"}]}

        with self.assertRaisesRegex(ValueError, "Conflicting extensions"):
            validate_extension_selection([extension("flash", ["sage"]), extension("sage", [])])

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
