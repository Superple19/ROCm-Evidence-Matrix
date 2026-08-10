"""Explicit, archive-only legacy source adapters."""

from ..legacy import build_legacy_candidates, collect_legacy_windows_sources, render_legacy_windows
from ..legacy_linux import build_legacy_linux_candidates, classify_legacy_linux_framework, collect_legacy_linux_sources, render_legacy_linux
from ..version_history import collect_legacy_version_history

__all__ = [
    "build_legacy_candidates",
    "build_legacy_linux_candidates",
    "classify_legacy_linux_framework",
    "collect_legacy_linux_sources",
    "collect_legacy_version_history",
    "collect_legacy_windows_sources",
    "render_legacy_linux",
    "render_legacy_windows",
]
