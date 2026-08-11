"""Normalize extension artifacts into an evidence-backed catalog."""

import hashlib
import json
import re
from pathlib import Path

from .persistence import atomic_write_json
from .simple_index import normalize_package_name, version_key
from .source_adapter import monotonic_generated_at
from .validation import validate_extension_snapshot


EXTENSION_PACKAGES = {
    "bitsandbytes": ("bitsandbytes",),
    "flash-attention": ("flash-attn", "flash-attention", "flash_attention"),
    "aiter": ("aiter", "amd-aiter"),
    "sageattention": ("sageattention", "sage-attention"),
    "triton": ("triton",),
}
PACKAGE_TO_EXTENSION = {
    normalize_package_name(package): extension
    for extension, packages in EXTENSION_PACKAGES.items()
    for package in packages
}
_ROCM_RE = re.compile(r"(?:^|[.+-])rocm(?P<version>\d+(?:\.\d+)+(?:[a-z]+\d+)?)", re.IGNORECASE)
_REQUIREMENT_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*(.*)$")


def extension_candidate_id(extension, version, python_tag, platform_tag, source_id, artifact_url, abi_tag="unknown"):
    """Return a stable identity for one exact extension artifact candidate."""

    identity = {
        "artifact_url": str(artifact_url),
        "abi_tag": str(abi_tag),
        "extension": str(extension),
        "platform_tag": str(platform_tag),
        "python_tag": str(python_tag),
        "source_id": str(source_id),
        "version": str(version),
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    def safe(value):
        return str(value).replace(":", "_")
    return f"extension:{safe(extension)}:{safe(version)}:{safe(python_tag)}:{safe(platform_tag)}:{digest}"


def _source_record(source, observed_at):
    return {
        "id": source["id"],
        "url": source["url"],
        "distribution_family": source.get("distribution_family", "external"),
        "platform": source.get("platform", "unknown"),
        "channel": source.get("channel", "external"),
        "observed_at": observed_at,
    }


def extension_for_package(package_name):
    """Return the stable profile ID for a normalized package name."""

    return PACKAGE_TO_EXTENSION.get(normalize_package_name(package_name))


def _rocm_version(version):
    match = _ROCM_RE.search(str(version or ""))
    return match.group("version") if match else None


def _platform_tags(artifacts):
    return sorted({artifact.get("platform_tag", "unknown") for artifact in artifacts})


def _python_tags(artifacts):
    return sorted({artifact.get("python_tag", "unknown") for artifact in artifacts})


def _abi_tags(artifacts):
    return sorted({artifact.get("abi_tag", "unknown") for artifact in artifacts})


def _record_id(extension, source, version, python_tags, platform_tags):
    values = (
        "extension",
        extension,
        source.get("distribution_family", "external"),
        source.get("platform", "unknown"),
        source.get("channel", "external"),
        version,
        ",".join(python_tags),
        ",".join(platform_tags),
    )
    return ":".join(str(value).replace(":", "_") for value in values)


def _requirement_values(artifacts):
    requirements = sorted({
        str(requirement)
        for artifact in artifacts
        for requirement in artifact.get("requires_dist", ())
        if requirement
    })
    torch_constraints = []
    rocm_constraints = []
    hip_constraints = []
    for requirement in requirements:
        match = _REQUIREMENT_RE.match(requirement)
        if not match:
            continue
        package = normalize_package_name(match.group(1))
        if package in {"torch", "torchvision", "torchaudio"}:
            torch_constraints.append(requirement)
        elif package in {"rocm", "rocm-sdk", "rocm-sdk-core"}:
            rocm_constraints.append(requirement)
        elif package in {"hip", "hip-runtime", "hip-sdk"}:
            hip_constraints.append(requirement)
    return requirements, torch_constraints, rocm_constraints, hip_constraints


def _group_artifacts(source, package_name, artifacts):
    extension = extension_for_package(package_name)
    if not extension:
        return []
    grouped = {}
    for artifact in artifacts or ():
        version = artifact.get("version")
        if not version:
            continue
        grouped.setdefault(version, []).append(artifact)
    records = []
    source_id = f"packages-{source['id']}"
    for version, version_artifacts in grouped.items():
        normalized_artifacts = []
        for artifact in version_artifacts:
            normalized = dict(artifact)
            normalized.setdefault("build_tag", None)
            normalized.setdefault("requires_dist", [])
            normalized.setdefault("sha256", None)
            normalized["candidate_id"] = extension_candidate_id(
                extension,
                version,
                normalized.get("python_tag", "unknown"),
                normalized.get("platform_tag", "unknown"),
                source_id,
                normalized.get("url", ""),
                normalized.get("abi_tag", "unknown"),
            )
            normalized_artifacts.append(normalized)
        requirements, torch_constraints, rocm_constraints, hip_constraints = _requirement_values(normalized_artifacts)
        python_tags = _python_tags(normalized_artifacts)
        abi_tags = _abi_tags(normalized_artifacts)
        platform_tags = _platform_tags(normalized_artifacts)
        records.append(
            {
                "id": _record_id(extension, source, version, python_tags, platform_tags),
                "extension": extension,
                "package_name": normalize_package_name(package_name),
                "distribution_family": source.get("distribution_family", "external"),
                "platform": source.get("platform", "unknown"),
                "channel": source.get("channel", "external"),
                "lifecycle": "historical",
                "version": version,
                "python_tags": python_tags,
                "abi_tags": abi_tags,
                "platform_tags": platform_tags,
                "artifacts": sorted(normalized_artifacts, key=lambda artifact: artifact.get("filename", "")),
                "artifact_urls": sorted({artifact.get("url") for artifact in normalized_artifacts if artifact.get("url")}),
                "candidate_ids": sorted({artifact["candidate_id"] for artifact in normalized_artifacts}),
                "source_id": source_id,
                "rocm_version": _rocm_version(version),
                "requires_dist": requirements,
                "build_tags": sorted({artifact.get("build_tag") for artifact in normalized_artifacts if artifact.get("build_tag")}),
                "torch_constraints": torch_constraints,
                "rocm_constraints": rocm_constraints,
                "hip_constraints": hip_constraints,
                "gfx_targets": [],
                "artifact_available": True,
                "evidence_status": "artifact_available",
            }
        )
    return records


def build_extension_observations(snapshot, observed_at=None):
    """Extract only known extension packages from one package snapshot."""

    source = snapshot["source"]
    observed_at = observed_at or snapshot["last_observed_at"]
    observations = []
    for package_name, artifacts in sorted(snapshot.get("packages", {}).items()):
        observations.extend(_group_artifacts(source, package_name, artifacts))
    for item in observations:
        item["first_observed_at"] = observed_at
        item["last_observed_at"] = observed_at
    return observations


def _migrate_record(record):
    """Backfill candidate and metadata fields on records from older schemas."""

    migrated = dict(record)
    source_id = migrated.get("source_id", "unknown")
    artifacts = []
    for artifact in migrated.get("artifacts", ()):
        normalized = dict(artifact)
        normalized.setdefault("build_tag", None)
        normalized.setdefault("requires_dist", [])
        normalized.setdefault("sha256", None)
        normalized.setdefault(
            "candidate_id",
            extension_candidate_id(
                migrated.get("extension", "unknown"),
                migrated.get("version", "unknown"),
                normalized.get("python_tag", "unknown"),
                normalized.get("platform_tag", "unknown"),
                source_id,
                normalized.get("url", ""),
                normalized.get("abi_tag", "unknown"),
            ),
        )
        artifacts.append(normalized)
    migrated["artifacts"] = artifacts
    migrated["candidate_ids"] = sorted({artifact["candidate_id"] for artifact in artifacts})
    migrated.setdefault("abi_tags", _abi_tags(artifacts))
    requirements, torch_constraints, rocm_constraints, hip_constraints = _requirement_values(artifacts)
    migrated.setdefault("requires_dist", requirements)
    migrated.setdefault("build_tags", sorted({artifact.get("build_tag") for artifact in artifacts if artifact.get("build_tag")}))
    migrated.setdefault("rocm_constraints", rocm_constraints)
    migrated.setdefault("torch_constraints", torch_constraints)
    migrated.setdefault("hip_constraints", hip_constraints)
    return migrated


def merge_extension_catalog(existing, observations, observed_at):
    """Merge extension observations append-only and assign lifecycle labels."""

    existing = existing or {
        "schema_version": 1,
        "generated_at": observed_at,
        "sources": {},
        "extensions": [],
    }
    records = {item["id"]: _migrate_record(item) for item in existing.get("extensions", [])}
    for item in observations:
        current = records.get(item["id"])
        if current is None:
            records[item["id"]] = dict(item)
            continue
        current.update({key: value for key, value in item.items() if key not in {"id", "first_observed_at"}})
        current["last_observed_at"] = max(current.get("last_observed_at", observed_at), item["last_observed_at"])

    latest = {}
    for item in records.values():
        key = (item["extension"], item["package_name"], item["distribution_family"], item["platform"], item["channel"])
        current = latest.get(key)
        if current is None or version_key(item["version"]) > version_key(current["version"]):
            latest[key] = item
    for item in records.values():
        key = (item["extension"], item["package_name"], item["distribution_family"], item["platform"], item["channel"])
        item["lifecycle"] = "current" if item["id"] == latest[key]["id"] else "historical"

    return {
        "schema_version": 1,
        "generated_at": monotonic_generated_at(existing, observed_at),
        "sources": dict(existing.get("sources", {})),
        "extensions": sorted(
            records.values(),
            key=lambda item: (
                item["extension"],
                item["distribution_family"],
                item["platform"],
                item["channel"],
                version_key(item["version"]),
                item["id"],
            ),
        ),
    }


def merge_extension_history(existing, observations, observed_at):
    """Append extension observations without replacing prior versions."""

    existing = existing or {
        "schema_version": 1,
        "generated_at": observed_at,
        "sources": {},
        "extensions": [],
    }
    records = {item["id"]: _migrate_record(item) for item in existing.get("extensions", [])}
    for item in observations:
        current = records.get(item["id"])
        if current is None:
            records[item["id"]] = dict(item)
        else:
            current["last_observed_at"] = max(current.get("last_observed_at", observed_at), item.get("last_observed_at", observed_at))
    return {
        "schema_version": 1,
        "generated_at": monotonic_generated_at(existing, observed_at),
        "sources": dict(existing.get("sources", {})),
        "extensions": sorted(records.values(), key=lambda item: (item["extension"], version_key(item["version"]), item["id"])),
    }


def rebuild_extension_catalog(snapshot_dir, catalog_path, observed_at, read_json, extension_snapshot_dir=None, history_path=None):
    """Rebuild the extension catalog from normalized package snapshots offline."""

    observations = []
    sources = {}
    snapshot_paths = list(Path(snapshot_dir).glob("*.json"))
    if extension_snapshot_dir:
        snapshot_paths.extend(Path(extension_snapshot_dir).glob("*.json"))
    for path in sorted(set(snapshot_paths)):
        snapshot = read_json(path)
        if extension_snapshot_dir and Path(path).parent == Path(extension_snapshot_dir):
            validate_extension_snapshot(snapshot)
        source = snapshot["source"]
        observations.extend(build_extension_observations(snapshot, snapshot["last_observed_at"]))
        source_id = f"packages-{source['id']}"
        sources[source_id] = _source_record({**source, "id": source_id}, snapshot["last_observed_at"])
    existing = read_json(catalog_path) if Path(catalog_path).exists() else None
    document = merge_extension_catalog(existing, observations, observed_at)
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


def render_extension_catalog(document):
    """Render the machine-readable extension catalog for human review."""

    lines = [
        "# Extension artifact catalog",
        "",
        "> Artifact availability is not installation or runtime compatibility.",
        "",
        "| Extension | Version | Platform | Channel | Python | ABI | Wheel platform | Candidate IDs | Lifecycle | Evidence |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in document.get("extensions", []):
        lines.append(
            "| {extension} | {version} | {platform} | {channel} | {python} | {abi} | {tags} | {candidates} | {lifecycle} | {evidence} |".format(
                extension=item["extension"],
                version=item["version"],
                platform=item["platform"],
                channel=item["channel"],
                python=", ".join(item["python_tags"]),
                abi=", ".join(item.get("abi_tags", ())),
                tags=", ".join(item["platform_tags"]),
                candidates=", ".join(item.get("candidate_ids", ())),
                lifecycle=item["lifecycle"],
                evidence=item["evidence_status"],
            )
        )
    if len(lines) == 6:
        lines.append("| — | — | — | — | — | — | — | — | — | not_collected |")
    return "\n".join(lines) + "\n"
