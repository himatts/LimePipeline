"""
UI State Validation and Path Resolution

This module provides comprehensive validation for Lime Pipeline UI state and automatic
path resolution for project file placement. It validates project settings, computes
target paths, and ensures compliance with Lime Pipeline naming and organizational
conventions.

The validation system checks project root validity, revision letters, scene numbers,
directory structure compliance, and file path constraints before allowing file
creation or project operations to proceed.

Key Features:
- Complete UI state validation with detailed error reporting
- Automatic project path resolution following RAMV structure
- Scene number validation with step constraints and existence checking
- Project root validation with pattern matching and studio invariants
- Path length validation with configurable warning and error thresholds
- Duplicate file detection and prevention
- Integration with Lime Pipeline preferences and settings
- Comprehensive error categorization (errors vs warnings)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .naming import RE_PROJECT_DIR, make_filename, resolve_project_name, TOKENS_BY_PTYPE, find_project_root
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

    local_mode = bool(getattr(state, "use_local_project", False))

    if local_mode:
        local_name = (getattr(state, "local_project_name", "") or "").strip()
        if not local_name:
            errors.append("Enter a Local Project Name")

    # Root directory (accept subfolders and auto-detect project root)
    root_input = getattr(state, "project_root", None)
    root: Path | None = None
    if root_input:
        try:
            if local_mode:
                root = Path(root_input)
            else:
                # If user selected a deeper folder, walk up to find the actual project root
                detected = find_project_root(root_input)
                if detected is not None and detected.exists():
                    root = detected
                else:
                    cand = Path(root_input)
                    root = cand if cand.exists() else None
        except Exception:
            root = None

    if not root:
        errors.append("Set a Local Project Name to generate a project folder" if local_mode else "Pick a valid project root folder")
        return False, errors, warns, filename, target_path, backups
    if not local_mode and not root.exists():
        errors.append("Pick a valid project root folder")
        return False, errors, warns, filename, target_path, backups

    # Root must match pattern after detection
    if not local_mode and not RE_PROJECT_DIR.match(root.name):
        errors.append("Root folder must match 'XX-##### Project Name'")

    # Enforce root resides under default projects root (studio invariant)
    if not local_mode:
        try:
            default_root = Path(getattr(prefs, 'default_projects_root', '') or '')
            if default_root and default_root.exists():
                try:
                    # Python 3.11: use relative_to for robust check
                    _ = root.resolve().relative_to(default_root.resolve())
                except Exception:
                    errors.append(f"Project must be inside: {default_root}")
        except Exception:
            pass

    # Revision letter
    rev = (getattr(state, "rev_letter", "") or "").strip().upper()
    if not (len(rev) == 1 and 'A' <= rev <= 'Z'):
        errors.append("Rev must be exactly 1 letter A-Z")

    # Project type and base paths
    try:
        base_dir, folder_type, scenes, target_dir, backups = paths_for_type(
            root,
            state.project_type,
            rev,
            getattr(state, "sc_number", None),
            local=local_mode,
        )
    except Exception:
        errors.append("Select a valid Project Type")
        return False, errors, warns, filename, target_path, backups

    # Scene number validation (required except Base and Tmp)
    needs_sc = state.project_type not in {'BASE', 'TMP'}
    if needs_sc:
        sc = int(getattr(state, "sc_number", 0) or 0)
        if not (1 <= sc <= 999):
            errors.append("SC must be 001-999")
        else:
            free_mode = bool(getattr(state, "free_scene_numbering", False))
            if not free_mode and (sc % prefs.scene_step != 0):
                errors.append(f"SC must be a multiple of {prefs.scene_step}")
        if scenes and scenes.exists() and sc:
            if _glob_scene_exists(scenes, sc):
                errors.append(f"Scene SC{sc:03d} already exists")

    # Critical directories must exist to proceed
    if not local_mode and not base_dir.exists():
        errors.append("Critical directories missing; use 'Create missing folders'")
    if needs_sc and scenes and not scenes.exists():
        warns.append("Scenes directory missing; can be created")

    # Filename and target path
    try:
        proj_name = resolve_project_name(state)
        token = TOKENS_BY_PTYPE.get(state.project_type)
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


