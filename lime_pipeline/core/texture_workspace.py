"""Shared texture workspace helpers (no Blender dependency).

Keeps texture-organization path decisions consistent across operators.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from .naming import find_project_root
from .paths import get_ramv_dir


_LOCAL_TYPE_FOLDERS = frozenset(
    {
        "3D Base Model",
        "Proposal Views",
        "Renders",
        "Storyboard",
        "Animation",
        "tmp",
    }
)


def unique_paths(paths: Iterable[Path]) -> tuple[Path, ...]:
    """Return de-duplicated paths while preserving order."""
    out: list[Path] = []
    seen: set[str] = set()
    for raw in list(paths or []):
        if raw is None:
            continue
        try:
            p = raw.resolve()
        except Exception:
            p = raw
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return tuple(out)


def extra_protected_texture_roots() -> tuple[Path, ...]:
    """Return extra non-project texture libraries to keep untouched."""
    xpbr_root = Path.home() / "Documents" / "Blender Addons" / "XPBR"
    return unique_paths((xpbr_root,))


def infer_local_project_root_from_blend_path(blend_path: str | Path) -> Optional[Path]:
    """Infer local project root from a saved .blend path.

    Local layout expected:
    <local_root>/<Type Folder>/Rev X[/scenes]/file.blend
    """
    try:
        path = Path(blend_path)
    except Exception:
        return None

    raw = str(path).strip()
    if not raw:
        return None

    # Treat explicit .blend paths as files, even when they do not exist yet.
    start = path.parent if path.suffix.lower() == ".blend" else path
    chain = [start, *list(start.parents)]
    for current in chain:
        try:
            parent = current.parent
            if current.name.startswith("Rev ") and parent.name in _LOCAL_TYPE_FOLDERS:
                return parent.parent
        except Exception:
            continue
    return None


def deduce_texture_project_root(
    *,
    state_project_root: str,
    use_local_project: bool,
    blend_path: str,
) -> Optional[Path]:
    """Resolve project root for texture operators.

    In local mode, accepts project root even if the folder does not exist yet.
    """
    raw = (state_project_root or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if use_local_project:
            try:
                return p.resolve() if p.exists() else p
            except Exception:
                return p
        try:
            if p.exists():
                return p.resolve()
        except Exception:
            pass

    blend = (blend_path or "").strip()
    if not blend:
        return None

    try:
        root = infer_local_project_root_from_blend_path(blend) if use_local_project else find_project_root(blend)
        return root.resolve() if root is not None else None
    except Exception:
        return None


def deduce_texture_project_workspace(
    *,
    state_project_root: str,
    use_local_project: bool,
    blend_path: str,
) -> tuple[Optional[Path], bool]:
    """Resolve (project_root, local_mode) for texture operators.

    This is resilient to stale UI state:
    - In non-local mode, if no canonical shared root is detected, it falls back to
      local-layout inference and enables local_mode.
    """
    raw = (state_project_root or "").strip()
    local_mode = bool(use_local_project)

    if raw:
        p = Path(raw).expanduser()
        if local_mode:
            try:
                return (p.resolve() if p.exists() else p), True
            except Exception:
                return p, True

        try:
            detected = find_project_root(str(p))
            if detected is not None:
                return detected.resolve(), False
        except Exception:
            pass

        # Non-local mode without canonical project root: treat as local workspace root.
        try:
            return (p.resolve() if p.exists() else p), True
        except Exception:
            return p, True

    blend = (blend_path or "").strip()
    if not blend:
        return None, local_mode

    if local_mode:
        try:
            local_root = infer_local_project_root_from_blend_path(blend)
            return (local_root.resolve() if local_root is not None else None), True
        except Exception:
            return None, True

    # Preferred shared root detection first.
    try:
        shared_root = find_project_root(blend)
        if shared_root is not None:
            return shared_root.resolve(), False
    except Exception:
        pass

    # Fallback for local-like blends even if the local toggle is off.
    try:
        local_root = infer_local_project_root_from_blend_path(blend)
        if local_root is not None:
            return local_root.resolve(), True
    except Exception:
        pass

    return None, False


def resolve_texture_root(project_root: Optional[Path], *, local_mode: bool, blend_dir: Path) -> Path:
    """Return canonical texture root for current mode."""
    if project_root is not None:
        if local_mode:
            return project_root / "rsc" / "Textures"
        try:
            return get_ramv_dir(project_root) / "rsc" / "Textures"
        except Exception:
            pass
    return blend_dir / "rsc" / "Textures"
