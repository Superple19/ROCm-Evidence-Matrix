import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .validation import validate_source_manifest


USER_AGENT = "windows-rocm-matrix/0.1 (+https://github.com/Superple19/windows-rocm-matrix)"


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class SourceCache:
    def __init__(self, cache_dir, manifest_path, timeout, opener=urlopen, observed_at=utc_now):
        self.cache_dir = Path(cache_dir)
        self.manifest_path = Path(manifest_path)
        self.timeout = timeout
        self.opener = opener
        self.observed_at = observed_at
        self.generated_at = observed_at()
        self.lock = threading.Lock()
        self.responses = {}
        if self.manifest_path.exists():
            with self.manifest_path.open(encoding="utf-8") as handle:
                manifest = json.load(handle)
            validate_source_manifest(manifest)
            self.responses = {response["url"]: response for response in manifest.get("responses", [])}

    def __call__(self, url):
        with self.lock:
            previous = self.responses.get(url)
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
        cached_path = self.cache_dir / previous["sha256"] if previous else None
        if cached_path and cached_path.exists():
            if previous.get("etag"):
                headers["If-None-Match"] = previous["etag"]
            if previous.get("last_modified"):
                headers["If-Modified-Since"] = previous["last_modified"]

        request = Request(url, headers=headers)
        try:
            with self.opener(request, timeout=self.timeout) as response:
                content = response.read()
                etag = response.headers.get("ETag")
                last_modified = response.headers.get("Last-Modified")
                encoding = response.headers.get_content_charset() or "utf-8"
        except HTTPError as error:
            if error.code != 304 or previous is None:
                raise
            if not cached_path.exists():
                raise OSError(f"Cached source response is missing: {cached_path}") from error
            content = cached_path.read_bytes()
            etag = error.headers.get("ETag") or previous.get("etag")
            last_modified = error.headers.get("Last-Modified") or previous.get("last_modified")
            encoding = previous.get("encoding", "utf-8")

        digest = hashlib.sha256(content).hexdigest()
        cache_path = self.cache_dir / digest
        with self.lock:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            if not cache_path.exists():
                cache_path.write_bytes(content)
            self.responses[url] = {
                "url": url,
                "sha256": digest,
                "etag": etag,
                "last_modified": last_modified,
                "observed_at": self.observed_at(),
                "encoding": encoding,
            }
        return content.decode(encoding, errors="replace")

    def write_manifest(self):
        manifest = {
            "schema_version": 1,
            "generated_at": self.generated_at,
            "responses": sorted(self.responses.values(), key=lambda response: response["url"]),
        }
        validate_source_manifest(manifest)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        return manifest


class CachedSourceReader:
    def __init__(self, cache_dir, manifest_path):
        self.cache_dir = Path(cache_dir)
        self.manifest_path = Path(manifest_path)
        if not self.manifest_path.exists():
            raise OSError(f"Source manifest is missing: {self.manifest_path}")
        with self.manifest_path.open(encoding="utf-8") as handle:
            manifest = json.load(handle)
        validate_source_manifest(manifest)
        self.generated_at = manifest["generated_at"]
        self.responses = {response["url"]: response for response in manifest["responses"]}

    def __call__(self, url):
        response = self.responses.get(url)
        if response is None:
            raise OSError(f"Source response is not recorded in the manifest: {url}")
        cache_path = self.cache_dir / response["sha256"]
        if not cache_path.exists():
            raise OSError(f"Cached source response is missing: {cache_path}")
        return cache_path.read_bytes().decode(response["encoding"], errors="replace")

    def latest_observed_at(self, urls=(), prefixes=()):
        exact_urls = set(urls)
        observed_at = [
            response["observed_at"]
            for response in self.responses.values()
            if response["url"] in exact_urls or any(response["url"].startswith(prefix) for prefix in prefixes)
        ]
        if not observed_at:
            raise ValueError("No cached source observations match the requested sources")
        return max(observed_at)
