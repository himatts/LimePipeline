"""Target resolution orchestration for AI Asset Organizer."""

from __future__ import annotations

import json
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from bpy.types import Collection, Object

from ...core.asset_naming import is_valid_collection_name, normalize_collection_name
from ...core.ai_asset_collection_paths import (
    is_shot_collection_name,
    normalize_collection_path_value,
    parse_target_candidates_json,
    serialize_ranked_candidates,
)
from ...core.collection_resolver import (
    CollectionCandidate,
    extract_shot_root_from_path,
    resolve_collection_destination,
    tokenize as tokenize_name,
)
from ...props_ai_assets import LimeAIAssetItem
from .scene_snapshot import build_scene_collection_snapshot, object_collection_paths


_GENERIC_COLLECTION_RE = re.compile(r"^Collection(?:\.\d{3})?$")
_GENERIC_AI_COLLECTION_HINTS = {
    "archive",
    "archived",
    "collection",
    "collections",
    "object",
    "objects",
    "misc",
    "others",
    "other",
    "props",
}
_OBJECT_HINT_KEYWORDS: Dict[str, set[str]] = {
    "Electronics": {
        "controller", "screen", "lens", "sensor", "servo", "motor", "battery", "pcb", "board",
        "switch", "cable", "wire", "display", "led", "connector",
    },
    "Fasteners": {
        "screw", "screws", "bolt", "bolts", "nut", "nuts", "thread", "phillips", "washer", "fastener",
    },
    "Mechanical": {
        "gear", "roller", "lever", "bracket", "shaft", "hinge", "bearing", "mech", "mechanical",
    },
    "Shell": {
        "shell", "lid", "base", "tray", "bowl", "visor", "cover", "housing",
    },
    "Bristles": {
        "bristle", "bristles", "sweeper", "brush",
    },
}
_CONTROLLER_ROLE_TOKENS = {
    "controller",
    "control",
    "ctrl",
    "rig",
    "master",
    "root",
    "driver",
    "manager",
}
_CONTROLLER_LOCATOR_TOKENS = {"pivot", "origin", "locator", "null", "handle", "target"}
_ROOT_HINT_TOKENS = {"main", "global", "system", "assembly", "root", "master"}
_TECHNICAL_SUBPATH_TOKENS = {"electronics", "electronic", "fasteners"}


def _collection_is_active_destination(coll: Optional[Collection], activity_index: Dict[int, Dict[str, bool]]) -> Tuple[bool, str]:
    if coll is None:
        return False, "missing collection"
    if bool(getattr(coll, "hide_viewport", False)):
        return False, "collection.hide_viewport"
    ptr = coll.as_pointer()
    layer_state = activity_index.get(ptr)
    if layer_state and bool(layer_state.get("exclude", False)):
        return False, "layer_collection.exclude"
    if layer_state and bool(layer_state.get("hide_viewport_layer", False)):
        return False, "layer_collection.hide_viewport"
    return True, "active"


def _preferred_shot_roots(paths: Iterable[str]) -> List[str]:
    roots: List[str] = []
    for path in list(paths or []):
        root = extract_shot_root_from_path(path or "")
        if root and root not in roots:
            roots.append(root)
    return roots


def _normalize_hint_path(
    hint: str,
    candidates: Sequence[CollectionCandidate],
    preferred_shot_roots: Sequence[str],
) -> str:
    raw = (hint or "").strip()
    if not raw:
        return ""
    if "/" in raw:
        return raw
    lower_raw = raw.lower()
    matches = [c.path for c in candidates if (c.name or "").strip().lower() == lower_raw]
    if preferred_shot_roots:
        preferred_set = set(preferred_shot_roots)
        preferred_matches = [
            c.path
            for c in candidates
            if (c.name or "").strip().lower() == lower_raw and c.shot_root_name in preferred_set
        ]
        if len(preferred_matches) == 1:
            return preferred_matches[0]
        if preferred_matches:
            matches = preferred_matches
    if len(matches) == 1:
        return matches[0]
    return ""


def _is_generic_ai_hint(value: str) -> bool:
    norm = normalize_collection_name(value or "").strip()
    if not norm:
        return True
    return norm.lower() in _GENERIC_AI_COLLECTION_HINTS


def _object_semantic_tags(name: str, obj_type: str) -> List[str]:
    tokens = {t.lower() for t in tokenize_name(name or "")}
    tags: List[str] = []
    for label, keywords in _OBJECT_HINT_KEYWORDS.items():
        if tokens.intersection(keywords):
            tags.append(label)
    kind = (obj_type or "").strip().upper()
    if kind in {"LIGHT", "CAMERA"}:
        tags.append(kind.title())
    return tags[:4]


def _object_root_name(obj: Optional[Object]) -> str:
    current = obj
    guard = 0
    last_name = ""
    while current is not None and guard < 128:
        last_name = str(getattr(current, "name", "") or last_name)
        current = getattr(current, "parent", None)
        guard += 1
    return last_name


def _object_hierarchy_depth(obj: Optional[Object]) -> int:
    current = getattr(obj, "parent", None) if obj is not None else None
    depth = 0
    guard = 0
    while current is not None and guard < 128:
        depth += 1
        current = getattr(current, "parent", None)
        guard += 1
    return depth


def _infer_hierarchy_role(obj: Optional[Object]) -> Tuple[str, str]:
    if obj is None:
        return "COMPONENT", "No object reference"
    name = str(getattr(obj, "name", "") or "")
    tokens = {t.lower() for t in tokenize_name(name)}
    obj_type = str(getattr(obj, "type", "") or "").upper()
    parent = getattr(obj, "parent", None)
    depth = _object_hierarchy_depth(obj)
    children_count = len(list(getattr(obj, "children", []) or []))

    has_controller_tokens = bool(tokens.intersection(_CONTROLLER_ROLE_TOKENS))
    has_root_tokens = bool(tokens.intersection(_ROOT_HINT_TOKENS))
    is_root = parent is None

    if is_root and (has_controller_tokens or has_root_tokens or children_count >= 3):
        if has_controller_tokens:
            return "ROOT_CONTROLLER", "Root object with controller/root naming"
        if children_count >= 3:
            return "ROOT_CONTROLLER", "Root object controlling multiple children"
        return "GROUP_ROOT", "Root object with structural role"

    if has_controller_tokens and (children_count >= 1 or depth <= 1):
        return "CONTROLLER", "Controller token plus hierarchical responsibility"

    if obj_type == "EMPTY":
        if tokens.intersection(_CONTROLLER_LOCATOR_TOKENS):
            return "LOCATOR", "Empty object used as locator/pivot/origin"
        if children_count >= 2:
            return "GROUP_ROOT", "Empty object grouping multiple children"
        return "HELPER", "Empty object with helper role"

    if children_count >= 2 and depth <= 2:
        return "GROUP_ROOT", "Parent object with multiple children"

    return "COMPONENT", "Leaf/component role inferred from hierarchy"


def _heuristic_collection_hint_for_object(
    name: str,
    obj_type: str,
    *,
    parent_name: str = "",
    root_name: str = "",
) -> str:
    tags = _object_semantic_tags(name, obj_type)
    if not tags and parent_name:
        tags = _object_semantic_tags(parent_name, "")
    if not tags and root_name:
        tags = _object_semantic_tags(root_name, "")
    if tags:
        return tags[0]
    return ""


def _normalized_virtual_hint_path(raw_hint: str) -> str:
    raw = (raw_hint or "").strip()
    if not raw:
        return ""

    segments = [seg for seg in raw.split("/") if (seg or "").strip()]
    if not segments:
        segments = [raw]
    normalized_segments: List[str] = []
    for seg in segments:
        norm = normalize_collection_name(seg)
        if not norm or not is_valid_collection_name(norm):
            return ""
        if is_shot_collection_name(norm):
            return ""
        normalized_segments.append(norm)
    return "/".join(normalized_segments)


def _path_has_inactive_ancestor(
    path: str,
    inactive_paths_norm: set[str],
    inactive_names_norm: Optional[set[str]] = None,
) -> bool:
    raw = (path or "").strip()
    if not raw:
        return False
    parts = [p for p in raw.split("/") if p]
    if not parts:
        return False
    current = ""
    for segment in parts:
        current = segment if not current else f"{current}/{segment}"
        if current.lower() in inactive_paths_norm:
            return True
        if inactive_names_norm and segment.lower() in inactive_names_norm:
            return True
    return False


def _path_contains_technical_subcategory(path: str) -> bool:
    parts = [p.strip().lower() for p in (path or "").split("/") if p.strip()]
    if not parts:
        return False
    return any(part in _TECHNICAL_SUBPATH_TOKENS for part in parts)


def _safe_controller_collection_path(obj: Optional[Object]) -> str:
    root_name = _object_root_name(obj)
    normalized_root = normalize_collection_name(root_name)
    if (
        normalized_root
        and is_valid_collection_name(normalized_root)
        and not is_shot_collection_name(normalized_root)
        and not _is_generic_ai_hint(normalized_root)
    ):
        return normalized_root
    return "Controllers"


def resolve_object_targets_for_state(
    scene,
    state,
    *,
    hints_by_item_id: Optional[Dict[str, str]] = None,
    preserve_confirmed: bool = True,
) -> Dict[str, object]:
    snapshot = build_scene_collection_snapshot(scene)
    all_candidates = [c for c in list(snapshot.get("candidates", []) or []) if not getattr(c, "is_shot_root", False)]
    if not all_candidates:
        all_candidates = list(snapshot.get("candidates", []) or [])
    path_to_collection = snapshot.get("path_to_collection", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(path_to_collection, dict):
        path_to_collection = {}
    activity_index = snapshot.get("collection_activity", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(activity_index, dict):
        activity_index = {}
    hints = hints_by_item_id or {}
    active_only = bool(getattr(state, "use_active_collections_only", True))
    debug_flow = bool(getattr(state, "debug_collection_flow", False))

    for row in list(getattr(state, "items", []) or []):
        if getattr(row, "item_type", "") != "OBJECT":
            continue
        obj = getattr(row, "object_ref", None)
        if obj is None:
            row.target_collection_path = ""
            row.target_status = "NONE"
            row.target_confidence = 0.0
            row.target_candidates_json = ""
            row.target_debug_json = ""
            continue

        if preserve_confirmed and getattr(row, "target_status", "") == "CONFIRMED":
            continue

        excluded_inactive: List[Dict[str, str]] = []
        excluded_inactive_paths_norm: set[str] = set()
        excluded_inactive_names_norm: set[str] = set()
        candidates: List[CollectionCandidate] = []
        for cand in all_candidates:
            coll = path_to_collection.get((cand.path or "").strip())
            is_active, reason = _collection_is_active_destination(coll, activity_index)
            if active_only and not is_active:
                excluded_inactive.append({"path": cand.path, "reason": reason})
                excluded_inactive_paths_norm.add((cand.path or "").strip().lower())
                if coll is not None:
                    coll_name_norm = normalize_collection_name(str(getattr(coll, "name", "") or ""))
                    if coll_name_norm:
                        excluded_inactive_names_norm.add(coll_name_norm.lower())
                for seg in [s for s in str(cand.path or "").split("/") if s]:
                    seg_norm = normalize_collection_name(seg)
                    if seg_norm:
                        excluded_inactive_names_norm.add(seg_norm.lower())
                continue
            candidates.append(cand)

        current_paths = object_collection_paths(obj, snapshot)
        preferred_roots = _preferred_shot_roots(current_paths)
        hint_raw = (hints.get(getattr(row, "item_id", "") or "") or "").strip()
        effective_hint_raw = hint_raw
        heuristic_hint = _heuristic_collection_hint_for_object(
            (getattr(row, "suggested_name", "") or "").strip() or (getattr(row, "original_name", "") or "").strip(),
            str(getattr(obj, "type", "") or ""),
            parent_name=str(getattr(getattr(obj, "parent", None), "name", "") or ""),
            root_name=_object_root_name(obj),
        )
        heuristic_used = False
        if heuristic_hint and (not effective_hint_raw or _is_generic_ai_hint(effective_hint_raw)):
            effective_hint_raw = heuristic_hint
            heuristic_used = True

        hint_path = _normalize_hint_path(effective_hint_raw, candidates, preferred_roots)
        inferred_role, inferred_role_reason = _infer_hierarchy_role(obj)
        controller_guardrail_applied = False
        controller_guardrail_from = ""
        controller_guardrail_to = ""
        if inferred_role in {"ROOT_CONTROLLER", "CONTROLLER"} and hint_path and _path_contains_technical_subcategory(hint_path):
            controller_guardrail_from = hint_path
            hint_path = _safe_controller_collection_path(obj)
            controller_guardrail_to = hint_path
            controller_guardrail_applied = True
        hint_blocked_inactive = False
        if active_only and hint_path and _path_has_inactive_ancestor(
            hint_path,
            excluded_inactive_paths_norm,
            excluded_inactive_names_norm,
        ):
            hint_path = ""
            hint_blocked_inactive = True
        virtual_hint_path = ""
        virtual_hint_used = False

        if not candidates and not hint_path:
            virtual_hint_path = _normalized_virtual_hint_path(effective_hint_raw)
            if virtual_hint_path and (
                not _path_has_inactive_ancestor(
                    virtual_hint_path,
                    excluded_inactive_paths_norm,
                    excluded_inactive_names_norm,
                )
            ):
                hint_path = virtual_hint_path
                virtual_hint_used = True

        name_hint = (getattr(row, "suggested_name", "") or "").strip() or (getattr(row, "original_name", "") or "").strip()
        result = resolve_collection_destination(
            object_name=name_hint or getattr(obj, "name", ""),
            object_type=str(getattr(obj, "type", "") or ""),
            candidates=candidates,
            current_collection_paths=current_paths,
            preferred_shot_roots=preferred_roots,
            hint_path=hint_path,
            last_used_path=(getattr(state, "last_used_collection_path", "") or "").strip(),
        )
        row.target_collection_path = result.selected_path
        row.target_status = result.status if result.selected_path else "NONE"
        row.target_confidence = float(result.confidence or 0.0)
        row.target_candidates_json = serialize_ranked_candidates(result.candidates)
        if virtual_hint_used and result.selected_path:
            row.target_status = "AUTO"
            row.target_confidence = max(float(row.target_confidence or 0.0), 0.55)
        if debug_flow:
            debug_payload = {
                "object_name": getattr(row, "original_name", "") or getattr(obj, "name", ""),
                "active_only": active_only,
                "candidates_considered": len(candidates),
                "excluded_inactive_count": len(excluded_inactive),
                "excluded_inactive_samples": excluded_inactive[:8],
                "excluded_inactive_names_sample": sorted(list(excluded_inactive_names_norm))[:12],
                "ai_hint_raw": hint_raw,
                "effective_hint_raw": effective_hint_raw,
                "heuristic_hint": heuristic_hint,
                "heuristic_hint_used": heuristic_used,
                "inferred_role": inferred_role,
                "inferred_role_reason": inferred_role_reason,
                "controller_guardrail_applied": controller_guardrail_applied,
                "controller_guardrail_from": controller_guardrail_from,
                "controller_guardrail_to": controller_guardrail_to,
                "hint_blocked_inactive": hint_blocked_inactive,
                "ai_hint_normalized": hint_path,
                "virtual_hint_path": virtual_hint_path,
                "virtual_hint_used": virtual_hint_used,
                "current_paths": current_paths,
                "preferred_shot_roots": preferred_roots,
                "resolver_status": result.status,
                "resolver_confidence": float(result.confidence or 0.0),
                "selected_path": result.selected_path,
                "ranked_candidates": [
                    {
                        "path": str(getattr(c, "path", "") or ""),
                        "score": float(getattr(c, "score", 0.0) or 0.0),
                        "exists": bool(getattr(c, "exists", True)),
                    }
                    for c in list(result.candidates or [])
                ],
            }
            try:
                row.target_debug_json = json.dumps(debug_payload, ensure_ascii=True, separators=(",", ":"))
            except Exception:
                row.target_debug_json = ""
        else:
            row.target_debug_json = ""
    return snapshot


def find_row_by_item_id(state, item_id: str) -> Optional[LimeAIAssetItem]:
    target = (item_id or "").strip()
    if not target:
        return None
    for row in list(getattr(state, "items", []) or []):
        if (getattr(row, "item_id", "") or "").strip() == target:
            return row
    return None


def selected_object_rows(state) -> List[LimeAIAssetItem]:
    rows: List[LimeAIAssetItem] = []
    for row in list(getattr(state, "items", []) or []):
        if getattr(row, "item_type", "") != "OBJECT":
            continue
        if not bool(getattr(row, "selected_for_apply", False)):
            continue
        rows.append(row)
    return rows


def target_option_items_for_rows(scene, state, rows: Sequence[LimeAIAssetItem]):
    if state is None:
        return []
    if not rows:
        return []

    snapshot = build_scene_collection_snapshot(scene)
    path_to_collection = snapshot.get("path_to_collection", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(path_to_collection, dict):
        path_to_collection = {}
    activity_index = snapshot.get("collection_activity", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(activity_index, dict):
        activity_index = {}

    options: List[Tuple[str, str, str, int]] = []
    seen: set[str] = set()
    idx = 0

    for path, coll in sorted(path_to_collection.items(), key=lambda kv: (kv[0].count("/"), kv[0].lower())):
        if not path:
            continue
        is_active, _reason = _collection_is_active_destination(coll, activity_index)
        if bool(getattr(state, "use_active_collections_only", True)) and not is_active:
            continue
        options.append((path, path, "Existing collection", idx))
        seen.add(path.lower())
        idx += 1

    for row in list(getattr(state, "items", []) or []):
        if getattr(row, "item_type", "") != "PLANNED_COLLECTION":
            continue
        path = normalize_collection_path_value(getattr(row, "suggested_name", "") or getattr(row, "original_name", "") or "")
        if not path:
            continue
        key = path.lower()
        if key in seen:
            continue
        options.append((path, path, "Planned collection (will be created on apply)", idx))
        seen.add(key)
        idx += 1

    for row in rows:
        path = normalize_collection_path_value(getattr(row, "target_collection_path", "") or "")
        if not path:
            continue
        key = path.lower()
        if key in seen:
            continue
        options.append((path, path, "Current selected-row target", idx))
        seen.add(key)
        idx += 1

    return options


def parse_row_target_candidates(row) -> List[Dict[str, object]]:
    return parse_target_candidates_json(getattr(row, "target_candidates_json", "") or "")


__all__ = [
    "resolve_object_targets_for_state",
    "target_option_items_for_rows",
    "selected_object_rows",
    "find_row_by_item_id",
    "parse_row_target_candidates",
]
