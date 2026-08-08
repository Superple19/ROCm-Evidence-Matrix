import unittest

from windows_rocm_matrix.frameworks import build_jax_observations, build_sdk_components


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


if __name__ == "__main__":
    unittest.main()
