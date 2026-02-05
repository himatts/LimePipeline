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
_NAME_TOKEN_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[0-9]+")
_OBJECT_VALID_RE = re.compile(r"^[A-Z][A-Za-z0-9]*(?:_(?:[A-Z][A-Za-z0-9]*|[0-9]+))*$")
_COLLECTION_VALID_RE = re.compile(r"^[A-Z][A-Za-z0-9]*(?:_(?:[A-Z][A-Za-z0-9]*|[0-9]+))*$")
_CAMEL_TOKEN_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z][a-z0-9]*")
_NUM_SUFFIX_RE = re.compile(r"^(?P<head>.+?)(?:_(?P<num>\d+))?$")
_VARIANT_TOKENS = {
    "small",
    "medium",
    "large",
    "xs",
    "s",
    "m",
    "l",
    "xl",
    "xxl",
    "xxxl",
    "short",
    "long",
    "tall",
    "wide",
    "high",
    "low",
    "left",
    "right",
    "front",
    "back",
    "top",
    "bottom",
    "upper",
    "lower",
    "inner",
    "outer",
    "near",
    "far",
}


def _pascalize_tokens(tokens: Iterable[str]) -> str:
    parts: list[str] = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if len(token) <= 3 and token.isupper():
            parts.append(token)
            continue
        if any(ch.isupper() for ch in token[1:]):
            parts.append(token[0].upper() + token[1:])
        else:
            parts.append(token[0].upper() + token[1:].lower())
    return "".join(parts)


def _alpha_tokens_to_segments(tokens: list[str]) -> list[str]:
    if not tokens:
        return []

    split_index = len(tokens)
    while split_index > 0 and tokens[split_index - 1].lower() in _VARIANT_TOKENS:
        split_index -= 1

    segments: list[str] = []
    if split_index > 0:
        segments.append(_pascalize_tokens(tokens[:split_index]))
    for token in tokens[split_index:]:
        segments.append(_pascalize_tokens([token]))
    return segments


def _tokenize_block(block: str) -> list[str]:
    return [t for t in _NAME_TOKEN_RE.findall(block or "") if t]


def normalize_object_name(raw: str, *, fallback: str = "Asset", max_len: int = 63) -> str:
    """Normalize a string to PascalCase segments separated by underscores.

    Rules:
    - Removes diacritics and non-ASCII compatible characters.
    - Splits on non-alphanumerics to define segment boundaries.
    - Each segment is PascalCase; numeric suffixes are isolated as `_NN`.
    - Ensures the name starts with a letter (prefixes fallback if needed).
    """
    s = strip_diacritics(str(raw or "")).strip()
    if not s:
        return fallback[:max_len]

    blocks = [t for t in _NON_ALNUM.split(s) if t]
    if not blocks:
        return fallback[:max_len]

    segments: list[str] = []
    for block in blocks:
        tokens = _tokenize_block(block)
        if not tokens:
            continue
        current_alpha: list[str] = []
        for token in tokens:
            if token.isdigit():
                segments.extend(_alpha_tokens_to_segments(current_alpha))
                current_alpha = []
                segments.append(token)
            else:
                current_alpha.append(token)
        segments.extend(_alpha_tokens_to_segments(current_alpha))

    if not segments:
        return fallback[:max_len]

    if not segments[0] or not segments[0][0].isalpha():
        segments.insert(0, _pascalize_tokens([fallback]))

    name = "_".join(segments)
    if len(name) > max_len:
        name = name[:max_len].rstrip("_")
    if not name:
        name = fallback[:max_len]
    return name


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

    match = _NUM_SUFFIX_RE.match(base)
    if match:
        head = match.group("head") or base
        num_str = match.group("num")
    else:
        head = base
        num_str = None

    width = len(num_str) if num_str else 2
    counter = int(num_str) if num_str else 1

    while True:
        counter += 1
        suffix = f"{counter:0{width}d}"
        trimmed_head = head[: max(1, max_len - (len(suffix) + 1))].rstrip("_")
        candidate = f"{trimmed_head}_{suffix}"
        if candidate not in used:
            return candidate


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

    match = _NUM_SUFFIX_RE.match(base)
    if match:
        head = match.group("head") or base
        num_str = match.group("num")
    else:
        head = base
        num_str = None

    width = len(num_str) if num_str else 2
    counter = int(num_str) if num_str else 1

    while True:
        counter += 1
        suffix = f"{counter:0{width}d}"
        trimmed_head = head[: max(1, max_len - (len(suffix) + 1))].rstrip("_")
        candidate = f"{trimmed_head}_{suffix}"
        if candidate not in used:
            return candidate


def asset_group_key_from_name(name: str) -> str:
    """Derive a stable grouping token from a PascalCase/underscore asset name."""
    normalized = normalize_object_name(name or "", fallback="Asset")
    head = normalized.split("_", 1)[0]
    match = _CAMEL_TOKEN_RE.match(head)
    if not match:
        return head or normalized
    token = match.group(0) or head or normalized
    if token.isdigit():
        return head or normalized
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
