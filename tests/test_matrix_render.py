import unittest

from rocm_evidence_matrix.matrix_render import target_platform


class MatrixRenderTests(unittest.TestCase):
    def test_missing_platform_does_not_fall_back_to_windows_fields(self):
        target = {
            "windows_release_support": {"rocm_version": "7.14.0"},
            "therock_windows_status": {"build_passing": True},
        }

        self.assertEqual(target_platform(target, "linux"), {})
        self.assertEqual(target_platform(target, "windows"), {})


if __name__ == "__main__":
    unittest.main()
