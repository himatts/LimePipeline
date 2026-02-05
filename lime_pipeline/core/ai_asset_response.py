"""Helpers to parse AI response payloads for asset organizer workflows."""

from __future__ import annotations

from typing import Dict, List, Optional


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

