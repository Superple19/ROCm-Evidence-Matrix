import unittest

from windows_rocm_matrix.extensions import build_triton_observations, merge_extension_history, render_extension_history
from windows_rocm_matrix.validation import validate_extension_history


class ExtensionHistoryTests(unittest.TestCase):
    def test_tracks_triton_without_creating_core_candidates(self):
        source = {"id": "stable-linux", "distribution_family": "therock", "platform": "linux", "channel": "stable"}
        packages = {
            "triton": [
                {"version": "3.6.0+rocm7.14.0", "python_tag": "cp312"},
                {"version": "3.6.0+rocm7.14.0", "python_tag": "cp313"},
            ]
        }
        observations = build_triton_observations(source, packages)
        document = merge_extension_history(None, observations, "2026-08-08T00:00:00Z")
        validate_extension_history(document)
        self.assertEqual(len(document["extensions"]), 1)
        self.assertEqual(document["extensions"][0]["python_tags"], ["cp312", "cp313"])
        self.assertIn("Optional ROCm extension history", render_extension_history(document))


if __name__ == "__main__":
    unittest.main()
