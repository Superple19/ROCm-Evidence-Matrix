"""Build and verify immutable catalog bundles."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from .catalog import REQUIRED_ARTIFACT_IDS as REQUIRED_CATALOG_ARTIFACT_IDS


BUNDLE_MANIFEST_SCHEMA = "schemas/catalog-bundle.schema.json"
CONTRACT_VERSION = 1
REQUIRED_ARTIFACT_IDS = {"catalog", *REQUIRED_CATALOG_ARTIFACT_IDS}
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_BUNDLE_VERSION_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")


class BundleError(ValueError):
    """Raised when a catalog bundle is invalid or cannot be built."""


def _read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BundleError(f"cannot read JSON: {path}") from error
    if not isinstance(value, dict):
        raise BundleError(f"expected a JSON object: {path}")
    return value


def _member_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise BundleError(f"invalid bundle path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ":" in path.parts[0] or any(part in {"", ".", ".."} for part in path.parts):
        raise BundleError(f"unsafe bundle path: {value!r}")
    return path.as_posix()


def _canonical_bytes(path):
    return Path(path).read_bytes().replace(b"\r\n", b"\n")


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


def _source_artifacts(root):
    root = Path(root).resolve()
    catalog = _read_json(root / "data" / "catalog.json")
    entries = catalog.get("artifacts")
    if not isinstance(entries, list):
        raise BundleError("data/catalog.json has no artifact list")

    artifacts = [
        {
            "id": "catalog",
            "path": "data/catalog.json",
            "schema_version": int(catalog.get("schema_version", 1)),
        }
    ]
    seen_ids = {"catalog"}
    seen_paths = {"data/catalog.json"}
    for entry in entries:
        if not isinstance(entry, dict):
            raise BundleError("data/catalog.json contains an invalid artifact")
        artifact_id = entry.get("id")
        relative = _member_path(entry.get("path"))
        schema_version = entry.get("schema_version")
        if not isinstance(artifact_id, str) or not artifact_id:
            raise BundleError("catalog artifact has no ID")
        if not isinstance(schema_version, int):
            raise BundleError(f"catalog artifact has no schema version: {artifact_id}")
        if artifact_id in seen_ids or relative in seen_paths:
            raise BundleError(f"duplicate catalog artifact: {artifact_id}")
        seen_ids.add(artifact_id)
        seen_paths.add(relative)
        artifacts.append({"id": artifact_id, "path": relative, "schema_version": schema_version})

    if not REQUIRED_ARTIFACT_IDS.issubset(seen_ids):
        missing = sorted(REQUIRED_ARTIFACT_IDS - seen_ids)
        raise BundleError(f"catalog is missing required bundle artifacts: {', '.join(missing)}")

    for path in sorted((root / "schemas").glob("*.json")):
        relative = path.relative_to(root).as_posix()
        if relative not in seen_paths:
            artifacts.append({"id": f"schema:{path.stem}", "path": relative, "schema_version": 1})
            seen_paths.add(relative)

    if BUNDLE_MANIFEST_SCHEMA not in seen_paths:
        raise BundleError(f"missing bundle manifest schema: {BUNDLE_MANIFEST_SCHEMA}")
    return root, sorted(artifacts, key=lambda item: item["path"])


def _artifact_path(root, relative):
    relative = _member_path(relative)
    path = root.joinpath(*PurePosixPath(relative).parts)
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise BundleError(f"bundle artifact escapes repository root: {relative}") from error
    if not path.is_file():
        raise BundleError(f"bundle artifact is missing: {relative}")
    return path


def _git_value(root, args):
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise BundleError(f"cannot read Git metadata: {' '.join(args)}")
    return completed.stdout.strip()


def _matrix_commit(root, value):
    value = value or os.environ.get("GITHUB_SHA") or _git_value(root, ["rev-parse", "HEAD"])
    if not _COMMIT_RE.fullmatch(value):
        raise BundleError("matrix_commit must be a full 40-character Git SHA")
    return value.lower()


def _timestamp(root, value, matrix_commit):
    value = value or _git_value(root, ["show", "-s", "--format=%cI", matrix_commit])
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise BundleError(f"generated_at is not an ISO-8601 timestamp: {value}") from error
    if parsed.tzinfo is None:
        raise BundleError("generated_at must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bundle_version(value, generated_at):
    value = value or generated_at[:10].replace("-", ".")
    if not _BUNDLE_VERSION_RE.fullmatch(value):
        raise BundleError("bundle_version must use YYYY.MM.DD")
    return value


def _manifest(root, artifacts, *, bundle_version, matrix_commit, generated_at, manager_min):
    manifest_artifacts = []
    for entry in artifacts:
        path = _artifact_path(root, entry["path"])
        content = _canonical_bytes(path)
        manifest_artifacts.append(
            {
                "id": entry["id"],
                "path": entry["path"],
                "schema_version": entry["schema_version"],
                "sha256": _sha256(content),
            }
        )
    return {
        "bundle_version": _bundle_version(bundle_version, generated_at),
        "contract_version": CONTRACT_VERSION,
        "matrix_commit": matrix_commit,
        "generated_at": generated_at,
        "artifacts": manifest_artifacts,
        "manager_compatibility": {"min": manager_min},
    }


def _manifest_bytes(manifest):
    return (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _validate_manifest(manifest, schema):
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator = validator_class(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(manifest), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(str(item) for item in error.path) or "$"
        raise BundleError(f"manifest validation failed at {location}: {error.message}")
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise BundleError(f"unsupported bundle contract: {manifest.get('contract_version')!r}")


def verify_bundle(path):
    path = Path(path)
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise BundleError("bundle contains duplicate entries")
            safe_names = {_member_path(name) for name in names}
            if "manifest.json" not in safe_names or BUNDLE_MANIFEST_SCHEMA not in safe_names:
                raise BundleError("bundle is missing manifest.json or its schema")
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            schema = json.loads(archive.read(BUNDLE_MANIFEST_SCHEMA).decode("utf-8"))
            if not isinstance(manifest, dict) or not isinstance(schema, dict):
                raise BundleError("bundle manifest and schema must be JSON objects")
            _validate_manifest(manifest, schema)
            artifacts = manifest.get("artifacts", [])
            artifact_paths = [item["path"] for item in artifacts]
            artifact_ids = [item["id"] for item in artifacts]
            if len(artifact_paths) != len(set(artifact_paths)) or len(artifact_ids) != len(set(artifact_ids)):
                raise BundleError("manifest contains duplicate artifact IDs or paths")
            if "manifest.json" in artifact_paths:
                raise BundleError("manifest.json cannot hash itself")
            expected_names = {"manifest.json", *artifact_paths}
            if safe_names != expected_names:
                raise BundleError("bundle entries do not match manifest artifacts")
            if not REQUIRED_ARTIFACT_IDS.issubset(set(artifact_ids)):
                raise BundleError("manifest is missing required bundle artifacts")
            for item in artifacts:
                relative = _member_path(item["path"])
                content = archive.read(relative)
                if _sha256(content) != item["sha256"]:
                    raise BundleError(f"artifact digest mismatch: {relative}")
            return manifest
    except (OSError, zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BundleError(f"cannot read catalog bundle: {path}") from error


def build_bundle(
    root=".",
    output="dist/catalog.zip",
    *,
    bundle_version=None,
    matrix_commit=None,
    generated_at=None,
    manager_min="0.1.0",
):
    root, artifacts = _source_artifacts(root)
    matrix_commit = _matrix_commit(root, matrix_commit)
    generated_at = _timestamp(root, generated_at, matrix_commit)
    manifest = _manifest(
        root,
        artifacts,
        bundle_version=bundle_version,
        matrix_commit=matrix_commit,
        generated_at=generated_at,
        manager_min=manager_min,
    )
    output = Path(output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        manifest_info = zipfile.ZipInfo("manifest.json", date_time=(1980, 1, 1, 0, 0, 0))
        manifest_info.create_system = 0
        manifest_info.external_attr = 0
        archive.writestr(manifest_info, _manifest_bytes(manifest))
        for entry in manifest["artifacts"]:
            info = zipfile.ZipInfo(entry["path"], date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, _canonical_bytes(_artifact_path(root, entry["path"])))
    verify_bundle(output)
    return output
