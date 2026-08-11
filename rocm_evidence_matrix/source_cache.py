import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .persistence import atomic_write_bytes, atomic_write_text
from .validation import validate_source_manifest


USER_AGENT = "rocm-evidence-matrix/0.1 (+https://github.com/Superple19/rocm-evidence-matrix)"


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _age_seconds(observed_at, checked_at):
    if not observed_at or not checked_at:
        return None
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        checked = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return max(0, int((checked - observed).total_seconds()))


class SourceCache:
    def __init__(self, cache_dir, manifest_path, timeout, opener=urlopen, observed_at=utc_now, github_token=None, sleep=time.sleep, github_retries=3):
        self.cache_dir = Path(cache_dir)
        self.manifest_path = Path(manifest_path)
        self.timeout = timeout
        self.opener = opener
        self.observed_at = observed_at
        self.github_token = github_token if github_token is not None else os.environ.get("GITHUB_TOKEN")
        self.sleep = sleep
        self.github_retries = github_retries
        self.generated_at = observed_at()
        self.lock = threading.Lock()
        self.responses = {}
        self.last_results = {}
        if self.manifest_path.exists():
            with self.manifest_path.open(encoding="utf-8") as handle:
                manifest = json.load(handle)
            validate_source_manifest(manifest)
            self.responses = {response["url"]: response for response in manifest.get("responses", [])}

    def __call__(self, url):
        with self.lock:
            previous = self.responses.get(url)
        headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json, application/json;q=0.9, text/html;q=0.8"}
        if self.github_token and url.lower().startswith("https://api.github.com/"):
            headers["Authorization"] = f"Bearer {self.github_token}"
        cached_path = self.cache_dir / previous["sha256"] if previous else None
        cached_content = None
        if cached_path and cached_path.exists():
            cached_content = cached_path.read_bytes()
            if hashlib.sha256(cached_content).hexdigest() != previous["sha256"]:
                cached_path = None
                cached_content = None
        if cached_path and cached_content is not None:
            if previous.get("etag"):
                headers["If-None-Match"] = previous["etag"]
            if previous.get("last_modified"):
                headers["If-Modified-Since"] = previous["last_modified"]

        request = Request(url, headers=headers)
        cache_status = "fresh"
        previous_observed_at = previous.get("observed_at") if previous else None
        for attempt in range(self.github_retries + 1):
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    content = response.read()
                    etag = response.headers.get("ETag")
                    last_modified = response.headers.get("Last-Modified")
                    encoding = response.headers.get_content_charset() or "utf-8"
                break
            except HTTPError as error:
                if error.code == 304 and previous is not None:
                    if cached_content is None:
                        raise OSError(f"Cached source response is missing: {cached_path}") from error
                    content = cached_content
                    if hashlib.sha256(content).hexdigest() != previous["sha256"]:
                        raise OSError(f"Cached source response hash mismatch: {cached_path}") from error
                    etag = error.headers.get("ETag") or previous.get("etag")
                    last_modified = error.headers.get("Last-Modified") or previous.get("last_modified")
                    encoding = previous.get("encoding", "utf-8")
                    cache_status = "revalidated"
                    break
                rate_limited = url.lower().startswith("https://api.github.com/") and error.code in {403, 429}
                if not rate_limited or attempt >= self.github_retries:
                    raise
                retry_after = error.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 2**attempt
                except ValueError:
                    delay = 2**attempt
                self.sleep(min(max(delay, 1.0), 30.0))

        digest = hashlib.sha256(content).hexdigest()
        cache_path = self.cache_dir / digest
        with self.lock:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            if not cache_path.exists():
                atomic_write_bytes(cache_path, content)
            self.responses[url] = {
                "url": url,
                "sha256": digest,
                "etag": etag,
                "last_modified": last_modified,
                "observed_at": self.observed_at(),
                "encoding": encoding,
            }
            checked_at = self.observed_at()
            self.last_results[url] = {
                "source_status": cache_status,
                "cache_age_seconds": _age_seconds(previous_observed_at, checked_at) if cache_status == "revalidated" else 0,
            }
        return content.decode(encoding, errors="replace")

    def metadata(self, url):
        """Return operational status for the most recent read of *url*."""
        result = self.last_results.get(url)
        if result is not None:
            return dict(result)
        response = self.responses.get(url)
        if response is None:
            return {"source_status": "not_cached", "cache_age_seconds": None}
        return {
            "source_status": "cached",
            "cache_age_seconds": _age_seconds(response.get("observed_at"), self.observed_at()),
        }

    def write_manifest(self):
        manifest = {
            "schema_version": 1,
            "generated_at": self.generated_at,
            "responses": sorted(self.responses.values(), key=lambda response: response["url"]),
        }
        validate_source_manifest(manifest)
        atomic_write_text(self.manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
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
        content = cache_path.read_bytes()
        if hashlib.sha256(content).hexdigest() != response["sha256"]:
            raise OSError(f"Cached source response hash mismatch: {cache_path}")
        return content.decode(response["encoding"], errors="replace")

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
