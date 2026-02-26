"""Collection-path utilities for AI Asset Organizer."""

from __future__ import annotations

import json
import re
from typing import Dict, Iterable, List

from .asset_naming import is_valid_collection_name, normalize_collection_name


_SHOT_ROOT_RE = re.compile(r"^SHOT \d{2,3}$")
_SHOT_CHILD_RE = re.compile(r"^SH\d{2,3}_")


def is_shot_collection_name(name: str) -> bool:
    value = (name or "").strip()
    return bool(_SHOT_ROOT_RE.match(value) or _SHOT_CHILD_RE.match(value))


def build_missing_path_segments(target_paths: Iterable[str], existing_paths: Iterable[str]) -> List[str]:
    available = {p for p in list(existing_paths or []) if (p or "").strip()}
    missing: List[str] = []
    uniq_targets = sorted({p for p in list(target_paths or []) if (p or "").strip()}, key=lambda p: (p.count("/"), p))
    for target_path in uniq_targets:
        current = ""
        for segment in [part for part in target_path.split("/") if part]:
            current = segment if not current else f"{current}/{segment}"
            if current in available:
                continue
            available.add(current)
            missing.append(current)
    return missing


def normalize_collection_path_value(raw: str) -> str:
    parts = [p for p in str(raw or "").split("/") if (p or "").strip()]
    normalized: List[str] = []
    for segment in parts:
        value = normalize_collection_name(segment)
        if not value or not is_valid_collection_name(value):
            continue
        if is_shot_collection_name(value):
            continue
        normalized.append(value)
    return "/".join(normalized)


def canonical_collection_name_key(raw: str) -> str:
    normalized = normalize_collection_name(str(raw or ""))
    if not normalized or not is_valid_collection_name(normalized):
        return ""
    return normalized.lower()


def canonical_collection_path_key(raw: str) -> str:
    normalized = normalize_collection_path_value(raw)
    if not normalized:
        return ""
    parts = [canonical_collection_name_key(part) for part in normalized.split("/") if part]
    parts = [part for part in parts if part]
    return "/".join(parts)


def replace_path_prefix(path: str, old_prefix: str, new_prefix: str) -> str:
    value = (path or "").strip()
    old = (old_prefix or "").strip()
    new = (new_prefix or "").strip()
    if not value or not old or not new:
        return value
    low_value = value.lower()
    low_old = old.lower()
    if low_value == low_old:
        return new
    marker = f"{old}/"
    if low_value.startswith(marker.lower()):
        return f"{new}/{value[len(old) + 1:]}"
    return value


def serialize_ranked_candidates(candidates) -> str:
    payload: List[Dict[str, object]] = []
    for cand in list(candidates or [])[:3]:
        path = (getattr(cand, "path", "") or "").strip()
        if not path:
            continue
        payload.append(
            {
                "path": path,
                "score": float(getattr(cand, "score", 0.0) or 0.0),
                "exists": bool(getattr(cand, "exists", True)),
            }
        )
    try:
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    except Exception:
        return "[]"


def parse_target_candidates_json(value: str) -> List[Dict[str, object]]:
    raw = (value or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    out: List[Dict[str, object]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        out.append(
            {
                "path": path,
                "score": float(item.get("score") or 0.0),
                "exists": bool(item.get("exists", True)),
            }
        )
    return out


__all__ = [
    "build_missing_path_segments",
    "normalize_collection_path_value",
    "canonical_collection_name_key",
    "canonical_collection_path_key",
    "replace_path_prefix",
    "serialize_ranked_candidates",
    "parse_target_candidates_json",
    "is_shot_collection_name",
]
