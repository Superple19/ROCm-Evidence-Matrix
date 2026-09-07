import json
from pathlib import Path

from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from .catalog import REQUIRED_ARTIFACT_IDS, build_catalog
from .extensions import render_extension_history
from .extension_catalog import render_extension_catalog
from .frameworks import render_framework_history, render_sdk_components
from .history import migrate_history, render_history
from .legacy import render_legacy_windows
from .legacy_linux import render_legacy_linux
from .matrix_render import render_compatibility_matrix
from .paths import LEGACY_LINUX, LEGACY_LINUX_DOC, LEGACY_STATUS, LEGACY_WINDOWS, LEGACY_WINDOWS_DOC, THEROCK_SNAPSHOTS, THEROCK_STATUS, first_existing
from .profile import validate_profile
from .render import render_snapshots
from .validation import (
    validate_compatibility_matrix,
    validate_collection_status,
    validate_documentation_snapshot,
    validate_extension_history,
    validate_extension_catalog,
    validate_extension_snapshot,
    validate_framework_history,
    validate_history,
    validate_legacy_linux,
    validate_legacy_windows,
    validate_sdk_components,
    validate_snapshot,
    validate_source_manifest,
    validate_version_history,
)
from .version_history import render_version_history


SCHEMA_VALIDATORS = {
    "compatibility-matrix.schema.json": validate_compatibility_matrix,
    "collection-status.schema.json": validate_collection_status,
    "documentation-snapshot.schema.json": validate_documentation_snapshot,
    "extension-history.schema.json": validate_extension_history,
    "extension-catalog.schema.json": validate_extension_catalog,
    "extension-snapshot.schema.json": validate_extension_snapshot,
    "framework-history.schema.json": validate_framework_history,
    "history.schema.json": validate_history,
    "legacy-linux.schema.json": validate_legacy_linux,
    "legacy-windows.schema.json": validate_legacy_windows,
    "package-snapshot.schema.json": validate_snapshot,
    "source-manifest.schema.json": validate_source_manifest,
    "sdk-components.schema.json": validate_sdk_components,
    "version-history.schema.json": validate_version_history,
    "profile.schema.json": validate_profile,
}


def read_json(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_json_schema(value, schema_path):
    schema = read_json(schema_path)
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator = validator_class(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(value), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(str(item) for item in error.path) or "$"
        raise ValueError(f"{schema_path.name} validation failed at {location}: {error.message}")


def validate_catalog(root: str | Path):
    root = Path(root)
    catalog_path = root / "data" / "catalog.json"
    catalog = read_json(catalog_path)
    validate_json_schema(catalog, root / "schemas" / "catalog.schema.json")
    if catalog.get("schema_version") != 1:
        raise ValueError("Unsupported catalog schema")
    artifact_ids = [artifact["id"] for artifact in catalog["artifacts"]]
    artifact_paths = [artifact["path"] for artifact in catalog["artifacts"]]
    if not artifact_ids:
        raise ValueError("Catalog has no artifacts")
    if len(artifact_ids) != len(set(artifact_ids)):
        raise ValueError("Catalog contains duplicate artifact IDs")
    if len(artifact_paths) != len(set(artifact_paths)):
        raise ValueError("Catalog contains duplicate artifact paths")
    missing = sorted(REQUIRED_ARTIFACT_IDS - set(artifact_ids))
    if missing:
        raise ValueError(f"Catalog is missing required artifacts: {', '.join(missing)}")
    expected = build_catalog(root)
    if catalog.get("artifacts") != expected["artifacts"]:
        raise ValueError("Catalog artifacts are stale; run rocm-matrix catalog")
    if catalog.get("dimensions") != expected["dimensions"]:
        raise ValueError("Catalog dimensions are stale; run rocm-matrix catalog")
    for artifact in catalog["artifacts"]:
        data_path = root / artifact["path"]
        schema_path = root / artifact["schema"]
        if not data_path.exists() or not schema_path.exists():
            raise ValueError(f"Catalog entry points to a missing file: {artifact['id']}")
        schema_name = schema_path.name
        validator = SCHEMA_VALIDATORS.get(schema_name)
        if validator is None:
            raise ValueError(f"No validator registered for {schema_name}")
        value = read_json(data_path)
        validate_json_schema(value, schema_path)
        if value.get("schema_version") != artifact["schema_version"]:
            raise ValueError(f"Schema version mismatch: {artifact['id']}")
        validator(value)


def validate_standalone_data(root):
    root = Path(root)
    validators = (
        ("data/observations/source-manifest.json", validate_source_manifest, "source-manifest.schema.json"),
        (LEGACY_STATUS, validate_collection_status, "collection-status.schema.json"),
        (THEROCK_STATUS, validate_collection_status, "collection-status.schema.json"),
    )
    for relative_path, validator, schema_name in validators:
        path = first_existing(root, relative_path)
        if path.exists():
            validator(read_json(path))
            validate_json_schema(read_json(path), root / "schemas" / schema_name)

def validate_profiles(root):
    root = Path(root)
    history = read_json(root / "data" / "history.json")
    source_ids = set((history or {}).get("sources", {}))
    documentation = read_json(root / "data" / "documentation.json")
    source_ids.update((documentation or {}).get("sources", {}))
    for path in sorted(first_existing(root, THEROCK_SNAPSHOTS).glob("*.json")):
        snapshot = read_json(path)
        source = snapshot.get("source", {})
        if source.get("enabled", True) is False:
            continue
        if source.get("id"):
            source_ids.add(f"packages-{source['id']}")
    for path in sorted((Path(root) / "profiles").rglob("*.json")):
        profile = read_json(path)
        validate_profile(profile)
        validate_json_schema(profile, root / "schemas" / "profile.schema.json")
        references = set(profile.get("evidence_refs", []))
        references.update(reference for constraint in profile.get("constraints", []) for reference in constraint.get("evidence_refs", []))
        for reference in references:
            if reference.startswith("source:") and reference.removeprefix("source:") not in source_ids:
                raise ValueError(f"Profile references unknown source evidence: {reference}")


def validate_schema_files(root):
    for path in sorted((Path(root) / "schemas").glob("*.json")):
        schema = read_json(path)
        validator_for(schema).check_schema(schema)


def validate_generated_documents(root):
    root = Path(root)
    data = root / "data"
    history = migrate_history(read_json(data / "history.json"))
    matrix = read_json(data / "matrix.json")
    legacy_windows = read_json(first_existing(root, LEGACY_WINDOWS))
    legacy_linux = read_json(first_existing(root, LEGACY_LINUX))
    version_history = read_json(data / "version-history.json")
    framework_history = read_json(data / "framework-history.json")
    sdk_components = read_json(data / "sdk-components.json")
    extension_history = read_json(data / "extension-history.json")
    extension_catalog = read_json(data / "extensions" / "catalog.json")
    snapshots = []
    for path in sorted(first_existing(root, THEROCK_SNAPSHOTS).glob("*.json")):
        if read_json(path).get("source", {}).get("enabled", True) is not False:
            snapshots.append(path)
    expected = {
        "compatibility-matrix.md": render_compatibility_matrix(matrix),
        "framework-history.md": render_framework_history(framework_history),
        "history.md": render_history(history),
        LEGACY_LINUX_DOC.removeprefix("docs/generated/"): render_legacy_linux(legacy_linux),
        LEGACY_WINDOWS_DOC.removeprefix("docs/generated/"): render_legacy_windows(legacy_windows),
        "package-availability.md": render_snapshots(snapshots),
        "sdk-components.md": render_sdk_components(sdk_components),
        "extension-history.md": render_extension_history(extension_history),
        "extension-catalog.md": render_extension_catalog(extension_catalog),
        "version-history.md": render_version_history(version_history),
    }
    output_dir = root / "docs" / "generated"
    actual_names = {path.relative_to(output_dir).as_posix() for path in output_dir.rglob("*.md")}
    if actual_names != set(expected):
        raise ValueError("Generated document set is stale")
    for name, content in expected.items():
        path = output_dir / name
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            raise ValueError(f"Generated document is stale: {name}")


def run_check(root="."):
    root = Path(root)
    checks = (
        ("schema files", lambda: validate_schema_files(root)),
        ("catalog and catalog artifacts", lambda: validate_catalog(root)),
        ("standalone evidence", lambda: validate_standalone_data(root)),
        ("profiles", lambda: validate_profiles(root)),
        ("generated documents", lambda: validate_generated_documents(root)),
    )
    errors = []
    for name, check in checks:
        try:
            check()
        except Exception as error:
            errors.append(f"{name}: {type(error).__name__}: {error}")
    if errors:
        raise SystemExit("CHECK FAILED\n" + "\n".join(f"- {error}" for error in errors))
    print(f"CHECK PASSED: {len(checks)} groups validated")


if __name__ == "__main__":
    run_check()
