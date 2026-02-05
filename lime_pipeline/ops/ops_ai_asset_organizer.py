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
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import bpy
from bpy.types import Collection, Material, Object, Operator

from ..core.asset_naming import (
    asset_group_key_from_name,
    bump_material_version_until_unique,
    ensure_unique_collection_name,
    ensure_unique_object_name,
    is_valid_collection_name,
    is_valid_object_name,
    normalize_collection_name,
    normalize_object_name,
)
from ..core.ai_asset_response import parse_items_from_response as parse_ai_asset_items
from ..core.material_naming import ALLOWED_MATERIAL_TYPES, parse_name as parse_material_name
from ..props_ai_assets import LimeAIAssetItem
from .ai_http import (
    OPENROUTER_CHAT_URL,
    extract_message_content,
    http_post_json,
    openrouter_headers,
    parse_json_from_text,
)


_DEFAULT_MODEL = "google/gemini-2.0-flash-lite-001"
_MAX_IMAGE_BYTES = 3 * 1024 * 1024

_SHOT_ROOT_RE = re.compile(r"^SHOT \d{2,3}$")
_SHOT_CHILD_RE = re.compile(r"^SH\d{2,3}_")
_GENERIC_COLLECTION_RE = re.compile(r"^Collection(?:\.\d{3})?$")

_RESERVED_GROUP_NAMES = {"Asset", "Object", "Collection", "Material"}


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


def _object_uses_shot_structure(obj: Object) -> bool:
    for coll in list(getattr(obj, "users_collection", []) or []):
        if _is_shot_collection_name(getattr(coll, "name", "") or ""):
            return True
    return False


def _find_root_child(scene, name: str) -> Optional[Collection]:
    root = getattr(scene, "collection", None)
    if root is None:
        return None
    for child in list(getattr(root, "children", []) or []):
        if (getattr(child, "name", "") or "") == name:
            return child
    return None


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


def _build_prompt(
    context_text: str,
    scene_summary: str,
    objects: List[Dict[str, object]],
    materials: List[Dict[str, object]],
    collections: List[Dict[str, object]],
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
    compact_json = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))

    return (
        "Return ONLY JSON per schema.\n"
        f"{context_line}"
        "Rules:\n"
        "- Objects: CamelCase ASCII alphanumeric, no spaces/underscores/dots/dashes, no shot/scene prefixes.\n"
        "- Materials: MAT_{SceneTag?}_{MaterialType}_{Finish}_{V##}. SceneTag optional.\n"
        f"- MaterialType must be one of: {allowed_types}.\n"
        "- Collections: CamelCase ASCII alphanumeric, no spaces/underscores/dots/dashes, avoid shot prefixes.\n"
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
        "max_tokens": 900,
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


def _row_can_apply(row: LimeAIAssetItem) -> bool:
    if not getattr(row, "selected_for_apply", False):
        return False
    if getattr(row, "read_only", False):
        return False
    suggested = (getattr(row, "suggested_name", "") or "").strip()
    if not suggested:
        return False
    if _status_invalid(getattr(row, "status", "")):
        return False
    return True


def _build_rename_plan(state) -> Dict[str, object]:
    obj_existing = {o.name for o in bpy.data.objects}
    mat_existing = {m.name for m in bpy.data.materials}
    coll_existing = {c.name for c in bpy.data.collections}

    object_ops: List[Tuple[Object, str]] = []
    material_ops: List[Tuple[Material, str]] = []
    collection_ops: List[Tuple[Collection, str]] = []
    future_object_names: Dict[int, str] = {}
    org_objects: List[Object] = []
    org_seen: set[int] = set()

    for row in list(getattr(state, "items", []) or []):
        if getattr(row, "item_type", "OBJECT") == "OBJECT":
            obj = getattr(row, "object_ref", None)
            if obj is None:
                continue
            key = obj.as_pointer()
            if _row_can_apply(row) and key not in org_seen:
                org_seen.add(key)
                org_objects.append(obj)
            if not _row_can_apply(row):
                continue
            old = obj.name
            obj_existing.discard(old)
            normalized = normalize_object_name(getattr(row, "suggested_name", ""))
            if not is_valid_object_name(normalized):
                obj_existing.add(old)
                continue
            unique = ensure_unique_object_name(normalized, obj_existing)
            obj_existing.add(unique)
            future_object_names[key] = unique
            if unique != old:
                object_ops.append((obj, unique))
            continue

        if getattr(row, "item_type", "") == "MATERIAL":
            mat = getattr(row, "material_ref", None)
            if mat is None or not _row_can_apply(row):
                continue
            old = mat.name
            mat_existing.discard(old)
            suggested = (getattr(row, "suggested_name", "") or "").strip()
            if not parse_material_name(suggested):
                mat_existing.add(old)
                continue
            unique = bump_material_version_until_unique(mat_existing, suggested)
            mat_existing.add(unique)
            if unique != old:
                material_ops.append((mat, unique))
            continue

        if getattr(row, "item_type", "") == "COLLECTION":
            coll = getattr(row, "collection_ref", None)
            if coll is None or not _row_can_apply(row):
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
        "future_object_names": future_object_names,
        "org_objects": org_objects,
    }


def _build_collection_reorg_plan(
    scene,
    objects: Iterable[Object],
    *,
    future_object_names: Optional[Dict[int, str]] = None,
) -> Dict[str, object]:
    future_object_names = future_object_names or {}
    unique_objects: List[Object] = []
    seen: set[int] = set()
    for obj in list(objects or []):
        if obj is None:
            continue
        key = obj.as_pointer()
        if key in seen:
            continue
        seen.add(key)
        unique_objects.append(obj)

    group_key_by_obj: Dict[int, str] = {}
    group_counts: Dict[str, int] = {}
    for obj in unique_objects:
        if _is_object_read_only(obj) or _object_uses_shot_structure(obj):
            continue
        if getattr(obj, "type", "") in {"LIGHT", "CAMERA"}:
            continue
        name_hint = future_object_names.get(obj.as_pointer(), obj.name)
        key = asset_group_key_from_name(name_hint)
        if not key or key in _RESERVED_GROUP_NAMES:
            continue
        group_key_by_obj[obj.as_pointer()] = key
        group_counts[key] = group_counts.get(key, 0) + 1

    create_names: set[str] = set()
    move_plan: List[Tuple[Object, str]] = []
    root_names = {c.name for c in list(getattr(scene.collection, "children", []) or [])}

    for obj in unique_objects:
        if _is_object_read_only(obj) or _object_uses_shot_structure(obj):
            continue

        target_name = ""
        obj_type = getattr(obj, "type", "")
        if obj_type == "LIGHT":
            target_name = "Lights"
        elif obj_type == "CAMERA":
            target_name = "Cameras"
        else:
            key = group_key_by_obj.get(obj.as_pointer(), "")
            if key and group_counts.get(key, 0) >= 2:
                target_name = key

        if not target_name:
            continue

        users_collection = list(getattr(obj, "users_collection", []) or [])
        has_generic_source = (not users_collection) or any(_is_generic_collection(c, scene) for c in users_collection)
        if not has_generic_source:
            continue

        target_coll = _find_root_child(scene, target_name)
        linked_to_target = bool(target_coll is not None and obj in list(getattr(target_coll, "objects", []) or []))
        generic_to_unlink = [c for c in users_collection if _is_generic_collection(c, scene) and c != target_coll]

        if linked_to_target and not generic_to_unlink:
            continue

        move_plan.append((obj, target_name))
        if target_coll is None and target_name not in root_names:
            create_names.add(target_name)
            root_names.add(target_name)

    return {"create_names": create_names, "moves": move_plan}


def _update_preview_state(context, state) -> None:
    rename_plan = _build_rename_plan(state)
    obj_count = len(rename_plan.get("object_ops", []))
    mat_count = len(rename_plan.get("material_ops", []))
    col_count = len(rename_plan.get("collection_ops", []))

    create_count = 0
    move_count = 0
    if bool(getattr(state, "organize_collections", False)):
        reorg_plan = _build_collection_reorg_plan(
            context.scene,
            rename_plan.get("org_objects", []),
            future_object_names=rename_plan.get("future_object_names", {}),
        )
        create_count = len(reorg_plan.get("create_names", []))
        move_count = len(reorg_plan.get("moves", []))

    state.planned_renames_objects = obj_count
    state.planned_renames_materials = mat_count
    state.planned_renames_collections = col_count
    state.planned_collections_created = create_count
    state.planned_objects_moved = move_count
    state.preview_summary = (
        f"Will rename {obj_count} objects, {mat_count} materials, {col_count} collections.\n"
        f"Will create {create_count} collections and move {move_count} objects."
    )
    state.preview_dirty = False


def _ensure_root_collection(scene, desired_name: str, root_names: set[str]) -> Tuple[Optional[Collection], bool]:
    existing = _find_root_child(scene, desired_name)
    if existing is not None:
        return existing, False
    unique = ensure_unique_collection_name(desired_name, root_names)
    try:
        coll = bpy.data.collections.new(unique)
        scene.collection.children.link(coll)
        root_names.add(unique)
        return coll, True
    except Exception:
        return None, False


def _apply_collection_reorganization(scene, reorg_plan: Dict[str, object], report) -> Tuple[int, int]:
    created_count = 0
    moved_count = 0

    root_names = {c.name for c in list(getattr(scene.collection, "children", []) or [])}
    target_by_request: Dict[str, Collection] = {}

    create_names = sorted(list(reorg_plan.get("create_names", set()) or []))
    for requested in create_names:
        coll, created = _ensure_root_collection(scene, requested, root_names)
        if coll is None:
            report({"WARNING"}, f"Failed to create collection '{requested}'")
            continue
        target_by_request[requested] = coll
        if created:
            created_count += 1

    for obj, requested in list(reorg_plan.get("moves", []) or []):
        if obj is None:
            continue
        target = target_by_request.get(requested) or _find_root_child(scene, requested)
        if target is None:
            target, created = _ensure_root_collection(scene, requested, root_names)
            if target is None:
                report({"WARNING"}, f"Missing target collection for object '{obj.name}'")
                continue
            if created:
                created_count += 1
            target_by_request[requested] = target

        changed = False
        try:
            if obj not in list(getattr(target, "objects", []) or []):
                target.objects.link(obj)
                changed = True
        except Exception as ex:
            report({"WARNING"}, f"Failed linking '{obj.name}' to '{target.name}': {ex}")
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

        if changed:
            moved_count += 1

    return created_count, moved_count


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
        if not (getattr(prefs, "openrouter_api_key", "") or "").strip():
            self.report({"ERROR"}, "OpenRouter API key not set in Preferences")
            return {"CANCELLED"}

        include_collections = bool(getattr(state, "include_collections", True))
        objects, materials, collections = _collect_selection(context, include_collections=include_collections)
        if not objects:
            self.report({"ERROR"}, "No objects selected")
            return {"CANCELLED"}

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
            coll_hints = [
                c.name
                for c in list(getattr(obj, "users_collection", []) or [])
                if c is not None and not _is_shot_collection_name(c.name or "")
            ][:3]
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
        prompt = _build_prompt(getattr(state, "context", ""), scene_summary, obj_items, mat_items, col_items)
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
        state.preview_dirty = False
        state.planned_renames_objects = 0
        state.planned_renames_materials = 0
        state.planned_renames_collections = 0
        state.planned_collections_created = 0
        state.planned_objects_moved = 0

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
                    by_id: Dict[str, str] = {}
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
                            item_id = entry.get("id")
                            name = entry.get("name")
                            if isinstance(item_id, str) and isinstance(name, str):
                                by_id[item_id] = name

                    if by_id:
                        items = [{"id": k, "name": v} for k, v in by_id.items()]
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

        by_id: Dict[str, str] = {}
        for entry in items:
            if not isinstance(entry, dict):
                continue
            item_id = entry.get("id")
            name = entry.get("name")
            if isinstance(item_id, str) and isinstance(name, str):
                by_id[item_id] = name

        for item_id, info in self._id_map.items():
            row: LimeAIAssetItem = state.items.add()
            row.item_type = str(info.get("item_type") or "OBJECT")
            row.object_ref = info.get("object_ref")
            row.material_ref = info.get("material_ref")
            row.collection_ref = info.get("collection_ref")
            row.original_name = str(info.get("original_name") or "")
            row.read_only = bool(info.get("read_only") or False)

            suggested_raw = (by_id.get(item_id) or "").strip()
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
                row.suggested_name = suggested_raw
                row.status = "" if (not suggested_raw or parse_material_name(suggested_raw)) else "INVALID"
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

        _update_preview_state(context, state)
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

        _update_preview_state(context, state)
        rename_plan = _build_rename_plan(state)
        object_ops = list(rename_plan.get("object_ops", []))
        material_ops = list(rename_plan.get("material_ops", []))
        collection_ops = list(rename_plan.get("collection_ops", []))

        renamed_objects = 0
        renamed_materials = 0
        renamed_collections = 0
        skipped = 0

        successful_materials: List[Material] = []
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
                successful_materials.append(mat)
            except Exception as ex:
                skipped += 1
                self.report({"WARNING"}, f"Failed to rename material '{old}': {ex}")

        for coll, new_name in collection_ops:
            old = coll.name
            try:
                coll.name = new_name
                renamed_collections += 1
            except Exception as ex:
                skipped += 1
                self.report({"WARNING"}, f"Failed to rename collection '{old}': {ex}")

        created_collections = 0
        moved_objects = 0
        if bool(getattr(state, "organize_collections", False)):
            reorg_plan = _build_collection_reorg_plan(scene, rename_plan.get("org_objects", []))
            created_collections, moved_objects = _apply_collection_reorganization(scene, reorg_plan, self.report)

        _update_preview_state(context, state)
        self.report(
            {"INFO"},
            (
                f"Applied: {renamed_objects} object(s), {renamed_materials} material(s), "
                f"{renamed_collections} collection(s). "
                f"Collections created: {created_collections}. Objects moved: {moved_objects}. "
                f"Skipped: {skipped}."
            ),
        )
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
        state.preview_summary = ""
        state.preview_dirty = False
        state.planned_renames_objects = 0
        state.planned_renames_materials = 0
        state.planned_renames_collections = 0
        state.planned_collections_created = 0
        state.planned_objects_moved = 0
        self.report({"INFO"}, "AI suggestions cleared")
        return {"FINISHED"}


__all__ = [
    "LIME_TB_OT_ai_asset_suggest_names",
    "LIME_TB_OT_ai_asset_apply_names",
    "LIME_TB_OT_ai_asset_clear",
]
