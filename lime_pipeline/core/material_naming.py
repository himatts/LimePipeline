"""
Material naming utilities for Lime Pipeline.

Provides parsing, building and normalization helpers for the schemas:
Legacy: MAT_{TagEscena}_{Familia}_{Acabado}_{V##}
New (tagless): MAT_{Familia}_{Acabado}_{V##}
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, Optional, Tuple

PREFIX = "MAT"
SEPARATOR = "_"
VERSION_PREFIX = "V"
MAX_LENGTH = 64
ALLOWED_FAMILIES = [
    "Plastic",
    "Metal",
    "Glass",
    "Rubber",
    "Paint",
    "Wood",
    "Fabric",
    "Ceramic",
    "Emissive",
    "Stone",
    "Concrete",
    "Paper",
    "Leather",
    "Liquid",
]
SCENE_TAG_PATTERN = re.compile(r"^(S\d+|Demo|CU)$", re.IGNORECASE)
LEGACY_NAME_PATTERN = re.compile(
    rf"^{re.escape(PREFIX)}{re.escape(SEPARATOR)}"
    r"([A-Za-z0-9]+)"             # tag
    rf"{re.escape(SEPARATOR)}"
    r"([A-Za-z]+)"                # family
    rf"{re.escape(SEPARATOR)}"
    r"([A-Za-z0-9]+)"             # finish
    rf"{re.escape(SEPARATOR)}"
    r"([A-Za-z0-9]+)$"            # version block
)
NAME_PATTERN = re.compile(
    rf"^{re.escape(PREFIX)}{re.escape(SEPARATOR)}"
    r"([A-Za-z]+)"                # family
    rf"{re.escape(SEPARATOR)}"
    r"([A-Za-z0-9]+)"             # finish
    rf"{re.escape(SEPARATOR)}"
    r"([A-Za-z0-9]+)$"            # version block
)
INVALID_CHARS_PATTERN = re.compile(r"[^A-Za-z0-9_]")
NUMERIC_SUFFIX_PATTERN = re.compile(r"\.(\d{3})$")


# -----------------------------------------------------------------------------
# Helper utilities
# -----------------------------------------------------------------------------

def normalize_finish(value: str) -> str:
    """Sanitize finish tokens and provide a Generic fallback."""
    if not value:
        return "Generic"
    # Keep existing capitalization, only remove invalid chars and ensure CamelCase-like format
    cleaned = re.sub(r"[^0-9A-Za-z]", "", value)
    if not cleaned:
        return "Generic"
    # Capitalize first letter only if it's not already capitalized
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def normalize_family(value: str) -> str:
    """Return a valid family value, defaulting to Plastic."""
    if not value:
        return "Plastic"
    normalized = value[0].upper() + value[1:].lower()
    return normalized if normalized in ALLOWED_FAMILIES else "Plastic"


def parse_version(block: str) -> Optional[int]:
    """Return the integer index represented by a V## block."""
    if not block or len(block) < 2:
        return None
    if not block.startswith(VERSION_PREFIX):
        return None
    digits = block[1:]
    if not digits.isdigit():
        return None
    idx = int(digits)
    return idx if 1 <= idx <= 99 else None


def build_version(index: int) -> str:
    """Build a `V##` block from an integer index (clamped to 1..99)."""
    idx = max(1, min(int(index or 1), 99))
    return f"{VERSION_PREFIX}{idx:02d}"


def validate_scene_tag(tag: str) -> Optional[str]:
    if not tag:
        return None
    norm = tag.strip()
    if norm in RESERVED_SCENE_TAGS:
        return norm
    if not SCENE_TAG_PATTERN.match(norm):
        return None
    if norm[0].upper() != "S":
        return norm
    return f"S{int(norm[1:]):d}"


def group_key(tag: str, family: str, finish: str) -> Tuple[str, str, str]:
    """Return normalized tuple used to group versions (tag kept for legacy)."""
    return (
        validate_scene_tag(tag) or "S1",
        normalize_family(family),
        normalize_finish(finish),
    )


# -----------------------------------------------------------------------------
# Parsing and building
# -----------------------------------------------------------------------------

def parse_name(name: str) -> Optional[Dict[str, str]]:
    """Parse a material name into schema components."""
    if not name or len(name) > MAX_LENGTH:
        return None

    # Try legacy pattern (with tag)
    m = LEGACY_NAME_PATTERN.match(name)
    if m:
        raw_tag, raw_family, raw_finish, raw_version = m.groups()
        tag = validate_scene_tag(raw_tag)
        family = normalize_family(raw_family)
        version_idx = parse_version(raw_version)
        finish = normalize_finish(raw_finish)
        if tag is None or raw_family not in ALLOWED_FAMILIES or version_idx is None:
            return None
        return {
            "tag": tag,
            "familia": family,
            "acabado": finish,
            "version": build_version(version_idx),
            "version_index": version_idx,
        }

    # Try tagless pattern and assign a neutral tag for legacy callers
    m2 = NAME_PATTERN.match(name)
    if not m2:
        return None
    raw_family, raw_finish, raw_version = m2.groups()
    family = normalize_family(raw_family)
    version_idx = parse_version(raw_version)
    finish = normalize_finish(raw_finish)
    if raw_family not in ALLOWED_FAMILIES or version_idx is None:
        return None
    return {
        "tag": "S1",
        "familia": family,
        "acabado": finish,
        "version": build_version(version_idx),
        "version_index": version_idx,
    }


def build_name(tag: str, familia: str, acabado: str, version: str | int) -> str:
    """Build a normalized material name from components."""
    family_normalized = normalize_family(familia)
    finish_normalized = normalize_finish(acabado)

    if isinstance(version, int):
        version_block = build_version(version)
    else:
        parsed_idx = parse_version(version)
        version_block = build_version(parsed_idx or 1)

    parts = [PREFIX, family_normalized, finish_normalized, version_block]
    name = SEPARATOR.join(parts)
    if len(name) <= MAX_LENGTH:
        return name

    # Truncate finish to satisfy max length.
    # Ensure we always keep at least one character from finish.
    head_len = len(SEPARATOR.join([PREFIX, family_normalized])) + len(SEPARATOR) + len(version_block)
    max_finish_len = max(1, MAX_LENGTH - head_len)
    truncated_finish = finish_normalized[:max_finish_len]
    return SEPARATOR.join([PREFIX, tag_normalized, family_normalized, truncated_finish, version_block])


def is_valid_name(name: str) -> bool:
    return parse_name(name) is not None


# -----------------------------------------------------------------------------
# Legacy helpers
# -----------------------------------------------------------------------------

def detect_issues(name: str) -> list[str]:
    """Detect schema issues for legacy panels."""
    issues: list[str] = []
    if not name:
        issues.append("Empty name")
        return issues

    if len(name) > MAX_LENGTH:
        issues.append("Exceeds maximum length")

    if INVALID_CHARS_PATTERN.search(name):
        issues.append("Contains invalid characters (spaces, special chars)")

    parsed = parse_name(name)
    if parsed is None:
        issues.append("Does not match MAT_{Tag}_{Familia}_{Acabado}_{V##} schema")
    else:
        if NUMERIC_SUFFIX_PATTERN.search(name):
            issues.append("Has numeric suffix (.###)")
    return issues


def iter_group_versions(universe: Iterable[str], tag: str, familia: str, acabado: str) -> Iterable[int]:
    """Yield version indices already used for the provided group (tag ignored)."""
    key = group_key(tag, familia, acabado)
    pattern = re.compile(
        rf"^{PREFIX}_{re.escape(key[0])}_{re.escape(key[1])}_{VERSION_PREFIX}(\d{{2}})$"
    )
    for name in universe:
        match = pattern.match(name)
        if not match:
            continue
        try:
            yield int(match.group(1))
        except ValueError:
            continue


def next_version_index(universe_names: Iterable[str], tag: str, familia: str, acabado: str, start: int = 1) -> int:
    """Return the next available version index within the provided group."""
    used = set(iter_group_versions(universe_names, tag, familia, acabado))
    idx = max(1, int(start))
    while idx in used:
        idx += 1
    return idx


def bump_version_until_unique(universe_names: Iterable[str], tag: str, familia: str, acabado: str, start_idx: int = 1) -> str:
    """Build names by incrementing V## until unique within the universe."""
    idx = max(1, int(start_idx))
    universe = set(universe_names)
    while True:
        candidate = build_name(tag, familia, acabado, build_version(idx))
        if candidate not in universe:
            return candidate
        idx += 1


def strip_numeric_suffix(name: str) -> str:
    """Return name without trailing .### suffix commonly added by Blender."""
    match = NUMERIC_SUFFIX_PATTERN.search(name)
    if not match:
        return name
    return name[: -len(match.group(0))]


__all__ = [
    "ALLOWED_FAMILIES",
    "PREFIX",
    "build_name",
    "build_version",
    "detect_issues",
    "group_key",
    "is_valid_name",
    "normalize_family",
    "normalize_finish",
    "parse_name",
    "parse_version",
    "strip_numeric_suffix",
    "next_version_index",
    "bump_version_until_unique",
    "validate_scene_tag",
]
