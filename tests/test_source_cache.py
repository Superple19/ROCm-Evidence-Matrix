import hashlib
import json
import unittest
from email.message import Message
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError

from windows_rocm_matrix.source_cache import CachedSourceReader, SourceCache
from windows_rocm_matrix.validation import validate_source_manifest


class Response:
    def __init__(self, content, headers=None):
        self.content = content
        self.headers = Message()
        for name, value in (headers or {}).items():
            self.headers[name] = value

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.content


class SourceCacheTests(unittest.TestCase):
    def test_stores_response_by_hash_and_records_manifest_metadata(self):
        content = b"source response"

        def open_response(request, timeout):
            self.assertEqual(timeout, 5)
            return Response(
                content,
                {
                    "Content-Type": "text/plain; charset=utf-8",
                    "ETag": '"revision-1"',
                    "Last-Modified": "Fri, 07 Aug 2026 00:00:00 GMT",
                },
            )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            cache = SourceCache(root / "cache", root / "manifest.json", 5, opener=open_response, observed_at=lambda: "2026-08-07T00:00:00Z")

            self.assertEqual(cache("https://example.test/source"), "source response")
            manifest = cache.write_manifest()

            digest = hashlib.sha256(content).hexdigest()
            self.assertEqual((root / "cache" / digest).read_bytes(), content)
            self.assertEqual(manifest["responses"][0]["sha256"], digest)
            self.assertEqual(manifest["responses"][0]["etag"], '"revision-1"')
            self.assertEqual(manifest["responses"][0]["last_modified"], "Fri, 07 Aug 2026 00:00:00 GMT")
            validate_source_manifest(json.loads((root / "manifest.json").read_text(encoding="utf-8")))

    def test_uses_conditional_request_and_cached_body_for_not_modified_response(self):
        content = b"unchanged"
        calls = []

        def first_response(request, timeout):
            return Response(content, {"ETag": '"revision-1"', "Last-Modified": "Fri, 07 Aug 2026 00:00:00 GMT"})

        def not_modified(request, timeout):
            calls.append(request)
            raise HTTPError(request.full_url, 304, "Not Modified", Message(), None)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = SourceCache(root / "cache", root / "manifest.json", 5, opener=first_response, observed_at=lambda: "2026-08-07T00:00:00Z")
            first("https://example.test/source")
            first.write_manifest()

            second = SourceCache(root / "cache", root / "manifest.json", 5, opener=not_modified, observed_at=lambda: "2026-08-08T00:00:00Z")
            self.assertEqual(second("https://example.test/source"), "unchanged")

            self.assertEqual(calls[0].get_header("If-none-match"), '"revision-1"')
            self.assertEqual(calls[0].get_header("If-modified-since"), "Fri, 07 Aug 2026 00:00:00 GMT")
            self.assertEqual(second.write_manifest()["responses"][0]["observed_at"], "2026-08-08T00:00:00Z")

    def test_deduplicates_identical_content_from_different_urls(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cache = SourceCache(root / "cache", root / "manifest.json", 5, opener=lambda request, timeout: Response(b"same"))

            cache("https://example.test/one")
            cache("https://example.test/two")

            self.assertEqual(len(list((root / "cache").iterdir())), 1)
            self.assertEqual(len(cache.write_manifest()["responses"]), 2)

    def test_fetches_full_response_when_manifest_cache_file_is_absent(self):
        requests = []

        def open_response(request, timeout):
            requests.append(request)
            return Response(b"restored", {"ETag": '"revision-2"'})

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {
                "schema_version": 1,
                "generated_at": "2026-08-07T00:00:00Z",
                "responses": [
                    {
                        "url": "https://example.test/source",
                        "sha256": "0" * 64,
                        "etag": '"revision-1"',
                        "last_modified": None,
                        "observed_at": "2026-08-07T00:00:00Z",
                        "encoding": "utf-8",
                    }
                ],
            }
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            cache = SourceCache(root / "cache", root / "manifest.json", 5, opener=open_response)

            self.assertEqual(cache("https://example.test/source"), "restored")

            self.assertIsNone(requests[0].get_header("If-none-match"))
            self.assertTrue((root / "cache" / hashlib.sha256(b"restored").hexdigest()).exists())

    def test_reads_cached_response_without_a_network_client(self):
        content = b"offline source"
        digest = hashlib.sha256(content).hexdigest()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cache").mkdir()
            (root / "cache" / digest).write_bytes(content)
            manifest = {
                "schema_version": 1,
                "generated_at": "2026-08-07T00:00:00Z",
                "responses": [
                    {
                        "url": "https://example.test/source",
                        "sha256": digest,
                        "etag": None,
                        "last_modified": None,
                        "observed_at": "2026-08-07T00:00:00Z",
                        "encoding": "utf-8",
                    }
                ],
            }
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            reader = CachedSourceReader(root / "cache", root / "manifest.json")

            self.assertEqual(reader.generated_at, "2026-08-07T00:00:00Z")
            self.assertEqual(reader("https://example.test/source"), "offline source")
            self.assertEqual(reader.latest_observed_at(prefixes=["https://example.test/"]), "2026-08-07T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
