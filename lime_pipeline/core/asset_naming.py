"""Asset naming helpers for Lime Pipeline.

This module provides small, Blender-agnostic helpers used by tools that rename
scene assets (objects/materials). It intentionally avoids `bpy` imports so it
can be unit-tested outside Blender.
"""

from __future__ import annotations

import re
from typing import Iterable

from .naming import strip_diacritics
from .material_naming import (
    PREFIX as MAT_PREFIX,
    SEPARATOR as MAT_SEPARATOR,
    MAX_LENGTH as MAT_MAX_LENGTH,
    build_version,
    parse_name as parse_material_name,
)


_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")
_OBJECT_VALID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
_COLLECTION_VALID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
_CAMEL_TOKEN_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z][a-z0-9]*")


def normalize_object_name(raw: str, *, fallback: str = "Asset", max_len: int = 63) -> str:
    """Normalize a string to a CamelCase alphanumeric identifier.

    Rules:
    - Removes diacritics and non-ASCII compatible characters.
    - Splits on non-alphanumerics and joins tokens in CamelCase.
    - Ensures the name starts with a letter (prefixes fallback if needed).
    """
    s = strip_diacritics(str(raw or "")).strip()
    if not s:
        return fallback[:max_len]

    tokens = [t for t in _NON_ALNUM.split(s) if t]
    if not tokens:
        return fallback[:max_len]

    out: list[str] = []
    for token in tokens:
        if not token:
            continue
        # Preserve short acronyms (e.g., UV, HDR).
        if len(token) <= 3 and token.isupper():
            out.append(token)
            continue
        # Preserve internal CamelCase when detected.
        if any(ch.isupper() for ch in token[1:]):
            out.append(token[0].upper() + token[1:])
        else:
            out.append(token[0].upper() + token[1:].lower())

    name = "".join(out)
    if not name:
        name = fallback
    if not name[0].isalpha():
        name = f"{fallback}{name}"
    return name[:max_len]


def is_valid_object_name(name: str) -> bool:
    """Return True if name matches the strict object name convention."""
    if not name:
        return False
    return _OBJECT_VALID_RE.match(name) is not None


def ensure_unique_object_name(name: str, existing: Iterable[str], *, max_len: int = 63) -> str:
    """Return a unique object name by appending numeric suffixes when needed."""
    used = set(existing or [])
    base = normalize_object_name(name, max_len=max_len)
    if base not in used:
        return base

    suffix = 2
    while True:
        suffix_str = str(suffix)
        trimmed = base[: max(1, max_len - len(suffix_str))]
        candidate = f"{trimmed}{suffix_str}"
        if candidate not in used:
            return candidate
        suffix += 1


def normalize_collection_name(raw: str, *, fallback: str = "CollectionAsset", max_len: int = 63) -> str:
    """Normalize a collection name with the same strict policy as objects."""
    return normalize_object_name(raw, fallback=fallback, max_len=max_len)


def is_valid_collection_name(name: str) -> bool:
    """Return True if collection name matches the strict collection convention."""
    if not name:
        return False
    return _COLLECTION_VALID_RE.match(name) is not None


def ensure_unique_collection_name(name: str, existing: Iterable[str], *, max_len: int = 63) -> str:
    """Return a unique collection name by appending numeric suffixes when needed."""
    used = set(existing or [])
    base = normalize_collection_name(name, max_len=max_len)
    if base not in used:
        return base

    suffix = 2
    while True:
        suffix_str = str(suffix)
        trimmed = base[: max(1, max_len - len(suffix_str))]
        candidate = f"{trimmed}{suffix_str}"
        if candidate not in used:
            return candidate
        suffix += 1


def asset_group_key_from_name(name: str) -> str:
    """Derive a stable grouping token from a CamelCase-style asset name."""
    normalized = normalize_object_name(name or "", fallback="Asset")
    match = _CAMEL_TOKEN_RE.match(normalized)
    if not match:
        return normalized
    token = match.group(0) or normalized
    if token.isdigit():
        return normalized
    return token


def build_material_name_with_scene_tag(
    scene_tag: str,
    material_type: str,
    finish: str,
    version_index: int,
) -> str:
    """Build a material name `MAT_{SceneTag?}_{MaterialType}_{Finish}_{V##}`.

    The `scene_tag` component is optional; when empty it is omitted.
    The output is truncated (finish only) to satisfy the core max length.
    """
    tag = (scene_tag or "").strip()
    type_token = (material_type or "").strip()
    finish_token = (finish or "").strip()
    version_block = build_version(int(version_index or 1))

    prefix_parts = [MAT_PREFIX]
    if tag:
        prefix_parts.append(tag)
    prefix_parts.append(type_token)

    parts = prefix_parts + [finish_token, version_block]
    name = MAT_SEPARATOR.join(parts)
    if len(name) <= MAT_MAX_LENGTH:
        return name

    prefix_block = MAT_SEPARATOR.join(prefix_parts)
    head_len = len(prefix_block) + 2 + len(version_block)
    max_finish_len = max(1, MAT_MAX_LENGTH - head_len)
    truncated_finish = finish_token[:max_finish_len]
    return MAT_SEPARATOR.join(prefix_parts + [truncated_finish, version_block])


def bump_material_version_until_unique(universe: Iterable[str], proposed_name: str) -> str:
    """Ensure material name uniqueness by bumping the version token when possible."""
    used = set(universe or [])
    if proposed_name not in used:
        return proposed_name

    parsed = parse_material_name(proposed_name)
    if not parsed:
        base = proposed_name
        suffix = 2
        while f"{base}{MAT_SEPARATOR}{suffix}" in used:
            suffix += 1
        return f"{base}{MAT_SEPARATOR}{suffix}"

    scene_tag = parsed.get("scene_tag") or ""
    material_type = parsed.get("material_type") or ""
    finish = parsed.get("finish") or ""
    start_idx = int(parsed.get("version_index") or 1)

    idx = max(1, start_idx)
    for _ in range(0, 99):
        idx += 1
        candidate = build_material_name_with_scene_tag(scene_tag, material_type, finish, idx)
        if candidate not in used:
            return candidate

    return proposed_name
