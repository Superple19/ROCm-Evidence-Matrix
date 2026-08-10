"""Compatibility namespace for the renamed ROCm Evidence Matrix package."""

from pathlib import Path

from rocm_evidence_matrix import __version__

__path__ = [str(Path(__file__).resolve().parent.parent / "rocm_evidence_matrix")]
