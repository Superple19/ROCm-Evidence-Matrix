import re
from pathlib import Path

from .simple_index import version_key
from .source_adapter import monotonic_generated_at


def _rocm_version(version):
    match = re.search(r"(?:^|[.+-])rocm(\d+(?:\.\d+)+(?:[a-z]+\d+)?)", version)
    return match.group(1) if match else None


def _versions(artifacts):
    versions = {}
    for artifact in artifacts:
        versions.setdefault(artifact["version"], set()).add(artifact["python_tag"])
    return versions


def build_triton_observations(source, packages):
    observations = []
    for version, python_tags in _versions(packages.get("triton", [])).items():
        rocm_version = _rocm_version(version)
        if rocm_version is None:
            continue
        tags = sorted(tag for tag in python_tags if tag.startswith("cp"))
        if not tags:
            continue
        observations.append(
            {
                "id": ":".join(("triton", source.get("distribution_family", "therock"), source.get("platform", "unknown"), source["channel"], rocm_version, version, ",".join(tags))),
                "distribution_family": source.get("distribution_family", "therock"),
                "extension": "triton",
                "package_name": "triton",
                "platform": source.get("platform", "unknown"),
                "channel": source["channel"],
                "rocm_version": rocm_version,
                "version": version,
                "python_tags": tags,
                "artifact_available": True,
                "source_id": f"packages-{source['id']}",
            }
        )
    return observations


def build_triton_observations_from_history(history):
    observations = []
    sources = history.get("sources", {})
    for candidate in history.get("candidates", []):
        version = candidate.get("triton_version")
        rocm_version = _rocm_version(version or "")
        source = sources.get(candidate.get("source_id"), {})
        if not version or not rocm_version:
            continue
        tags = sorted(tag for tag in candidate.get("python_tags", []) if tag.startswith("cp"))
        if not tags:
            continue
        observations.append(
            {
                "id": ":".join(("triton", candidate.get("distribution_family", "therock"), candidate.get("platform", "unknown"), candidate["channel"], rocm_version, version, ",".join(tags))),
                "distribution_family": candidate.get("distribution_family", "therock"),
                "extension": "triton",
                "package_name": "triton",
                "platform": candidate.get("platform", "unknown"),
                "channel": candidate["channel"],
                "rocm_version": rocm_version,
                "version": version,
                "python_tags": tags,
                "artifact_available": True,
                "source_id": candidate.get("source_id") or source.get("id", ""),
            }
        )
    return observations


def merge_extension_history(existing, observations, observed_at):
    existing = existing or {"schema_version": 1, "generated_at": observed_at, "sources": {}, "extensions": []}
    records = {item["id"]: dict(item) for item in existing.get("extensions", [])}
    for item in observations:
        current = records.get(item["id"])
        if current is None:
            records[item["id"]] = {**item, "first_observed_at": observed_at, "last_observed_at": observed_at}
        else:
            current.update({key: value for key, value in item.items() if key not in {"id", "first_observed_at"}})
            current["last_observed_at"] = max(current.get("last_observed_at", observed_at), observed_at)
    latest = {}
    for item in records.values():
        key = (item["distribution_family"], item["extension"], item["platform"], item["channel"])
        current = latest.get(key)
        version = version_key(item["rocm_version"])
        if current is None or version > current:
            latest[key] = version
    for item in records.values():
        key = (item["distribution_family"], item["extension"], item["platform"], item["channel"])
        item["lifecycle"] = "current" if version_key(item["rocm_version"]) == latest[key] else "historical"
    return {
        "schema_version": 1,
        "generated_at": monotonic_generated_at(existing, observed_at),
        "sources": dict(existing.get("sources", {})),
        "extensions": sorted(records.values(), key=lambda item: (item["distribution_family"], item["extension"], item["platform"], item["channel"], version_key(item["rocm_version"]), version_key(item["version"]))),
    }


def rebuild_extension_history(output_dir, extension_history_path, observed_at, read_json, write_json, history=None):
    observations = []
    sources = {}
    for path in sorted(Path(output_dir).glob("*.json")):
        snapshot = read_json(path)
        source = snapshot["source"]
        sources[f"packages-{source['id']}"] = {**source, "observed_at": snapshot["last_observed_at"]}
        observations.extend(build_triton_observations(source, snapshot["packages"]))
    if history:
        observations.extend(build_triton_observations_from_history(history))
        sources.update({key: value for key, value in history.get("sources", {}).items() if key.startswith("packages-")})
    document = merge_extension_history(read_json(extension_history_path), observations, observed_at)
    document["sources"].update(sources)
    write_json(document, extension_history_path)
    return document


def render_extension_history(document):
    lines = [
        "<!-- Generated by rocm_evidence_matrix.collect. Do not edit manually. -->",
        "",
        "# Optional ROCm extension history",
        "",
        "Triton is tracked separately from core Torch candidates. These artifacts are optional compatibility evidence and do not prove resolver, runtime, or hardware success.",
        "",
        "| Distribution | Platform | Channel | Lifecycle | ROCm | Triton | Python tags |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in document.get("extensions", []):
        lines.append(f"| {item['distribution_family']} | {item['platform']} | {item['channel']} | {item['lifecycle']} | `{item['rocm_version']}` | `{item['version']}` | {', '.join(f'`{tag}`' for tag in item['python_tags'])} |")
    return "\n".join(lines) + "\n"
