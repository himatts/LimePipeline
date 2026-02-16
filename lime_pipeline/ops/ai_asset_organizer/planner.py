"""Planning helpers for AI Asset Organizer."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Tuple

import bpy
from bpy.types import Collection, Material, Object

from ...core.asset_naming import (
    bump_material_version_until_unique,
    ensure_unique_collection_name,
    ensure_unique_object_name,
    is_valid_collection_name,
    is_valid_object_name,
    normalize_collection_name,
    normalize_object_name,
)
from ...core.ai_asset_collection_paths import (
    build_missing_path_segments,
    normalize_collection_path_value,
    replace_path_prefix,
)
from ...core.ai_asset_material_rules import normalize_material_name_for_organizer as core_normalize_material_name_for_organizer
from ...core.material_naming import parse_name as parse_material_name
from ...props_ai_assets import LimeAIAssetItem
from .material_probe import material_shader_profile
from .scene_snapshot import build_scene_collection_snapshot, is_collection_read_only


_GENERIC_COLLECTION_RE = re.compile(r"^Collection(?:\.\d{3})?$")


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


def _is_object_read_only(obj: Object) -> bool:
    return bool(getattr(obj, "library", None) or getattr(obj, "override_library", None))


def _is_generic_collection_name(name: str) -> bool:
    return bool(_GENERIC_COLLECTION_RE.match((name or "").strip()))


def _is_generic_collection(coll: Optional[Collection], scene) -> bool:
    if coll is None:
        return True
    if coll == getattr(scene, "collection", None):
        return True
    return _is_generic_collection_name(getattr(coll, "name", "") or "")


def _material_shader_profile(mat: Optional[Material]) -> Dict[str, object]:
    return material_shader_profile(mat)


def build_rename_plan(state) -> Dict[str, object]:
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
            profile = _material_shader_profile(mat)
            source_name = str(getattr(mat, "name", "") or "")
            suggested = core_normalize_material_name_for_organizer(
                suggested_raw,
                profile=profile,
                source_name=source_name,
            )
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


def sync_planned_collection_rows(scene, state, snapshot: Optional[Dict[str, object]] = None) -> None:
    snapshot = snapshot or build_scene_collection_snapshot(scene)
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

    create_paths = build_missing_path_segments(object_target_paths, existing_paths)
    create_paths = [normalize_collection_path_value(path) for path in create_paths]
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


def build_collection_reorg_plan(scene, state, snapshot: Dict[str, object]) -> Dict[str, object]:
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

        path_to_collection = snapshot.get("path_to_collection", {}) if isinstance(snapshot, dict) else {}
        target_coll = path_to_collection.get(target_path) if isinstance(path_to_collection, dict) else None
        users_collection = list(getattr(obj, "users_collection", []) or [])
        source_other_editable = [
            c
            for c in users_collection
            if c is not None and c != target_coll and not is_collection_read_only(c)
        ]
        already_linked = bool(target_coll is not None and obj in list(getattr(target_coll, "objects", []) or []))

        if already_linked and not source_other_editable:
            continue

        move_ops.append({"row": row, "object": obj, "target_path": target_path})
        if target_coll is None:
            target_paths_to_create.append(target_path)

    create_paths = build_missing_path_segments(target_paths_to_create, existing_paths)
    return {"move_ops": move_ops, "create_paths": create_paths, "ambiguous_rows": ambiguous_rows}


def build_unified_plan(scene, state) -> Dict[str, object]:
    snapshot = build_scene_collection_snapshot(scene)
    rename_plan = build_rename_plan(state)
    reorg_plan = build_collection_reorg_plan(scene, state, snapshot)
    reorg_plan["collection_ops"] = list(rename_plan.get("collection_ops", []) or [])
    return {
        "snapshot": snapshot,
        "rename_plan": rename_plan,
        "reorg_plan": reorg_plan,
    }


def apply_preview_from_plan(state, plan: Dict[str, object]) -> None:
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


def update_preview_state(context, state) -> None:
    scene = getattr(context, "scene", None) if context else None
    if scene is None:
        return
    plan = build_unified_plan(scene, state)
    apply_preview_from_plan(state, plan)


def clear_preview_state(state) -> None:
    state.preview_summary = ""
    state.preview_dirty = False
    state.planned_renames_objects = 0
    state.planned_renames_materials = 0
    state.planned_renames_collections = 0
    state.planned_collections_created = 0
    state.planned_objects_moved = 0
    state.planned_ambiguities_objects = 0
    state.planned_objects_skipped_ambiguous = 0


def ensure_collection_path(
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
            if is_collection_read_only(coll):
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
            if is_collection_read_only(found):
                report({"WARNING"}, f"Cannot use read-only collection '{candidate_path}'")
                return None, created_count, candidate_path
            path_to_collection[candidate_path] = found
            parent = found
            current_parts.append(getattr(found, "name", segment) or segment)
            built_path = "/".join(current_parts)
            continue

        if is_collection_read_only(parent):
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


def apply_collection_reorganization(scene, reorg_plan: Dict[str, object], report, state=None) -> Tuple[int, int, int, List[str]]:
    created_count = 0
    moved_count = 0
    skipped_count = 0
    ambiguous_names: List[str] = []
    snapshot = build_scene_collection_snapshot(scene)
    path_to_collection = snapshot.get("path_to_collection", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(path_to_collection, dict):
        path_to_collection = {}
    collection_ptr_to_paths = snapshot.get("collection_ptr_to_paths", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(collection_ptr_to_paths, dict):
        collection_ptr_to_paths = {}

    # Add aliases for collections that will be renamed in the same Apply run.
    # This prevents creating duplicate collections when a target path points to
    # a name that already exists as a pending rename.
    collection_ops = list(reorg_plan.get("collection_ops", []) or [])
    if collection_ops:
        base_entries = list(path_to_collection.items())
        for op in collection_ops:
            if not isinstance(op, tuple) or len(op) != 2:
                continue
            coll, new_name = op
            if coll is None:
                continue
            desired_name = normalize_collection_name(str(new_name or ""))
            if not desired_name:
                continue
            old_paths = list(collection_ptr_to_paths.get(coll.as_pointer(), []) or [])
            for old_path in old_paths:
                if not old_path:
                    continue
                parent_path = old_path.rsplit("/", 1)[0] if "/" in old_path else ""
                new_prefix = f"{parent_path}/{desired_name}" if parent_path else desired_name
                if new_prefix not in path_to_collection:
                    path_to_collection[new_prefix] = coll
                old_prefix = f"{old_path}/"
                for existing_path, existing_coll in base_entries:
                    if not existing_path.startswith(old_prefix):
                        continue
                    suffix = existing_path[len(old_prefix):]
                    if not suffix:
                        continue
                    aliased_path = f"{new_prefix}/{suffix}"
                    if aliased_path not in path_to_collection:
                        path_to_collection[aliased_path] = existing_coll

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
            target, created, final_path = ensure_collection_path(scene, requested_path, path_to_collection, report)
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
            if is_collection_read_only(source):
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


__all__ = [
    "build_unified_plan",
    "apply_preview_from_plan",
    "build_rename_plan",
    "build_collection_reorg_plan",
    "apply_collection_reorganization",
    "sync_planned_collection_rows",
    "update_preview_state",
    "clear_preview_state",
    "ensure_collection_path",
    "normalize_collection_path_value",
    "replace_path_prefix",
]
