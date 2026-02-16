"""Suggest operators for AI Asset Organizer."""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

import bpy
from bpy.types import Operator

from ...core.asset_naming import (
    bump_material_version_until_unique,
    is_valid_collection_name,
    is_valid_object_name,
    normalize_collection_name,
    normalize_object_name,
)
from ...core.material_naming import parse_name as parse_material_name
from ...props_ai_assets import LimeAIAssetItem
from .material_probe import (
    build_material_scene_context,
    material_shader_profile,
    material_texture_hints,
)
from .openrouter_client import DEFAULT_MODEL, openrouter_suggest
from .planner import clear_preview_state
from .runtime_api import suspend_preview, sync_planned_rows, sync_row_selection
from .suggest_support import (
    addon_prefs,
    build_object_group_hints,
    build_prompt,
    build_scene_collection_snapshot,
    build_scene_summary,
    collect_selection,
    context_requests_material_tag,
    empty_role_hint,
    extract_context_material_tag_directive,
    fold_text_for_match,
    force_material_name_tag,
    infer_hierarchy_role,
    is_collection_read_only,
    is_material_read_only,
    is_object_read_only,
    load_image_data_url,
    material_status_from_trace,
    normalize_material_name_for_organizer,
    normalize_tag_token,
    object_collection_paths,
    object_hierarchy_depth,
    object_root_name,
    object_semantic_tags,
    resolve_object_targets_for_state,
    tokenize_name,
)
from ..ai_http import has_openrouter_api_key, openrouter_headers


def _status_invalid(status: str) -> bool:
    return (status or "").strip().upper().startswith("INVALID")


def _material_tag_candidate_from_object_name(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return ""
    lead = raw.split("_", 1)[0].strip()
    tag = normalize_tag_token(lead)
    if tag:
        return tag
    return normalize_tag_token(raw)


def _infer_auto_material_tag(usage_names: List[str]) -> str:
    votes: Dict[str, int] = {}
    for name in list(usage_names or []):
        candidate = _material_tag_candidate_from_object_name(str(name or ""))
        if not candidate:
            continue
        votes[candidate] = votes.get(candidate, 0) + 1
    if not votes:
        return ""
    return sorted(votes.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0][0]


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
    _require_material_tag: bool = False
    _auto_material_tag_by_ptr: Dict[int, str] = {}

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

        prefs = addon_prefs(context)
        if prefs is None:
            self.report({"ERROR"}, "Addon preferences unavailable")
            return {"CANCELLED"}
        if not has_openrouter_api_key():
            self.report({"ERROR"}, "OpenRouter API key not found in .env")
            return {"CANCELLED"}

        include_collections = bool(getattr(state, "include_collections", True))
        objects, materials, collections = collect_selection(context, include_collections=include_collections)
        if not objects:
            self.report({"ERROR"}, "No objects selected")
            return {"CANCELLED"}
        forced_tag, object_filter = extract_context_material_tag_directive(getattr(state, "context", "") or "")
        self._require_material_tag = context_requests_material_tag(getattr(state, "context", "") or "")
        self._forced_material_tag = forced_tag
        self._forced_material_object_filter = object_filter
        self._forced_material_ptrs = set()
        self._auto_material_tag_by_ptr = {}
        if forced_tag:
            candidate_objects = list(objects)
            if object_filter:
                needle = fold_text_for_match(object_filter)
                candidate_objects = [
                    obj
                    for obj in objects
                    if needle and needle in fold_text_for_match(getattr(obj, "name", "") or "")
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
        scene_snapshot = build_scene_collection_snapshot(scene)
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
            root_name = object_root_name(obj)
            depth = object_hierarchy_depth(obj)
            sibling_count = 0
            if parent is not None:
                sibling_count = max(0, len(list(getattr(parent, "children", []) or [])) - 1)
            children = list(getattr(obj, "children", []) or [])
            children_preview = [str(getattr(child, "name", "") or "") for child in children[:6]]
            empty_role = empty_role_hint(obj)
            hierarchy_role, hierarchy_role_reason = infer_hierarchy_role(obj)
            collection_paths = object_collection_paths(obj, scene_snapshot)
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
                "semantic_tags": object_semantic_tags(obj.name, str(getattr(obj, "type", "") or "")),
            }
            obj_items.append(item)
            self._id_map[token] = {
                "item_type": "OBJECT",
                "object_ref": obj,
                "material_ref": None,
                "collection_ref": None,
                "original_name": obj.name,
                "read_only": is_object_read_only(obj),
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

        default_auto_tag = _infer_auto_material_tag([str(getattr(obj, "name", "") or "") for obj in list(objects or [])])
        for mat in list(materials or []):
            if mat is None:
                continue
            ptr = mat.as_pointer()
            auto_tag = _infer_auto_material_tag(mat_usage_names.get(ptr, []))
            if not auto_tag:
                auto_tag = default_auto_tag
            if auto_tag:
                self._auto_material_tag_by_ptr[ptr] = auto_tag

        for idx, mat in enumerate(materials[:60]):
            token = f"mat_{idx}"
            entry = {"id": token, "name": mat.name}
            used_on = mat_usage_names.get(mat.as_pointer(), [])
            used_on_ids = mat_usage_ids.get(mat.as_pointer(), [])
            if used_on:
                entry["used_on"] = used_on[:5]
            if used_on_ids:
                entry["used_on_ids"] = used_on_ids[:5]
            entry["shader_profile"] = material_shader_profile(mat)
            texture_hints = material_texture_hints(mat)
            if texture_hints:
                entry["texture_hints"] = texture_hints
            mat_items.append(entry)
            self._id_map[token] = {
                "item_type": "MATERIAL",
                "object_ref": None,
                "material_ref": mat,
                "collection_ref": None,
                "original_name": mat.name,
                "read_only": is_material_read_only(mat),
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
                "read_only": is_collection_read_only(coll),
            }

        if len(objects) > 60 or len(materials) > 60 or len(collections) > 60:
            self.report({"WARNING"}, "Selection is large; only first 60 items per category are sent to AI")

        scene_summary = build_scene_summary(obj_items, mat_items, col_items)
        material_scene_context = build_material_scene_context(materials)
        object_group_hints = build_object_group_hints(obj_items)
        prompt = build_prompt(
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
        model = (getattr(prefs, "openrouter_model", "") or "").strip() or DEFAULT_MODEL
        debug = bool(getattr(prefs, "openrouter_debug", False))

        image_data_url = None
        if getattr(state, "use_image_context", False):
            raw_path = (getattr(state, "image_path", "") or "").strip()
            if raw_path:
                resolved = bpy.path.abspath(raw_path)
                image_data_url, image_err = load_image_data_url(resolved)
                if image_err:
                    self.report({"WARNING"}, image_err)
                    if debug:
                        print("[AI Asset Organizer] Image skipped:", image_err)

        state.is_busy = True
        state.last_error = ""
        state.items.clear()
        state.preview_summary = ""
        clear_preview_state(state)

        self._result = None
        self._error = None

        def worker():
            try:
                total_items = len(obj_items) + len(mat_items) + len(col_items)
                items, err, finish_reason = openrouter_suggest(
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
                    combined: List[tuple[str, Dict[str, object]]] = []
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
                        chunk_summary = build_scene_summary(chunk_objects, chunk_materials, chunk_collections)
                        chunk_prompt = build_prompt(
                            getattr(state, "context", ""),
                            chunk_summary,
                            chunk_objects,
                            chunk_materials,
                            chunk_collections,
                            collection_hierarchy=hierarchy_paths,
                            material_scene_context=material_scene_context,
                            object_group_hints=object_group_hints,
                        )
                        chunk_items, chunk_err, _ = openrouter_suggest(
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

        material_name_universe = {m.name for m in list(getattr(bpy.data, "materials", []) or [])}
        with suspend_preview():
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
                        normalize_material_name_for_organizer(suggested_raw, mat=mat, trace=notes) if suggested_raw else ""
                    )
                    forced_tag = (getattr(self, "_forced_material_tag", "") or "").strip()
                    forced_ptrs = set(getattr(self, "_forced_material_ptrs", set()) or set())
                    if suggested_norm and forced_tag and mat is not None:
                        mat_ptr = mat.as_pointer()
                        if (not forced_ptrs) or (mat_ptr in forced_ptrs):
                            forced_name = force_material_name_tag(suggested_norm, forced_tag)
                            if forced_name != suggested_norm:
                                notes.append(f"Forced context tag: {forced_tag}")
                            suggested_norm = forced_name
                    require_tag = bool(getattr(self, "_require_material_tag", False))
                    if suggested_norm and require_tag and mat is not None:
                        parsed_with_context = parse_material_name(suggested_norm)
                        current_tag = (
                            str(parsed_with_context.get("scene_tag") or "").strip()
                            if isinstance(parsed_with_context, dict)
                            else ""
                        )
                        if not current_tag:
                            auto_tag = str(getattr(self, "_auto_material_tag_by_ptr", {}).get(mat.as_pointer(), "") or "")
                            if auto_tag:
                                auto_name = force_material_name_tag(suggested_norm, auto_tag)
                                if auto_name != suggested_norm:
                                    notes.append(f"Auto-added context tag: {auto_tag}")
                                suggested_norm = auto_name
                    if suggested_norm and parse_material_name(suggested_norm):
                        unique = bump_material_version_until_unique(material_name_universe, suggested_norm)
                        if unique != suggested_norm:
                            notes.append("Bumped version to avoid name collision")
                        material_name_universe.add(unique)
                        row.suggested_name = unique
                        row.status = material_status_from_trace(suggested_raw, row.suggested_name, notes)
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

        resolve_object_targets_for_state(
            scene,
            state,
            hints_by_item_id=by_id_hint,
            preserve_confirmed=False,
        )
        sync_planned_rows(scene, state)
        sync_row_selection(scene)
        self.report({"INFO"}, f"AI suggestions created: {len(state.items)} item(s)")
        return {"FINISHED"}


__all__ = ["LIME_TB_OT_ai_asset_suggest_names"]
