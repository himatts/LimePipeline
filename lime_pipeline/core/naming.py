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


