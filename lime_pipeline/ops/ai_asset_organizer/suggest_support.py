"""Support helpers for AI Asset Organizer suggest flow."""

from __future__ import annotations

import base64
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import bpy
from bpy.types import Collection, Material, Object

from ...core.ai_asset_material_rules import (
    extract_context_material_tag_directive as core_extract_context_material_tag_directive,
    fold_text_for_match as core_fold_text_for_match,
    force_material_name_tag as core_force_material_name_tag,
    material_status_from_trace as core_material_status_from_trace,
    normalize_material_name_for_organizer as core_normalize_material_name_for_organizer,
)
from ...core.ai_asset_prompt import build_prompt as core_build_prompt
from ...core.collection_resolver import tokenize as tokenize_name
from .material_probe import material_shader_profile
from .scene_snapshot import build_scene_collection_snapshot, object_collection_paths
from .target_resolver import resolve_object_targets_for_state


_MAX_IMAGE_BYTES = 3 * 1024 * 1024
_SHOT_ROOT_RE = re.compile(r"^SHOT \d{2,3}$")
_SHOT_CHILD_RE = re.compile(r"^SH\d{2,3}_")
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


def addon_prefs(context) -> Optional[Any]:
    try:
        return context.preferences.addons[__package__.split(".")[0]].preferences
    except Exception:
        return None


def is_object_read_only(obj: Object) -> bool:
    return bool(getattr(obj, "library", None) or getattr(obj, "override_library", None))


def is_material_read_only(mat: Material) -> bool:
    return bool(getattr(mat, "library", None) or getattr(mat, "override_library", None))


def is_collection_read_only(coll: Collection) -> bool:
    return bool(getattr(coll, "library", None) or getattr(coll, "override_library", None))


def _is_shot_collection_name(name: str) -> bool:
    value = (name or "").strip()
    return bool(_SHOT_ROOT_RE.match(value) or _SHOT_CHILD_RE.match(value))


def collect_selection(
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


def _image_mime_for_path(path: str) -> Optional[str]:
    ext = (os.path.splitext(path)[1] or "").lower()
    if ext in {".png"}:
        return "image/png"
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext in {".webp"}:
        return "image/webp"
    return None


def load_image_data_url(path: str) -> Tuple[Optional[str], Optional[str]]:
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


def object_semantic_tags(name: str, obj_type: str) -> List[str]:
    tokens = {t.lower() for t in tokenize_name(name or "")}
    tags: List[str] = []
    for label, keywords in _OBJECT_HINT_KEYWORDS.items():
        if tokens.intersection(keywords):
            tags.append(label)
    kind = (obj_type or "").strip().upper()
    if kind in {"LIGHT", "CAMERA"}:
        tags.append(kind.title())
    return tags[:4]


def object_root_name(obj: Optional[Object]) -> str:
    current = obj
    guard = 0
    last_name = ""
    while current is not None and guard < 128:
        last_name = str(getattr(current, "name", "") or last_name)
        current = getattr(current, "parent", None)
        guard += 1
    return last_name


def object_hierarchy_depth(obj: Optional[Object]) -> int:
    current = getattr(obj, "parent", None) if obj is not None else None
    depth = 0
    guard = 0
    while current is not None and guard < 128:
        depth += 1
        current = getattr(current, "parent", None)
        guard += 1
    return depth


def empty_role_hint(obj: Optional[Object]) -> str:
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


def infer_hierarchy_role(obj: Optional[Object]) -> Tuple[str, str]:
    if obj is None:
        return "COMPONENT", "No object reference"
    name = str(getattr(obj, "name", "") or "")
    tokens = {t.lower() for t in tokenize_name(name)}
    obj_type = str(getattr(obj, "type", "") or "").upper()
    parent = getattr(obj, "parent", None)
    depth = object_hierarchy_depth(obj)
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


def build_scene_summary(
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


def build_object_group_hints(objects: Sequence[Dict[str, object]]) -> Dict[str, object]:
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


def build_prompt(
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
    return core_build_prompt(
        context_text,
        scene_summary,
        objects,
        materials,
        collections,
        collection_hierarchy=collection_hierarchy,
        material_scene_context=material_scene_context,
        object_group_hints=object_group_hints,
    )


def normalize_material_name_for_organizer(
    raw: str,
    *,
    mat: Optional[Material] = None,
    trace: Optional[List[str]] = None,
) -> str:
    profile = material_shader_profile(mat) if mat is not None else None
    source_name = str(getattr(mat, "name", "") or "") if mat is not None else ""
    return core_normalize_material_name_for_organizer(
        raw,
        profile=profile,
        source_name=source_name,
        trace=trace,
    )


def extract_context_material_tag_directive(context_text: str) -> Tuple[str, str]:
    return core_extract_context_material_tag_directive(context_text)


def force_material_name_tag(name: str, forced_tag: str) -> str:
    return core_force_material_name_tag(name, forced_tag)


def fold_text_for_match(value: str) -> str:
    return core_fold_text_for_match(value)


def material_status_from_trace(
    ai_raw: str,
    final_name: str,
    notes: Sequence[str],
) -> str:
    return core_material_status_from_trace(ai_raw, final_name, notes)


__all__ = [
    "addon_prefs",
    "build_object_group_hints",
    "build_prompt",
    "build_scene_collection_snapshot",
    "build_scene_summary",
    "collect_selection",
    "empty_role_hint",
    "extract_context_material_tag_directive",
    "fold_text_for_match",
    "force_material_name_tag",
    "infer_hierarchy_role",
    "is_collection_read_only",
    "is_material_read_only",
    "is_object_read_only",
    "load_image_data_url",
    "material_status_from_trace",
    "normalize_material_name_for_organizer",
    "object_collection_paths",
    "object_hierarchy_depth",
    "object_root_name",
    "object_semantic_tags",
    "resolve_object_targets_for_state",
    "tokenize_name",
]

