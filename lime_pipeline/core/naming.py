"""
Project and Scene Naming Utilities

This module provides comprehensive utilities for Lime Pipeline project and scene naming
conventions, filename parsing, and project root detection. It handles the canonical
naming scheme used throughout the pipeline for consistent file organization.

The naming system supports project identification (XX-##### format), scene numbering
(SC###), revision tracking (Rev A-Z), and automatic project type detection from
filenames. It includes utilities for normalizing project names, parsing file metadata,
and finding project roots within directory structures.

Key Features:
- Project name normalization with diacritic removal and special character handling
- Canonical filename format: {ProjectName}_{Type}_SC{###}_Rev_{Letter}
- Bidirectional mapping between project types and filename tokens
- Automatic project root detection by walking up directory trees
- Scene metadata parsing from .blend filenames
- Windows reserved character filtering and path safety
- Integration with RAMV directory structure conventions
"""

from __future__ import annotations

import math
import re
import unicodedata
from pathlib import Path

from .paths import paths_for_type


# Extracts "Project Name" from "XX-##### Project Name"
RE_PROJECT_DIR = re.compile(r'^[A-Z]{2}-\d{5}\s+(.+)$')

# Windows reserved characters
WIN_RESERVED = r'<>:"/\\|?*'
RE_STRIP = re.compile(fr"[{re.escape(WIN_RESERVED)}\(\)'\"\.,;:!¿?_@#^`~\-\+]")


def strip_diacritics(text: str) -> str:
    normalized = unicodedata.normalize('NFKD', text)
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_tokens_keep_camel(tokens: list[str]) -> str:
    out: list[str] = []
    for token in tokens:
        if not token:
            continue
        if token[0].isalpha():
            token = token[0].upper() + token[1:]
        out.append(token)
    return ''.join(out)


def normalize_project_name(raw: str) -> str:
    stripped = raw.strip()
    m = RE_PROJECT_DIR.match(stripped)
    name = m.group(1) if m else stripped

    name = strip_diacritics(name)
    name = RE_STRIP.sub(' ', name)
    name = re.sub(r'\s+', ' ', name)
    tokens = [t for t in name.split(' ') if t]
    tokens = [t if any(c.isupper() for c in t[1:]) else t.title() for t in tokens]
    return _normalize_tokens_keep_camel(tokens)


def make_filename(project_name: str, token: str, rev: str, sc: int | None) -> str:
    rev_clean = (rev or '').strip().upper()
    assert len(rev_clean) == 1 and 'A' <= rev_clean <= 'Z'
    # Special cases with no SC numbering
    if token in {'BaseModel', 'Tmp'}:
        return f"{project_name}_{token}_Rev_{rev_clean}"
    if sc is None:
        raise ValueError("SC required for this type")
    return f"{project_name}_{token}_SC{sc:03d}_Rev_{rev_clean}"


def resolve_project_name(state) -> str:
    """Resolve the canonical project name from UI state.

    - If state.use_custom_name: normalize state.custom_name.
    - Else: normalize the basename of state.project_root.
    - Fallbacks handled gracefully (empty -> empty string).
    """
    if bool(getattr(state, "use_local_project", False)):
        raw_local = getattr(state, "local_project_name", "") or ""
        return normalize_project_name(raw_local)

    use_custom = bool(getattr(state, "use_custom_name", False))
    if use_custom:
        raw = getattr(state, "custom_name", "") or ""
        return normalize_project_name(raw)

    root = getattr(state, "project_root", None)
    base = ""
    if root:
        try:
            base = Path(root).name
        except Exception:
            base = str(root)
    return normalize_project_name(base)


# Central mapping between project type code and filename token
# Kept here to avoid duplication and allow parsing from filenames.
TOKENS_BY_PTYPE: dict[str, str] = {
    'BASE': 'BaseModel',
    'PV': 'PV',
    'REND': 'Render',
    'SB': 'SB',
    'ANIM': 'Anim',
    'TMP': 'Tmp',
}

PTYPE_BY_TOKEN: dict[str, str] = {v: k for k, v in TOKENS_BY_PTYPE.items()}


def detect_ptype_from_filename(path_or_name: str) -> str | None:
    """Detect the Lime Pipeline project type code from a .blend filename.

    Returns one of {'BASE','PV','REND','SB','ANIM','TMP'} or None if not matching
    the canonical naming scheme produced by make_filename().
    """
    try:
        name = Path(path_or_name).name
    except Exception:
        name = str(path_or_name or "")

    # Strip extension if present
    if name.lower().endswith('.blend'):
        name = name[:-6]

    # Patterns:
    # With SC: <ProjectName>_(PV|Render|SB|Anim)_SC###_Rev_X
    # No SC:  <ProjectName>_(BaseModel|Tmp)_Rev_X
    m_sc = re.match(r"^(.+?)_(PV|Render|SB|Anim)_SC(\d{3})_Rev_([A-Z])$", name)
    if m_sc:
        token = m_sc.group(2)
        return PTYPE_BY_TOKEN.get(token)

    m_nosc = re.match(r"^(.+?)_(BaseModel|Tmp)_Rev_([A-Z])$", name)
    if m_nosc:
        token = m_nosc.group(2)
        return PTYPE_BY_TOKEN.get(token)

    return None


def parse_blend_details(path_or_name: str) -> dict | None:
    """Parse key metadata from a .blend filename following Lime naming.

    Returns dict with keys: {
        'project_name': str,
        'ptype': str | None,  # 'BASE','PV','REND','SB','ANIM','TMP'
        'sc': int | None,
        'rev': str | None,   # single uppercase letter
    } or None if not parseable.
    """
    try:
        name = Path(path_or_name).name
    except Exception:
        name = str(path_or_name or "")
    if not name:
        return None
    if name.lower().endswith('.blend'):
        name = name[:-6]

    # With SC: <ProjectName>_(PV|Render|SB|Anim)_SC###_Rev_X
    m_sc = re.match(r"^(.+?)_(PV|Render|SB|Anim)_SC(\d{3})_Rev_([A-Z])$", name)
    if m_sc:
        return {
            'project_name': m_sc.group(1),
            'ptype': PTYPE_BY_TOKEN.get(m_sc.group(2)),
            'sc': int(m_sc.group(3)),
            'rev': m_sc.group(4),
        }

    # No SC:  <ProjectName>_(BaseModel|Tmp)_Rev_X
    m_nosc = re.match(r"^(.+?)_(BaseModel|Tmp)_Rev_([A-Z])$", name)
    if m_nosc:
        return {
            'project_name': m_nosc.group(1),
            'ptype': PTYPE_BY_TOKEN.get(m_nosc.group(2)),
            'sc': None,
            'rev': m_nosc.group(3),
        }
    return None


def find_project_root(selected_path: str) -> Path | None:
    """Walk up from selected_path to find a folder matching RE_PROJECT_DIR.

    Returns the matching Path or None.
    """
    try:
        path = Path(selected_path)
        if not path.exists():
            return None
        # If a file was passed, move to its parent
        if path.is_file():
            path = path.parent
        # Check current folder first
        if RE_PROJECT_DIR.match(path.name):
            return path
        # Walk up
        for parent in path.parents:
            if RE_PROJECT_DIR.match(parent.name):
                return parent
        return None
    except Exception:
        return None


def hydrate_state_from_filepath(state, force: bool = False) -> None:
    """Populate WindowManager LimePipelineState from current .blend filepath when possible.

    Sets: project_root, project_type, rev_letter, sc_number if not already set.
    Safe no-op on errors.
    """
    try:
        import bpy  # local import to avoid hard dependency at module import time
        from pathlib import Path as _P
        blend_path = _P(getattr(bpy.data, 'filepath', '') or '')
        if not blend_path:
            return
        info = parse_blend_details(blend_path.name)
        if info:
            # Project type
            if info.get('ptype') and (force or not getattr(state, 'project_type', None)):
                state.project_type = info['ptype']
            # Revision letter (+ keep rev_index in sync if present)
            if info.get('rev') and (force or not getattr(state, 'rev_letter', None)):
                state.rev_letter = info['rev']
                try:
                    state.rev_index = ord(info['rev']) - ord('A') + 1  # type: ignore[attr-defined]
                except Exception:
                    pass
            # Scene number
            try:
                current_sc = int(getattr(state, 'sc_number', 0) or 0)
            except Exception:
                current_sc = 0
            if info.get('sc') is not None and (force or current_sc == 0):
                state.sc_number = int(info['sc'])

        # Deduce project_root from folder structure using canonical RAMV segments
        try:
            from .paths import RAMV_DIR_1
        except Exception:
            RAMV_DIR_1 = '2. Graphic & Media'
        gm = None
        for parent in blend_path.parents:
            if parent.name == RAMV_DIR_1:
                gm = parent
                break
        if gm is not None and (force or not getattr(state, 'project_root', None)):
            root = gm.parent
            state.project_root = str(root)
    except Exception:
        pass


def build_next_scene_path(
    current_blend_path: str | Path,
    *,
    project_root: str | Path | None = None,
    local_mode: bool = False,
    state=None,
    prefs=None,
    scene_step: int | None = None,
    free_scene_numbering: bool | None = None,
):
    """Compute the next scene .blend path based on the current file naming.

    Relies on the canonical Lime naming helpers (parse_blend_details, make_filename,
    paths_for_type). Returns (target_path: Path, info: dict) where info includes:
        project_name, ptype, rev, current_sc, next_sc, root

    Raises ValueError with a descriptive message when the context cannot be resolved.
    """
    try:
        path = Path(current_blend_path)
    except Exception as ex:
        raise ValueError(f"Invalid blend path: {ex}") from ex

    if not path.name:
        raise ValueError("Current .blend filepath is empty; save the file first.")
    info = parse_blend_details(path.name)
    if not info:
        raise ValueError("Filename does not match Lime naming; cannot derive next scene.")

    project_name = info.get("project_name") or ""
    ptype = info.get("ptype")
    rev = (info.get("rev") or "").strip().upper()
    current_sc = info.get("sc")
    if ptype not in TOKENS_BY_PTYPE:
        raise ValueError("Project type not recognized from filename.")
    if not rev:
        raise ValueError("Revision letter missing in filename.")
    if current_sc is None:
        raise ValueError("Scene number (SC###) missing in filename; required for continuity.")

    # Resolve numbering mode (respect Scene Step unless free numbering is enabled)
    is_free = bool(
        free_scene_numbering
        if free_scene_numbering is not None
        else getattr(state, "free_scene_numbering", False)
    )

    step_val = scene_step
    if step_val is None and prefs is not None:
        try:
            step_val = int(getattr(prefs, "scene_step", 0) or 0)
        except Exception:
            step_val = None
    if step_val is None:
        try:
            import bpy  # Local import to avoid hard dependency during docs/tests

            addon_key = (__package__ or "lime_pipeline").split(".", 1)[0]
            addons = getattr(bpy.context.preferences, "addons", None)
            addon = addons.get(addon_key) if addons and hasattr(addons, "get") else None
            if addon is not None:
                step_val = int(getattr(addon.preferences, "scene_step", 0) or 0)
        except Exception:
            step_val = None
    if step_val is None or step_val <= 0:
        step_val = 1

    if is_free:
        next_sc = current_sc + 1
    else:
        next_sc = (math.floor(current_sc / step_val) + 1) * step_val

    token = TOKENS_BY_PTYPE[ptype]

    root = Path(project_root) if project_root else find_project_root(str(path))
    if root is None:
        raise ValueError("Project root could not be resolved from the current filepath.")

    _ramv, folder_type, _scenes, target_dir, _backups = paths_for_type(
        root,
        ptype,
        rev,
        next_sc,
        local=local_mode,
    )
    dest_dir = target_dir or folder_type
    filename = make_filename(project_name, token, rev, next_sc) + ".blend"
    target_path = dest_dir / filename

    return target_path, {
        "project_name": project_name,
        "ptype": ptype,
        "rev": rev,
        "current_sc": current_sc,
        "next_sc": next_sc,
        "root": root,
        "scene_step": step_val,
        "free_scene_numbering": is_free,
    }
