import json
from datetime import datetime, timezone
from pathlib import Path


ARTIFACTS = (
    ("compatibility_matrix", "data/matrix.json", "schemas/compatibility-matrix.schema.json"),
    ("package_history", "data/history.json", "schemas/history.schema.json"),
    ("package_snapshots", "data/snapshots", "schemas/package-snapshot.schema.json"),
    ("documentation", "data/documentation.json", "schemas/documentation-snapshot.schema.json"),
    ("legacy_linux", "data/legacy-linux.json", "schemas/legacy-linux.schema.json"),
    ("version_history", "data/version-history.json", "schemas/version-history.schema.json"),
    ("resolver_verifications", "data/verifications/resolver.json", "schemas/resolver-verifications.schema.json"),
)


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def build_catalog(root="."):
    root = Path(root)
    artifacts = []
    platforms = set()
    families = set()
    channels = set()
    for artifact_id, relative_path, schema in ARTIFACTS:
        path = root / relative_path
        if path.is_dir():
            paths = sorted(path.glob("*.json"))
        else:
            paths = [path] if path.exists() else []
        for item in paths:
            value = read_json(item)
            source = value.get("source", {})
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
                }
            )
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "dimensions": {
            "distribution_families": sorted(families),
            "platforms": sorted(platforms),
            "channels": sorted(channels),
        },
        "artifacts": artifacts,
    }


def write_catalog(root=".", output="data/catalog.json"):
    path = Path(root) / output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_catalog(root), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return path
