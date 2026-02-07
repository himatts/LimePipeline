"""Runtime API for AI Asset Organizer state callbacks.

This module is the public bridge used by props callbacks.
"""

from __future__ import annotations

from contextlib import contextmanager

import bpy

from ...core.ai_asset_collection_paths import normalize_collection_path_value, replace_path_prefix
from .planner import (
    apply_preview_from_plan,
    build_unified_plan,
    sync_planned_collection_rows,
)
from .scene_snapshot import build_scene_collection_snapshot
from .target_resolver import find_row_by_item_id


_PREVIEW_SUSPENDED = False
_NAME_EDIT_GUARD = 0


def _status_invalid(status: str) -> bool:
    return (status or "").strip().upper().startswith("INVALID")


def _scope_allows_row(state, row) -> bool:
    item_type = (getattr(row, "item_type", "") or "").upper()
    if item_type == "OBJECT":
        return bool(getattr(state, "apply_scope_objects", True))
    if item_type == "MATERIAL":
        return bool(getattr(state, "apply_scope_materials", True))
    if item_type == "COLLECTION":
        return bool(getattr(state, "apply_scope_collections", True))
    return False


def _row_default_selected_for_apply(row) -> bool:
    if getattr(row, "read_only", False):
        return False
    suggested = (getattr(row, "suggested_name", "") or "").strip()
    if not suggested:
        return False
    if _status_invalid(getattr(row, "status", "")):
        return False
    return True


@contextmanager
def suspend_preview():
    global _PREVIEW_SUSPENDED
    previous = _PREVIEW_SUSPENDED
    _PREVIEW_SUSPENDED = True
    try:
        yield
    finally:
        _PREVIEW_SUSPENDED = previous


def is_preview_suspended() -> bool:
    return bool(_PREVIEW_SUSPENDED)


def refresh_preview(scene=None) -> None:
    scene = scene or getattr(bpy.context, "scene", None)
    if scene is None:
        return
    state = getattr(scene, "lime_ai_assets", None)
    if state is None:
        return
    plan = build_unified_plan(scene, state)
    apply_preview_from_plan(state, plan)


def refresh_ai_asset_preview(scene=None) -> None:
    refresh_preview(scene)


def sync_planned_rows(scene, state, snapshot=None) -> None:
    with suspend_preview():
        sync_planned_collection_rows(scene, state, snapshot=snapshot)


def sync_row_selection(scene=None) -> None:
    scene = scene or getattr(bpy.context, "scene", None)
    if scene is None:
        return
    state = getattr(scene, "lime_ai_assets", None)
    if state is None:
        return

    with suspend_preview():
        for row in list(getattr(state, "items", []) or []):
            if not _scope_allows_row(state, row):
                row.selected_for_apply = False
                continue
            row.selected_for_apply = _row_default_selected_for_apply(row)

    refresh_preview(scene)


def on_name_changed(scene, item_id: str) -> None:
    global _NAME_EDIT_GUARD
    if _NAME_EDIT_GUARD > 0:
        return
    state = getattr(scene, "lime_ai_assets", None) if scene is not None else None
    if state is None:
        return
    row = find_row_by_item_id(state, item_id)
    if row is None:
        refresh_preview(scene)
        return

    if getattr(row, "item_type", "") != "PLANNED_COLLECTION":
        refresh_preview(scene)
        return

    old_path = (getattr(row, "original_name", "") or "").strip()
    new_path = normalize_collection_path_value(getattr(row, "suggested_name", "") or "")
    if not new_path:
        new_path = old_path

    _NAME_EDIT_GUARD += 1
    try:
        with suspend_preview():
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
                replaced = replace_path_prefix(target, old_path, new_path)
                if replaced != target:
                    obj_row.target_collection_path = replaced
                    if (getattr(obj_row, "target_status", "") or "").upper() == "NONE":
                        obj_row.target_status = "AUTO"

        snapshot = build_scene_collection_snapshot(scene)
        sync_planned_rows(scene, state, snapshot=snapshot)
        refresh_preview(scene)
    finally:
        _NAME_EDIT_GUARD -= 1


__all__ = [
    "is_preview_suspended",
    "suspend_preview",
    "refresh_preview",
    "refresh_ai_asset_preview",
    "sync_planned_rows",
    "sync_row_selection",
    "on_name_changed",
]
