"""Material naming utilities for Lime Pipeline.

Defines helpers for the schema `MAT_{MaterialType}_{MaterialFinish}_{Version}`.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, Optional, Tuple

PREFIX = "MAT"
SEPARATOR = "_"
VERSION_PREFIX = "V"
MAX_LENGTH = 64
ALLOWED_MATERIAL_TYPES = [
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
# Backwards compatibility with older constants.
ALLOWED_FAMILIES = ALLOWED_MATERIAL_TYPES

INVALID_CHARS_PATTERN = re.compile(r"[^A-Za-z0-9_]")
NUMERIC_SUFFIX_PATTERN = re.compile(r"\.(\d{3})$")


# -----------------------------------------------------------------------------
# Normalization helpers
# -----------------------------------------------------------------------------

def normalize_material_type(value: str) -> str:
    """Return a valid material type value (defaults to Plastic)."""
    if not value:
        return "Plastic"
    normalized = value[0].upper() + value[1:].lower()
    return normalized if normalized in ALLOWED_MATERIAL_TYPES else "Plastic"


def normalize_finish(value: str) -> str:
    """Return a CamelCase alphanumeric finish or Generic."""
    if not value:
        return "Generic"
    cleaned = re.sub(r"[^0-9A-Za-z]", "", value)
    if not cleaned:
        return "Generic"
    if cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


# -----------------------------------------------------------------------------
# Version helpers
# -----------------------------------------------------------------------------

def parse_version(block: str) -> Optional[int]:
    """Return the integer index represented by a V## block."""
    if not block or len(block) < 2 or not block.startswith(VERSION_PREFIX):
        return None
    digits = block[1:]
    if not digits.isdigit():
        return None
    idx = int(digits)
    return idx if 1 <= idx <= 99 else None


def build_version(index: int) -> str:
    """Build a `V##` block from an integer index (clamped 1..99)."""
    idx = max(1, min(int(index or 1), 99))
    return f"{VERSION_PREFIX}{idx:02d}"


# -----------------------------------------------------------------------------
# Parsing / building
# -----------------------------------------------------------------------------

def parse_name(name: str) -> Optional[Dict[str, str]]:
    """Parse material names adhering to MAT_{MaterialType}_{MaterialFinish}_{Version}."""
    if not name or INVALID_CHARS_PATTERN.search(name):
        return None

    parts = name.split(SEPARATOR)
    if len(parts) < 4 or parts[0] != PREFIX:
        return None

    material_type_raw = parts[1]
    version_block = parts[-1]
    if len(parts) == 3:
        finish_raw = parts[2]
    else:
        finish_raw = SEPARATOR.join(parts[2:-1])

    version_idx = parse_version(version_block)
    if version_idx is None:
        return None

    material_type = normalize_material_type(material_type_raw)
    if material_type not in ALLOWED_MATERIAL_TYPES:
        return None

    finish = normalize_finish(finish_raw)
    if not finish:
        return None

    return {
        "material_type": material_type,
        "finish": finish,
        "version": build_version(version_idx),
        "version_index": version_idx,
    }


def build_name(material_type: str, version: int | str, finish: str) -> str:
    """Build a normalized material name from components."""
    material_type_normalized = normalize_material_type(material_type)
    finish_normalized = normalize_finish(finish)

    if isinstance(version, int):
        version_block = build_version(version)
    else:
        parsed_idx = parse_version(version)
        version_block = build_version(parsed_idx or 1)

    parts = [PREFIX, material_type_normalized, finish_normalized, version_block]
    name = SEPARATOR.join(parts)
    if len(name) <= MAX_LENGTH:
        return name

    # Truncate finish to satisfy max length, keeping at least one character.
    head_len = len(SEPARATOR.join([PREFIX, material_type_normalized])) + len(SEPARATOR) + len(version_block)
    max_finish_len = max(1, MAX_LENGTH - head_len)
    truncated_finish = finish_normalized[:max_finish_len]
    return SEPARATOR.join([PREFIX, material_type_normalized, truncated_finish, version_block])


def is_valid_name(name: str) -> bool:
    return parse_name(name) is not None


# -----------------------------------------------------------------------------
# Uniqueness helpers
# -----------------------------------------------------------------------------

def group_key(material_type: str, finish: str) -> Tuple[str, str]:
    """Normalized grouping key for version uniqueness."""
    return normalize_material_type(material_type), normalize_finish(finish)


def iter_group_versions(universe: Iterable[str], material_type: str, finish: str) -> Iterable[int]:
    """Yield version indices already used for (material_type, finish)."""
    target_type = normalize_material_type(material_type)
    target_finish = normalize_finish(finish)
    for name in universe:
        parsed = parse_name(name)
        if not parsed:
            continue
        if parsed["material_type"] != target_type:
            continue
        if normalize_finish(parsed["finish"]) != target_finish:
            continue
        version_index = parsed.get("version_index")
        if isinstance(version_index, int):
            yield version_index


def next_version_index(universe_names: Iterable[str], material_type: str, finish: str, start: int = 1) -> int:
    """Return the next available version index for the provided group."""
    used = set(iter_group_versions(universe_names, material_type, finish))
    idx = max(1, int(start))
    while idx in used:
        idx += 1
    return idx


def bump_version_until_unique(universe_names: Iterable[str], material_type: str, finish: str, start_idx: int = 1) -> str:
    """Increment version index until a unique name is found."""
    idx = max(1, int(start_idx))
    universe = set(universe_names)
    while True:
        candidate = build_name(material_type, idx, finish)
        if candidate not in universe:
            return candidate
        idx += 1


def strip_numeric_suffix(name: str) -> str:
    """Return name without trailing .### suffix commonly added by Blender."""
    match = NUMERIC_SUFFIX_PATTERN.search(name)
    if not match:
        return name
    return name[: -len(match.group(0))]


# -----------------------------------------------------------------------------
# Validation helpers
# -----------------------------------------------------------------------------

def detect_issues(name: str) -> list[str]:
    """Return human-readable issues describing why a name is out of spec."""
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
        issues.append("Does not match MAT_{MaterialType}_{MaterialFinish}_{Version} schema")
    else:
        if NUMERIC_SUFFIX_PATTERN.search(name):
            issues.append("Has numeric suffix (.###)")
    return issues


__all__ = [
    "ALLOWED_MATERIAL_TYPES",
    "ALLOWED_FAMILIES",
    "PREFIX",
    "build_name",
    "build_version",
    "bump_version_until_unique",
    "detect_issues",
    "group_key",
    "is_valid_name",
    "next_version_index",
    "normalize_finish",
    "normalize_material_type",
    "parse_name",
    "parse_version",
    "strip_numeric_suffix",
]
