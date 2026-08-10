"""Small, atomic persistence helpers for generated evidence files."""

import json
import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def atomic_write_text(path, content, encoding="utf-8"):
    atomic_write_bytes(path, content.encode(encoding))


def atomic_write_json(value, path):
    atomic_write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")
