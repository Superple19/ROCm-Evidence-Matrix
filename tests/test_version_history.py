import json
import unittest

from rocm_evidence_matrix.version_history import collect_legacy_version_history, merge_version_history, parse_documentation_branches, parse_rocm_release_history, parse_therock_releases, parse_therock_version, release_record
from rocm_evidence_matrix.validation import validate_version_history


OBSERVED_AT = "2026-08-08T00:00:00Z"


class VersionHistoryTests(unittest.TestCase):
    def test_discovers_official_rocm_release_links(self):
        html = """
        <table><tr><th>Version</th><th>Release date</th></tr>
        <tr><td><a href="../docs-6.1.0/">6.1.0</a></td><td>Apr 16, 2024</td></tr>
        <tr><td><a href="../docs-7.2.1/">7.2.1</a></td><td>March 25, 2026</td></tr></table>
        """

        releases = parse_rocm_release_history(html, "https://rocm.docs.amd.com/en/latest/release/versions.html", "releases")

        self.assertEqual(releases[0]["release_date"], "2024-04-16")
        self.assertEqual(releases[1]["version"], "7.2.1")
        self.assertEqual(releases[1]["release_date"], "2026-03-25")
        self.assertEqual(releases[1]["documentation_url"], "https://rocm.docs.amd.com/en/latest/docs-7.2.1/")

    def test_discovers_therock_releases_and_current_version(self):
        releases = parse_therock_releases(
            json.dumps([{"tag_name": "therock-7.14", "published_at": "2026-07-15T13:57:44Z", "html_url": "https://github.com/ROCm/TheRock/releases/tag/therock-7.14"}]),
            "therock-releases",
        )
        current = parse_therock_version('{"rocm-version":"10.1.0"}', "therock-version")

        self.assertEqual(releases[0]["version"], "7.14")
        self.assertIn("therock-7.14/SUPPORTED_GPUS.md", releases[0]["documentation_url"])
        self.assertEqual(current["version"], "10.1.0")

    def test_discovers_versioned_windows_documentation_branches(self):
        branches = parse_documentation_branches(json.dumps([{"name": "develop"}, {"name": "docs/6.4.2"}, {"name": "docs/7.2"}]), "branches")

        self.assertEqual([item["version"] for item in branches], ["6.4.2", "7.2"])

    def test_keeps_missing_archive_distinct_from_unsupported(self):
        config = {
            "rocm_releases": {"id": "releases", "url": "https://example.test/releases"},
            "documentation_branches": {"id": "branches", "url": "https://example.test/branches"},
        }
        legacy = {
            "sources": {"versions": {"id": "versions"}},
            "hip_sdk_releases": [
                {"rocm_series": "5.5", "windows_support": True, "source_id": "versions"},
                {"rocm_series": "5.6", "windows_support": False, "source_id": "versions"},
            ],
            "hip_sdk_gpu_support": [],
            "pytorch_windows_support": [],
            "artifact_releases": [],
        }
        pages = {
            "https://example.test/releases": """
                <table><tr><th>Version</th><th>Release date</th></tr>
                <tr><td>5.5.0</td><td>May 1, 2023</td></tr>
                <tr><td>5.6.0</td><td>June 28, 2023</td></tr></table>
            """,
            "https://example.test/branches": '[{"name":"docs/5.6.0"}]',
        }

        history, results = collect_legacy_version_history(config, pages.__getitem__, legacy, observed_at=OBSERVED_AT)
        by_version = {item["version"]: item for item in history["releases"]}

        self.assertEqual(by_version["5.5.0"]["windows_support"], "supported")
        self.assertEqual(by_version["5.5.0"]["documentation_status"], "archive_missing")
        self.assertEqual(by_version["5.6.0"]["windows_support"], "unsupported")
        self.assertEqual(by_version["5.6.0"]["documentation_status"], "available")
        self.assertNotIn("5.5", by_version)
        self.assertNotIn("5.6", by_version)
        self.assertTrue(all(result["status"] == "passed" for result in results))
        validate_version_history(history)

    def test_preserves_release_only_patch_versions(self):
        config = {
            "rocm_releases": {"id": "releases", "url": "https://example.test/releases"},
            "documentation_branches": {"id": "branches", "url": "https://example.test/branches"},
        }
        legacy = {
            "sources": {"versions": {"id": "versions"}},
            "hip_sdk_releases": [],
            "hip_sdk_gpu_support": [],
            "pytorch_windows_support": [],
            "artifact_releases": [],
        }
        pages = {
            "https://example.test/releases": "<table><tr><th>Version</th><th>Release date</th></tr><tr><td>7.2.2</td><td>April 14, 2026</td></tr><tr><td>7.2.4</td><td>May 29, 2026</td></tr></table>",
            "https://example.test/branches": "[]",
        }
        history, _ = collect_legacy_version_history(config, pages.__getitem__, legacy, observed_at=OBSERVED_AT)
        self.assertEqual([item["version"] for item in history["releases"]], ["7.2.2", "7.2.4"])

    def test_derives_lifecycle_without_changing_distribution_family(self):
        older = release_record("therock", "7.14", OBSERVED_AT, source_ids=["source"])
        newer = release_record("therock", "10.1.0", OBSERVED_AT, source_ids=["source"])
        history = merge_version_history(None, "therock", [older, newer], [], {"source": {}}, OBSERVED_AT)
        by_version = {item["version"]: item for item in history["releases"]}

        self.assertEqual(by_version["7.14"]["lifecycle"], "historical")
        self.assertEqual(by_version["10.1.0"]["lifecycle"], "current")
        self.assertEqual(by_version["7.14"]["distribution_family"], "therock")
        validate_version_history(history)

    def test_lifecycle_is_scoped_to_distribution_and_channel(self):
        history = merge_version_history(
            None,
            "legacy",
            [release_record("legacy", "7.2.4", OBSERVED_AT, channel="stable", source_ids=["source"])],
            [],
            {"source": {}},
            OBSERVED_AT,
        )
        history = merge_version_history(
            history,
            "therock",
            [release_record("therock", "10.1.0", OBSERVED_AT, channel="nightly", source_ids=["source"])],
            [],
            {"source": {}},
            OBSERVED_AT,
        )
        by_id = {item["id"]: item for item in history["releases"]}
        self.assertEqual(by_id["legacy:7.2.4"]["lifecycle"], "current")
        self.assertEqual(by_id["therock:10.1.0"]["lifecycle"], "current")
        validate_version_history(history)

    def test_lifecycle_is_scoped_to_platform(self):
        history = merge_version_history(
            None,
            "therock",
            [
                release_record("therock", "7.14", OBSERVED_AT, platform="windows", channel="stable", source_ids=["source"]),
                release_record("therock", "7.2.4", OBSERVED_AT, platform="linux", channel="stable", source_ids=["source"]),
            ],
            [],
            {"source": {}},
            OBSERVED_AT,
        )
        by_id = {item["id"]: item for item in history["releases"]}
        self.assertEqual(by_id["therock:7.14"]["lifecycle"], "current")
        self.assertEqual(by_id["therock:linux:7.2.4"]["lifecycle"], "current")
        validate_version_history(history)

    def test_platform_evidence_is_not_forced_to_windows(self):
        record = release_record("therock", "10.1.0", OBSERVED_AT, platform="linux", source_ids=["source"])
        self.assertIn("linux", record["platform_evidence"])
        self.assertIn("windows", record["platform_evidence"])
        self.assertEqual(record["platform_evidence"]["linux"]["documentation_status"], "not_collected")
        self.assertEqual(record["windows_support"], "unknown")

    def test_platform_record_uses_platform_specific_evidence(self):
        record = release_record(
            "therock",
            "10.1.0",
            OBSERVED_AT,
            platform="linux",
            linux_support="supported",
            linux_package_available=True,
            linux_ci_verified=True,
            source_ids=["source"],
        )
        self.assertEqual(record["platform_evidence"]["linux"]["support"], "supported")
        self.assertTrue(record["platform_evidence"]["linux"]["package_available"])
        self.assertTrue(record["platform_evidence"]["linux"]["ci_verified"])
        self.assertEqual(record["windows_support"], "unknown")
        history = merge_version_history(None, "therock", [record], [], {"source": {}}, OBSERVED_AT)
        validate_version_history(history)


if __name__ == "__main__":
    unittest.main()
