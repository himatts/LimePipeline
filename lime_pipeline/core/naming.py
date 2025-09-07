from __future__ import annotations

import re
import unicodedata
from pathlib import Path


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


def hydrate_state_from_filepath(state) -> None:
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
            if not getattr(state, 'project_type', None) and info.get('ptype'):
                state.project_type = info['ptype']
            if not getattr(state, 'rev_letter', None) and info.get('rev'):
                state.rev_letter = info['rev']
            try:
                current_sc = int(getattr(state, 'sc_number', 0) or 0)
            except Exception:
                current_sc = 0
            if current_sc == 0 and info.get('sc') is not None:
                state.sc_number = int(info['sc'])

        # Deduce project_root from folder structure: <root>/2. Graphic & Media/3. Rendering-Animation-Video/...
        gm = None
        for parent in blend_path.parents:
            if parent.name == '2. Graphic & Media':
                gm = parent
                break
        if gm is not None and not getattr(state, 'project_root', None):
            root = gm.parent
            state.project_root = str(root)
    except Exception:
        pass


