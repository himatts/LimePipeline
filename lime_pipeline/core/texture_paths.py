"""
Texture path helpers (no Blender dependencies).

Used by operators to classify whether an image comes from inside the current
project or from external user folders.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PathClassification:
    kind: str
    reason: str


def _safe_resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except Exception:
        return path


def is_subpath(candidate: Path, root: Path) -> bool:
    """Return True if candidate is within root (after resolving)."""
    try:
        candidate_r = _safe_resolve(candidate)
        root_r = _safe_resolve(root)
        return candidate_r.is_relative_to(root_r)  # type: ignore[attr-defined]
    except Exception:
        try:
            candidate_r = _safe_resolve(candidate)
            root_r = _safe_resolve(root)
            candidate_r.relative_to(root_r)
            return True
        except Exception:
            return False


def classify_path(
    abs_path: Path | None,
    *,
    project_root: Path | None,
    protected_roots: tuple[Path, ...] = (),
) -> PathClassification:
    """Classify an absolute filesystem path conservatively.

    Returns kinds:
    - "UNKNOWN": no usable path
    - "PROTECTED_ROOT": under protected_roots
    - "IN_PROJECT": within project_root
    - "EXTERNAL": outside project_root
    """

    if abs_path is None:
        return PathClassification(kind="UNKNOWN", reason="No resolved file path")

    if protected_roots:
        for root in protected_roots:
            if root and is_subpath(abs_path, root):
                return PathClassification(kind="PROTECTED_ROOT", reason=f"Under protected root: {root}")

    if project_root is None:
        return PathClassification(kind="UNKNOWN", reason="Project root not available")

    if is_subpath(abs_path, project_root):
        return PathClassification(kind="IN_PROJECT", reason="Path is inside project root")

    return PathClassification(kind="EXTERNAL", reason="Path is outside project root")

