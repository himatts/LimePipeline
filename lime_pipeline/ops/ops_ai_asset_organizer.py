"""AI Asset Organizer operators.

Suggests and applies names for selected objects/materials/collections with AI,
plus optional safe collection reorganization.
"""

from __future__ import annotations

import base64
import datetime
import json
import os
import re
import threading
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy.types import Collection, Material, Object, Operator

from ..core.asset_naming import (
    build_material_name_with_scene_tag,
    bump_material_version_until_unique,
    ensure_unique_collection_name,
    ensure_unique_object_name,
    is_valid_collection_name,
    is_valid_object_name,
    normalize_collection_name,
    normalize_object_name,
)
from ..core.ai_asset_response import parse_items_from_response as parse_ai_asset_items
from ..core.collection_resolver import (
    CollectionCandidate,
    extract_shot_root_from_path,
    resolve_collection_destination,
    tokenize as tokenize_name,
)
from ..core.material_naming import (
    ALLOWED_MATERIAL_TYPES,
    normalize_finish,
    normalize_material_type,
    parse_name as parse_material_name,
    parse_version as parse_material_version,
)
from ..core.material_taxonomy import get_token_material_type_mapping
from ..props_ai_assets import LimeAIAssetItem
from .ai_http import (
    OPENROUTER_CHAT_URL,
    OPENROUTER_MODELS_URL,
    extract_message_content,
    has_openrouter_api_key,
    http_get_json_with_status,
    http_post_json,
    http_post_json_with_status,
    openrouter_headers,
    parse_json_from_text,
)


_DEFAULT_MODEL = "google/gemini-2.0-flash-lite-001"
_MAX_IMAGE_BYTES = 3 * 1024 * 1024
_AI_MAX_TOKENS = 8000
_MATERIAL_NAME_CONTEXT_LIMIT = 320
_MATERIAL_GROUP_CONTEXT_LIMIT = 280

_SHOT_ROOT_RE = re.compile(r"^SHOT \d{2,3}$")
_SHOT_CHILD_RE = re.compile(r"^SH\d{2,3}_")
_GENERIC_COLLECTION_RE = re.compile(r"^Collection(?:\.\d{3})?$")
_AI_ASSET_PREVIEW_SUSPENDED = False
_AI_ASSET_NAME_EDIT_GUARD = 0
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
_EMISSIVE_HINT_TOKENS = {
    "emissive",
    "emission",
    "glow",
    "neon",
    "led",
    "screen",
}
_SPECIFIC_FINISH_HINTS = {
    "brushed",
    "anodized",
    "galvanized",
    "chrome",
    "rusty",
    "frosted",
}
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
_CONTEXT_TAG_RE = re.compile(r"(?:\btag\b|\betiqueta\b)[^\"'\n\r]{0,80}?(?:que diga|=|:)?\s*[\"']?([A-Za-z][A-Za-z0-9 _-]{0,31})[\"']?", re.IGNORECASE)
_CONTEXT_MAT_PATTERN_TAG_RE = re.compile(r"\bMAT_([A-Za-z][A-Za-z0-9]{1,24})_[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9]+_V\d{2}\b")
_CONTEXT_OBJECT_FILTER_RE = re.compile(
    r"(?:material(?:es)?(?:\s+del|\s+de)?\s+objeto|materials?\s+(?:for|of)\s+object)\s+['\"]?([A-Za-z0-9_ -]{1,48})['\"]?",
    re.IGNORECASE,
)
try:
    _MATERIAL_TYPE_TOKEN_MAP = {
        str(k).lower(): str(v)
        for k, v in dict(get_token_material_type_mapping() or {}).items()
    }
except Exception:
    _MATERIAL_TYPE_TOKEN_MAP = {}


def _image_mime_for_path(path: str) -> Optional[str]:
    ext = (os.path.splitext(path)[1] or "").lower()
    if ext in {".png"}:
        return "image/png"
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext in {".webp"}:
        return "image/webp"
    return None


def _load_image_data_url(path: str) -> Tuple[Optional[str], Optional[str]]:
    if not path:
        return None, None
    mime = _image_mime_for_path(path)
    if not mime:
        return None, "Unsupported image format (use PNG/JPG/WebP)"
    try:
        size = os.path.getsize(path)
        if size <= 0:
            return None, "Image file is empty"
        if size > _MAX_IMAGE_BYTES:
            return None, f"Image too large ({size} bytes). Max {_MAX_IMAGE_BYTES} bytes."
    except Exception as ex:
        return None, f"Cannot read image size: {ex}"
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        if not raw:
            return None, "Image file is empty"
        encoded = base64.b64encode(raw).decode("ascii")
        return f"data:{mime};base64,{encoded}", None
    except Exception as ex:
        return None, f"Failed to read image: {ex}"


def _addon_prefs(context) -> Optional[Any]:
    try:
        return context.preferences.addons[__package__.split(".")[0]].preferences
    except Exception:
        return None


def _schema_json_object() -> Dict[str, object]:
    return {"type": "json_object"}


def _schema_assets() -> Dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ai_asset_namer",
            "strict": True,
            "schema": {
                "type": "object",
                "required": ["items"],
                "additionalProperties": False,
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["id", "name"],
                            "additionalProperties": False,
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "target_collection_hint": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    }


def _schema_json_object() -> Dict[str, object]:
    return {"type": "json_object"}


def _is_object_read_only(obj: Object) -> bool:
    return bool(getattr(obj, "library", None) or getattr(obj, "override_library", None))


def _is_material_read_only(mat: Material) -> bool:
    return bool(getattr(mat, "library", None) or getattr(mat, "override_library", None))


def _is_collection_read_only(coll: Collection) -> bool:
    return bool(getattr(coll, "library", None) or getattr(coll, "override_library", None))


def _is_shot_collection_name(name: str) -> bool:
    value = (name or "").strip()
    return bool(_SHOT_ROOT_RE.match(value) or _SHOT_CHILD_RE.match(value))


def _is_generic_collection_name(name: str) -> bool:
    return bool(_GENERIC_COLLECTION_RE.match((name or "").strip()))


def _is_generic_collection(coll: Optional[Collection], scene) -> bool:
    if coll is None:
        return True
    if coll == getattr(scene, "collection", None):
        return True
    return _is_generic_collection_name(getattr(coll, "name", "") or "")


def _collect_selection(
    context,
    *,
    include_collections: bool,
) -> Tuple[List[Object], List[Material], List[Collection]]:
    objects = list(getattr(context, "selected_objects", None) or [])
    materials: List[Material] = []
    collections: List[Collection] = []

    seen_mats: set[int] = set()
    seen_cols: set[int] = set()
    scene_root = getattr(getattr(context, "scene", None), "collection", None)

    for obj in objects:
        for slot in getattr(obj, "material_slots", []) or []:
            mat = getattr(slot, "material", None)
            if mat is None:
                continue
            key = mat.as_pointer()
            if key in seen_mats:
                continue
            seen_mats.add(key)
            materials.append(mat)

        if not include_collections:
            continue
        for coll in list(getattr(obj, "users_collection", []) or []):
            if coll is None:
                continue
            if scene_root is not None and coll == scene_root:
                continue
            if _is_shot_collection_name(getattr(coll, "name", "") or ""):
                continue
            key = coll.as_pointer()
            if key in seen_cols:
                continue
            seen_cols.add(key)
            collections.append(coll)

    return objects, materials, collections


def _join_collection_path(parent_path: str, name: str) -> str:
    if not parent_path:
        return name
    return f"{parent_path}/{name}"


def _build_scene_collection_snapshot(scene) -> Dict[str, object]:
    root = getattr(scene, "collection", None)
    path_to_collection: Dict[str, Collection] = {}
    collection_ptr_to_paths: Dict[int, List[str]] = {}
    candidates: List[CollectionCandidate] = []
    hierarchy_paths: List[str] = []

    if root is None:
        return {
            "path_to_collection": path_to_collection,
            "collection_ptr_to_paths": collection_ptr_to_paths,
            "candidates": candidates,
            "hierarchy_paths": hierarchy_paths,
        }

    def walk(parent: Collection, parent_path: str, shot_root: Optional[str], stack: set[int]) -> None:
        children = list(getattr(parent, "children", []) or [])
        for child in children:
            child_name = getattr(child, "name", "") or ""
            if not child_name:
                continue

            path = _join_collection_path(parent_path, child_name)
            ptr = child.as_pointer()
            if path not in path_to_collection:
                path_to_collection[path] = child
                hierarchy_paths.append(path)
            collection_ptr_to_paths.setdefault(ptr, [])
            if path not in collection_ptr_to_paths[ptr]:
                collection_ptr_to_paths[ptr].append(path)

            child_shot_root = shot_root
            if _SHOT_ROOT_RE.match(child_name):
                child_shot_root = child_name

            candidates.append(
                CollectionCandidate(
                    path=path,
                    name=child_name,
                    depth=max(0, path.count("/")),
                    shot_root_name=child_shot_root,
                    is_shot_root=bool(_SHOT_ROOT_RE.match(child_name)),
                    is_read_only=_is_collection_read_only(child),
                    object_count=len(list(getattr(child, "objects", []) or [])),
                    path_tokens=tuple(tokenize_name(path)),
                    name_tokens=tuple(tokenize_name(child_name)),
                    exists=True,
                )
            )

            if ptr in stack:
                continue
            child_stack = set(stack)
            child_stack.add(ptr)
            walk(child, path, child_shot_root, child_stack)

    walk(root, "", None, set())
    hierarchy_paths.sort(key=lambda p: (p.count("/"), p.lower()))
    activity = _build_collection_activity_index(scene)
    return {
        "path_to_collection": path_to_collection,
        "collection_ptr_to_paths": collection_ptr_to_paths,
        "candidates": candidates,
        "hierarchy_paths": hierarchy_paths,
        "collection_activity": activity,
    }


def _walk_layer_collections(layer_collection, out: Dict[int, Dict[str, bool]]) -> None:
    coll = getattr(layer_collection, "collection", None)
    if coll is not None:
        out[coll.as_pointer()] = {
            "exclude": bool(getattr(layer_collection, "exclude", False)),
            "hide_viewport_layer": bool(getattr(layer_collection, "hide_viewport", False)),
        }
    for child in list(getattr(layer_collection, "children", []) or []):
        _walk_layer_collections(child, out)


def _build_collection_activity_index(scene) -> Dict[int, Dict[str, bool]]:
    index: Dict[int, Dict[str, bool]] = {}
    view_layer = getattr(bpy.context, "view_layer", None)
    layer_root = getattr(view_layer, "layer_collection", None)
    if layer_root is not None:
        _walk_layer_collections(layer_root, index)
    return index


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


def _object_collection_paths(obj: Object, snapshot: Dict[str, object]) -> List[str]:
    pointer_to_paths = snapshot.get("collection_ptr_to_paths", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(pointer_to_paths, dict):
        pointer_to_paths = {}
    paths: List[str] = []
    for coll in list(getattr(obj, "users_collection", []) or []):
        if coll is None:
            continue
        ptr = coll.as_pointer()
        known_paths = pointer_to_paths.get(ptr, [])
        if isinstance(known_paths, list):
            for path in known_paths:
                if path and path not in paths:
                    paths.append(path)
    return paths


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


def _empty_role_hint(obj: Optional[Object]) -> str:
    if obj is None or str(getattr(obj, "type", "") or "").upper() != "EMPTY":
        return ""
    name_tokens = {t.lower() for t in tokenize_name(str(getattr(obj, "name", "") or ""))}
    children_count = len(list(getattr(obj, "children", []) or []))
    if name_tokens.intersection({"ctrl", "control", "controller", "rig"}):
        return "Controller"
    if name_tokens.intersection({"pivot", "origin", "locator"}):
        return "Locator"
    if children_count >= 2:
        return "GroupRoot"
    return "Helper"


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
    """Build a virtual collection path from raw AI hint when no active candidates exist."""
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
        if _is_shot_collection_name(norm):
            return ""
        normalized_segments.append(norm)
    return "/".join(normalized_segments)


def _path_has_inactive_ancestor(
    path: str,
    inactive_paths_norm: set[str],
    inactive_names_norm: Optional[set[str]] = None,
) -> bool:
    """Return True when path references any known inactive collection segment path."""
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
        and not _is_shot_collection_name(normalized_root)
        and not _is_generic_ai_hint(normalized_root)
    ):
        return normalized_root
    return "Controllers"


def _serialize_ranked_candidates(candidates) -> str:
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


def _parse_target_candidates_json(value: str) -> List[Dict[str, object]]:
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


def _resolve_object_targets_for_state(
    scene,
    state,
    *,
    hints_by_item_id: Optional[Dict[str, str]] = None,
    preserve_confirmed: bool = True,
) -> Dict[str, object]:
    snapshot = _build_scene_collection_snapshot(scene)
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

        current_paths = _object_collection_paths(obj, snapshot)
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

        # Explicit fallback: if no active candidates remain, allow a virtual path from AI hint.
        # Guard rail: never re-enable an existing inactive collection via virtual fallback.
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
        row.target_candidates_json = _serialize_ranked_candidates(result.candidates)
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


def _build_scene_summary(
    objects: List[Dict[str, object]],
    materials: List[Dict[str, object]],
    collections: List[Dict[str, object]],
) -> str:
    type_counts: Dict[str, int] = {}
    for entry in objects:
        t = str(entry.get("type") or "UNKNOWN")
        type_counts[t] = type_counts.get(t, 0) + 1
    type_part = ", ".join(f"{k}:{v}" for k, v in sorted(type_counts.items()))
    if not type_part:
        type_part = "none"
    return (
        f"Selected assets -> Objects: {len(objects)} ({type_part}); "
        f"Materials: {len(materials)}; Collections: {len(collections)}."
    )


def _build_material_scene_context(selected_materials: Sequence[Material]) -> Dict[str, object]:
    selected_ptrs = {m.as_pointer() for m in list(selected_materials or []) if m is not None}
    all_names: List[str] = []
    non_selected_names: List[str] = []
    groups: Dict[Tuple[str, str, str], Dict[str, object]] = {}

    for mat in list(getattr(bpy.data, "materials", []) or []):
        if mat is None:
            continue
        name = (getattr(mat, "name", "") or "").strip()
        if not name:
            continue
        all_names.append(name)
        if mat.as_pointer() not in selected_ptrs:
            non_selected_names.append(name)

        parsed = parse_material_name(name)
        if not parsed:
            continue
        scene_tag = str(parsed.get("scene_tag") or "")
        material_type = str(parsed.get("material_type") or "Plastic")
        finish = str(parsed.get("finish") or "Generic")
        version_index = int(parsed.get("version_index") or 1)
        key = (scene_tag, material_type, finish)
        entry = groups.get(key)
        if entry is None:
            entry = {
                "scene_tag": scene_tag,
                "material_type": material_type,
                "finish": finish,
                "max_version_index": version_index,
                "count": 1,
            }
            groups[key] = entry
        else:
            entry["count"] = int(entry.get("count", 0) or 0) + 1
            entry["max_version_index"] = max(int(entry.get("max_version_index", 1) or 1), version_index)

    all_names_sorted = sorted(set(all_names))
    non_selected_sorted = sorted(set(non_selected_names))
    group_items = list(groups.values())
    group_items.sort(
        key=lambda item: (
            str(item.get("material_type") or ""),
            str(item.get("finish") or ""),
            str(item.get("scene_tag") or ""),
        )
    )

    return {
        "total_scene_materials": len(all_names_sorted),
        "selected_materials": len(selected_ptrs),
        "non_selected_materials": len(non_selected_sorted),
        "all_material_names": all_names_sorted[:_MATERIAL_NAME_CONTEXT_LIMIT],
        "all_material_names_truncated": len(all_names_sorted) > _MATERIAL_NAME_CONTEXT_LIMIT,
        "non_selected_material_names": non_selected_sorted[:_MATERIAL_NAME_CONTEXT_LIMIT],
        "non_selected_material_names_truncated": len(non_selected_sorted) > _MATERIAL_NAME_CONTEXT_LIMIT,
        "material_version_groups": group_items[:_MATERIAL_GROUP_CONTEXT_LIMIT],
        "material_version_groups_truncated": len(group_items) > _MATERIAL_GROUP_CONTEXT_LIMIT,
    }


def _build_object_group_hints(objects: Sequence[Dict[str, object]]) -> Dict[str, object]:
    semantic_counts: Dict[str, int] = {}
    prefix_counts: Dict[str, int] = {}
    root_counts: Dict[str, int] = {}
    empty_roles: Dict[str, int] = {}
    hierarchy_roles: Dict[str, int] = {}
    for item in list(objects or []):
        if not isinstance(item, dict):
            continue
        for tag in list(item.get("semantic_tags", []) or []):
            key = str(tag or "").strip()
            if not key:
                continue
            semantic_counts[key] = semantic_counts.get(key, 0) + 1
        tokens = [str(t or "").strip() for t in list(item.get("name_tokens", []) or []) if str(t or "").strip()]
        if tokens:
            prefix = tokens[0]
            if len(prefix) >= 2:
                prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
        root_name = str(item.get("root_name") or "").strip()
        if root_name:
            root_counts[root_name] = root_counts.get(root_name, 0) + 1
        empty_role = str(item.get("empty_role_hint") or "").strip()
        if empty_role:
            empty_roles[empty_role] = empty_roles.get(empty_role, 0) + 1
        hierarchy_role = str(item.get("hierarchy_role") or "").strip()
        if hierarchy_role:
            hierarchy_roles[hierarchy_role] = hierarchy_roles.get(hierarchy_role, 0) + 1

    semantic_sorted = sorted(semantic_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    prefix_sorted = sorted(prefix_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    root_sorted = sorted(root_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    role_sorted = sorted(empty_roles.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
    hierarchy_role_sorted = sorted(hierarchy_roles.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
    return {
        "semantic_clusters": [{"name": k, "count": v} for k, v in semantic_sorted],
        "prefix_clusters": [{"name": k, "count": v} for k, v in prefix_sorted if v >= 2],
        "root_clusters": [{"name": k, "count": v} for k, v in root_sorted if v >= 2],
        "empty_role_distribution": [{"name": k, "count": v} for k, v in role_sorted],
        "hierarchy_role_distribution": [{"name": k, "count": v} for k, v in hierarchy_role_sorted],
    }


def _material_shader_profile(mat: Optional[Material]) -> Dict[str, object]:
    profile: Dict[str, object] = {
        "uses_nodes": False,
        "metallic": 0.0,
        "roughness": 0.5,
        "transmission": 0.0,
        "ior": 1.45,
        "alpha": 1.0,
        "emission_strength": 0.0,
        "emission_luma": 0.0,
        "has_metallic_input": False,
        "has_roughness_input": False,
        "has_transmission_input": False,
        "has_normal_input": False,
        "has_emission_input": False,
    }
    if mat is None:
        return profile
    if not bool(getattr(mat, "use_nodes", False)):
        return profile
    profile["uses_nodes"] = True
    tree = getattr(mat, "node_tree", None)
    nodes = list(getattr(tree, "nodes", []) or [])
    if not nodes:
        return profile

    def _find_first_principled():
        for node in nodes:
            if getattr(node, "type", "") == "OUTPUT_MATERIAL" and bool(getattr(node, "is_active_output", False)):
                surface = getattr(node, "inputs", {}).get("Surface")
                if surface and bool(getattr(surface, "is_linked", False)):
                    links = list(getattr(surface, "links", []) or [])
                    if links:
                        src_node = getattr(links[0], "from_node", None)
                        if src_node is not None and getattr(src_node, "type", "") == "BSDF_PRINCIPLED":
                            return src_node
        for node in nodes:
            if getattr(node, "type", "") == "BSDF_PRINCIPLED":
                return node
        return None

    def _input_value(node, names: Sequence[str], default: float) -> float:
        inputs = getattr(node, "inputs", {})
        for name in names:
            socket = inputs.get(name)
            if socket is None:
                continue
            value = getattr(socket, "default_value", default)
            try:
                return float(value)
            except Exception:
                continue
        return default

    def _input_linked(node, names: Sequence[str]) -> bool:
        inputs = getattr(node, "inputs", {})
        for name in names:
            socket = inputs.get(name)
            if socket is not None and bool(getattr(socket, "is_linked", False)):
                return True
        return False

    def _input_color_luma(node, names: Sequence[str], default: float) -> float:
        inputs = getattr(node, "inputs", {})
        for name in names:
            socket = inputs.get(name)
            if socket is None:
                continue
            value = getattr(socket, "default_value", None)
            if isinstance(value, (list, tuple)) and len(value) >= 3:
                try:
                    r = float(value[0] or 0.0)
                    g = float(value[1] or 0.0)
                    b = float(value[2] or 0.0)
                    return max(0.0, (r + g + b) / 3.0)
                except Exception:
                    continue
        return default

    principled = _find_first_principled()
    if principled is None:
        return profile

    profile["metallic"] = _input_value(principled, ("Metallic",), 0.0)
    profile["roughness"] = _input_value(principled, ("Roughness",), 0.5)
    profile["transmission"] = _input_value(principled, ("Transmission Weight", "Transmission"), 0.0)
    profile["ior"] = _input_value(principled, ("IOR",), 1.45)
    profile["alpha"] = _input_value(principled, ("Alpha",), 1.0)
    profile["emission_strength"] = _input_value(principled, ("Emission Strength",), 0.0)
    profile["emission_luma"] = _input_color_luma(principled, ("Emission Color", "Emission"), 0.0)
    profile["has_metallic_input"] = _input_linked(principled, ("Metallic",))
    profile["has_roughness_input"] = _input_linked(principled, ("Roughness",))
    profile["has_transmission_input"] = _input_linked(principled, ("Transmission Weight", "Transmission"))
    profile["has_normal_input"] = _input_linked(principled, ("Normal",))
    profile["has_emission_input"] = _input_linked(principled, ("Emission Color", "Emission"))
    return profile


def _material_tokens_from_name(mat_name: str) -> set[str]:
    return {str(t or "").lower() for t in tokenize_name(mat_name or "")}


def _material_likely_metal(profile: Dict[str, object], tokens: Sequence[str]) -> bool:
    token_set = {str(t or "").lower() for t in list(tokens or [])}
    if token_set.intersection(_METAL_HINT_TOKENS):
        return True
    metallic = float(profile.get("metallic", 0.0) or 0.0)
    if metallic >= 0.35:
        return True
    if bool(profile.get("has_metallic_input", False)):
        return True
    return False


def _material_likely_emissive(profile: Dict[str, object], tokens: Sequence[str]) -> bool:
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


def _fallback_material_type_from_profile(
    profile: Dict[str, object],
    *,
    mat_name: str,
    allow_emissive: bool = True,
) -> str:
    token_set = _material_tokens_from_name(mat_name)
    for token in token_set:
        mapped = _MATERIAL_TYPE_TOKEN_MAP.get(str(token).lower())
        if not mapped:
            continue
        mapped_norm = normalize_material_type(str(mapped))
        if mapped_norm == "Emissive" and not allow_emissive:
            continue
        if mapped_norm == "Metal" and not _material_likely_metal(profile, token_set):
            continue
        if mapped_norm == "Emissive" and not _material_likely_emissive(profile, token_set):
            continue
        if mapped_norm in ALLOWED_MATERIAL_TYPES:
            return mapped_norm
    if allow_emissive and _material_likely_emissive(profile, token_set):
        return "Emissive"
    if _material_likely_metal(profile, token_set):
        return "Metal"
    if float(profile.get("transmission", 0.0) or 0.0) >= 0.5:
        if "water" in token_set or "liquid" in token_set:
            return "Liquid"
        return "Glass"
    return "Plastic"


def _refine_material_finish(
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
        if not _material_likely_emissive(profile, source_tokens):
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


def _apply_material_profile_guardrails(normalized: str, mat: Optional[Material]) -> str:
    parsed_final = parse_material_name(normalized)
    if not parsed_final or mat is None:
        return normalized

    profile = _material_shader_profile(mat)
    source_tokens = _material_tokens_from_name(getattr(mat, "name", "") or "")
    final_type = str(parsed_final.get("material_type") or "Plastic")
    final_finish = str(parsed_final.get("finish") or "Generic")
    scene_tag = str(parsed_final.get("scene_tag") or "")
    version_index = int(parsed_final.get("version_index") or 1)

    if final_type == "Metal" and not _material_likely_metal(profile, source_tokens):
        final_type = _fallback_material_type_from_profile(
            profile,
            mat_name=(getattr(mat, "name", "") or ""),
            allow_emissive=True,
        )
    if final_type == "Emissive" and not _material_likely_emissive(profile, source_tokens):
        final_type = _fallback_material_type_from_profile(
            profile,
            mat_name=(getattr(mat, "name", "") or ""),
            allow_emissive=False,
        )

    final_finish = _refine_material_finish(final_type, final_finish, profile, source_tokens)
    return build_material_name_with_scene_tag(scene_tag, final_type, final_finish, version_index)


def _material_texture_hints(mat: Optional[Material], *, limit: int = 8) -> List[str]:
    if mat is None or not bool(getattr(mat, "use_nodes", False)):
        return []
    tree = getattr(mat, "node_tree", None)
    nodes = list(getattr(tree, "nodes", []) or [])
    names: List[str] = []
    seen: set[str] = set()
    for node in nodes:
        if getattr(node, "type", "") != "TEX_IMAGE":
            continue
        image = getattr(node, "image", None)
        if image is None:
            continue
        image_name = (getattr(image, "name", "") or "").strip()
        image_path = (getattr(image, "filepath", "") or "").strip()
        hint = os.path.basename(image_path) if image_path else image_name
        hint = (hint or image_name or "").strip()
        if not hint:
            continue
        key = hint.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(hint)
        if len(names) >= limit:
            break
    return names


def _normalize_tag_token(raw: str) -> str:
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


def _extract_context_material_tag_directive(context_text: str) -> Tuple[str, str]:
    text = (context_text or "").strip()
    if not text:
        return "", ""

    # Strongest signal: explicit MAT example token (e.g., MAT_Iphone_Metal_Matte_V01).
    mat_match = _CONTEXT_MAT_PATTERN_TAG_RE.search(text)
    if mat_match:
        forced_tag = _normalize_tag_token(mat_match.group(1))
    else:
        forced_tag = ""
        tag_match = _CONTEXT_TAG_RE.search(text)
        if tag_match:
            forced_tag = _normalize_tag_token(tag_match.group(1))

    object_filter = ""
    obj_match = _CONTEXT_OBJECT_FILTER_RE.search(text)
    if obj_match:
        object_filter = _normalize_tag_token(obj_match.group(1))

    return forced_tag, object_filter


def _force_material_name_tag(name: str, forced_tag: str) -> str:
    forced = _normalize_tag_token(forced_tag)
    if not forced:
        return name
    parsed = parse_material_name((name or "").strip())
    if not parsed:
        return name
    material_type = str(parsed.get("material_type") or "Plastic")
    finish = str(parsed.get("finish") or "Generic")
    version_index = int(parsed.get("version_index") or 1)
    return build_material_name_with_scene_tag(forced, material_type, finish, version_index)


def _fold_text_for_match(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _normalize_material_name_for_organizer(
    raw: str,
    *,
    mat: Optional[Material] = None,
    trace: Optional[List[str]] = None,
) -> str:
    """Normalize to MAT_{Tag?}_{MaterialType}_{Finish}_{V##} for organizer workflows."""
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

        # Avoid repetitive names like MAT_Metal_MetalPolished_V01
        if len(finish_tokens) > 1:
            head_type = normalize_material_type(finish_tokens[0])
            if head_type == mtype:
                _note("Removed duplicated material type token from finish")
                finish_tokens = finish_tokens[1:]

        # Recover degraded AI proposals such as Plastic_MetalPolished / Plastic_GlassClear.
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
        guarded = _apply_material_profile_guardrails(normalized, mat)
        if guarded != normalized:
            _note("Applied shader-profile guardrails")
        return guarded

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
            guarded = _apply_material_profile_guardrails(normalized, mat)
            if guarded != normalized:
                _note("Applied shader-profile guardrails")
            return guarded

    finish_src = "_".join(parts[1:]) if len(parts) > 1 else "Generic"
    material_type, finish = _repair_components(material_type, finish_src)
    normalized = build_material_name_with_scene_tag(scene_tag, material_type, finish, version_idx)
    guarded = _apply_material_profile_guardrails(normalized, mat)
    if guarded != normalized:
        _note("Applied shader-profile guardrails")
    return guarded


def _material_status_from_trace(
    ai_raw: str,
    final_name: str,
    notes: Sequence[str],
) -> str:
    """Classify material result quality for clearer diagnostics."""
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


def _build_prompt(
    context_text: str,
    scene_summary: str,
    objects: List[Dict[str, object]],
    materials: List[Dict[str, object]],
    collections: List[Dict[str, object]],
    *,
    collection_hierarchy: Optional[List[str]] = None,
    material_scene_context: Optional[Dict[str, object]] = None,
    object_group_hints: Optional[Dict[str, object]] = None,
) -> str:
    allowed_types = ", ".join(ALLOWED_MATERIAL_TYPES)
    context_block = (context_text or "").strip() or scene_summary
    context_line = f"Context: {context_block}\n" if context_block else ""

    payload = {
        "scene_summary": scene_summary,
        "objects": objects,
        "materials": materials,
        "collections": collections,
    }
    if collection_hierarchy:
        payload["collection_hierarchy_paths"] = collection_hierarchy[:220]
    if material_scene_context:
        payload["material_scene_context"] = material_scene_context
    if object_group_hints:
        payload["object_group_hints"] = object_group_hints
    compact_json = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))

    return (
        "Return ONLY JSON per schema.\n"
        f"{context_line}"
        "Rules:\n"
        "- Objects: PascalCase segments separated by underscores (ASCII alphanumeric). "
        "No spaces/dots/dashes. Numeric identifiers must be a separate `_NN` block. "
        "No shot/scene prefixes.\n"
        "- Materials: MAT_{Tag?}_{MaterialType}_{Finish}_{V##}. Tag optional.\n"
        f"- MaterialType must be one of: {allowed_types}.\n"
        "- Collections: PascalCase segments separated by underscores (ASCII alphanumeric). "
        "No spaces/dots/dashes. Numeric identifiers must be a separate `_NN` block. "
        "Avoid shot prefixes.\n"
        "- For collection target suggestions, prefer human-friendly functional names (e.g., Background, Clothing, Accessories, Details, Lighting), not rigid academic taxonomy labels.\n"
        "- Treat target collections as suggestions to help users find items quickly in real production files.\n"
        "- Strong constraint: if an object is type LIGHT and already belongs to a LIGHTS collection path, keep it there.\n"
        "- Strong constraint: if an object is type CAMERA and already belongs to a CAM/CAMERA collection path, keep it there.\n"
        "- Do not suggest moving LIGHT/CAMERA objects to unrelated folders like props/annotations unless explicitly requested.\n"
        "- For object target collections, prioritize semantic clues in `name_tokens` and `semantic_tags` before generic buckets.\n"
        "- Avoid generic hints like Archive/Props unless there is no stronger semantic signal.\n"
        "- Use `object_group_hints` clusters to keep naming/grouping coherent across similar objects.\n"
        "- Material naming must consider all existing scene materials from material_scene_context (including non-selected).\n"
        "- Material naming must respect shader_profile cues in each material (metallic, roughness, transmission, emission).\n"
        "- Avoid Metal type when metallic is low and there is no explicit metal cue.\n"
        "- If finish/type is uncertain, prefer conservative generic names instead of over-specific labels.\n"
        "- Use specific finishes (e.g., Brushed, Chrome, Anodized, Frosted) only with clear evidence from source names, texture hints, or shader_profile.\n"
        "- Do not classify as Emissive when emission is effectively off (black emission or negligible emission energy).\n"
        "- Never propose a material name that already exists; if a group exists, propose the next available V##.\n"
        "- Optional for objects: include `target_collection_hint` with a full path when confident.\n"
        "- Use hierarchy/context hints (parent_id, children_count, shared_data_users, collection_hints, used_on).\n"
        "- Use hierarchy signals to infer semantics: parent_name, parent_type, root_name, hierarchy_depth, sibling_count, children_preview.\n"
        "- Treat EMPTY objects as meaningful semantic nodes using `empty_role_hint` (Controller, GroupRoot, Locator, Helper).\n"
        "- Infer hierarchical role from tree + naming: ROOT_CONTROLLER / CONTROLLER / GROUP_ROOT / COMPONENT.\n"
        "- Objects with role ROOT_CONTROLLER or CONTROLLER should prefer top-level/controller collections, not deep technical subcategories.\n"
        "- Never classify a root controller under Electronics/Fasteners unless there is explicit strong evidence in name + hierarchy.\n"
        "- Prefer grouping components under their controlling root_name when the hierarchy indicates a single system.\n"
        "- Keep parent/child families coherent: siblings should generally share collection intent unless explicit signal says otherwise.\n"
        "- For child objects with generic names (e.g., Mesh, Cube, Empty), inherit intent from parent/root semantics.\n"
        "- Names must be unique per category (object/material/collection).\n"
        "Items JSON:\n"
        f"{compact_json}\n"
    )


def _parse_items_from_response(parsed: Optional[Dict[str, object]]) -> Optional[List[Dict[str, object]]]:
    return parse_ai_asset_items(parsed)


def _openrouter_suggest(
    headers: Dict[str, str],
    model: str,
    prompt: str,
    *,
    timeout: int = 60,
    debug: bool = False,
    image_data_url: Optional[str] = None,
) -> Tuple[Optional[List[Dict[str, object]]], Optional[str], Optional[str]]:
    if image_data_url:
        user_content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]
    else:
        user_content = prompt

    messages = [
        {
            "role": "system",
            "content": "You rename Blender assets and must output strict JSON only.",
        },
        {"role": "user", "content": user_content},
    ]

    payload: Dict[str, object] = {
        "model": model or _DEFAULT_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": _AI_MAX_TOKENS,
        "response_format": _schema_assets(),
    }

    if debug:
        try:
            print("[AI Asset Organizer] OpenRouter model:", payload.get("model"))
            print("[AI Asset Organizer] Prompt chars:", len(prompt or ""))
            if image_data_url:
                print("[AI Asset Organizer] Image attached (data URL length):", len(image_data_url))
            print("[AI Asset Organizer] Prompt preview:\n", (prompt or "")[:2000])
        except Exception:
            pass

    result = http_post_json(OPENROUTER_CHAT_URL, payload, headers=headers, timeout=timeout)
    finish_reason = None
    try:
        finish_reason = (result or {}).get("choices", [{}])[0].get("finish_reason")
    except Exception:
        finish_reason = None
    text = extract_message_content(result or {}) if result else None
    if not text:
        try:
            choice = (result or {}).get("choices", [{}])[0]
            finish_reason = choice.get("finish_reason")
            if finish_reason:
                return (
                    None,
                    f"Model returned no content (finish_reason={finish_reason}). "
                    "Try a model that supports JSON output or reduce selection size.",
                    finish_reason,
                )
        except Exception:
            pass
    parsed = parse_json_from_text(text or "") if text else None
    items = _parse_items_from_response(parsed) if parsed else None
    if items:
        return items, None, finish_reason

    payload_fallback = dict(payload)
    payload_fallback["response_format"] = _schema_json_object()
    result2 = http_post_json(OPENROUTER_CHAT_URL, payload_fallback, headers=headers, timeout=timeout)
    finish_reason2 = None
    try:
        finish_reason2 = (result2 or {}).get("choices", [{}])[0].get("finish_reason")
    except Exception:
        finish_reason2 = None
    text2 = extract_message_content(result2 or {}) if result2 else None
    parsed2 = parse_json_from_text(text2 or "") if text2 else None
    items2 = _parse_items_from_response(parsed2) if parsed2 else None
    if items2:
        return items2, None, finish_reason2

    return None, "AI response was not valid JSON for the expected schema", finish_reason2 or finish_reason

def _status_invalid(status: str) -> bool:
    return (status or "").strip().upper().startswith("INVALID")


def _row_selected(row: LimeAIAssetItem) -> bool:
    if not getattr(row, "selected_for_apply", False):
        return False
    if getattr(row, "read_only", False):
        return False
    return True


def _row_can_rename(row: LimeAIAssetItem) -> bool:
    if not _row_selected(row):
        return False
    suggested = (getattr(row, "suggested_name", "") or "").strip()
    if not suggested:
        return False
    if _status_invalid(getattr(row, "status", "")):
        return False
    return True


def _scope_allows_row(state, row: LimeAIAssetItem) -> bool:
    item_type = (getattr(row, "item_type", "") or "").upper()
    if item_type == "OBJECT":
        return bool(getattr(state, "apply_scope_objects", True))
    if item_type == "MATERIAL":
        return bool(getattr(state, "apply_scope_materials", True))
    if item_type == "COLLECTION":
        return bool(getattr(state, "apply_scope_collections", True))
    return False


def _row_default_selected_for_apply(row: LimeAIAssetItem) -> bool:
    if getattr(row, "read_only", False):
        return False
    suggested = (getattr(row, "suggested_name", "") or "").strip()
    if not suggested:
        return False
    if _status_invalid(getattr(row, "status", "")):
        return False
    return True


def sync_ai_asset_row_selection(scene=None) -> None:
    scene = scene or getattr(bpy.context, "scene", None)
    if scene is None:
        return
    state = getattr(scene, "lime_ai_assets", None)
    if state is None:
        return

    global _AI_ASSET_PREVIEW_SUSPENDED
    _AI_ASSET_PREVIEW_SUSPENDED = True
    try:
        for row in list(getattr(state, "items", []) or []):
            if not _scope_allows_row(state, row):
                row.selected_for_apply = False
                continue
            row.selected_for_apply = _row_default_selected_for_apply(row)
    finally:
        _AI_ASSET_PREVIEW_SUSPENDED = False

    refresh_ai_asset_preview(scene)


def _build_rename_plan(state) -> Dict[str, object]:
    obj_existing = {o.name for o in bpy.data.objects}
    mat_existing = {m.name for m in bpy.data.materials}
    coll_existing = {c.name for c in bpy.data.collections}

    object_ops: List[Tuple[Object, str]] = []
    material_ops: List[Tuple[Material, str]] = []
    collection_ops: List[Tuple[Collection, str]] = []

    for row in list(getattr(state, "items", []) or []):
        if not _scope_allows_row(state, row):
            continue

        if getattr(row, "item_type", "OBJECT") == "OBJECT":
            obj = getattr(row, "object_ref", None)
            if obj is None or not _row_can_rename(row):
                continue
            old = obj.name
            obj_existing.discard(old)
            normalized = normalize_object_name(getattr(row, "suggested_name", ""))
            if not is_valid_object_name(normalized):
                obj_existing.add(old)
                continue
            unique = ensure_unique_object_name(normalized, obj_existing)
            obj_existing.add(unique)
            if unique != old:
                object_ops.append((obj, unique))
            continue

        if getattr(row, "item_type", "") == "MATERIAL":
            mat = getattr(row, "material_ref", None)
            if mat is None or not _row_can_rename(row):
                continue
            old = mat.name
            mat_existing.discard(old)
            suggested_raw = (getattr(row, "suggested_name", "") or "").strip()
            suggested = _normalize_material_name_for_organizer(suggested_raw, mat=mat)
            if not suggested or not parse_material_name(suggested):
                mat_existing.add(old)
                continue
            unique = bump_material_version_until_unique(mat_existing, suggested)
            mat_existing.add(unique)
            if unique != old:
                material_ops.append((mat, unique))
            continue

        if getattr(row, "item_type", "") == "COLLECTION":
            coll = getattr(row, "collection_ref", None)
            if coll is None or not _row_can_rename(row):
                continue
            old = coll.name
            coll_existing.discard(old)
            normalized = normalize_collection_name(getattr(row, "suggested_name", ""))
            if not is_valid_collection_name(normalized):
                coll_existing.add(old)
                continue
            unique = ensure_unique_collection_name(normalized, coll_existing)
            coll_existing.add(unique)
            if unique != old:
                collection_ops.append((coll, unique))

    return {
        "object_ops": object_ops,
        "material_ops": material_ops,
        "collection_ops": collection_ops,
    }


def _build_missing_path_segments(target_paths: Iterable[str], existing_paths: Iterable[str]) -> List[str]:
    available = {p for p in list(existing_paths or []) if (p or "").strip()}
    missing: List[str] = []
    for target_path in sorted({p for p in list(target_paths or []) if (p or "").strip()}, key=lambda p: (p.count("/"), p)):
        current = ""
        for segment in [part for part in target_path.split("/") if part]:
            current = segment if not current else f"{current}/{segment}"
            if current in available:
                continue
            available.add(current)
            missing.append(current)
    return missing


def _normalize_collection_path_value(raw: str) -> str:
    parts = [p for p in str(raw or "").split("/") if (p or "").strip()]
    normalized: List[str] = []
    for segment in parts:
        value = normalize_collection_name(segment)
        if not value or not is_valid_collection_name(value):
            continue
        if _is_shot_collection_name(value):
            continue
        normalized.append(value)
    return "/".join(normalized)


def _replace_path_prefix(path: str, old_prefix: str, new_prefix: str) -> str:
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


def _sync_planned_collection_rows(scene, state, snapshot: Optional[Dict[str, object]] = None) -> None:
    snapshot = snapshot or _build_scene_collection_snapshot(scene)
    existing_paths = list((snapshot.get("path_to_collection", {}) or {}).keys()) if isinstance(snapshot, dict) else []

    object_target_paths: List[str] = []
    for row in list(getattr(state, "items", []) or []):
        if getattr(row, "item_type", "") != "OBJECT":
            continue
        target_status = (getattr(row, "target_status", "") or "").upper()
        target_path = (getattr(row, "target_collection_path", "") or "").strip()
        if target_status not in {"AUTO", "CONFIRMED"} or not target_path:
            continue
        object_target_paths.append(target_path)

    create_paths = _build_missing_path_segments(object_target_paths, existing_paths)
    create_paths = [_normalize_collection_path_value(path) for path in create_paths]
    create_paths = [path for path in create_paths if path]

    keep_rows: List[Dict[str, object]] = []
    for src in list(getattr(state, "items", []) or []):
        if getattr(src, "item_type", "") == "PLANNED_COLLECTION":
            continue
        keep_rows.append(
            {
                "item_type": str(getattr(src, "item_type", "") or "OBJECT"),
                "object_ref": getattr(src, "object_ref", None),
                "material_ref": getattr(src, "material_ref", None),
                "collection_ref": getattr(src, "collection_ref", None),
                "item_id": str(getattr(src, "item_id", "") or ""),
                "original_name": str(getattr(src, "original_name", "") or ""),
                "suggested_name": str(getattr(src, "suggested_name", "") or ""),
                "ai_raw_name": str(getattr(src, "ai_raw_name", "") or ""),
                "normalization_notes": str(getattr(src, "normalization_notes", "") or ""),
                "normalization_changed": bool(getattr(src, "normalization_changed", False)),
                "selected_for_apply": bool(getattr(src, "selected_for_apply", False)),
                "read_only": bool(getattr(src, "read_only", False)),
                "status": str(getattr(src, "status", "") or ""),
                "target_collection_path": str(getattr(src, "target_collection_path", "") or ""),
                "target_status": str(getattr(src, "target_status", "") or "NONE"),
                "target_confidence": float(getattr(src, "target_confidence", 0.0) or 0.0),
                "target_candidates_json": str(getattr(src, "target_candidates_json", "") or ""),
                "target_debug_json": str(getattr(src, "target_debug_json", "") or ""),
            }
        )
    new_virtual_rows = [{"path": path} for path in sorted(set(create_paths), key=lambda p: (p.count("/"), p.lower()))]

    global _AI_ASSET_PREVIEW_SUSPENDED
    previous = _AI_ASSET_PREVIEW_SUSPENDED
    _AI_ASSET_PREVIEW_SUSPENDED = True
    try:
        state.items.clear()
        for src in keep_rows:
            row = state.items.add()
            row.item_type = str(src.get("item_type") or "OBJECT")
            row.object_ref = src.get("object_ref")
            row.material_ref = src.get("material_ref")
            row.collection_ref = src.get("collection_ref")
            row.item_id = str(src.get("item_id") or "")
            row.original_name = str(src.get("original_name") or "")
            row.suggested_name = str(src.get("suggested_name") or "")
            row.ai_raw_name = str(src.get("ai_raw_name") or "")
            row.normalization_notes = str(src.get("normalization_notes") or "")
            row.normalization_changed = bool(src.get("normalization_changed") or False)
            row.selected_for_apply = bool(src.get("selected_for_apply") or False)
            row.read_only = bool(src.get("read_only") or False)
            row.status = str(src.get("status") or "")
            row.target_collection_path = str(src.get("target_collection_path") or "")
            row.target_status = str(src.get("target_status") or "NONE")
            row.target_confidence = float(src.get("target_confidence") or 0.0)
            row.target_candidates_json = str(src.get("target_candidates_json") or "")
            row.target_debug_json = str(src.get("target_debug_json") or "")

        for idx, info in enumerate(new_virtual_rows):
            path = str(info.get("path") or "")
            row = state.items.add()
            row.item_type = "PLANNED_COLLECTION"
            row.object_ref = None
            row.material_ref = None
            row.collection_ref = None
            row.item_id = f"vcol_{idx}_{path}"
            row.original_name = path
            row.suggested_name = path
            row.selected_for_apply = False
            row.read_only = False
            row.status = "PLANNED_CREATE"
            row.target_collection_path = path
            row.target_status = "AUTO"
            row.target_confidence = 1.0
            row.target_candidates_json = ""
            row.target_debug_json = ""
    finally:
        _AI_ASSET_PREVIEW_SUSPENDED = previous


def on_ai_asset_item_suggested_name_changed(scene, item_id: str) -> None:
    """Handle inline edits for item suggested names, including virtual planned collections."""
    global _AI_ASSET_NAME_EDIT_GUARD
    if _AI_ASSET_NAME_EDIT_GUARD > 0:
        return
    state = getattr(scene, "lime_ai_assets", None) if scene is not None else None
    if state is None:
        return
    row = _find_row_by_item_id(state, item_id)
    if row is None:
        refresh_ai_asset_preview(scene)
        return

    if getattr(row, "item_type", "") != "PLANNED_COLLECTION":
        refresh_ai_asset_preview(scene)
        return

    old_path = (getattr(row, "original_name", "") or "").strip()
    new_path = _normalize_collection_path_value(getattr(row, "suggested_name", "") or "")
    if not new_path:
        new_path = old_path

    _AI_ASSET_NAME_EDIT_GUARD += 1
    try:
        global _AI_ASSET_PREVIEW_SUSPENDED
        previous = _AI_ASSET_PREVIEW_SUSPENDED
        _AI_ASSET_PREVIEW_SUSPENDED = True
        try:
            row.suggested_name = new_path
            row.original_name = new_path
            row.target_collection_path = new_path
            row.status = "PLANNED_CREATE" if new_path else "INVALID"
            for obj_row in list(getattr(state, "items", []) or []):
                if getattr(obj_row, "item_type", "") != "OBJECT":
                    continue
                target = (getattr(obj_row, "target_collection_path", "") or "").strip()
                if not target:
                    continue
                replaced = _replace_path_prefix(target, old_path, new_path)
                if replaced != target:
                    obj_row.target_collection_path = replaced
                    if (getattr(obj_row, "target_status", "") or "").upper() == "NONE":
                        obj_row.target_status = "AUTO"
        finally:
            _AI_ASSET_PREVIEW_SUSPENDED = previous

        snapshot = _build_scene_collection_snapshot(scene)
        _sync_planned_collection_rows(scene, state, snapshot=snapshot)
        refresh_ai_asset_preview(scene)
    finally:
        _AI_ASSET_NAME_EDIT_GUARD -= 1


def _build_collection_reorg_plan(scene, state, snapshot: Dict[str, object]) -> Dict[str, object]:
    move_ops: List[Dict[str, object]] = []
    ambiguous_rows: List[LimeAIAssetItem] = []
    target_paths_to_create: List[str] = []
    existing_paths = list((snapshot.get("path_to_collection", {}) or {}).keys())

    if not bool(getattr(state, "organize_collections", False)):
        return {"move_ops": move_ops, "create_paths": target_paths_to_create, "ambiguous_rows": ambiguous_rows}
    if not bool(getattr(state, "apply_scope_objects", True)):
        return {"move_ops": move_ops, "create_paths": target_paths_to_create, "ambiguous_rows": ambiguous_rows}

    for row in list(getattr(state, "items", []) or []):
        if getattr(row, "item_type", "") != "OBJECT":
            continue
        if not _row_selected(row):
            continue

        obj = getattr(row, "object_ref", None)
        if obj is None or _is_object_read_only(obj):
            continue

        target_status = (getattr(row, "target_status", "") or "").upper()
        target_path = (getattr(row, "target_collection_path", "") or "").strip()
        if target_status == "AMBIGUOUS":
            ambiguous_rows.append(row)
            continue
        if target_status not in {"AUTO", "CONFIRMED"} or not target_path:
            continue

        users_collection = list(getattr(obj, "users_collection", []) or [])
        source_generic = [c for c in users_collection if _is_generic_collection(c, scene)]
        path_to_collection = snapshot.get("path_to_collection", {}) if isinstance(snapshot, dict) else {}
        target_coll = path_to_collection.get(target_path) if isinstance(path_to_collection, dict) else None
        already_linked = bool(target_coll is not None and obj in list(getattr(target_coll, "objects", []) or []))

        if already_linked and not source_generic:
            continue

        move_ops.append({"row": row, "object": obj, "target_path": target_path})
        if target_coll is None:
            target_paths_to_create.append(target_path)

    create_paths = _build_missing_path_segments(target_paths_to_create, existing_paths)
    return {"move_ops": move_ops, "create_paths": create_paths, "ambiguous_rows": ambiguous_rows}


def _build_unified_plan(scene, state) -> Dict[str, object]:
    snapshot = _build_scene_collection_snapshot(scene)
    rename_plan = _build_rename_plan(state)
    reorg_plan = _build_collection_reorg_plan(scene, state, snapshot)
    return {
        "snapshot": snapshot,
        "rename_plan": rename_plan,
        "reorg_plan": reorg_plan,
    }


def _apply_preview_from_plan(state, plan: Dict[str, object]) -> None:
    rename_plan = plan.get("rename_plan", {}) if isinstance(plan, dict) else {}
    reorg_plan = plan.get("reorg_plan", {}) if isinstance(plan, dict) else {}
    obj_count = len(list(rename_plan.get("object_ops", []) or []))
    mat_count = len(list(rename_plan.get("material_ops", []) or []))
    col_count = len(list(rename_plan.get("collection_ops", []) or []))
    create_count = len(list(reorg_plan.get("create_paths", []) or []))
    move_count = len(list(reorg_plan.get("move_ops", []) or []))
    ambiguous_count = len(list(reorg_plan.get("ambiguous_rows", []) or []))

    state.planned_renames_objects = obj_count
    state.planned_renames_materials = mat_count
    state.planned_renames_collections = col_count
    state.planned_collections_created = create_count
    state.planned_objects_moved = move_count
    state.planned_ambiguities_objects = ambiguous_count
    state.planned_objects_skipped_ambiguous = ambiguous_count
    state.preview_summary = (
        f"Will rename {obj_count} objects, {mat_count} materials, {col_count} collections.\n"
        f"Will create {create_count} collections, move {move_count} objects, "
        f"skip {ambiguous_count} ambiguous object(s)."
    )
    state.preview_dirty = False


def refresh_ai_asset_preview(scene=None) -> None:
    scene = scene or getattr(bpy.context, "scene", None)
    if scene is None:
        return
    state = getattr(scene, "lime_ai_assets", None)
    if state is None:
        return
    plan = _build_unified_plan(scene, state)
    _apply_preview_from_plan(state, plan)


def _update_preview_state(context, state) -> None:
    scene = getattr(context, "scene", None) if context else None
    if scene is None:
        return
    plan = _build_unified_plan(scene, state)
    _apply_preview_from_plan(state, plan)


def _clear_preview_state(state) -> None:
    state.preview_summary = ""
    state.preview_dirty = False
    state.planned_renames_objects = 0
    state.planned_renames_materials = 0
    state.planned_renames_collections = 0
    state.planned_collections_created = 0
    state.planned_objects_moved = 0
    state.planned_ambiguities_objects = 0
    state.planned_objects_skipped_ambiguous = 0


def _ensure_collection_path(
    scene,
    target_path: str,
    path_to_collection: Dict[str, Collection],
    report,
) -> Tuple[Optional[Collection], int, str]:
    parts = [p for p in (target_path or "").split("/") if p]
    if not parts:
        return None, 0, ""

    parent = getattr(scene, "collection", None)
    if parent is None:
        return None, 0, ""

    created_count = 0
    current_parts: List[str] = []
    built_path = ""
    existing_names = {c.name for c in bpy.data.collections}

    for segment in parts:
        candidate_path = "/".join(current_parts + [segment])
        coll = path_to_collection.get(candidate_path)
        if coll is not None:
            if _is_collection_read_only(coll):
                report({"WARNING"}, f"Cannot use read-only collection '{candidate_path}'")
                return None, created_count, candidate_path
            parent = coll
            current_parts.append(getattr(coll, "name", segment) or segment)
            built_path = "/".join(current_parts)
            continue

        found = None
        for child in list(getattr(parent, "children", []) or []):
            if (getattr(child, "name", "") or "") == segment:
                found = child
                break
        if found is not None:
            if _is_collection_read_only(found):
                report({"WARNING"}, f"Cannot use read-only collection '{candidate_path}'")
                return None, created_count, candidate_path
            path_to_collection[candidate_path] = found
            parent = found
            current_parts.append(getattr(found, "name", segment) or segment)
            built_path = "/".join(current_parts)
            continue

        if _is_collection_read_only(parent):
            parent_name = getattr(parent, "name", "<unknown>")
            report({"WARNING"}, f"Cannot create under read-only collection '{parent_name}'")
            return None, created_count, "/".join(current_parts)

        segment_unique = ensure_unique_collection_name(segment, existing_names)
        existing_names.add(segment_unique)
        try:
            new_coll = bpy.data.collections.new(segment_unique)
            parent.children.link(new_coll)
        except Exception as ex:
            report({"WARNING"}, f"Failed creating collection segment '{segment_unique}': {ex}")
            return None, created_count, "/".join(current_parts)

        current_parts.append(segment_unique)
        built_path = "/".join(current_parts)
        path_to_collection[built_path] = new_coll
        parent = new_coll
        created_count += 1

    return parent, created_count, built_path


def _apply_collection_reorganization(scene, reorg_plan: Dict[str, object], report, state=None) -> Tuple[int, int, int, List[str]]:
    created_count = 0
    moved_count = 0
    skipped_count = 0
    ambiguous_names: List[str] = []
    snapshot = _build_scene_collection_snapshot(scene)
    path_to_collection = snapshot.get("path_to_collection", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(path_to_collection, dict):
        path_to_collection = {}

    for row in list(reorg_plan.get("ambiguous_rows", []) or []):
        name = (getattr(row, "original_name", "") or "").strip() or "<unnamed>"
        ambiguous_names.append(name)
        row.target_status = "SKIPPED"

    for op in list(reorg_plan.get("move_ops", []) or []):
        if not isinstance(op, dict):
            continue
        row = op.get("row")
        obj = op.get("object")
        requested_path = str(op.get("target_path") or "").strip()
        if obj is None or not requested_path:
            continue

        target = path_to_collection.get(requested_path)
        final_path = requested_path
        if target is None:
            target, created, final_path = _ensure_collection_path(scene, requested_path, path_to_collection, report)
            created_count += created
            if target is None:
                skipped_count += 1
                if row is not None:
                    row.target_status = "SKIPPED"
                continue

        changed = False
        try:
            if obj not in list(getattr(target, "objects", []) or []):
                target.objects.link(obj)
                changed = True
        except Exception as ex:
            report({"WARNING"}, f"Failed linking '{obj.name}' to '{target.name}': {ex}")
            skipped_count += 1
            if row is not None:
                row.target_status = "SKIPPED"
            continue

        for source in list(getattr(obj, "users_collection", []) or []):
            if source == target:
                continue
            if not _is_generic_collection(source, scene):
                continue
            try:
                source.objects.unlink(obj)
                changed = True
            except Exception:
                pass

        if row is not None:
            row.target_status = "CONFIRMED"
            row.target_collection_path = final_path
            row.target_confidence = max(float(getattr(row, "target_confidence", 0.0) or 0.0), 0.99)
        if state is not None:
            try:
                state.last_used_collection_path = final_path
            except Exception:
                pass

        if changed:
            moved_count += 1

    return created_count, moved_count, skipped_count, ambiguous_names


def _find_row_by_item_id(state, item_id: str) -> Optional[LimeAIAssetItem]:
    target = (item_id or "").strip()
    if not target:
        return None
    for row in list(getattr(state, "items", []) or []):
        if (getattr(row, "item_id", "") or "").strip() == target:
            return row
    return None


def _selected_object_rows(state) -> List[LimeAIAssetItem]:
    rows: List[LimeAIAssetItem] = []
    for row in list(getattr(state, "items", []) or []):
        if getattr(row, "item_type", "") != "OBJECT":
            continue
        if not bool(getattr(row, "selected_for_apply", False)):
            continue
        rows.append(row)
    return rows


def _target_option_items_for_rows(scene, state, rows: Sequence[LimeAIAssetItem]):
    if state is None:
        return []
    if not rows:
        return []

    snapshot = _build_scene_collection_snapshot(scene)
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
        path = _normalize_collection_path_value(getattr(row, "suggested_name", "") or getattr(row, "original_name", "") or "")
        if not path:
            continue
        key = path.lower()
        if key in seen:
            continue
        options.append((path, path, "Planned collection (will be created on apply)", idx))
        seen.add(key)
        idx += 1

    for row in rows:
        path = _normalize_collection_path_value(getattr(row, "target_collection_path", "") or "")
        if not path:
            continue
        key = path.lower()
        if key in seen:
            continue
        options.append((path, path, "Current selected-row target", idx))
        seen.add(key)
        idx += 1

    return options


class LIME_TB_OT_ai_asset_suggest_names(Operator):
    bl_idname = "lime_tb.ai_asset_suggest_names"
    bl_label = "AI: Suggest Names"
    bl_description = "Suggest clearer names for selected objects, materials, and collections using OpenRouter"
    bl_options = {"REGISTER"}

    _thread: Optional[threading.Thread] = None
    _timer = None
    _result: Optional[Dict[str, object]] = None
    _error: Optional[str] = None
    _id_map: Dict[str, Dict[str, object]] = {}
    _forced_material_tag: str = ""
    _forced_material_object_filter: str = ""
    _forced_material_ptrs: set[int] = set()

    def _finish(self, context) -> None:
        wm = context.window_manager
        try:
            if self._timer is not None:
                wm.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = None

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}

        prefs = _addon_prefs(context)
        if prefs is None:
            self.report({"ERROR"}, "Addon preferences unavailable")
            return {"CANCELLED"}
        if not has_openrouter_api_key():
            self.report({"ERROR"}, "OpenRouter API key not found in .env")
            return {"CANCELLED"}

        include_collections = bool(getattr(state, "include_collections", True))
        objects, materials, collections = _collect_selection(context, include_collections=include_collections)
        if not objects:
            self.report({"ERROR"}, "No objects selected")
            return {"CANCELLED"}
        forced_tag, object_filter = _extract_context_material_tag_directive(getattr(state, "context", "") or "")
        self._forced_material_tag = forced_tag
        self._forced_material_object_filter = object_filter
        self._forced_material_ptrs = set()
        if forced_tag:
            candidate_objects = list(objects)
            if object_filter:
                needle = _fold_text_for_match(object_filter)
                candidate_objects = [
                    obj
                    for obj in objects
                    if needle and needle in _fold_text_for_match(getattr(obj, "name", "") or "")
                ]
            for obj in candidate_objects:
                for slot in list(getattr(obj, "material_slots", []) or []):
                    mat = getattr(slot, "material", None)
                    if mat is None:
                        continue
                    self._forced_material_ptrs.add(mat.as_pointer())
            if not object_filter and not self._forced_material_ptrs:
                self._forced_material_ptrs = {m.as_pointer() for m in list(materials or []) if m is not None}
            if object_filter and not self._forced_material_ptrs:
                self._forced_material_ptrs = {m.as_pointer() for m in list(materials or []) if m is not None}
                self.report(
                    {"WARNING"},
                    (
                        f"Context tag '{forced_tag}' found but no selected object matched '{object_filter}'. "
                        "Applying tag to selected materials."
                    ),
                )
        scene_snapshot = _build_scene_collection_snapshot(scene)
        hierarchy_paths = list(scene_snapshot.get("hierarchy_paths", []) or [])

        obj_items: List[Dict[str, object]] = []
        mat_items: List[Dict[str, object]] = []
        col_items: List[Dict[str, object]] = []
        self._id_map = {}

        object_pointer_to_token: Dict[int, str] = {}
        limited_objects = list(objects[:60])
        for idx, obj in enumerate(limited_objects):
            object_pointer_to_token[obj.as_pointer()] = f"obj_{idx}"

        for idx, obj in enumerate(limited_objects):
            token = object_pointer_to_token.get(obj.as_pointer(), f"obj_{idx}")
            parent = getattr(obj, "parent", None)
            parent_token = object_pointer_to_token.get(parent.as_pointer()) if parent is not None else None
            parent_name = str(getattr(parent, "name", "") or "")
            parent_type = str(getattr(parent, "type", "") or "")
            root_name = _object_root_name(obj)
            depth = _object_hierarchy_depth(obj)
            sibling_count = 0
            if parent is not None:
                sibling_count = max(0, len(list(getattr(parent, "children", []) or [])) - 1)
            children = list(getattr(obj, "children", []) or [])
            children_preview = [str(getattr(child, "name", "") or "") for child in children[:6]]
            empty_role = _empty_role_hint(obj)
            hierarchy_role, hierarchy_role_reason = _infer_hierarchy_role(obj)
            collection_paths = _object_collection_paths(obj, scene_snapshot)
            coll_hints = [p.split("/")[-1] for p in collection_paths][:5]
            shared_data_users = 1
            data_block = getattr(obj, "data", None)
            if data_block is not None:
                try:
                    shared_data_users = int(getattr(data_block, "users", 1) or 1)
                except Exception:
                    shared_data_users = 1
            item = {
                "id": token,
                "name": obj.name,
                "type": getattr(obj, "type", ""),
                "parent_id": parent_token,
                "parent_name": parent_name,
                "parent_type": parent_type,
                "root_name": root_name,
                "hierarchy_depth": depth,
                "children_count": len(children),
                "children_preview": children_preview,
                "sibling_count": sibling_count,
                "is_empty": str(getattr(obj, "type", "") or "").upper() == "EMPTY",
                "empty_role_hint": empty_role,
                "hierarchy_role": hierarchy_role,
                "hierarchy_role_reason": hierarchy_role_reason,
                "shared_data_users": shared_data_users,
                "collection_hints": coll_hints,
                "collection_paths": collection_paths[:5],
                "name_tokens": list(tokenize_name(obj.name))[:10],
                "semantic_tags": _object_semantic_tags(obj.name, str(getattr(obj, "type", "") or "")),
            }
            obj_items.append(item)
            self._id_map[token] = {
                "item_type": "OBJECT",
                "object_ref": obj,
                "material_ref": None,
                "collection_ref": None,
                "original_name": obj.name,
                "read_only": _is_object_read_only(obj),
            }

        mat_usage_names: Dict[int, List[str]] = {}
        mat_usage_ids: Dict[int, List[str]] = {}
        for obj in objects:
            obj_token = object_pointer_to_token.get(obj.as_pointer(), "")
            for slot in list(getattr(obj, "material_slots", []) or []):
                mat = getattr(slot, "material", None)
                if mat is None:
                    continue
                key = mat.as_pointer()
                mat_usage_names.setdefault(key, [])
                mat_usage_ids.setdefault(key, [])
                if obj.name not in mat_usage_names[key]:
                    mat_usage_names[key].append(obj.name)
                if obj_token and obj_token not in mat_usage_ids[key]:
                    mat_usage_ids[key].append(obj_token)

        for idx, mat in enumerate(materials[:60]):
            token = f"mat_{idx}"
            entry = {"id": token, "name": mat.name}
            used_on = mat_usage_names.get(mat.as_pointer(), [])
            used_on_ids = mat_usage_ids.get(mat.as_pointer(), [])
            if used_on:
                entry["used_on"] = used_on[:5]
            if used_on_ids:
                entry["used_on_ids"] = used_on_ids[:5]
            entry["shader_profile"] = _material_shader_profile(mat)
            texture_hints = _material_texture_hints(mat)
            if texture_hints:
                entry["texture_hints"] = texture_hints
            mat_items.append(entry)
            self._id_map[token] = {
                "item_type": "MATERIAL",
                "object_ref": None,
                "material_ref": mat,
                "collection_ref": None,
                "original_name": mat.name,
                "read_only": _is_material_read_only(mat),
            }

        for idx, coll in enumerate(collections[:60]):
            token = f"col_{idx}"
            member_count = len(list(getattr(coll, "objects", []) or []))
            col_items.append({"id": token, "name": coll.name, "member_count": member_count})
            self._id_map[token] = {
                "item_type": "COLLECTION",
                "object_ref": None,
                "material_ref": None,
                "collection_ref": coll,
                "original_name": coll.name,
                "read_only": _is_collection_read_only(coll),
            }

        if len(objects) > 60 or len(materials) > 60 or len(collections) > 60:
            self.report({"WARNING"}, "Selection is large; only first 60 items per category are sent to AI")

        scene_summary = _build_scene_summary(obj_items, mat_items, col_items)
        material_scene_context = _build_material_scene_context(materials)
        object_group_hints = _build_object_group_hints(obj_items)
        prompt = _build_prompt(
            getattr(state, "context", ""),
            scene_summary,
            obj_items,
            mat_items,
            col_items,
            collection_hierarchy=hierarchy_paths,
            material_scene_context=material_scene_context,
            object_group_hints=object_group_hints,
        )
        headers = openrouter_headers(prefs)
        model = (getattr(prefs, "openrouter_model", "") or "").strip() or _DEFAULT_MODEL
        debug = bool(getattr(prefs, "openrouter_debug", False))

        image_data_url = None
        if getattr(state, "use_image_context", False):
            raw_path = (getattr(state, "image_path", "") or "").strip()
            if raw_path:
                resolved = bpy.path.abspath(raw_path)
                image_data_url, image_err = _load_image_data_url(resolved)
                if image_err:
                    self.report({"WARNING"}, image_err)
                    if debug:
                        print("[AI Asset Organizer] Image skipped:", image_err)

        state.is_busy = True
        state.last_error = ""
        state.items.clear()
        state.preview_summary = ""
        _clear_preview_state(state)

        self._result = None
        self._error = None

        def worker():
            try:
                total_items = len(obj_items) + len(mat_items) + len(col_items)
                items, err, finish_reason = _openrouter_suggest(
                    headers,
                    model,
                    prompt,
                    timeout=60,
                    debug=debug,
                    image_data_url=image_data_url,
                )

                def _needs_chunking(item_list: Optional[List[Dict[str, object]]], reason: Optional[str]) -> bool:
                    if item_list is None:
                        return True
                    if reason and str(reason).lower() in {"length", "max_tokens", "stop_length"}:
                        return True
                    if len(item_list) < total_items:
                        return True
                    return False

                if err or _needs_chunking(items, finish_reason):
                    if debug:
                        print("[AI Asset Organizer] Falling back to chunked requests")
                    combined: List[Tuple[str, Dict[str, object]]] = []
                    for obj in obj_items:
                        combined.append(("objects", obj))
                    for mat in mat_items:
                        combined.append(("materials", mat))
                    for coll in col_items:
                        combined.append(("collections", coll))

                    chunk_size = 15
                    by_id: Dict[str, Dict[str, str]] = {}
                    chunk_errors: List[str] = []
                    for i in range(0, len(combined), chunk_size):
                        chunk = combined[i : i + chunk_size]
                        chunk_objects = [item for kind, item in chunk if kind == "objects"]
                        chunk_materials = [item for kind, item in chunk if kind == "materials"]
                        chunk_collections = [item for kind, item in chunk if kind == "collections"]
                        chunk_summary = _build_scene_summary(chunk_objects, chunk_materials, chunk_collections)
                        chunk_prompt = _build_prompt(
                            getattr(state, "context", ""),
                            chunk_summary,
                            chunk_objects,
                            chunk_materials,
                            chunk_collections,
                            collection_hierarchy=hierarchy_paths,
                            material_scene_context=material_scene_context,
                            object_group_hints=object_group_hints,
                        )
                        chunk_items, chunk_err, _ = _openrouter_suggest(
                            headers,
                            model,
                            chunk_prompt,
                            timeout=60,
                            debug=debug,
                            image_data_url=image_data_url,
                        )
                        if chunk_err:
                            chunk_errors.append(chunk_err)
                            continue
                        if not chunk_items:
                            chunk_errors.append("Chunk returned no items")
                            continue
                        for entry in chunk_items:
                            if not isinstance(entry, dict):
                                continue
                            item_id = str(entry.get("id") or "").strip()
                            name = str(entry.get("name") or "").strip()
                            if item_id and name:
                                by_id[item_id] = {
                                    "name": name,
                                    "target_collection_hint": str(entry.get("target_collection_hint") or "").strip(),
                                }

                    if by_id:
                        items = [{"id": k, **v} for k, v in by_id.items()]
                        err = None
                    else:
                        err = "; ".join(chunk_errors) if chunk_errors else err

                if err:
                    self._result = None
                    self._error = err
                    return

                self._result = {"items": items or []}
                self._error = None
            except Exception as ex:
                self._result = None
                self._error = str(ex)

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.2, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self._finish(context)
            return {"CANCELLED"}

        if event.type == "ESC":
            state.is_busy = False
            state.last_error = "Cancelled by user"
            self._finish(context)
            return {"CANCELLED"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        if self._thread and self._thread.is_alive():
            return {"PASS_THROUGH"}

        self._finish(context)
        state.is_busy = False

        if self._error:
            state.last_error = str(self._error)
            self.report({"ERROR"}, str(self._error))
            return {"CANCELLED"}

        data = self._result or {}
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            state.last_error = "AI response did not include 'items'"
            self.report({"ERROR"}, state.last_error)
            return {"CANCELLED"}

        by_id_name: Dict[str, str] = {}
        by_id_hint: Dict[str, str] = {}
        for entry in items:
            if not isinstance(entry, dict):
                continue
            item_id = entry.get("id")
            name = entry.get("name")
            if isinstance(item_id, str) and isinstance(name, str):
                by_id_name[item_id] = name
                hint = entry.get("target_collection_hint")
                if isinstance(hint, str):
                    by_id_hint[item_id] = hint

        global _AI_ASSET_PREVIEW_SUSPENDED
        _AI_ASSET_PREVIEW_SUSPENDED = True
        material_name_universe = {m.name for m in list(getattr(bpy.data, "materials", []) or [])}
        try:
            for item_id, info in self._id_map.items():
                row: LimeAIAssetItem = state.items.add()
                row.item_type = str(info.get("item_type") or "OBJECT")
                row.object_ref = info.get("object_ref")
                row.material_ref = info.get("material_ref")
                row.collection_ref = info.get("collection_ref")
                row.item_id = item_id
                row.original_name = str(info.get("original_name") or "")
                row.read_only = bool(info.get("read_only") or False)
                row.target_collection_path = ""
                row.target_status = "NONE"
                row.target_confidence = 0.0
                row.target_candidates_json = ""
                row.ai_raw_name = ""
                row.normalization_notes = ""
                row.normalization_changed = False

                suggested_raw = (by_id_name.get(item_id) or "").strip()
                if row.item_type == "OBJECT":
                    suggested_norm = normalize_object_name(suggested_raw) if suggested_raw else ""
                    row.suggested_name = suggested_norm
                    if suggested_raw and suggested_norm != suggested_raw:
                        row.status = "NORMALIZED"
                    elif suggested_norm and not is_valid_object_name(suggested_norm):
                        row.status = "INVALID"
                    else:
                        row.status = ""
                elif row.item_type == "MATERIAL":
                    mat = getattr(row, "material_ref", None)
                    debug_enabled = bool(getattr(state, "debug_material_flow", False))
                    row.ai_raw_name = suggested_raw
                    notes: List[str] = []
                    old_name = (getattr(mat, "name", "") or getattr(row, "original_name", "") or "").strip()
                    if old_name:
                        material_name_universe.discard(old_name)
                    suggested_norm = (
                        _normalize_material_name_for_organizer(suggested_raw, mat=mat, trace=notes) if suggested_raw else ""
                    )
                    forced_tag = (getattr(self, "_forced_material_tag", "") or "").strip()
                    forced_ptrs = set(getattr(self, "_forced_material_ptrs", set()) or set())
                    if suggested_norm and forced_tag and mat is not None:
                        mat_ptr = mat.as_pointer()
                        if (not forced_ptrs) or (mat_ptr in forced_ptrs):
                            forced_name = _force_material_name_tag(suggested_norm, forced_tag)
                            if forced_name != suggested_norm:
                                notes.append(f"Forced context tag: {forced_tag}")
                            suggested_norm = forced_name
                    if suggested_norm and parse_material_name(suggested_norm):
                        unique = bump_material_version_until_unique(material_name_universe, suggested_norm)
                        if unique != suggested_norm:
                            notes.append("Bumped version to avoid name collision")
                        material_name_universe.add(unique)
                        row.suggested_name = unique
                        row.status = _material_status_from_trace(suggested_raw, row.suggested_name, notes)
                    else:
                        row.suggested_name = suggested_norm
                        row.status = "INVALID" if suggested_norm else ""
                        if suggested_norm:
                            notes.append("Output still invalid after normalization")
                        if old_name:
                            material_name_universe.add(old_name)
                    row.normalization_changed = bool(suggested_raw and row.suggested_name and row.suggested_name != suggested_raw)
                    if notes and (debug_enabled or row.normalization_changed or row.status == "INVALID"):
                        row.normalization_notes = "; ".join(notes[:8])
                else:
                    suggested_norm = normalize_collection_name(suggested_raw) if suggested_raw else ""
                    row.suggested_name = suggested_norm
                    if suggested_raw and suggested_norm != suggested_raw:
                        row.status = "NORMALIZED"
                    elif suggested_norm and not is_valid_collection_name(suggested_norm):
                        row.status = "INVALID"
                    else:
                        row.status = ""

                row.selected_for_apply = bool(
                    not row.read_only and bool(row.suggested_name) and not _status_invalid(row.status)
                )
        finally:
            _AI_ASSET_PREVIEW_SUSPENDED = False

        _resolve_object_targets_for_state(
            scene,
            state,
            hints_by_item_id=by_id_hint,
            preserve_confirmed=False,
        )
        _sync_planned_collection_rows(scene, state)
        sync_ai_asset_row_selection(scene)
        self.report({"INFO"}, f"AI suggestions created: {len(state.items)} item(s)")
        return {"FINISHED"}


class LIME_TB_OT_ai_asset_apply_names(Operator):
    bl_idname = "lime_tb.ai_asset_apply_names"
    bl_label = "AI: Apply Names"
    bl_description = "Apply selected AI rename suggestions to objects, materials, and collections"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}
        if getattr(state, "is_busy", False):
            self.report({"WARNING"}, "AI request in progress")
            return {"CANCELLED"}
        if not any(
            [
                bool(getattr(state, "apply_scope_objects", True)),
                bool(getattr(state, "apply_scope_materials", True)),
                bool(getattr(state, "apply_scope_collections", True)),
            ]
        ):
            self.report({"WARNING"}, "Enable at least one Apply Scope filter")
            return {"CANCELLED"}

        plan = _build_unified_plan(scene, state)
        _apply_preview_from_plan(state, plan)
        rename_plan = plan.get("rename_plan", {}) if isinstance(plan, dict) else {}
        object_ops = list(rename_plan.get("object_ops", []))
        material_ops = list(rename_plan.get("material_ops", []))
        collection_ops = list(rename_plan.get("collection_ops", []))
        reorg_plan = plan.get("reorg_plan", {}) if isinstance(plan, dict) else {}

        renamed_objects = 0
        renamed_materials = 0
        renamed_collections = 0
        skipped = 0

        for obj, new_name in object_ops:
            old = obj.name
            try:
                obj.name = new_name
                renamed_objects += 1
            except Exception as ex:
                skipped += 1
                self.report({"WARNING"}, f"Failed to rename object '{old}': {ex}")

        for mat, new_name in material_ops:
            old = mat.name
            try:
                mat.name = new_name
                renamed_materials += 1
            except Exception as ex:
                skipped += 1
                self.report({"WARNING"}, f"Failed to rename material '{old}': {ex}")

        created_collections = 0
        moved_objects = 0
        skipped_ambiguous = 0
        ambiguous_names: List[str] = []
        if bool(getattr(state, "organize_collections", False)) and bool(getattr(state, "apply_scope_objects", True)):
            created_collections, moved_objects, skipped_ambiguous, ambiguous_names = _apply_collection_reorganization(
                scene,
                reorg_plan,
                self.report,
                state,
            )

        if ambiguous_names:
            names_preview = ", ".join(ambiguous_names[:5])
            if len(ambiguous_names) > 5:
                names_preview += ", ..."
            self.report(
                {"WARNING"},
                f"Skipped {len(ambiguous_names)} ambiguous object(s): {names_preview}",
            )

        for coll, new_name in collection_ops:
            old = coll.name
            try:
                coll.name = new_name
                renamed_collections += 1
            except Exception as ex:
                skipped += 1
                self.report({"WARNING"}, f"Failed to rename collection '{old}': {ex}")

        if skipped_ambiguous:
            skipped += skipped_ambiguous
        _update_preview_state(context, state)
        self.report(
            {"INFO"},
            (
                f"Applied: {renamed_objects} object(s), {renamed_materials} material(s), "
                f"{renamed_collections} collection(s). "
                f"Collections created: {created_collections}. Objects moved: {moved_objects}. "
                f"Ambiguous skipped: {len(ambiguous_names)}. "
                f"Skipped: {skipped}."
            ),
        )
        return {"FINISHED"}


class LIME_TB_OT_ai_asset_scope_preset(Operator):
    bl_idname = "lime_tb.ai_asset_scope_preset"
    bl_label = "AI: Scope Preset"
    bl_description = "Apply a quick preset for AI asset apply scope filters"
    bl_options = {"REGISTER"}

    preset: EnumProperty(
        name="Scope Preset",
        items=[
            ("ALL", "All", "Apply objects, materials, and collections"),
            ("OBJECTS", "Only Objects", "Apply object operations only"),
            ("MATERIALS", "Only Materials", "Apply material operations only"),
            ("COLLECTIONS", "Only Collections", "Apply collection operations only"),
        ],
        default="ALL",
    )

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}

        preset = (self.preset or "ALL").upper()
        if preset == "OBJECTS":
            state.apply_scope_objects = True
            state.apply_scope_materials = False
            state.apply_scope_collections = False
        elif preset == "MATERIALS":
            state.apply_scope_objects = False
            state.apply_scope_materials = True
            state.apply_scope_collections = False
        elif preset == "COLLECTIONS":
            state.apply_scope_objects = False
            state.apply_scope_materials = False
            state.apply_scope_collections = True
        else:
            state.apply_scope_objects = True
            state.apply_scope_materials = True
            state.apply_scope_collections = True

        sync_ai_asset_row_selection(scene)
        self.report({"INFO"}, "Apply scope preset updated")
        return {"FINISHED"}


class LIME_TB_OT_ai_asset_refresh_targets(Operator):
    bl_idname = "lime_tb.ai_asset_refresh_targets"
    bl_label = "AI: Refresh Targets"
    bl_description = "Recalculate collection destination targets for object rows"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}
        if getattr(state, "is_busy", False):
            self.report({"WARNING"}, "AI request in progress")
            return {"CANCELLED"}
        if not getattr(state, "items", None):
            self.report({"INFO"}, "No AI suggestions available")
            return {"CANCELLED"}

        _resolve_object_targets_for_state(scene, state, preserve_confirmed=True)
        _sync_planned_collection_rows(scene, state)
        refresh_ai_asset_preview(scene)
        self.report(
            {"INFO"},
            f"Targets refreshed. Ambiguous: {getattr(state, 'planned_ambiguities_objects', 0)}",
        )
        return {"FINISHED"}


def _resolve_target_candidate_items(self, context):
    scene = getattr(context, "scene", None) if context else None
    state = getattr(scene, "lime_ai_assets", None) if scene is not None else None
    row = _find_row_by_item_id(state, getattr(self, "item_id", "")) if state is not None else None
    if row is None:
        return []

    items = []
    for idx, cand in enumerate(_parse_target_candidates_json(getattr(row, "target_candidates_json", "") or "")):
        path = str(cand.get("path") or "").strip()
        if not path:
            continue
        score = float(cand.get("score") or 0.0)
        exists = bool(cand.get("exists", True))
        suffix = "existing" if exists else "will create"
        items.append((path, path, f"Score {score:.2f} ({suffix})", idx))
    return items


def _bulk_target_candidate_items(self, context):
    scene = getattr(context, "scene", None) if context else None
    state = getattr(scene, "lime_ai_assets", None) if scene is not None else None
    if state is None:
        return []

    selected_rows = _selected_object_rows(state)
    if not selected_rows:
        return []

    return _target_option_items_for_rows(scene, state, selected_rows)


def _single_target_candidate_items(self, context):
    scene = getattr(context, "scene", None) if context else None
    state = getattr(scene, "lime_ai_assets", None) if scene is not None else None
    if state is None:
        return []
    row = _find_row_by_item_id(state, getattr(self, "item_id", ""))
    if row is None or getattr(row, "item_type", "") != "OBJECT":
        return []
    return _target_option_items_for_rows(scene, state, [row])


class LIME_TB_OT_ai_asset_resolve_target(Operator):
    bl_idname = "lime_tb.ai_asset_resolve_target"
    bl_label = "AI: Resolve Target"
    bl_description = "Choose a destination collection path for an ambiguous object"
    bl_options = {"REGISTER"}

    item_id: StringProperty(name="Item ID", default="")
    candidate_path: EnumProperty(name="Destination", items=_resolve_target_candidate_items)

    def invoke(self, context, event):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}
        row = _find_row_by_item_id(state, self.item_id)
        if row is None:
            self.report({"ERROR"}, "Target row not found")
            return {"CANCELLED"}

        items = _resolve_target_candidate_items(self, context)
        if not items:
            self.report({"WARNING"}, "No target candidates available")
            return {"CANCELLED"}

        current = (getattr(row, "target_collection_path", "") or "").strip()
        valid_ids = {item[0] for item in items}
        if current in valid_ids:
            self.candidate_path = current
        else:
            self.candidate_path = items[0][0]
        return context.window_manager.invoke_props_dialog(self, width=560)

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        row = _find_row_by_item_id(state, self.item_id) if state is not None else None
        if row is not None:
            layout.label(text=f"Object: {getattr(row, 'original_name', '') or '<unnamed>'}", icon="OBJECT_DATA")
        layout.prop(self, "candidate_path", text="Collection Path")

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}
        row = _find_row_by_item_id(state, self.item_id)
        if row is None:
            self.report({"ERROR"}, "Target row not found")
            return {"CANCELLED"}

        target_path = (self.candidate_path or "").strip()
        if not target_path:
            self.report({"WARNING"}, "No destination selected")
            return {"CANCELLED"}

        row.target_collection_path = target_path
        row.target_status = "CONFIRMED"
        row.target_confidence = max(float(getattr(row, "target_confidence", 0.0) or 0.0), 0.99)
        state.last_used_collection_path = target_path
        _sync_planned_collection_rows(scene, state)
        refresh_ai_asset_preview(scene)
        self.report({"INFO"}, f"Target confirmed: {target_path}")
        return {"FINISHED"}


class LIME_TB_OT_ai_asset_set_target_for_item(Operator):
    bl_idname = "lime_tb.ai_asset_set_target_for_item"
    bl_label = "AI: Re-route Object"
    bl_description = "Set destination collection path for one object row"
    bl_options = {"REGISTER", "UNDO"}

    item_id: StringProperty(name="Item ID", default="")
    destination_path: EnumProperty(name="Destination", items=_single_target_candidate_items)

    def invoke(self, context, event):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}
        row = _find_row_by_item_id(state, self.item_id)
        if row is None or getattr(row, "item_type", "") != "OBJECT":
            self.report({"ERROR"}, "Target object row not found")
            return {"CANCELLED"}

        options = _single_target_candidate_items(self, context)
        if not options:
            self.report({"WARNING"}, "No destination options available")
            return {"CANCELLED"}

        current = _normalize_collection_path_value(getattr(row, "target_collection_path", "") or "")
        valid_ids = {item[0] for item in options}
        self.destination_path = current if current in valid_ids else options[0][0]
        return context.window_manager.invoke_props_dialog(self, width=620)

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        row = _find_row_by_item_id(state, self.item_id) if state is not None else None
        if row is not None:
            layout.label(text=f"Object: {getattr(row, 'original_name', '') or '<unnamed>'}", icon="OBJECT_DATA")
        layout.prop(self, "destination_path", text="Collection Path")

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}
        row = _find_row_by_item_id(state, self.item_id)
        if row is None or getattr(row, "item_type", "") != "OBJECT":
            self.report({"ERROR"}, "Target object row not found")
            return {"CANCELLED"}

        target_path = _normalize_collection_path_value(self.destination_path or "")
        if not target_path:
            self.report({"WARNING"}, "Destination path is not valid")
            return {"CANCELLED"}

        row.target_collection_path = target_path
        row.target_status = "CONFIRMED"
        row.target_confidence = 1.0
        state.last_used_collection_path = target_path
        _sync_planned_collection_rows(scene, state)
        refresh_ai_asset_preview(scene)
        self.report({"INFO"}, f"Re-routed object to {target_path}")
        return {"FINISHED"}


class LIME_TB_OT_ai_asset_set_target_for_selected(Operator):
    bl_idname = "lime_tb.ai_asset_set_target_for_selected"
    bl_label = "AI: Re-route Selected Objects"
    bl_description = "Set a destination collection path for all selected object rows"
    bl_options = {"REGISTER", "UNDO"}

    destination_path: EnumProperty(name="Destination", items=_bulk_target_candidate_items)

    def invoke(self, context, event):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}
        rows = _selected_object_rows(state)
        if not rows:
            self.report({"WARNING"}, "Select at least one object row first")
            return {"CANCELLED"}

        options = _bulk_target_candidate_items(self, context)
        if not options:
            self.report({"WARNING"}, "No destination options available")
            return {"CANCELLED"}

        current_targets = {
            _normalize_collection_path_value(getattr(row, "target_collection_path", "") or "")
            for row in rows
        }
        current_targets.discard("")
        valid_ids = {item[0] for item in options}
        if len(current_targets) == 1:
            only = list(current_targets)[0]
            if only in valid_ids:
                self.destination_path = only
            else:
                self.destination_path = options[0][0]
        else:
            self.destination_path = options[0][0]
        return context.window_manager.invoke_props_dialog(self, width=620)

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        selected_count = len(_selected_object_rows(state)) if state is not None else 0
        layout.label(text=f"Selected object rows: {selected_count}", icon="OBJECT_DATA")
        layout.prop(self, "destination_path", text="Collection Path")

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}
        rows = _selected_object_rows(state)
        if not rows:
            self.report({"WARNING"}, "Select at least one object row first")
            return {"CANCELLED"}

        target_path = _normalize_collection_path_value(self.destination_path or "")
        if not target_path:
            self.report({"WARNING"}, "Destination path is not valid")
            return {"CANCELLED"}

        updated = 0
        for row in rows:
            row.target_collection_path = target_path
            row.target_status = "CONFIRMED"
            row.target_confidence = 1.0
            updated += 1

        state.last_used_collection_path = target_path
        _sync_planned_collection_rows(scene, state)
        refresh_ai_asset_preview(scene)
        self.report({"INFO"}, f"Re-routed {updated} object(s) to {target_path}")
        return {"FINISHED"}


class LIME_TB_OT_ai_asset_clear(Operator):
    bl_idname = "lime_tb.ai_asset_clear"
    bl_label = "AI: Clear"
    bl_description = "Clear AI rename suggestions"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}
        if getattr(state, "is_busy", False):
            self.report({"WARNING"}, "AI request in progress")
            return {"CANCELLED"}

        state.items.clear()
        state.last_error = ""
        state.last_used_collection_path = ""
        _clear_preview_state(state)
        self.report({"INFO"}, "AI suggestions cleared")
        return {"FINISHED"}


class LIME_TB_OT_open_ai_asset_manager(Operator):
    bl_idname = "lime_tb.open_ai_asset_manager"
    bl_label = "Open AI Asset Manager"
    bl_description = "Open AI Asset Organizer in a larger popup window"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=885)

    def draw(self, context):
        from ..ui.ui_ai_asset_organizer import draw_ai_asset_organizer_content

        draw_ai_asset_organizer_content(self.layout, context, for_popup=True)

    def execute(self, context):
        self.report({"INFO"}, "AI Asset Manager opened")
        return {"FINISHED"}


class LIME_TB_OT_ai_asset_test_connection(Operator):
    bl_idname = "lime_tb.ai_asset_test_connection"
    bl_label = "AI: Test Connection"
    bl_description = "Verify OpenRouter connectivity for AI Asset Organizer"
    bl_options = {"REGISTER"}

    def execute(self, context):
        if not has_openrouter_api_key():
            self.report({"ERROR"}, "OpenRouter API key not found in .env")
            return {"CANCELLED"}

        prefs = context.preferences.addons[__package__.split(".")[0]].preferences
        headers = openrouter_headers(prefs)
        models_resp = http_get_json_with_status(OPENROUTER_MODELS_URL, headers=headers, timeout=15)
        data = models_resp.data if models_resp else None
        if not data or not isinstance(data, dict):
            detail = (models_resp.error or "No response body") if models_resp else "No response"
            status = models_resp.status if models_resp else None
            self.report({"ERROR"}, f"OpenRouter models check failed (status={status}): {detail[:220]}")
            return {"CANCELLED"}

        models = [m.get("id") for m in data.get("data", []) if isinstance(m, dict)] if "data" in data else []
        slug = (getattr(prefs, "openrouter_model", "") or "").strip()
        if slug and slug in models:
            self.report({"INFO"}, f"OpenRouter reachable. Model available: {slug}")
        elif slug:
            self.report({"WARNING"}, f"OpenRouter reachable. Model not found in provider list: {slug}")
        else:
            self.report({"INFO"}, "OpenRouter reachable.")

        payload = {
            "model": slug or _DEFAULT_MODEL,
            "messages": [
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": '{"ping": true}'},
            ],
            "temperature": 0,
            "max_tokens": 128,
            "response_format": _schema_json_object(),
        }
        chat_resp = http_post_json_with_status(OPENROUTER_CHAT_URL, payload, headers=headers, timeout=20)
        result = chat_resp.data if chat_resp else None
        content = extract_message_content(result or {}) if result else None
        if content:
            self.report({"INFO"}, "OpenRouter chat endpoint: OK")
        else:
            status = chat_resp.status if chat_resp else None
            detail = (chat_resp.error or "No response body") if chat_resp else "No response"
            self.report({"WARNING"}, f"OpenRouter chat endpoint incomplete (status={status}): {detail[:180]}")
        return {"FINISHED"}


class LIME_TB_OT_ai_asset_material_debug_report(Operator):
    bl_idname = "lime_tb.ai_asset_material_debug_report"
    bl_label = "AI: Material Debug Report"
    bl_description = "Export a material AI/normalization debug report to a Blender text block"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = getattr(context, "scene", None)
        state = getattr(scene, "lime_ai_assets", None) if scene is not None else None
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}

        rows = [row for row in list(getattr(state, "items", []) or []) if getattr(row, "item_type", "") == "MATERIAL"]
        if not rows:
            self.report({"INFO"}, "No material rows available for debug report")
            return {"CANCELLED"}

        lines = [
            "Lime Pipeline - AI Material Normalization Debug Report",
            f"Generated: {datetime.datetime.now().isoformat(timespec='seconds')}",
            f"Rows: {len(rows)}",
            "",
            "material_original | ai_output_raw | final_after_normalization | status | normalization_changed | notes",
        ]
        for row in rows:
            lines.append(
                " | ".join(
                    [
                        str(getattr(row, "original_name", "") or "").replace("\n", " ").strip(),
                        str(getattr(row, "ai_raw_name", "") or "").replace("\n", " ").strip(),
                        str(getattr(row, "suggested_name", "") or "").replace("\n", " ").strip(),
                        str(getattr(row, "status", "") or "").strip(),
                        str(bool(getattr(row, "normalization_changed", False))),
                        str(getattr(row, "normalization_notes", "") or "").replace("\n", " ").strip(),
                    ]
                )
            )

        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        text_name = f"AI_Material_Debug_{stamp}.txt"
        text_block = bpy.data.texts.new(text_name)
        text_block.write("\n".join(lines) + "\n")
        self.report({"INFO"}, f"Debug report created: {text_name}")
        return {"FINISHED"}


class LIME_TB_OT_ai_asset_collection_debug_report(Operator):
    bl_idname = "lime_tb.ai_asset_collection_debug_report"
    bl_label = "AI: Collection Debug Report"
    bl_description = "Export a collection target resolution debug report to a Blender text block"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = getattr(context, "scene", None)
        state = getattr(scene, "lime_ai_assets", None) if scene is not None else None
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}

        rows = [row for row in list(getattr(state, "items", []) or []) if getattr(row, "item_type", "") == "OBJECT"]
        if not rows:
            self.report({"INFO"}, "No object rows available for collection debug report")
            return {"CANCELLED"}

        lines = [
            "Lime Pipeline - AI Collection Resolution Debug Report",
            f"Generated: {datetime.datetime.now().isoformat(timespec='seconds')}",
            f"Rows: {len(rows)}",
            "",
            "object | selected_path | status | confidence | debug_json",
        ]
        for row in rows:
            lines.append(
                " | ".join(
                    [
                        str(getattr(row, "original_name", "") or "").replace("\n", " ").strip(),
                        str(getattr(row, "target_collection_path", "") or "").replace("\n", " ").strip(),
                        str(getattr(row, "target_status", "") or "").strip(),
                        f"{float(getattr(row, 'target_confidence', 0.0) or 0.0):.3f}",
                        str(getattr(row, "target_debug_json", "") or "").replace("\n", " ").strip(),
                    ]
                )
            )

        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        text_name = f"AI_Collection_Debug_{stamp}.txt"
        text_block = bpy.data.texts.new(text_name)
        text_block.write("\n".join(lines) + "\n")
        self.report({"INFO"}, f"Collection debug report created: {text_name}")
        return {"FINISHED"}


__all__ = [
    "refresh_ai_asset_preview",
    "LIME_TB_OT_ai_asset_suggest_names",
    "LIME_TB_OT_ai_asset_apply_names",
    "LIME_TB_OT_ai_asset_scope_preset",
    "LIME_TB_OT_ai_asset_refresh_targets",
    "LIME_TB_OT_ai_asset_resolve_target",
    "LIME_TB_OT_ai_asset_set_target_for_item",
    "LIME_TB_OT_ai_asset_set_target_for_selected",
    "LIME_TB_OT_ai_asset_clear",
    "LIME_TB_OT_open_ai_asset_manager",
    "LIME_TB_OT_ai_asset_test_connection",
    "LIME_TB_OT_ai_asset_material_debug_report",
    "LIME_TB_OT_ai_asset_collection_debug_report",
]
