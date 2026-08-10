"""Stable repository paths for active and archived evidence."""

from pathlib import Path


THEROCK_SNAPSHOTS = "data/therock/snapshots"
THEROCK_CI_COVERAGE = "data/therock/ci/coverage.json"
THEROCK_CI_EVIDENCE = "data/therock/ci/evidence.json"
THEROCK_STATUS = "data/therock/status.json"
LEGACY_ARCHIVE = "data/legacy/archive"
LEGACY_WINDOWS = f"{LEGACY_ARCHIVE}/windows.json"
LEGACY_LINUX = f"{LEGACY_ARCHIVE}/linux.json"
LEGACY_STATUS = f"{LEGACY_ARCHIVE}/status.json"
LEGACY_DOCS_DIR = "docs/generated/legacy"
LEGACY_WINDOWS_DOC = f"{LEGACY_DOCS_DIR}/legacy-windows.md"
LEGACY_LINUX_DOC = f"{LEGACY_DOCS_DIR}/legacy-linux.md"


FALLBACK_PATHS = {
    THEROCK_SNAPSHOTS: ("data/snapshots",),
    THEROCK_CI_COVERAGE: ("data/ci-coverage.json",),
    THEROCK_CI_EVIDENCE: ("data/ci-evidence.json",),
    THEROCK_STATUS: ("data/status/therock.json",),
    LEGACY_WINDOWS: ("data/legacy-windows.json",),
    LEGACY_LINUX: ("data/legacy-linux.json",),
    LEGACY_STATUS: ("data/status/legacy.json",),
}


def first_existing(root, preferred, *fallbacks):
    root = Path(root)
    candidates = (preferred, *fallbacks, *FALLBACK_PATHS.get(preferred, ()))
    for relative in candidates:
        path = root / relative
        if path.exists():
            return path
    return root / preferred
