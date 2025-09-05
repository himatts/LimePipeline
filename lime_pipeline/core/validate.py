from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .naming import RE_PROJECT_DIR, make_filename, resolve_project_name
from .paths import paths_for_type


def _glob_scene_exists(scenes_dir: Path, sc: int) -> bool:
    pattern = f"*SC{sc:03d}*.blend"
    for _ in scenes_dir.glob(pattern):
        return True
    return False


def validate_all(state: Any, prefs: Any):
    """Validate UI state and compute filename/paths.

    Returns a 6-tuple:
    (ok: bool, errors: list[str], warns: list[str], filename: str | None, target_path: Path | None, backups: Path | None)
    """
    errors: list[str] = []
    warns: list[str] = []
    filename: str | None = None
    target_path: Path | None = None
    backups: Path | None = None

    # Root directory
    root = Path(state.project_root) if getattr(state, "project_root", None) else None
    if not root or not root.exists():
        errors.append("Pick a valid project root folder")
        return False, errors, warns, filename, target_path, backups

    # Root must match pattern
    if not RE_PROJECT_DIR.match(root.name):
        errors.append("Root folder must match 'XX-##### Project Name'")

    # Revision letter
    rev = (getattr(state, "rev_letter", "") or "").strip().upper()
    if not (len(rev) == 1 and 'A' <= rev <= 'Z'):
        errors.append("Rev must be exactly 1 letter A–Z")

    # Project type and base paths
    try:
        _, folder_type, scenes, target_dir, backups = paths_for_type(root, state.project_type, rev, getattr(state, "sc_number", None))
    except Exception:
        errors.append("Select a valid Project Type")
        return False, errors, warns, filename, target_path, backups

    # Scene number validation (required except Base and Tmp)
    needs_sc = state.project_type not in {'BASE', 'TMP'}
    if needs_sc:
        sc = int(getattr(state, "sc_number", 0) or 0)
        if not (1 <= sc <= 999):
            errors.append("SC must be 001–999")
        else:
            free_mode = bool(getattr(state, "free_scene_numbering", False))
            if not free_mode and (sc % prefs.scene_step != 0):
                errors.append(f"SC must be a multiple of {prefs.scene_step}")
        if scenes and scenes.exists() and sc:
            if _glob_scene_exists(scenes, sc):
                errors.append(f"Scene SC{sc:03d} already exists")

    # Critical directories must exist to proceed
    ramv = root / r"2. Graphic & Media" / r"3. Rendering-Animation-Video"
    if not ramv.exists():
        errors.append("Critical directories missing; use 'Create missing folders'")
    if needs_sc and scenes and not scenes.exists():
        warns.append("Scenes directory missing; can be created")

    # Filename and target path
    try:
        proj_name = resolve_project_name(state)
        token_map = {'BASE': 'BaseModel', 'PV': 'PV', 'REND': 'Render', 'SB': 'SB', 'ANIM': 'Anim', 'TMP': 'Tmp'}
        token = token_map.get(state.project_type)
        filename = make_filename(proj_name, token, rev, getattr(state, "sc_number", None) if needs_sc else None) + ".blend"
        target_path = (target_dir or folder_type) / filename
    except Exception:
        # Likely due to invalid rev or project name
        pass

    # Duplicate target
    if target_path and target_path.exists():
        errors.append("Target .blend already exists")

    # Path length guard
    if target_path:
        plen = len(str(target_path))
        if plen > prefs.path_block_len:
            errors.append(f"Path too long ({plen} > {prefs.path_block_len})")
        elif plen > prefs.path_warn_len:
            warns.append(f"Long path warning ({plen} > {prefs.path_warn_len})")

    ok = len(errors) == 0
    return ok, errors, warns, filename, target_path, backups


