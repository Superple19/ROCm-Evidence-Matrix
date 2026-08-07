import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from windows_rocm_matrix.collect import collect_therock, parse_args
from windows_rocm_matrix.legacy import collect_legacy_windows_sources
from windows_rocm_matrix.source_adapter import collection_status, run_source_adapter
from windows_rocm_matrix.validation import validate_collection_status


class CollectionCommandTests(unittest.TestCase):
    def test_parses_distribution_family_commands(self):
        therock = parse_args(["collect", "therock"])
        legacy = parse_args(["collect", "legacy"])
        normalize_therock = parse_args(["normalize", "therock"])
        normalize_legacy = parse_args(["normalize", "legacy"])
        integrate = parse_args(["integrate"])
        render = parse_args(["render"])
        build = parse_args(["build"])

        self.assertEqual((therock.command, therock.family), ("collect", "therock"))
        self.assertEqual((legacy.command, legacy.family), ("collect", "legacy"))
        self.assertEqual((normalize_therock.command, normalize_therock.family), ("normalize", "therock"))
        self.assertEqual((normalize_legacy.command, normalize_legacy.family), ("normalize", "legacy"))
        self.assertEqual(integrate.command, "integrate")
        self.assertEqual(render.command, "render")
        self.assertEqual(build.command, "build")

    def test_source_failure_does_not_stop_next_adapter(self):
        failed_source = {"id": "failed", "url": "https://example.test/failed"}
        passed_source = {"id": "passed", "url": "https://example.test/passed"}

        def fail():
            raise OSError("offline")

        failed_value, failed = run_source_adapter(failed_source, fail, "2026-08-07T00:00:00Z")
        passed_value, passed = run_source_adapter(passed_source, lambda: "value", "2026-08-07T00:00:00Z")

        self.assertIsNone(failed_value)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(passed_value, "value")
        status = collection_status("therock", "2026-08-07T00:00:00Z", [failed, passed])
        validate_collection_status(status)

    def test_legacy_failure_retains_previous_source_evidence(self):
        config = {
            "hip_sdk_release_versions": {"id": "versions", "url": "https://example.test/versions"},
            "hip_sdk_gpu_support": [],
            "pytorch_windows_support": [],
            "artifact_index": {"id": "artifacts", "url": "https://example.test/artifacts/"},
        }
        existing = {
            "schema_version": 1,
            "generated_at": "2026-08-07T00:00:00Z",
            "sources": {"versions": {"id": "versions", "url": "https://example.test/versions", "observed_at": "2026-08-07T00:00:00Z"}},
            "hip_sdk_releases": [{"rocm_series": "6.4", "linux_support": True, "windows_support": True, "source_id": "versions"}],
            "hip_sdk_gpu_support": [],
            "pytorch_windows_support": [],
            "artifact_releases": [],
        }

        def fetch(url):
            if url.endswith("versions"):
                raise OSError("offline")
            return "<html></html>"

        document, results = collect_legacy_windows_sources(config, fetch, existing=existing)

        self.assertEqual(document["hip_sdk_releases"], existing["hip_sdk_releases"])
        self.assertEqual([result["status"] for result in results], ["failed", "passed"])

    def test_therock_package_failure_does_not_block_next_snapshot(self):
        documentation = {
            "schema_version": 1,
            "last_observed_at": "2026-08-07T00:00:00Z",
            "sources": {},
            "products": [],
            "windows_release_support": [],
            "therock_windows_status": [],
            "framework_compatibility": [],
        }
        sources = [
            {"id": "stable", "channel": "stable", "url": "https://example.test/stable/"},
            {"id": "nightly", "channel": "nightly", "url": "https://example.test/nightly/"},
        ]

        def package_result(source, **kwargs):
            if source["id"] == "stable":
                raise OSError("offline")
            return (
                {
                    "schema_version": 1,
                    "last_observed_at": "2026-08-07T00:00:00Z",
                    "source": source,
                    "gfx_targets": [],
                    "packages": {},
                },
                [],
            )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            args = SimpleNamespace(
                documentation_output=root / "documentation.json",
                sources=None,
                output_dir=root / "snapshots",
                history_output=root / "history.json",
                status_output=root / "status.json",
                cache_dir=root / "cache",
                source_manifest=root / "source-manifest.json",
                timeout=1,
                workers=1,
                gfx_targets=[],
            )
            config = {"documentation_sources": [], "artifact_sources": sources}
            with patch("windows_rocm_matrix.collect.collect_documentation_sources", return_value=(documentation, [])), patch(
                "windows_rocm_matrix.collect.collect_source", side_effect=package_result
            ):
                success = collect_therock(args, config)

            self.assertFalse(success)
            self.assertFalse((root / "snapshots" / "stable.json").exists())
            self.assertTrue((root / "snapshots" / "nightly.json").exists())


if __name__ == "__main__":
    unittest.main()
