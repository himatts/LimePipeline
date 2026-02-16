"""Material normalization rules for AI Asset Organizer.

Pure helpers that do not depend on bpy types.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from .asset_naming import build_material_name_with_scene_tag
from .material_naming import (
    ALLOWED_MATERIAL_TYPES,
    normalize_finish,
    normalize_material_type,
    parse_name as parse_material_name,
    parse_version as parse_material_version,
)
from .material_taxonomy import get_token_material_type_mapping


_CAMEL_TOKEN_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[0-9]+")
_METAL_HINT_TOKENS = {
    "metal",
    "metallic",
    "steel",
    "iron",
    "copper",
    "bronze",
    "aluminum",
    "aluminium",
    "chrome",
    "silver",
    "gold",
    "anodized",
    "galvanized",
}
_EMISSIVE_HINT_TOKENS = {"emissive", "emission", "glow", "neon", "led", "screen"}
_SPECIFIC_FINISH_HINTS = {"brushed", "anodized", "galvanized", "chrome", "rusty", "frosted"}
_CONTEXT_TAG_VALUE_RE = r"([A-Za-z][A-Za-z0-9_-]{0,23}(?:\s+[A-Za-z0-9_-]{1,23}){0,2})"
_CONTEXT_FORCE_TAG_PATTERNS = (
    re.compile(
        rf"(?:\bforce(?:d)?\s+tag\b|\btag\s+force\b|\bfixed\s+tag\b|\block(?:ed)?\s+tag\b|\betiqueta\s+forzada\b|\betiqueta\s+fija\b)\s*(?:que\s+diga|que\s+sea|sea|is|=|:|->|named|called)?\s*[\"']?{_CONTEXT_TAG_VALUE_RE}[\"']?",
        re.IGNORECASE,
    ),
)
_CONTEXT_MAT_PATTERN_TAG_RE = re.compile(r"\bMAT_([A-Za-z][A-Za-z0-9]{1,24})_[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9]+_V\d{2}\b")
_CONTEXT_OBJECT_FILTER_RE = re.compile(
    r"(?:material(?:es)?(?:\s+del|\s+de)?\s+objeto|materials?\s+(?:for|of)\s+object)\s+['\"]?([A-Za-z0-9_ -]{1,48})['\"]?",
    re.IGNORECASE,
)
_CONTEXT_TAG_TRAILING_STOPWORDS = {
    "for",
    "of",
    "material",
    "materials",
    "objeto",
    "object",
    "para",
    "de",
    "del",
}
_CONTEXT_NEGATIVE_TAG_REQUEST_RE = re.compile(
    r"\b(?:no|sin|without)\s+(?:un\s+|una\s+)?(?:tag|etiqueta)\b",
    re.IGNORECASE,
)
_CONTEXT_ADD_TAG_PATTERNS = (
    re.compile(
        r"(?:\bforce(?:d)?\s+tag\b|\btag\s+force\b|\bfixed\s+tag\b|\block(?:ed)?\s+tag\b)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:\badd\b|\binclude\b|\buse\b|\bput\b|\bdale\b|\bdar\b|\bagrega(?:r)?\b|\banade(?:r)?\b|\busa(?:r)?\b).{0,48}\b(?:tag|etiqueta)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:con|with)\s+(?:un\s+|una\s+)?(?:tag|etiqueta)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:tag|etiqueta)\b.{0,32}\b(?:relacionad[oa]|related)\b",
        re.IGNORECASE,
    ),
)

try:
    _MATERIAL_TYPE_TOKEN_MAP = {
        str(k).lower(): str(v)
        for k, v in dict(get_token_material_type_mapping() or {}).items()
    }
except Exception:
    _MATERIAL_TYPE_TOKEN_MAP = {}


def material_tokens_from_name(mat_name: str) -> set[str]:
    return {str(t or "").lower() for t in _CAMEL_TOKEN_RE.findall(mat_name or "") if t}


def material_likely_metal(profile: Dict[str, object], tokens: Sequence[str]) -> bool:
    token_set = {str(t or "").lower() for t in list(tokens or [])}
    if token_set.intersection(_METAL_HINT_TOKENS):
        return True
    metallic = float(profile.get("metallic", 0.0) or 0.0)
    if metallic >= 0.35:
        return True
    if bool(profile.get("has_metallic_input", False)):
        return True
    return False


def material_likely_emissive(profile: Dict[str, object], tokens: Sequence[str]) -> bool:
    token_set = {str(t or "").lower() for t in list(tokens or [])}
    strength = float(profile.get("emission_strength", 0.0) or 0.0)
    luma = float(profile.get("emission_luma", 0.0) or 0.0)
    energy = strength * luma
    if energy >= 0.06:
        return True
    if bool(profile.get("has_emission_input", False)) and strength >= 0.5:
        return True
    if token_set.intersection(_EMISSIVE_HINT_TOKENS) and energy >= 0.02:
        return True
    return False


def fallback_material_type_from_profile(
    profile: Dict[str, object],
    *,
    mat_name: str,
    allow_emissive: bool = True,
) -> str:
    token_set = material_tokens_from_name(mat_name)
    for token in token_set:
        mapped = _MATERIAL_TYPE_TOKEN_MAP.get(str(token).lower())
        if not mapped:
            continue
        mapped_norm = normalize_material_type(str(mapped))
        if mapped_norm == "Emissive" and not allow_emissive:
            continue
        if mapped_norm == "Metal" and not material_likely_metal(profile, token_set):
            continue
        if mapped_norm == "Emissive" and not material_likely_emissive(profile, token_set):
            continue
        if mapped_norm in ALLOWED_MATERIAL_TYPES:
            return mapped_norm
    if allow_emissive and material_likely_emissive(profile, token_set):
        return "Emissive"
    if material_likely_metal(profile, token_set):
        return "Metal"
    if float(profile.get("transmission", 0.0) or 0.0) >= 0.5:
        if "water" in token_set or "liquid" in token_set:
            return "Liquid"
        return "Glass"
    return "Plastic"


def refine_material_finish(
    material_type: str,
    finish: str,
    profile: Dict[str, object],
    source_tokens: set[str],
) -> str:
    finish_norm = normalize_finish(finish or "Generic")
    if not finish_norm:
        finish_norm = "Generic"
    finish_lower = finish_norm.lower()

    roughness = float(profile.get("roughness", 0.5) or 0.5)
    metallic = float(profile.get("metallic", 0.0) or 0.0)
    transmission = float(profile.get("transmission", 0.0) or 0.0)

    if material_type == "Emissive":
        if not material_likely_emissive(profile, source_tokens):
            return "Generic"
        if finish_lower in _SPECIFIC_FINISH_HINTS and finish_lower not in source_tokens:
            return "Generic"
        return finish_norm

    if material_type == "Metal":
        if finish_lower in {"brushed", "anodized", "galvanized", "chrome"} and finish_lower not in source_tokens:
            if roughness <= 0.2:
                return "Polished"
            if roughness >= 0.75:
                return "Rough"
            return "Generic"
        if finish_lower == "chrome" and (metallic < 0.9 or roughness > 0.2):
            return "Generic"
        if finish_lower in {"polished", "glossy"} and roughness > 0.35 and finish_lower not in source_tokens:
            return "Generic"
        if finish_lower in {"rough", "matte"} and roughness < 0.45 and finish_lower not in source_tokens:
            return "Generic"
        return finish_norm

    if material_type in {"Glass", "Liquid"}:
        if finish_lower == "clear" and not (transmission >= 0.55 and roughness <= 0.18):
            return "Generic"
        if finish_lower == "frosted" and not (transmission >= 0.45 and roughness >= 0.3):
            return "Generic"
        if finish_lower in _SPECIFIC_FINISH_HINTS and finish_lower not in source_tokens:
            return "Generic"
        return finish_norm

    if finish_lower in _SPECIFIC_FINISH_HINTS and finish_lower not in source_tokens:
        return "Generic"
    if finish_lower in {"polished", "glossy"} and roughness > 0.4 and finish_lower not in source_tokens:
        return "Generic"
    if finish_lower in {"rough", "matte"} and roughness < 0.35 and finish_lower not in source_tokens:
        return "Generic"
    return finish_norm


def apply_material_profile_guardrails(normalized: str, profile: Dict[str, object], source_name: str) -> str:
    parsed_final = parse_material_name(normalized)
    if not parsed_final:
        return normalized

    source_tokens = material_tokens_from_name(source_name)
    final_type = str(parsed_final.get("material_type") or "Plastic")
    final_finish = str(parsed_final.get("finish") or "Generic")
    scene_tag = str(parsed_final.get("scene_tag") or "")
    version_index = int(parsed_final.get("version_index") or 1)

    if final_type == "Metal" and not material_likely_metal(profile, source_tokens):
        final_type = fallback_material_type_from_profile(profile, mat_name=source_name, allow_emissive=True)
    if final_type == "Emissive" and not material_likely_emissive(profile, source_tokens):
        final_type = fallback_material_type_from_profile(profile, mat_name=source_name, allow_emissive=False)

    final_finish = refine_material_finish(final_type, final_finish, profile, source_tokens)
    return build_material_name_with_scene_tag(scene_tag, final_type, final_finish, version_index)


def normalize_tag_token(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", text)
    tokens = [t for t in cleaned.split() if t]
    if not tokens:
        return ""
    out: List[str] = []
    for token in tokens:
        if len(token) <= 3 and token.isupper():
            out.append(token)
        else:
            out.append(token[0].upper() + token[1:].lower())
    return "".join(out)[:24]


def _normalize_forced_tag_candidate(raw: str) -> str:
    candidate = (raw or "").strip()
    if not candidate:
        return ""
    candidate = re.split(r"[,;.\n\r]", candidate, maxsplit=1)[0].strip()
    tokens = [t for t in re.split(r"\s+", candidate) if t]
    while tokens and tokens[-1].lower() in _CONTEXT_TAG_TRAILING_STOPWORDS:
        tokens.pop()
    if not tokens:
        return ""
    return normalize_tag_token(" ".join(tokens))


def extract_context_material_tag_directive(context_text: str) -> Tuple[str, str]:
    text = (context_text or "").strip()
    if not text:
        return "", ""

    mat_match = _CONTEXT_MAT_PATTERN_TAG_RE.search(text)
    if mat_match:
        forced_tag = _normalize_forced_tag_candidate(mat_match.group(1))
    else:
        forced_tag = ""
        for pattern in _CONTEXT_FORCE_TAG_PATTERNS:
            tag_match = pattern.search(text)
            if not tag_match:
                continue
            forced_tag = _normalize_forced_tag_candidate(tag_match.group(1))
            if forced_tag:
                break

    object_filter = ""
    obj_match = _CONTEXT_OBJECT_FILTER_RE.search(text)
    if obj_match:
        object_filter = normalize_tag_token(obj_match.group(1))

    return forced_tag, object_filter


def context_requests_material_tag(context_text: str) -> bool:
    text = (context_text or "").strip()
    if not text:
        return False
    if _CONTEXT_NEGATIVE_TAG_REQUEST_RE.search(text):
        return False
    if _CONTEXT_MAT_PATTERN_TAG_RE.search(text):
        return True
    for pattern in _CONTEXT_FORCE_TAG_PATTERNS:
        if pattern.search(text):
            return True
    for pattern in _CONTEXT_ADD_TAG_PATTERNS:
        if pattern.search(text):
            return True
    return False


def force_material_name_tag(name: str, forced_tag: str) -> str:
    forced = normalize_tag_token(forced_tag)
    if not forced:
        return name
    parsed = parse_material_name((name or "").strip())
    if not parsed:
        return name
    material_type = str(parsed.get("material_type") or "Plastic")
    finish = str(parsed.get("finish") or "Generic")
    version_index = int(parsed.get("version_index") or 1)
    return build_material_name_with_scene_tag(forced, material_type, finish, version_index)


def fold_text_for_match(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def normalize_material_name_for_organizer(
    raw: str,
    *,
    profile: Optional[Dict[str, object]] = None,
    source_name: str = "",
    trace: Optional[List[str]] = None,
) -> str:
    notes = trace if trace is not None else []

    def _note(message: str) -> None:
        if trace is None:
            return
        text = (message or "").strip()
        if text:
            notes.append(text)

    def _split_tokens(value: str) -> List[str]:
        return [t for t in _CAMEL_TOKEN_RE.findall(value or "") if t]

    def _token_mapped_type(token: str) -> str:
        if not token:
            return "Plastic"
        direct = normalize_material_type(token)
        if direct != "Plastic":
            return direct
        mapped = _MATERIAL_TYPE_TOKEN_MAP.get(token.lower())
        if mapped:
            mapped_norm = normalize_material_type(mapped)
            if mapped_norm in ALLOWED_MATERIAL_TYPES:
                return mapped_norm
        return "Plastic"

    def _repair_components(material_type: str, finish: str) -> Tuple[str, str]:
        mtype = normalize_material_type(material_type or "Plastic")
        finish_tokens = _split_tokens(finish)

        if len(finish_tokens) > 1:
            head_type = normalize_material_type(finish_tokens[0])
            if head_type == mtype:
                _note("Removed duplicated material type token from finish")
                finish_tokens = finish_tokens[1:]

        if mtype == "Plastic" and finish_tokens:
            inferred = "Plastic"
            for token in finish_tokens:
                inferred = _token_mapped_type(token)
                if inferred != "Plastic":
                    break
            if inferred != "Plastic":
                _note(f"Inferred material type from finish tokens: {mtype} -> {inferred}")
                mtype = inferred
                if len(finish_tokens) > 1:
                    head_type = _token_mapped_type(finish_tokens[0])
                    if head_type == inferred:
                        _note("Removed inferred type token from finish")
                        finish_tokens = finish_tokens[1:]

        finish_raw = "".join(finish_tokens) if finish_tokens else finish
        finish_norm = normalize_finish(finish_raw)
        if not finish_norm:
            finish_norm = "Generic"
        return mtype, finish_norm

    text = (raw or "").strip()
    if not text:
        return ""

    parsed = parse_material_name(text)
    if parsed:
        _note("AI output already matches material schema")
        scene_tag = str(parsed.get("scene_tag") or "")
        material_type = str(parsed.get("material_type") or "Plastic")
        finish = str(parsed.get("finish") or "Generic")
        material_type, finish = _repair_components(material_type, finish)
        version_idx = int(parsed.get("version_index") or 1)
        normalized = build_material_name_with_scene_tag(scene_tag, material_type, finish, version_idx)
        if profile is not None:
            guarded = apply_material_profile_guardrails(normalized, profile, source_name)
            if guarded != normalized:
                _note("Applied shader-profile guardrails")
            return guarded
        return normalized

    cleaned = re.sub(r"[^A-Za-z0-9_ ]+", "_", text)
    if cleaned != text:
        _note("Sanitized invalid characters")
    cleaned = re.sub(r"[\s_]+", "_", cleaned).strip("_")
    if cleaned != text:
        _note("Collapsed spaces/underscores")
    if not cleaned:
        return ""
    parts = [p for p in cleaned.split("_") if p]
    if not parts:
        return ""
    if parts[0].upper() == "MAT":
        _note("Removed MAT prefix before reconstruction")
        parts = parts[1:]
    if not parts:
        return build_material_name_with_scene_tag("", "Plastic", "Generic", 1)

    version_idx = 1
    tail = parts[-1].upper()
    parsed_ver = parse_material_version(tail)
    if parsed_ver is not None:
        _note(f"Detected version token: V{parsed_ver:02d}")
        version_idx = parsed_ver
        parts = parts[:-1]
    if not parts:
        return build_material_name_with_scene_tag("", "Plastic", "Generic", version_idx)

    scene_tag = ""
    material_type = normalize_material_type(parts[0])
    if len(parts) >= 2:
        candidate_type = normalize_material_type(parts[1])
        if candidate_type in ALLOWED_MATERIAL_TYPES and candidate_type != "Plastic":
            scene_tag = parts[0]
            _note(f"Interpreted leading token as scene tag: {scene_tag}")
            material_type = candidate_type
            finish_src = "_".join(parts[2:]) if len(parts) > 2 else "Generic"
            _, finish = _repair_components(material_type, finish_src)
            normalized = build_material_name_with_scene_tag(scene_tag, material_type, finish, version_idx)
            if profile is not None:
                guarded = apply_material_profile_guardrails(normalized, profile, source_name)
                if guarded != normalized:
                    _note("Applied shader-profile guardrails")
                return guarded
            return normalized

    finish_src = "_".join(parts[1:]) if len(parts) > 1 else "Generic"
    material_type, finish = _repair_components(material_type, finish_src)
    normalized = build_material_name_with_scene_tag(scene_tag, material_type, finish, version_idx)
    if profile is not None:
        guarded = apply_material_profile_guardrails(normalized, profile, source_name)
        if guarded != normalized:
            _note("Applied shader-profile guardrails")
        return guarded
    return normalized


def material_status_from_trace(
    ai_raw: str,
    final_name: str,
    notes: Sequence[str],
) -> str:
    raw = (ai_raw or "").strip()
    final = (final_name or "").strip()
    if not raw or not final:
        return ""

    changed = raw != final
    semantic_changed = any("shader-profile guardrails" in str(note).lower() for note in list(notes or []))
    if semantic_changed:
        return "NORMALIZED_SEMANTIC"
    if changed:
        return "NORMALIZED_STRUCTURAL"
    return "AI_EXACT"


__all__ = [
    "normalize_material_name_for_organizer",
    "material_status_from_trace",
    "extract_context_material_tag_directive",
    "context_requests_material_tag",
    "force_material_name_tag",
    "fold_text_for_match",
    "material_tokens_from_name",
    "material_likely_metal",
    "material_likely_emissive",
    "apply_material_profile_guardrails",
    "refine_material_finish",
    "fallback_material_type_from_profile",
    "normalize_tag_token",
]
