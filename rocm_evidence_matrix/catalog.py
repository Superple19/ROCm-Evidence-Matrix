import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .persistence import atomic_write_json
from .paths import EXTENSION_ARTIFACT_HISTORY, EXTENSION_CATALOG, EXTENSION_SNAPSHOTS, LEGACY_LINUX, LEGACY_STATUS, LEGACY_WINDOWS, THEROCK_CI_COVERAGE, THEROCK_CI_EVIDENCE, THEROCK_SNAPSHOTS, THEROCK_STATUS, first_existing


ARTIFACTS = (
    ("compatibility_matrix", "data/matrix.json", "schemas/compatibility-matrix.schema.json"),
    ("package_history", "data/history.json", "schemas/history.schema.json"),
    ("package_snapshots", THEROCK_SNAPSHOTS, "schemas/package-snapshot.schema.json"),
    ("framework_history", "data/framework-history.json", "schemas/framework-history.schema.json"),
    ("extension_history", "data/extension-history.json", "schemas/extension-history.schema.json"),
    ("extension_catalog", EXTENSION_CATALOG, "schemas/extension-catalog.schema.json"),
    ("extension_artifact_history", EXTENSION_ARTIFACT_HISTORY, "schemas/extension-catalog.schema.json"),
    ("extension_snapshots", EXTENSION_SNAPSHOTS, "schemas/extension-snapshot.schema.json"),
    ("extension_status", "data/extensions/status.json", "schemas/collection-status.schema.json"),
    ("sdk_components", "data/sdk-components.json", "schemas/sdk-components.schema.json"),
    ("documentation", "data/documentation.json", "schemas/documentation-snapshot.schema.json"),
    ("legacy_windows", LEGACY_WINDOWS, "schemas/legacy-windows.schema.json"),
    ("legacy_linux", LEGACY_LINUX, "schemas/legacy-linux.schema.json"),
    ("legacy_archive_manifest", "data/legacy/archive/manifest.json", "schemas/legacy-archive-manifest.schema.json"),
    ("version_history", "data/version-history.json", "schemas/version-history.schema.json"),
    ("ci_coverage", THEROCK_CI_COVERAGE, "schemas/ci-coverage.schema.json"),
    ("ci_evidence", THEROCK_CI_EVIDENCE, "schemas/ci-evidence.schema.json"),
    ("source_manifest", "data/observations/source-manifest.json", "schemas/source-manifest.schema.json"),
    ("collection_status:legacy", LEGACY_STATUS, "schemas/collection-status.schema.json"),
    ("collection_status:therock", THEROCK_STATUS, "schemas/collection-status.schema.json"),
    ("resolver_verifications", "data/verifications/resolver.json", "schemas/resolver-verifications.schema.json"),
    ("comfyui_profile", "profiles/comfyui/profile.json", "schemas/profile.schema.json"),
    ("comfyui_extension_profiles", "profiles/comfyui/extensions", "schemas/profile.schema.json"),
)


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def build_catalog(root: str | Path = "."):
    root = Path(root)
    artifacts = []
    platforms = set()
    families = set()
    channels = set()
    timestamps = []
    for artifact_id, relative_path, schema in ARTIFACTS:
        path = first_existing(root, relative_path)
        if path.is_dir():
            paths = sorted(path.glob("*.json"))
        else:
            paths = [path] if path.exists() else []
        for item in paths:
            value = read_json(item)
            timestamp = value.get("generated_at") or value.get("last_observed_at")
            if timestamp:
                timestamps.append(timestamp)
            source = value.get("source", {})
            if value.get("distribution_family"):
                families.add(value["distribution_family"])
            if value.get("platform"):
                platforms.add(value["platform"])
            if value.get("channel"):
                channels.add(value["channel"])
            if source.get("platform"):
                platforms.add(source["platform"])
            if source.get("distribution_family"):
                families.add(source["distribution_family"])
            if source.get("channel"):
                channels.add(source["channel"])
            for record in value.get("releases", []) + value.get("candidates", []):
                if record.get("platform"):
                    platforms.add(record["platform"])
                if record.get("distribution_family"):
                    families.add(record["distribution_family"])
                if record.get("channel"):
                    channels.add(record["channel"])
            artifacts.append(
                {
                    "id": artifact_id if not path.is_dir() else f"{artifact_id}:{item.stem}",
                    "path": item.relative_to(root).as_posix(),
                    "schema": schema,
                    "schema_version": value.get("schema_version"),
                    "sha256": hashlib.sha256(item.read_bytes()).hexdigest(),
                }
            )
    return {
        "schema_version": 1,
        "generated_at": max(timestamps) if timestamps else utc_now(),
        "dimensions": {
            "distribution_families": sorted(families),
            "platforms": sorted(platforms),
            "channels": sorted(channels),
        },
        "artifacts": artifacts,
    }


def write_catalog(root: str | Path = ".", output: str | Path = "data/catalog.json"):
    path = Path(root) / output
    atomic_write_json(build_catalog(root), path)
    return path
