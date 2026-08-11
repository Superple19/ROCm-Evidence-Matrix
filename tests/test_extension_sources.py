import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from rocm_evidence_matrix.extension_sources import build_extension_snapshot, collect_extension_sources, parse_extension_source, parse_github_releases, parse_pypi_json, parse_simple_index
from rocm_evidence_matrix.validation import validate_extension_snapshot


class ExtensionSourceTests(unittest.TestCase):
    def test_parses_pypi_wheels_and_source_dist(self):
        document = {
            "info": {
                "version": "0.48.2",
                "requires_dist": ["torch>=2.0"],
            },
            "releases": {
                "0.48.2": [
                    {
                        "filename": "bitsandbytes-0.48.2-cp312-cp312-manylinux_2_24_x86_64.whl",
                        "url": "https://files.example/bitsandbytes.whl",
                    },
                    {
                        "filename": "bitsandbytes-0.48.2.tar.gz",
                        "url": "https://files.example/bitsandbytes.tar.gz",
                    },
                    {
                        "filename": "bitsandbytes-0.48.2-1-cp312-cp312-win_amd64.whl",
                        "url": "https://files.example/bitsandbytes-build.whl",
                    },
                ]
            }
        }
        artifacts = parse_pypi_json(document, "bitsandbytes")
        self.assertEqual(len(artifacts), 3)
        self.assertEqual(artifacts[0]["version"], "0.48.2")
        self.assertIn("cp", artifacts[0]["python_tag"])
        self.assertEqual(artifacts[0]["requires_dist"], ["torch>=2.0"])
        self.assertEqual(artifacts[0]["sha256"], None)
        build = next(item for item in artifacts if "-1-cp312" in item["filename"])
        self.assertEqual(build["build_tag"], "1")

    def test_parses_simple_index_without_platform_filtering(self):
        html = (
            '<a href="flash_attn-2.8.3+rocm-cp312-cp312-win_amd64.whl">win</a>'
            '<a href="flash_attn-2.8.3+rocm-cp312-cp312-manylinux_2_28_x86_64.whl">linux</a>'
        )
        artifacts = parse_simple_index(html, "https://example.test/simple/flash-attn/", "flash-attn")
        self.assertEqual({item["platform_tag"] for item in artifacts}, {"win_amd64", "manylinux_2_28_x86_64"})

    def test_parses_github_release_assets(self):
        releases = [{
            "tag_name": "v1",
            "assets": [{
                "name": "aiter-0.1.0-cp312-cp312-win_amd64.whl",
                "browser_download_url": "https://github.example/aiter.whl",
            }],
        }]
        self.assertEqual(parse_github_releases(releases, "aiter")[0]["version"], "0.1.0")

    def test_dispatches_json_source(self):
        source = {"package_name": "bitsandbytes", "source_kind": "pypi-json"}
        body = json.dumps({"releases": {"1.0.0": []}})
        self.assertEqual(parse_extension_source(source, body), [])

    def test_built_snapshot_has_external_dimensions(self):
        snapshot = build_extension_snapshot(
            {
                "id": "pypi-bitsandbytes",
                "package_name": "bitsandbytes",
                "url": "https://pypi.org/pypi/bitsandbytes/json",
                "distribution_family": "external",
                "platform": "unknown",
                "channel": "external",
            },
            [{
                "filename": "bitsandbytes-0.50.0-py3-none-any.whl",
                "version": "0.50.0",
                "python_tag": "py3",
                "abi_tag": "none",
                "platform_tag": "any",
                "url": "https://files.example/bitsandbytes.whl",
            }],
            "2026-08-08T00:00:00Z",
        )
        self.assertEqual(snapshot["source"]["distribution_family"], "external")
        self.assertEqual(snapshot["source"]["channel"], "external")
        validate_extension_snapshot(snapshot)
        snapshot["packages"]["bitsandbytes"][0]["url"] = "file:///bitsandbytes.whl"
        with self.assertRaises(ValueError):
            validate_extension_snapshot(snapshot)

    def test_github_release_sources_fetch_bounded_pages_and_record_metadata(self):
        calls = []

        class Reader:
            def __call__(self, url):
                calls.append(url)
                if url.endswith("page=1"):
                    return json.dumps([{"id": 1, "assets": [{"name": "aiter-0.1.0-cp312-cp312-win_amd64.whl", "browser_download_url": "https://files.example/aiter-0.1.0.whl"}]}])
                if url.endswith("page=2"):
                    return "[]"
                raise AssertionError(url)

            def metadata(self, url):
                return {"source_status": "revalidated", "cache_age_seconds": 12}

        with TemporaryDirectory() as directory:
            results = collect_extension_sources(
                [{
                    "id": "github-aiter",
                    "package_name": "aiter",
                    "url": "https://api.github.com/repos/ROCm/aiter/releases?per_page=100",
                    "source_kind": "github-releases",
                    "pagination": {"page_size": 1, "max_pages": 10},
                }],
                Reader(),
                Path(directory),
                "2026-08-10T00:00:00Z",
            )
        self.assertEqual(len(calls), 2)
        self.assertEqual(results[0]["status"], "passed")
        self.assertEqual(results[0]["details"]["pages_fetched"], 2)
        self.assertEqual(results[0]["details"]["source_status"], "revalidated")
        self.assertEqual(results[0]["details"]["cache_age_seconds"], 12)

    def test_github_release_pagination_failure_is_explicit(self):
        class Reader:
            def __call__(self, url):
                return json.dumps([{}])

        with TemporaryDirectory() as directory:
            results = collect_extension_sources(
                [{
                    "id": "github-aiter",
                    "package_name": "aiter",
                    "url": "https://api.github.com/repos/ROCm/aiter/releases",
                    "source_kind": "github-releases",
                    "pagination": {"page_size": 1, "max_pages": 1},
                }],
                Reader(),
                Path(directory),
                "2026-08-10T00:00:00Z",
            )
        self.assertEqual(results[0]["status"], "failed")
        self.assertTrue(results[0]["details"]["truncated"])
        self.assertIn("exceeded 1 pages", results[0]["error"])


if __name__ == "__main__":
    unittest.main()
