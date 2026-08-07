import unittest

from windows_rocm_matrix.ci import build_evidence, parse_matrix
from windows_rocm_matrix.validation import validate_ci_coverage, validate_ci_evidence


MATRIX = """
amdgpu_family_info_matrix_presubmit = {
    'gfx120x': {'windows': {'test-runs-on': 'windows-gfx120X-gpu-rocm', 'family': 'gfx120X-all', 'fetch-gfx-targets': [], 'build_variants': ['release']}},
    'linux': {'linux': {'test-runs-on': 'ubuntu-latest', 'family': 'gfx90a', 'fetch-gfx-targets': ['gfx90a']}},
}
"""


class CITests(unittest.TestCase):
    def test_matrix_keeps_configured_coverage_separate_from_results(self):
        coverage = parse_matrix(MATRIX, "2026-08-08T00:00:00Z")
        validate_ci_coverage(coverage)
        self.assertEqual(coverage["entries"][0]["configured_targets"], ["gfx120X-all", "gfx120x"])
        self.assertNotIn("success", coverage["entries"][0])

    def test_evidence_preserves_attempts_and_deduplicates_observations(self):
        record = {"id": "github:1:2:1:3", "source": "github_actions", "workflow_id": 1, "workflow_name": "Windows", "run_id": 2, "run_attempt": 1, "job_id": 3, "job_name": "Build gfx1201", "head_sha": "a" * 40, "platform": "windows", "targets": ["gfx1201"], "test_kind": "build", "observations": [{"state": "success", "run_status": "completed", "conclusion": "success", "started_at": "2026-08-08T00:00:00Z", "completed_at": "2026-08-08T00:01:00Z", "observed_at": "2026-08-08T00:02:00Z"}]}
        document = build_evidence([record, record], [], observed_at="2026-08-08T00:02:00Z")
        validate_ci_evidence(document)
        self.assertEqual(len(document["executions"]), 1)
        self.assertEqual(len(document["executions"][0]["observations"]), 1)


if __name__ == "__main__":
    unittest.main()
