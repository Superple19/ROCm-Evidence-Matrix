import unittest
from pathlib import Path

from windows_rocm_matrix.check import run_check


class CheckCommandTests(unittest.TestCase):
    def test_committed_evidence_passes_check(self):
        run_check(Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    unittest.main()
