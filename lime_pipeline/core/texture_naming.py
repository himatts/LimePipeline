"""
Texture naming helpers (no Blender dependencies).

This module centralizes the conventions for generating stable, collision-resistant
texture filenames when adopting external textures into a project-local folder.

Rules:
- Do not read Blender state here (no bpy imports).
- Keep output deterministic given the same inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from pathlib import Path
from typing import Iterable


_NON_ALNUM_RE = re.compile(r"[^0-9A-Za-z]+")
_MAT_VERSION_SUFFIX_RE = re.compile(r"_V\d+$", re.IGNORECASE)
_STEM_ALLOWED_RE = re.compile(r"[^0-9A-Za-z_]+")
_STEM_UNDERSCORES_RE = re.compile(r"_+")
_NUM_SUFFIX_RE = re.compile(r"(?:_|-)?(\d{1,3})$")


@dataclass(frozen=True, slots=True)
class TextureNameHints:
    material_name: str = ""
    map_type: str = ""
    source_path: str = ""


def _title_compact(tokens: Iterable[str]) -> str:
    parts = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        parts.append(token[0].upper() + token[1:])
    return "".join(parts)


def sanitize_token(value: str, fallback: str) -> str:
    """Return a compact alphanumeric token suitable for filenames."""
    tokens = [t for t in _NON_ALNUM_RE.split(value or "") if t]
    if not tokens:
        return fallback
    return _title_compact(tokens)


def sanitize_filename_stem(value: str, *, max_len: int = 64) -> str:
    """Sanitize a filename stem while preserving underscores.

    Allowed characters: letters, digits, underscore. Collapses repeated underscores.
    """
    text = (value or "").strip()
    if not text:
        return ""
    text = text.replace(" ", "_").replace("-", "_").replace(".", "_")
    text = _STEM_ALLOWED_RE.sub("", text)
    text = _STEM_UNDERSCORES_RE.sub("_", text).strip("_")
    max_len = max(8, min(int(max_len), 120))
    if len(text) > max_len:
        text = text[:max_len].rstrip("_")
    return text


def canonicalize_texture_stem(
    *,
    project_token: str,
    stem: str,
    map_type: str,
    default_number: int = 1,
) -> str:
    """Normalize texture stems to a shared structure.

    Structure:
      <ProjectToken>_<Descriptor>_<MapType>_<NN>

    - If stem already starts with the project token, it is reused (inserting an
      underscore boundary if needed).
    - If stem ends with digits, those are treated as the numeric suffix.
    - If no numeric suffix exists, default_number is used.
    """

    proj = sanitize_filename_stem(project_token or "", max_len=32) or "Project"
    raw = sanitize_filename_stem(stem or "", max_len=80) or "Texture"
    map_part = sanitize_filename_stem(map_type or "", max_len=24) or "Generic"

    num = int(default_number) if int(default_number) > 0 else 1
    width = 2
    base = raw
    m = _NUM_SUFFIX_RE.search(raw)
    if m:
        try:
            num = int(m.group(1))
            width = max(2, len(m.group(1)))
        except Exception:
            num = int(default_number) if int(default_number) > 0 else 1
            width = 2
        base = raw[: m.start()].rstrip("_")

    if base.startswith(proj):
        # Ensure boundary underscore: ReticleTrainerApp -> ReticleTrainer_App
        if len(base) > len(proj) and base[len(proj)] != "_":
            base = proj + "_" + base[len(proj) :].lstrip("_")
    else:
        base = f"{proj}_{base}" if base else proj

    suffix = f"{num:0{width}d}"
    # Avoid duplicate map tokens if descriptor already ends with it.
    if base.lower().endswith(f"_{map_part.lower()}"):
        return f"{base}_{suffix}"
    return f"{base}_{map_part}_{suffix}"


def material_stem(name: str) -> str:
    """Convert a material name into a stable stem for texture filenames."""
    value = (name or "").strip()
    if value.upper().startswith("MAT_"):
        value = value[4:]
    value = _MAT_VERSION_SUFFIX_RE.sub("", value)
    tokens = [t for t in _NON_ALNUM_RE.split(value) if t]
    if not tokens:
        return "Material"
    return "_".join(tokens)


def map_type_from_text(text: str) -> str:
    lower = (text or "").lower()
    if any(k in lower for k in ("normal", "_nrm", "_nor", "bump")):
        return "Normal"
    if any(k in lower for k in ("rough", "gloss")):
        return "Roughness"
    if any(k in lower for k in ("metal", "metallic")):
        return "Metallic"
    if any(k in lower for k in ("ao", "ambient occlusion", "occlusion")):
        return "AO"
    if any(k in lower for k in ("alpha", "opacity", "mask")):
        return "Alpha"
    if any(k in lower for k in ("height", "displace", "disp")):
        return "Height"
    if any(k in lower for k in ("emit", "emission")):
        return "Emission"
    if any(k in lower for k in ("color", "albedo", "diffuse", "base")):
        return "BaseColor"
    return "Generic"


def short_hash(value: str, *, length: int = 8) -> str:
    """Return a short hex hash for stable disambiguation."""
    digest = hashlib.sha1((value or "").encode("utf-8", errors="ignore")).hexdigest()
    length = max(4, min(int(length), 16))
    return digest[:length]


def propose_texture_filename(
    hints: TextureNameHints,
    *,
    ext: str | None = None,
    hash_length: int = 8,
) -> str:
    """Propose a filename like TX_<Material>_<Map>_<hash>.<ext>.

    The hash is derived from source_path by default to keep the name stable
    during Scan/Report even when the file isn't read.
    """

    material_part = sanitize_token(material_stem(hints.material_name), "Material")
    map_part = sanitize_token(hints.map_type or "Generic", "Generic")
    identity = (hints.source_path or f"{hints.material_name}|{hints.map_type}").strip()
    hash_part = short_hash(identity, length=hash_length)

    suffix = ext
    if not suffix:
        suffix = Path(hints.source_path).suffix if hints.source_path else ""
    suffix = (suffix or ".png").lower()
    if not suffix.startswith("."):
        suffix = "." + suffix

    return f"TX_{material_part}_{map_part}_{hash_part}{suffix}"
