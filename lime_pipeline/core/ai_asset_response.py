"""Helpers to parse and validate AI response payloads for asset organizer workflows."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Tuple


_ITEM_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_:-]{0,63}$")
_SAFE_HINT_CHAR_RE = re.compile(r"[^A-Za-z0-9_/\- ]+")
_SAFE_SLASH_RE = re.compile(r"/+")


def sanitize_target_collection_hint(raw: str, *, max_len: int = 240) -> str:
    value = str(raw or "").strip().replace("\\", "/")
    value = _SAFE_HINT_CHAR_RE.sub("", value)
    value = _SAFE_SLASH_RE.sub("/", value)
    value = "/".join(part.strip() for part in value.split("/") if part.strip())
    value = value.strip("/")
    if max_len > 0:
        value = value[:max_len].strip("/")
    return value


def parse_items_from_response(parsed: Optional[Dict[str, object]]) -> Optional[List[Dict[str, object]]]:
    """Extract a flat `items` list from multiple accepted AI response formats."""
    if not isinstance(parsed, dict):
        return None
    items = parsed.get("items")
    if isinstance(items, list):
        return items

    objects = parsed.get("objects")
    materials = parsed.get("materials")
    collections = parsed.get("collections")
    if isinstance(objects, list) or isinstance(materials, list) or isinstance(collections, list):
        combined: List[Dict[str, object]] = []
        if isinstance(objects, list):
            combined.extend(objects)
        if isinstance(materials, list):
            combined.extend(materials)
        if isinstance(collections, list):
            combined.extend(collections)
        return combined if combined else None
    return None


def validate_items_payload(
    items: Optional[List[Dict[str, object]]],
    *,
    expected_ids: Optional[Iterable[str]] = None,
    max_name_len: int = 96,
    max_hint_len: int = 240,
) -> Tuple[Optional[List[Dict[str, str]]], Optional[str]]:
    if not isinstance(items, list):
        return None, "AI response did not include a valid items list"

    out: List[Dict[str, str]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            return None, f"AI response item at index {index} is not an object"

        item_id_raw = item.get("id")
        name_raw = item.get("name")
        if not isinstance(item_id_raw, str) or not isinstance(name_raw, str):
            return None, f"AI response item at index {index} must include string 'id' and 'name'"

        item_id = item_id_raw.strip()
        name = name_raw.strip()
        if not item_id or not _ITEM_ID_RE.match(item_id):
            return None, f"AI response item has invalid id '{item_id_raw}'"
        if item_id in seen_ids:
            return None, f"AI response contains duplicated id '{item_id}'"
        if not name:
            return None, f"AI response item '{item_id}' has empty name"
        if max_name_len > 0 and len(name) > max_name_len:
            return None, f"AI response item '{item_id}' exceeds name length limit ({max_name_len})"

        entry: Dict[str, str] = {"id": item_id, "name": name}
        raw_hint = item.get("target_collection_hint")
        if raw_hint is not None:
            if not isinstance(raw_hint, str):
                return None, f"AI response item '{item_id}' has non-string target_collection_hint"
            hint = sanitize_target_collection_hint(raw_hint, max_len=max_hint_len)
            if raw_hint.strip() and not hint:
                return None, f"AI response item '{item_id}' has invalid target_collection_hint"
            if hint:
                entry["target_collection_hint"] = hint

        out.append(entry)
        seen_ids.add(item_id)

    if expected_ids is not None:
        expected_list = [str(value or "").strip() for value in list(expected_ids)]
        expected_list = [value for value in expected_list if value]
        expected_set = set(expected_list)
        if len(expected_set) != len(expected_list):
            return None, "Internal error: expected IDs contain duplicates"
        missing = sorted(expected_set.difference(seen_ids))
        unexpected = sorted(seen_ids.difference(expected_set))
        if missing or unexpected:
            if missing and unexpected:
                return None, (
                    "AI response IDs mismatch. "
                    f"Missing: {', '.join(missing[:8])}. Unexpected: {', '.join(unexpected[:8])}."
                )
            if missing:
                return None, f"AI response missing IDs: {', '.join(missing[:8])}."
            return None, f"AI response returned unexpected IDs: {', '.join(unexpected[:8])}."
        if len(out) != len(expected_list):
            return None, "AI response must include exactly one item per requested ID"

    return out, None


def parse_items_from_response_strict(
    parsed: Optional[Dict[str, object]],
    *,
    expected_ids: Optional[Iterable[str]] = None,
    max_name_len: int = 96,
    max_hint_len: int = 240,
) -> Tuple[Optional[List[Dict[str, str]]], Optional[str]]:
    items = parse_items_from_response(parsed)
    return validate_items_payload(
        items,
        expected_ids=expected_ids,
        max_name_len=max_name_len,
        max_hint_len=max_hint_len,
    )


__all__ = [
    "parse_items_from_response",
    "parse_items_from_response_strict",
    "validate_items_payload",
    "sanitize_target_collection_hint",
]
