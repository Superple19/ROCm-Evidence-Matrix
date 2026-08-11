"""Collect extension package artifacts from explicit upstream sources."""

import json
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urlparse, urlunparse

from packaging.utils import InvalidWheelFilename, parse_wheel_filename

from .extension_catalog import extension_for_package
from .persistence import atomic_write_json
from .simple_index import normalize_package_name, parse_links, version_key
from .validation import validate_extension_snapshot


class GitHubPaginationError(ValueError):
    def __init__(self, message, *, pages_fetched, items_fetched, truncated):
        super().__init__(message)
        self.details = {
            "pages_fetched": pages_fetched,
            "items_fetched": items_fetched,
            "truncated": truncated,
        }


def _github_page_url(url, page, page_size):
    parsed = urlparse(url)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key not in {"page", "per_page"}]
    query.extend((("per_page", str(page_size)), ("page", str(page))))
    return urlunparse(parsed._replace(query=urlencode(query)))


def _collect_github_release_pages(source, fetch):
    options = source.get("pagination") or {}
    page_size = int(options.get("page_size", 100))
    max_pages = int(options.get("max_pages", 10))
    if not 1 <= page_size <= 100:
        raise ValueError(f"GitHub page_size must be between 1 and 100: {source['id']}")
    if not 1 <= max_pages <= 100:
        raise ValueError(f"GitHub max_pages must be between 1 and 100: {source['id']}")
    releases = []
    pages_fetched = 0
    cache_metadata = []
    for page in range(1, max_pages + 1):
        page_url = _github_page_url(source["url"], page, page_size)
        try:
            payload = json.loads(fetch(page_url))
            if hasattr(fetch, "metadata"):
                cache_metadata.append(fetch.metadata(page_url))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise GitHubPaginationError(
                f"GitHub release page {page} failed for {source['id']}: {error}",
                pages_fetched=pages_fetched,
                items_fetched=len(releases),
                truncated=True,
            ) from error
        if not isinstance(payload, list):
            raise GitHubPaginationError(
                f"GitHub releases response is not a list: {source['id']}",
                pages_fetched=pages_fetched,
                items_fetched=len(releases),
                truncated=True,
            )
        pages_fetched += 1
        releases.extend(payload)
        if len(payload) < page_size:
            return releases, _pagination_details(pages_fetched, len(releases), False, cache_metadata)
    raise GitHubPaginationError(
        f"GitHub release pagination exceeded {max_pages} pages: {source['url']}",
        pages_fetched=pages_fetched,
        items_fetched=len(releases),
        truncated=True,
    )


def _pagination_details(pages_fetched, items_fetched, truncated, cache_metadata=()):
    details = {"pages_fetched": pages_fetched, "items_fetched": items_fetched, "truncated": truncated}
    statuses = {item.get("source_status") for item in cache_metadata if item.get("source_status")}
    if statuses:
        details["source_status"] = "revalidated" if statuses == {"revalidated"} else "fresh"
    ages = [item.get("cache_age_seconds") for item in cache_metadata if item.get("cache_age_seconds") is not None]
    if ages:
        details["cache_age_seconds"] = max(ages)
    return details


def _artifact_sha256(url):
    fragment = parse_qs(urlparse(url).fragment)
    values = fragment.get("sha256") or ()
    return values[0] if values else None


def _wheel_artifact(url, filename, *, requires_dist=()):
    try:
        name, version, build, tags = parse_wheel_filename(filename)
    except (InvalidWheelFilename, ValueError):
        return None
    tag = next(iter(sorted(tags, key=str)), None)
    if tag is None:
        return None
    return {
        "filename": filename,
        "version": str(version),
        "python_tag": tag.interpreter,
        "abi_tag": tag.abi,
        "platform_tag": tag.platform,
        "build_tag": ".".join(str(value) for value in build if str(value)) if build else None,
        "requires_dist": sorted({str(value) for value in requires_dist if value}),
        "sha256": _artifact_sha256(url),
        "url": url,
    }


def _source_artifact(url, filename, package_name, *, requires_dist=()):
    stem = filename[:-7] if filename.endswith(".tar.gz") else filename[:-4]
    name, separator, version = stem.rpartition("-")
    if not separator or normalize_package_name(name) != normalize_package_name(package_name) or not version:
        return None
    return {
        "filename": filename,
        "version": version,
        "python_tag": "source",
        "abi_tag": "source",
        "platform_tag": "source",
        "build_tag": None,
        "requires_dist": sorted({str(value) for value in requires_dist if value}),
        "sha256": _artifact_sha256(url),
        "url": url,
    }


def _deduplicate(artifacts):
    records = {item["url"]: item for item in artifacts if item}
    return sorted(records.values(), key=lambda item: (version_key(item["version"]), item["filename"]))


def parse_simple_index(html, base_url, package_name):
    expected = normalize_package_name(package_name)
    artifacts = []
    for url, _ in parse_links(html, base_url):
        filename = unquote(Path(urlparse(url).path).name)
        if filename.endswith(".whl"):
            artifact = _wheel_artifact(url, filename)
            if artifact and normalize_package_name(filename.split("-", 1)[0]) == expected:
                artifacts.append(artifact)
        elif filename.endswith(".tar.gz"):
            artifacts.append(_source_artifact(url, filename, package_name))
    return _deduplicate(artifacts)


def parse_pypi_json(document, package_name):
    info = document.get("info") or {}
    current_version = str(info.get("version") or "")
    requires_dist = tuple(info.get("requires_dist") or ())
    artifacts = []
    for version, release_files in (document.get("releases") or {}).items():
        for release in release_files:
            filename = release.get("filename")
            url = release.get("url")
            if not filename or not url:
                continue
            if filename.endswith(".whl"):
                metadata = requires_dist if str(version) == current_version else ()
                artifact = _wheel_artifact(url, filename, requires_dist=metadata)
                if artifact:
                    artifact["sha256"] = release.get("digests", {}).get("sha256") or artifact.get("sha256")
                artifacts.append(artifact)
            elif filename.endswith(".tar.gz"):
                metadata = requires_dist if str(version) == current_version else ()
                artifact = _source_artifact(url, filename, package_name, requires_dist=metadata)
                if artifact:
                    artifact["sha256"] = release.get("digests", {}).get("sha256") or artifact.get("sha256")
                artifacts.append(artifact)
    return _deduplicate(artifacts)


def parse_github_releases(document, package_name):
    artifacts = []
    for release in document if isinstance(document, list) else []:
        for asset in release.get("assets", []):
            filename = asset.get("name")
            url = asset.get("browser_download_url")
            if not filename or not url:
                continue
            if filename.endswith(".whl"):
                artifacts.append(_wheel_artifact(url, filename))
            elif filename.endswith(".tar.gz"):
                artifacts.append(_source_artifact(url, filename, package_name))
    return _deduplicate(artifacts)


def parse_extension_source(source, body):
    kind = source.get("source_kind", "simple-index")
    package_name = source["package_name"]
    if kind == "pypi-json":
        return parse_pypi_json(json.loads(body), package_name)
    if kind == "github-releases":
        return parse_github_releases(json.loads(body), package_name)
    if kind == "simple-index":
        return parse_simple_index(body, source["url"], package_name)
    raise ValueError(f"Unsupported extension source kind: {kind}")


def build_extension_snapshot(source, artifacts, observed_at):
    package_name = normalize_package_name(source["package_name"])
    if not extension_for_package(package_name):
        raise ValueError(f"Unsupported extension package: {package_name}")
    snapshot_source = {
        "id": source["id"],
        "distribution_family": source.get("distribution_family", "external"),
        "platform": source.get("platform", "unknown"),
        "channel": source.get("channel", "external"),
        "url": source["url"],
    }
    return {
        "schema_version": 1,
        "last_observed_at": observed_at,
        "source": snapshot_source,
        "gfx_targets": [],
        "packages": {package_name: artifacts},
    }


def collect_extension_sources(sources, fetch, output_dir, observed_at):
    output_dir = Path(output_dir)
    results = []
    for source in sources:
        details = {}
        try:
            if source.get("source_kind") == "github-releases":
                releases, pagination = _collect_github_release_pages(source, fetch)
                details.update(pagination)
                artifacts = parse_github_releases(releases, source["package_name"])
            else:
                body = fetch(source["url"])
                artifacts = parse_extension_source(source, body)
            if hasattr(fetch, "metadata"):
                details.update(fetch.metadata(source["url"]))
            snapshot = build_extension_snapshot(source, artifacts, observed_at)
            validate_extension_snapshot(snapshot)
            output_path = output_dir / f"{source['id']}.json"
            atomic_write_json(snapshot, output_path)
            results.append({"source_id": source["id"], "status": "passed", "error": None, "artifact_count": len(artifacts), "details": details})
        except GitHubPaginationError as error:
            details.update(error.details)
            results.append({"source_id": source["id"], "status": "failed", "error": f"{type(error).__name__}: {error}", "details": details})
        except (OSError, ValueError, json.JSONDecodeError) as error:
            results.append({"source_id": source["id"], "status": "failed", "error": f"{type(error).__name__}: {error}", "details": details})
    return results


def rebuild_extension_catalog_from_sources(snapshot_dir, catalog_path, observed_at, read_json, existing=None, history_path=None):
    from .extension_catalog import build_extension_observations, merge_extension_catalog, merge_extension_history

    observations = []
    sources = {}
    for path in sorted(Path(snapshot_dir).glob("*.json")):
        snapshot = read_json(path)
        validate_extension_snapshot(snapshot)
        source = snapshot["source"]
        observations.extend(build_extension_observations(snapshot, snapshot["last_observed_at"]))
        source_id = f"packages-{source['id']}"
        sources[source_id] = {**source, "id": source_id, "observed_at": snapshot["last_observed_at"]}
    document = merge_extension_catalog(existing or (read_json(catalog_path) if Path(catalog_path).exists() else None), observations, observed_at)
    document["sources"].update(sources)
    atomic_write_json(document, catalog_path)
    if history_path:
        existing_history = read_json(history_path) if Path(history_path).exists() else None
        history = merge_extension_history(existing_history, observations, observed_at)
        history["sources"].update(sources)
        lifecycles = {item["id"]: item["lifecycle"] for item in document["extensions"]}
        for item in history["extensions"]:
            if item["id"] in lifecycles:
                item["lifecycle"] = lifecycles[item["id"]]
        atomic_write_json(history, history_path)
    return document
