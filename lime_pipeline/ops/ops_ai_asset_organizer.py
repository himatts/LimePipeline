"""AI Asset Organizer operators.

Suggests and applies names for selected objects/materials/collections with AI,
plus optional safe collection reorganization.
"""

from __future__ import annotations

import base64
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
    extract_message_content,
    has_openrouter_api_key,
    http_post_json,
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
    return {
        "path_to_collection": path_to_collection,
        "collection_ptr_to_paths": collection_ptr_to_paths,
        "candidates": candidates,
        "hierarchy_paths": hierarchy_paths,
    }


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
    candidates = [c for c in list(snapshot.get("candidates", []) or []) if not getattr(c, "is_shot_root", False)]
    if not candidates:
        candidates = list(snapshot.get("candidates", []) or [])
    hints = hints_by_item_id or {}

    for row in list(getattr(state, "items", []) or []):
        if getattr(row, "item_type", "") != "OBJECT":
            continue
        obj = getattr(row, "object_ref", None)
        if obj is None:
            row.target_collection_path = ""
            row.target_status = "NONE"
            row.target_confidence = 0.0
            row.target_candidates_json = ""
            continue

        if preserve_confirmed and getattr(row, "target_status", "") == "CONFIRMED":
            continue

        current_paths = _object_collection_paths(obj, snapshot)
        preferred_roots = _preferred_shot_roots(current_paths)
        hint_raw = (hints.get(getattr(row, "item_id", "") or "") or "").strip()
        hint_path = _normalize_hint_path(hint_raw, candidates, preferred_roots)

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


def _normalize_material_name_for_organizer(raw: str, *, mat: Optional[Material] = None) -> str:
    """Normalize to MAT_{Tag?}_{MaterialType}_{Finish}_{V##} for organizer workflows."""

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
                finish_tokens = finish_tokens[1:]

        # Recover degraded AI proposals such as Plastic_MetalPolished / Plastic_GlassClear.
        if mtype == "Plastic" and finish_tokens:
            inferred = "Plastic"
            for token in finish_tokens:
                inferred = _token_mapped_type(token)
                if inferred != "Plastic":
                    break
            if inferred != "Plastic":
                mtype = inferred
                if len(finish_tokens) > 1:
                    head_type = _token_mapped_type(finish_tokens[0])
                    if head_type == inferred:
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
        scene_tag = str(parsed.get("scene_tag") or "")
        material_type = str(parsed.get("material_type") or "Plastic")
        finish = str(parsed.get("finish") or "Generic")
        material_type, finish = _repair_components(material_type, finish)
        version_idx = int(parsed.get("version_index") or 1)
        normalized = build_material_name_with_scene_tag(scene_tag, material_type, finish, version_idx)
        return _apply_material_profile_guardrails(normalized, mat)

    cleaned = re.sub(r"[^A-Za-z0-9_ ]+", "_", text)
    cleaned = re.sub(r"[\s_]+", "_", cleaned).strip("_")
    if not cleaned:
        return ""
    parts = [p for p in cleaned.split("_") if p]
    if not parts:
        return ""
    if parts[0].upper() == "MAT":
        parts = parts[1:]
    if not parts:
        return build_material_name_with_scene_tag("", "Plastic", "Generic", 1)

    version_idx = 1
    tail = parts[-1].upper()
    parsed_ver = parse_material_version(tail)
    if parsed_ver is not None:
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
            material_type = candidate_type
            finish_src = "_".join(parts[2:]) if len(parts) > 2 else "Generic"
            _, finish = _repair_components(material_type, finish_src)
            normalized = build_material_name_with_scene_tag(scene_tag, material_type, finish, version_idx)
            return _apply_material_profile_guardrails(normalized, mat)

    finish_src = "_".join(parts[1:]) if len(parts) > 1 else "Generic"
    material_type, finish = _repair_components(material_type, finish_src)
    normalized = build_material_name_with_scene_tag(scene_tag, material_type, finish, version_idx)
    return _apply_material_profile_guardrails(normalized, mat)


def _build_prompt(
    context_text: str,
    scene_summary: str,
    objects: List[Dict[str, object]],
    materials: List[Dict[str, object]],
    collections: List[Dict[str, object]],
    *,
    collection_hierarchy: Optional[List[str]] = None,
    material_scene_context: Optional[Dict[str, object]] = None,
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
        "- Material naming must consider all existing scene materials from material_scene_context (including non-selected).\n"
        "- Material naming must respect shader_profile cues in each material (metallic, roughness, transmission, emission).\n"
        "- Avoid Metal type when metallic is low and there is no explicit metal cue.\n"
        "- If finish/type is uncertain, prefer conservative generic names instead of over-specific labels.\n"
        "- Use specific finishes (e.g., Brushed, Chrome, Anodized, Frosted) only with clear evidence from source names, texture hints, or shader_profile.\n"
        "- Do not classify as Emissive when emission is effectively off (black emission or negligible emission energy).\n"
        "- Never propose a material name that already exists; if a group exists, propose the next available V##.\n"
        "- Optional for objects: include `target_collection_hint` with a full path when confident.\n"
        "- Use hierarchy/context hints (parent_id, children_count, shared_data_users, collection_hints, used_on).\n"
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
                "children_count": len(list(getattr(obj, "children", []) or [])),
                "shared_data_users": shared_data_users,
                "collection_hints": coll_hints,
                "collection_paths": collection_paths[:5],
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
        prompt = _build_prompt(
            getattr(state, "context", ""),
            scene_summary,
            obj_items,
            mat_items,
            col_items,
            collection_hierarchy=hierarchy_paths,
            material_scene_context=material_scene_context,
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
                    old_name = (getattr(mat, "name", "") or getattr(row, "original_name", "") or "").strip()
                    if old_name:
                        material_name_universe.discard(old_name)
                    suggested_norm = (
                        _normalize_material_name_for_organizer(suggested_raw, mat=mat) if suggested_raw else ""
                    )
                    forced_tag = (getattr(self, "_forced_material_tag", "") or "").strip()
                    forced_ptrs = set(getattr(self, "_forced_material_ptrs", set()) or set())
                    if suggested_norm and forced_tag and mat is not None:
                        mat_ptr = mat.as_pointer()
                        if (not forced_ptrs) or (mat_ptr in forced_ptrs):
                            suggested_norm = _force_material_name_tag(suggested_norm, forced_tag)
                    if suggested_norm and parse_material_name(suggested_norm):
                        unique = bump_material_version_until_unique(material_name_universe, suggested_norm)
                        material_name_universe.add(unique)
                        row.suggested_name = unique
                        if suggested_raw and unique != suggested_raw:
                            row.status = "NORMALIZED"
                        else:
                            row.status = ""
                    else:
                        row.suggested_name = suggested_norm
                        row.status = "INVALID" if suggested_norm else ""
                        if old_name:
                            material_name_universe.add(old_name)
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
        refresh_ai_asset_preview(scene)
        self.report({"INFO"}, f"Target confirmed: {target_path}")
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


__all__ = [
    "refresh_ai_asset_preview",
    "LIME_TB_OT_ai_asset_suggest_names",
    "LIME_TB_OT_ai_asset_apply_names",
    "LIME_TB_OT_ai_asset_scope_preset",
    "LIME_TB_OT_ai_asset_refresh_targets",
    "LIME_TB_OT_ai_asset_resolve_target",
    "LIME_TB_OT_ai_asset_clear",
]
