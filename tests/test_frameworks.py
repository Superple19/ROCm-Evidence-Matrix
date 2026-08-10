import unittest

from rocm_evidence_matrix.frameworks import build_jax_observations, build_sdk_components, merge_framework_history, merge_sdk_components
from rocm_evidence_matrix.validation import validate_framework_history


class FrameworkEvidenceTests(unittest.TestCase):
    def test_builds_jax_candidate_from_universal_pjrt_and_python_plugin(self):
        source = {"id": "stable-linux", "distribution_family": "therock", "platform": "linux", "channel": "stable"}
        packages = {
            "jax-rocm7-pjrt": [{"version": "0.10.0+rocm7.14.0", "python_tag": "py3"}],
            "jax-rocm7-plugin": [{"version": "0.10.0+rocm7.14.0", "python_tag": "cp312"}],
        }

        candidates = build_jax_observations(source, packages)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["python_tags"], ["cp312"])
        self.assertEqual(candidates[0]["rocm_version"], "7.14.0")

    def test_keeps_sdk_components_outside_framework_candidates(self):
        source = {"id": "stable-linux", "distribution_family": "therock", "platform": "linux", "channel": "stable"}
        components = build_sdk_components(source, {"rocm-profiler": [{"version": "1.0", "python_tag": "py3"}]})

        self.assertEqual(components[0]["component_kind"], "sdk-component")
        self.assertEqual(components[0]["package_name"], "rocm-profiler")

    def test_framework_lifecycle_is_scoped_to_platform(self):
        def candidate(platform, version):
            return {
                "id": f"jax:{platform}:{version}",
                "distribution_family": "therock",
                "framework": "jax",
                "runtime_family": "jax-rocm7",
                "platform": platform,
                "channel": "stable",
                "rocm_version": version,
                "pjrt_package": "jax-rocm7-pjrt",
                "pjrt_version": "0.10.0",
                "plugin_package": "jax-rocm7-plugin",
                "plugin_version": "0.10.0",
                "python_tags": ["cp312"],
                "artifact_available": True,
                "source_id": "packages-stable",
            }

        history = merge_framework_history(
            None,
            [candidate("windows", "7.14.0"), candidate("linux", "7.2.4")],
            {"packages-stable": {}},
            "2026-08-08T00:00:00Z",
        )
        self.assertEqual({item["platform"]: item["lifecycle"] for item in history["candidates"]}, {"windows": "current", "linux": "current"})
        validate_framework_history(history)

    def test_sdk_generated_at_does_not_regress_offline(self):
        existing = {"schema_version": 1, "generated_at": "2026-08-08T14:13:02Z", "components": []}
        merged = merge_sdk_components(existing, [], "2026-08-08T10:15:14Z")
        self.assertEqual(merged["generated_at"], "2026-08-08T14:13:02Z")


if __name__ == "__main__":
    unittest.main()
