import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from rocm_evidence_matrix.collect import collect_therock, collect_source, parse_args
from rocm_evidence_matrix.legacy import collect_legacy_windows_sources
from rocm_evidence_matrix.paths import LEGACY_LINUX, LEGACY_STATUS, LEGACY_WINDOWS, THEROCK_CI_COVERAGE, THEROCK_CI_EVIDENCE, THEROCK_SNAPSHOTS, THEROCK_STATUS
from rocm_evidence_matrix.source_adapter import collection_status, run_source_adapter
from rocm_evidence_matrix.validation import validate_collection_status


class CollectionCommandTests(unittest.TestCase):
    def test_collects_apex_and_device_aliases_without_making_them_full_targets(self):
        root = """
        <a href="apex/">apex</a>
        <a href="amd-torch-device-gfx12-0/">amd-torch-device-gfx12-0</a>
        <a href="rocm-sdk-device-gfx1201/">rocm-sdk-device-gfx1201</a>
        <a href="torch/">torch</a>
        """
        package_page = {
            "apex": '<a href="apex-1.0+rocm7.14.0-cp312-cp312-manylinux_2_28_x86_64.whl">a</a>',
            "amd-torch-device-gfx12-0": '<a href="amd_torch_device_gfx12_0-2.10.0+rocm7.14.0-cp312-cp312-manylinux_2_28_x86_64.whl">a</a>',
            "rocm-sdk-device-gfx1201": '<a href="rocm_sdk_device_gfx1201-7.14.0-py3-none-manylinux_2_28_x86_64.whl">a</a>',
            "torch": '<a href="torch-2.12.0+rocm7.14.0-cp312-cp312-manylinux_2_28_x86_64.whl">a</a>',
        }

        def fetch(url):
            if url.rstrip("/") == "https://example.test":
                return root
            package = url.rstrip("/").rsplit("/", 1)[-1]
            return package_page[package]

        snapshot, _ = collect_source(
            {"id": "stable-linux", "channel": "stable", "platform": "linux", "url": "https://example.test/"},
            fetch=fetch,
            framework_compatibility=[],
            workers=1,
        )

        self.assertIn("apex", snapshot["packages"])
        self.assertIn("amd-torch-device-gfx12-0", snapshot["packages"])
        self.assertEqual([item["gfx"] for item in snapshot["gfx_targets"]], ["gfx1201"])

    def test_parses_distribution_family_commands(self):
        therock = parse_args(["collect", "therock"])
        legacy = parse_args(["collect", "legacy"])
        normalize_therock = parse_args(["normalize", "therock"])
        normalize_legacy = parse_args(["normalize", "legacy"])
        integrate = parse_args(["integrate"])
        render = parse_args(["render"])
        build = parse_args(["build"])
        check = parse_args(["check"])
        bundle = parse_args(["bundle", "--output", "dist/catalog.zip"])
        verify_bundle = parse_args(["verify-bundle", "dist/catalog.zip"])

        self.assertEqual((therock.command, therock.family), ("collect", "therock"))
        self.assertEqual((legacy.command, legacy.family), ("collect", "legacy"))
        self.assertEqual((normalize_therock.command, normalize_therock.family), ("normalize", "therock"))
        self.assertEqual((normalize_legacy.command, normalize_legacy.family), ("normalize", "legacy"))
        self.assertEqual((therock.output_dir, therock.status_output), (THEROCK_SNAPSHOTS, THEROCK_STATUS))
        self.assertEqual((therock.ci_coverage_output, therock.ci_evidence_output), (THEROCK_CI_COVERAGE, THEROCK_CI_EVIDENCE))
        self.assertEqual((legacy.legacy_output, legacy.legacy_linux_output, legacy.status_output), (LEGACY_WINDOWS, LEGACY_LINUX, LEGACY_STATUS))
        self.assertEqual(integrate.command, "integrate")
        self.assertEqual(render.command, "render")
        self.assertEqual(build.command, "build")
        self.assertEqual(check.command, "check")
        self.assertEqual(bundle.command, "bundle")
        self.assertEqual(verify_bundle.command, "verify-bundle")

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

    def test_collection_status_preserves_pagination_details(self):
        status = collection_status(
            "external",
            "2026-08-07T00:00:00Z",
            [{
                "source_id": "github-aiter",
                "status": "failed",
                "error": "pagination limit",
                "details": {"pages_fetched": 10, "items_fetched": 1000, "max_pages": 10, "truncated": True, "reason": "pagination_limit", "source_status": "revalidated", "cache_age_seconds": 3600},
            }],
        )
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
            {
                "id": "stable",
                "distribution_family": "therock",
                "channel": "stable",
                "platform": "windows",
                "url": "https://example.test/stable/",
            },
            {
                "id": "nightly",
                "distribution_family": "therock",
                "channel": "nightly",
                "platform": "windows",
                "url": "https://example.test/nightly/",
            },
        ]

        def package_result(source, **_kwargs):
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
            archive_path = root / "legacy" / "archive" / "windows.json"
            archive_path.parent.mkdir(parents=True)
            archive_path.write_text("archive-sentinel", encoding="utf-8")
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
            with patch("rocm_evidence_matrix.collect.collect_documentation_sources", return_value=(documentation, [])), patch(
                "rocm_evidence_matrix.collect.collect_source", side_effect=package_result
            ):
                success = collect_therock(args, config)

            self.assertFalse(success)
            self.assertFalse((root / "snapshots" / "stable.json").exists())
            self.assertTrue((root / "snapshots" / "nightly.json").exists())
            self.assertEqual(archive_path.read_text(encoding="utf-8"), "archive-sentinel")


if __name__ == "__main__":
    unittest.main()
