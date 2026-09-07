import json
import unittest

from rocm_evidence_matrix.ci import CICollectionError, build_evidence, collect_github, parse_matrix
from rocm_evidence_matrix.validation import validate_ci_coverage, validate_ci_evidence


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

    def test_adapter_failure_keeps_existing_evidence(self):
        existing = {"schema_version": 1, "generated_at": "2026-08-08T00:00:00Z", "executions": [{"id": "old", "observations": []}], "adapter_failures": []}
        document = build_evidence([], [], existing=existing, observed_at="2026-08-08T00:01:00Z", failures=[{"adapter": "github_actions", "error": "rate limited", "observed_at": "2026-08-08T00:01:00Z"}])
        self.assertEqual([item["id"] for item in document["executions"]], ["old"])
        self.assertEqual(document["adapter_failures"][0]["adapter"], "github_actions")

    def test_github_collection_reads_bounded_api_pages(self):
        config = {
            "workflows": {"url": "https://api.example.test/workflows?per_page=100"},
            "runs_api": "https://api.example.test/workflows/{workflow_id}/runs?per_page=100",
            "jobs_api": "https://api.example.test/actions/runs/{run_id}/jobs",
        }

        def reader(url):
            if url == config["workflows"]["url"]:
                return '{"workflows": [{"id": 1, "path": ".github/workflows/windows.yml", "name": "Windows"}]}'
            if "workflows/1/runs" in url:
                return '{"workflow_runs": [{"id": 2, "workflow_id": 1, "run_attempt": 1, "status": "completed", "head_sha": "' + "a" * 40 + '", "created_at": "2026-08-08T00:00:00Z"}]}'
            if "actions/runs/2/jobs" in url:
                return '{"jobs": [{"id": 3, "name": "Build gfx1201", "labels": ["windows"], "status": "completed", "conclusion": "success", "html_url": "https://example.test/job/3", "started_at": "2026-08-08T00:00:00Z", "completed_at": "2026-08-08T00:01:00Z"}]}'
            if "page=2" in url:
                return '{"workflows": [], "workflow_runs": [], "jobs": []}'
            raise AssertionError(url)

        records = collect_github(config, reader, "2026-08-08T00:02:00Z")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["targets"], ["gfx1201"])

    def test_github_collection_keeps_linux_jobs(self):
        config = {
            "workflows": {"url": "https://api.example.test/workflows?per_page=100"},
            "runs_api": "https://api.example.test/workflows/{workflow_id}/runs?per_page=100",
            "jobs_api": "https://api.example.test/actions/runs/{run_id}/jobs",
        }

        def reader(url):
            if url == config["workflows"]["url"]:
                return '{"workflows": [{"id": 1, "path": ".github/workflows/linux.yml", "name": "Linux"}]}'
            if "workflows/1/runs" in url:
                return '{"workflow_runs": [{"id": 2, "workflow_id": 1, "run_attempt": 1, "status": "completed", "head_sha": "' + "a" * 40 + '", "created_at": "2026-08-08T00:00:00Z"}]}'
            if "actions/runs/2/jobs" in url:
                return '{"jobs": [{"id": 3, "name": "Build gfx90a", "labels": ["ubuntu-latest"], "status": "completed", "conclusion": "success"}]}'
            raise AssertionError(url)

        records = collect_github(config, reader, "2026-08-08T00:02:00Z")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["platform"], "linux")

    def test_github_collection_allows_configured_workflow_budget(self):
        config = {
            "workflows": {"url": "https://api.example.test/workflows?per_page=100", "max_selected_workflows": 50},
            "runs_api": "https://api.example.test/workflows/{workflow_id}/runs?per_page=100",
            "jobs_api": "https://api.example.test/actions/runs/{run_id}/jobs",
        }
        workflows = [{"id": index, "path": f".github/workflows/linux-{index}.yml"} for index in range(50)]

        def reader(url):
            if url == config["workflows"]["url"]:
                return json.dumps({"workflows": workflows})
            if "/workflows/" in url:
                return json.dumps({"workflow_runs": []})
            raise AssertionError(url)

        self.assertEqual(collect_github(config, reader, "2026-08-08T00:02:00Z"), [])

    def test_github_collection_rejects_workflows_over_configured_budget(self):
        config = {
            "workflows": {"url": "https://api.example.test/workflows?per_page=100", "max_selected_workflows": 50},
            "runs_api": "https://api.example.test/workflows/{workflow_id}/runs?per_page=100",
            "jobs_api": "https://api.example.test/actions/runs/{run_id}/jobs",
        }
        workflows = [{"id": index, "path": f".github/workflows/linux-{index}.yml"} for index in range(51)]

        def reader(url):
            if url == config["workflows"]["url"]:
                return json.dumps({"workflows": workflows})
            raise AssertionError(url)

        with self.assertRaises(CICollectionError) as context:
            collect_github(config, reader, "2026-08-08T00:02:00Z")
        self.assertIn("50-workflow", str(context.exception))
        self.assertEqual(context.exception.details["items_fetched"], 51)
        self.assertEqual(context.exception.details["max_pages"], 50)
        self.assertTrue(context.exception.details["truncated"])

    def test_github_collection_records_recent_run_truncation(self):
        config = {
            "workflows": {"url": "https://api.example.test/workflows?per_page=100", "max_run_pages": 2},
            "runs_api": "https://api.example.test/workflows/{workflow_id}/runs?per_page=100",
            "jobs_api": "https://api.example.test/actions/runs/{run_id}/jobs",
        }

        def reader(url):
            if url == config["workflows"]["url"]:
                return '{"workflows": [{"id": 1, "path": ".github/workflows/linux.yml", "name": "Linux"}]}'
            if "workflows/1/runs" in url:
                return '{"workflow_runs": [' + ",".join(
                    '{"id": %d, "workflow_id": 1, "run_attempt": 1}' % index
                    for index in range(100)
                ) + ']}'
            if "actions/runs/" in url:
                return '{"jobs": []}'
            raise AssertionError(url)

        pagination = []
        self.assertEqual(collect_github(config, reader, "2026-08-08T00:02:00Z", pagination), [])
        self.assertEqual(pagination[0]["items_fetched"], 200)
        self.assertEqual(pagination[0]["max_pages"], 2)
        self.assertEqual(pagination[0]["reason"], "pagination_limit")
        self.assertTrue(pagination[0]["truncated"])

    def test_github_collection_fails_on_run_page_fetch_error(self):
        config = {
            "workflows": {"url": "https://api.example.test/workflows?per_page=100", "max_run_pages": 2},
            "runs_api": "https://api.example.test/workflows/{workflow_id}/runs?per_page=100",
            "jobs_api": "https://api.example.test/actions/runs/{run_id}/jobs",
        }

        def reader(url):
            if url == config["workflows"]["url"]:
                return '{"workflows": [{"id": 1, "path": ".github/workflows/linux.yml"}]}'
            if "workflows/1/runs" in url and "page=2" not in url:
                return '{"workflow_runs": [' + ",".join(
                    '{"id": %d, "workflow_id": 1, "run_attempt": 1}' % index
                    for index in range(100)
                ) + ']}'
            if "workflows/1/runs" in url:
                raise OSError("offline")
            raise AssertionError(url)

        with self.assertRaises(CICollectionError) as context:
            collect_github(config, reader, "2026-08-08T00:02:00Z")
        self.assertEqual(context.exception.details["reason"], "page_fetch_failed")
        self.assertEqual(context.exception.details["pages_fetched"], 1)


if __name__ == "__main__":
    unittest.main()
