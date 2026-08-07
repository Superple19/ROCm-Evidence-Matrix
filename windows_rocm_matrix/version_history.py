import json
import re
from datetime import datetime
from urllib.error import HTTPError
from urllib.parse import urljoin

from .documentation import parse_html_tables, parse_therock_windows_status
from .simple_index import version_key
from .source_adapter import run_source_adapter, utc_now


def version_series(version):
    match = re.match(r"(\d+\.\d+)", version)
    return match.group(1) if match else None


def is_therock_version(version):
    """TheRock replaced the legacy Windows release line starting with 7.10."""
    parts = version.split(".")
    return len(parts) >= 2 and (int(parts[0]) > 7 or (int(parts[0]) == 7 and int(parts[1]) >= 10))


def parse_release_date(value):
    for pattern in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Invalid ROCm release date: {value}")


def parse_rocm_release_history(html, base_url, source_id):
    releases = []
    for table in parse_html_tables(html):
        if not table["rows"]:
            continue
        headers = [cell["text"] for cell in table["rows"][0]["cells"]]
        if headers[:2] != ["Version", "Release date"]:
            continue
        for row in table["rows"][1:]:
            cells = row["cells"]
            if len(cells) < 2 or not re.fullmatch(r"\d+(?:\.\d+){1,2}", cells[0]["text"]):
                continue
            links = cells[0].get("links", [])
            releases.append(
                {
                    "version": cells[0]["text"],
                    "release_date": parse_release_date(cells[1]["text"]),
                    "documentation_url": urljoin(base_url, links[0]) if links else None,
                    "source_id": source_id,
                }
            )
    if not releases:
        raise ValueError("Could not find ROCm release history table")
    return sorted(releases, key=lambda item: version_key(item["version"]))


def parse_therock_releases(value, source_id):
    releases = []
    payload = json.loads(value)
    if not isinstance(payload, list):
        raise ValueError("TheRock releases response is not a list")
    for release in payload:
        match = re.fullmatch(r"therock-(\d+(?:\.\d+){1,2})", release.get("tag_name", ""))
        if not match:
            continue
        version = match.group(1)
        releases.append(
            {
                "version": version,
                "release_date": release.get("published_at", "")[:10] or None,
                "documentation_url": f"https://raw.githubusercontent.com/ROCm/TheRock/{release['tag_name']}/SUPPORTED_GPUS.md",
                "source_id": source_id,
            }
        )
    return sorted(releases, key=lambda item: version_key(item["version"]))


def parse_therock_version(value, source_id):
    version = json.loads(value).get("rocm-version")
    if not isinstance(version, str) or not re.fullmatch(r"\d+(?:\.\d+){1,2}", version):
        raise ValueError("TheRock version.json has no valid rocm-version")
    return {"version": version, "source_id": source_id}


def parse_documentation_branches(value, source_id):
    versions = []
    payload = json.loads(value)
    if not isinstance(payload, list):
        raise ValueError("Windows documentation branches response is not a list")
    for branch in payload:
        match = re.fullmatch(r"docs/(\d+(?:\.\d+){1,2})", branch.get("name", ""))
        if match:
            versions.append({"version": match.group(1), "source_id": source_id})
    if not versions:
        raise ValueError("No versioned Windows documentation branches found")
    return sorted(versions, key=lambda item: version_key(item["version"]))


def documentation_branch(version, branches):
    exact = next((item for item in branches if item["version"] == version), None)
    if exact:
        return exact["version"]
    series = version_series(version)
    matching = [item["version"] for item in branches if version_series(item["version"]) == series]
    return max(matching, key=version_key) if matching else None


def matching_release(version, releases):
    exact = next((item for item in releases if item["version"] == version), None)
    if exact:
        return exact
    series = version_series(version)
    matching = [item for item in releases if version_series(item["version"]) == series]
    return max(matching, key=lambda item: version_key(item["version"])) if matching else None


def release_record(family, version, observed_at, **values):
    return {
        "id": f"{family}:{version}",
        "distribution_family": family,
        "version": version,
        "channel": values.get("channel", "stable"),
        "release_date": values.get("release_date"),
        "windows_support": values.get("windows_support", "unknown"),
        "windows_package_available": values.get("windows_package_available", False),
        "windows_ci_verified": values.get("windows_ci_verified"),
        "documentation_status": values.get("documentation_status", "unknown"),
        "documentation_url": values.get("documentation_url"),
        "source_ids": sorted(set(values.get("source_ids", []))),
        "gpu_support_observations": values.get("gpu_support_observations", 0),
        "framework_support_observations": values.get("framework_support_observations", 0),
        "package_artifacts": values.get("package_artifacts", 0),
        "first_observed_at": observed_at,
        "last_observed_at": observed_at,
    }


def merge_version_history(existing, family, releases, gpu_support, sources, observed_at):
    existing = existing or {"schema_version": 1, "sources": {}, "releases": [], "therock_gpu_support": []}
    records = {}
    for item in existing.get("releases", []):
        item = dict(item)
        item.setdefault("channel", "nightly" if item["distribution_family"] == "therock" and item["version"] == "10.1.0" else "stable")
        item.setdefault("windows_package_available", item.get("package_artifacts", 0) > 0)
        item.setdefault("windows_ci_verified", None)
        records[item["id"]] = item
    for release in releases:
        current = records.get(release["id"])
        if current:
            release["first_observed_at"] = current["first_observed_at"]
            release["release_date"] = release["release_date"] or current["release_date"]
            release["source_ids"] = sorted(set(release["source_ids"]) | set(current["source_ids"]))
        records[release["id"]] = release
        if family == "therock":
            records.pop(f"legacy:{release['version']}", None)
    exact_records = {
        version_series(item["version"]): item
        for item in records.values()
        if item.get("distribution_family") == family and len(item["version"].split(".")) >= 3
    }
    for key, item in list(records.items()):
        if item.get("distribution_family") != family or len(item["version"].split(".")) != 2:
            continue
        exact = exact_records.get(version_series(item["version"]))
        if exact:
            exact["source_ids"] = sorted(set(exact["source_ids"]) | set(item["source_ids"]))
            for field in ("gpu_support_observations", "framework_support_observations", "package_artifacts"):
                exact[field] = max(exact[field], item[field])
            if exact["documentation_status"] == "archive_missing" and item["documentation_status"] == "available":
                exact["documentation_status"] = item["documentation_status"]
                exact["documentation_url"] = item["documentation_url"]
            records.pop(key, None)
    exact_versions = {release["version"] for release in releases}
    exact_series = {version_series(version) for version in exact_versions}
    records = {
        key: item
        for key, item in records.items()
        if item.get("distribution_family") != family
        or item["version"] not in exact_series
        or item["version"] in exact_versions
    }
    latest = {}
    for item in records.values():
        item_family = (item["distribution_family"], item["channel"])
        version = version_key(item["version"])
        if item_family not in latest or version > latest[item_family]:
            latest[item_family] = version
    for item in records.values():
            item["lifecycle"] = "current" if version_key(item["version"]) == latest[(item["distribution_family"], item["channel"])] else "historical"
    updated_gpu_versions = {item["version"] for item in gpu_support}
    existing_gpu = [
        item
        for item in existing.get("therock_gpu_support", [])
        if item["distribution_family"] != family or item["version"] not in updated_gpu_versions
    ]
    merged_sources = dict(existing.get("sources", {}))
    merged_sources.update(sources)
    return {
        "schema_version": 1,
        "generated_at": observed_at,
        "sources": {key: merged_sources[key] for key in sorted(merged_sources)},
        "releases": sorted(records.values(), key=lambda item: (item["distribution_family"], version_key(item["version"]))),
        "therock_gpu_support": sorted(existing_gpu + gpu_support, key=lambda item: (version_key(item["version"]), item["gfx"])),
    }


def collect_therock_version_history(config, fetch_text, current_status, existing=None, observed_at=None):
    observed_at = observed_at or utc_now()
    results = []
    source_records = {}

    def collect(source, parser):
        value, result = run_source_adapter(source, lambda: parser(fetch_text(source["url"]), source["id"]), observed_at)
        results.append(result)
        if value is not None:
            source_records[source["id"]] = {**source, "observed_at": observed_at}
        return value

    releases = collect(config["releases"], parse_therock_releases) or []
    current = collect(config["version"], parse_therock_version)
    records = []
    gpu_support = []
    previous = {item["id"]: item for item in (existing or {}).get("releases", [])}
    for release in releases:
        source_id = f"therock-supported-gpus-{release['version']}"
        source = {"id": source_id, "url": release["documentation_url"]}
        status = None
        try:
            status = parse_therock_windows_status(fetch_text(source["url"]), source_id)
            source_records[source_id] = {**source, "observed_at": observed_at}
            results.append({"source_id": source_id, "url": source["url"], "status": "passed", "observed_at": observed_at, "error": None})
            documentation_status = "available"
        except HTTPError as error:
            if error.code != 404:
                raise
            documentation_status = "archive_missing"
            results.append({"source_id": source_id, "url": source["url"], "status": "passed", "observed_at": observed_at, "error": None})
        except OSError:
            old = previous.get(f"therock:{release['version']}")
            documentation_status = old["documentation_status"] if old else "unknown"
            if old is None or documentation_status != "archive_missing":
                results.append({"source_id": source_id, "url": source["url"], "status": "failed", "observed_at": observed_at, "error": "OSError: historical support document is unavailable"})
        except ValueError as error:
            old = previous.get(f"therock:{release['version']}")
            documentation_status = old["documentation_status"] if old else "unknown"
            results.append({"source_id": source_id, "url": source["url"], "status": "failed", "observed_at": observed_at, "error": f"ValueError: {error}"})
        if status:
            for item in status:
                gpu_support.append({**item, "version": release["version"], "distribution_family": "therock"})
        records.append(
            release_record(
                "therock",
                release["version"],
                observed_at,
                release_date=release["release_date"],
                channel="stable",
                documentation_status=documentation_status,
                documentation_url=release["documentation_url"],
                source_ids=[release["source_id"], source_id] if status else [release["source_id"]],
                gpu_support_observations=len(status) if status is not None else (previous.get(f"therock:{release['version']}") or {}).get("gpu_support_observations", 0),
            )
        )
    if current:
        current_source = config["current_support"]
        source_records[current_source["id"]] = {**current_source, "observed_at": observed_at}
        records.append(
            release_record(
                "therock",
                current["version"],
                observed_at,
                documentation_status="available",
                documentation_url=current_source["url"],
                source_ids=[current["source_id"], current_source["id"]],
                gpu_support_observations=len(current_status),
                channel="nightly",
            )
        )
        gpu_support.extend({**item, "version": current["version"], "distribution_family": "therock"} for item in current_status)
    return merge_version_history(existing, "therock", records, gpu_support, source_records, observed_at), results


def collect_legacy_version_history(config, fetch_text, legacy, existing=None, observed_at=None):
    observed_at = observed_at or utc_now()
    results = []
    source_records = dict(legacy["sources"])

    def collect(source, parser):
        value, result = run_source_adapter(source, lambda: parser(fetch_text(source["url"]), source["url"], source["id"]), observed_at)
        results.append(result)
        if value is not None:
            source_records[source["id"]] = {**source, "observed_at": observed_at}
        return value

    release_history = collect(config["rocm_releases"], parse_rocm_release_history) or []
    branches_source = config["documentation_branches"]
    branches, result = run_source_adapter(branches_source, lambda: parse_documentation_branches(fetch_text(branches_source["url"]), branches_source["id"]), observed_at)
    results.append(result)
    branches = branches or []
    if branches:
        source_records[branches_source["id"]] = {**branches_source, "observed_at": observed_at}
    releases_by_version = {item["version"]: item for item in release_history}
    support_by_series = {item["rocm_series"]: item["windows_support"] for item in legacy["hip_sdk_releases"]}
    versions = set(support_by_series)
    versions.update(item["rocm_series"] for item in legacy["hip_sdk_gpu_support"])
    versions.update(item["rocm_version"] for item in legacy["pytorch_windows_support"])
    versions.update(item["release_id"] for item in legacy["artifact_releases"])
    # Preserve every official release-table row, including patch releases that
    # have no separate Windows support or package observation.
    versions.update(item["version"] for item in release_history)
    # A support source may identify a series (for example ``7.2``) while the
    # release table contains its exact patch releases. Keep the exact rows and
    # avoid presenting the series alias as a second release.
    exact_series = {version_series(item["version"]) for item in release_history}
    versions = {version for version in versions if version not in exact_series or version in releases_by_version}
    records = []
    for version in sorted(versions, key=version_key):
        series = version_series(version)
        release = releases_by_version.get(version) or matching_release(version, release_history)
        branch = documentation_branch(version, branches)
        support = support_by_series.get(series)
        gpu_count = sum(item["rocm_series"] == series for item in legacy["hip_sdk_gpu_support"])
        framework_count = sum(item["rocm_version"] == version for item in legacy["pytorch_windows_support"])
        package_count = sum(len(item["artifacts"]) for item in legacy["artifact_releases"] if item["release_id"] == version)
        source_ids = []
        if release:
            source_ids.append(release["source_id"])
        source_ids.extend(item["source_id"] for item in legacy["hip_sdk_releases"] if item["rocm_series"] == series)
        source_ids.extend(item["source_id"] for item in legacy["hip_sdk_gpu_support"] if item["rocm_series"] == series)
        source_ids.extend(item["source_id"] for item in legacy["pytorch_windows_support"] if item["rocm_version"] == version)
        source_ids.extend(item["source_id"] for item in legacy["artifact_releases"] if item["release_id"] == version)
        family = "therock" if release and is_therock_version(version) else "legacy"
        records.append(
            release_record(
                family,
                version,
                observed_at,
                release_date=release["release_date"] if release else None,
                channel="stable",
                windows_support="supported" if support is True else "unsupported" if support is False else "unknown",
                documentation_status="available" if branch else "archive_missing",
                documentation_url=f"https://rocm.docs.amd.com/projects/install-on-windows/en/docs-{branch}/" if branch else None,
                source_ids=source_ids,
                gpu_support_observations=gpu_count,
                framework_support_observations=framework_count,
                package_artifacts=package_count,
                windows_package_available=package_count > 0,
            )
        )
    history = merge_version_history(existing, "legacy", [item for item in records if item["distribution_family"] == "legacy"], [], source_records, observed_at)
    therock_records = [item for item in records if item["distribution_family"] == "therock"]
    if therock_records:
        history = merge_version_history(history, "therock", therock_records, [], source_records, observed_at)
    return history, results


def render_version_history(document):
    lines = [
        "<!-- Generated by windows_rocm_matrix.collect. Do not edit manually. -->",
        "",
        "# Windows ROCm version history",
        "",
        "Windows support, documentation availability, and observed package or test evidence are independent fields. A missing archive is not an unsupported release.",
        "",
        "| Distribution | Version | Channel | Lifecycle | Windows support | Windows package | Windows CI | Documentation | GPU observations | Framework observations | Package artifacts |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for item in document["releases"]:
        lines.append(
            f"| {item['distribution_family']} | `{item['version']}` | {item['channel']} | {item['lifecycle']} | {item['windows_support']} | "
            f"{item['windows_package_available']} | {item['windows_ci_verified']} | {item['documentation_status']} | {item['gpu_support_observations']} | {item['framework_support_observations']} | {item['package_artifacts']} |"
        )
    return "\n".join(lines).rstrip() + "\n"
