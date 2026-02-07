"""Target-routing operators for AI Asset Organizer."""

from __future__ import annotations

from bpy.props import EnumProperty, StringProperty
from bpy.types import Operator

from ...core.ai_asset_collection_paths import normalize_collection_path_value
from .runtime_api import refresh_preview, sync_planned_rows
from .target_resolver import (
    find_row_by_item_id,
    parse_row_target_candidates,
    selected_object_rows,
    target_option_items_for_rows,
)


def _resolve_target_candidate_items(self, context):
    scene = getattr(context, "scene", None) if context else None
    state = getattr(scene, "lime_ai_assets", None) if scene is not None else None
    if state is None:
        return []
    row = find_row_by_item_id(state, getattr(self, "item_id", ""))
    if row is None:
        return []

    items = []
    for idx, cand in enumerate(parse_row_target_candidates(row)):
        path = str(cand.get("path") or "").strip()
        if not path:
            continue
        score = float(cand.get("score") or 0.0)
        exists = bool(cand.get("exists", True))
        suffix = "existing" if exists else "will create"
        items.append((path, path, f"Score {score:.2f} ({suffix})", idx))
    if not items:
        candidates = target_option_items_for_rows(scene, state, [row])
        for idx, cand in enumerate(candidates):
            path = str(cand[0] or "").strip()
            if not path:
                continue
            desc = str(cand[2] or "") if len(cand) >= 3 else "Candidate"
            items.append((path, path, desc, idx))
    return items


def _bulk_target_candidate_items(self, context):
    scene = getattr(context, "scene", None) if context else None
    state = getattr(scene, "lime_ai_assets", None) if scene is not None else None
    if state is None:
        return []

    selected_rows = selected_object_rows(state)
    if not selected_rows:
        return []

    return target_option_items_for_rows(scene, state, selected_rows)


def _single_target_candidate_items(self, context):
    scene = getattr(context, "scene", None) if context else None
    state = getattr(scene, "lime_ai_assets", None) if scene is not None else None
    if state is None:
        return []
    row = find_row_by_item_id(state, getattr(self, "item_id", ""))
    if row is None or getattr(row, "item_type", "") != "OBJECT":
        return []
    return target_option_items_for_rows(scene, state, [row])


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
        row = find_row_by_item_id(state, self.item_id)
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
        row = find_row_by_item_id(state, self.item_id) if state is not None else None
        if row is not None:
            layout.label(text=f"Object: {getattr(row, 'original_name', '') or '<unnamed>'}", icon="OBJECT_DATA")
        layout.prop(self, "candidate_path", text="Collection Path")

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}
        row = find_row_by_item_id(state, self.item_id)
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
        sync_planned_rows(scene, state)
        refresh_preview(scene)
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
        row = find_row_by_item_id(state, self.item_id)
        if row is None or getattr(row, "item_type", "") != "OBJECT":
            self.report({"ERROR"}, "Target object row not found")
            return {"CANCELLED"}

        options = _single_target_candidate_items(self, context)
        if not options:
            self.report({"WARNING"}, "No destination options available")
            return {"CANCELLED"}

        current = normalize_collection_path_value(getattr(row, "target_collection_path", "") or "")
        valid_ids = {item[0] for item in options}
        self.destination_path = current if current in valid_ids else options[0][0]
        return context.window_manager.invoke_props_dialog(self, width=620)

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        row = find_row_by_item_id(state, self.item_id) if state is not None else None
        if row is not None:
            layout.label(text=f"Object: {getattr(row, 'original_name', '') or '<unnamed>'}", icon="OBJECT_DATA")
        layout.prop(self, "destination_path", text="Collection Path")

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}
        row = find_row_by_item_id(state, self.item_id)
        if row is None or getattr(row, "item_type", "") != "OBJECT":
            self.report({"ERROR"}, "Target object row not found")
            return {"CANCELLED"}

        target_path = normalize_collection_path_value(self.destination_path or "")
        if not target_path:
            self.report({"WARNING"}, "Destination path is not valid")
            return {"CANCELLED"}

        row.target_collection_path = target_path
        row.target_status = "CONFIRMED"
        row.target_confidence = 1.0
        state.last_used_collection_path = target_path
        sync_planned_rows(scene, state)
        refresh_preview(scene)
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
        rows = selected_object_rows(state)
        if not rows:
            self.report({"WARNING"}, "Select at least one object row first")
            return {"CANCELLED"}

        options = _bulk_target_candidate_items(self, context)
        if not options:
            self.report({"WARNING"}, "No destination options available")
            return {"CANCELLED"}

        current_targets = {
            normalize_collection_path_value(getattr(row, "target_collection_path", "") or "")
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
        selected_count = len(selected_object_rows(state)) if state is not None else 0
        layout.label(text=f"Selected object rows: {selected_count}", icon="OBJECT_DATA")
        layout.prop(self, "destination_path", text="Collection Path")

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}
        rows = selected_object_rows(state)
        if not rows:
            self.report({"WARNING"}, "Select at least one object row first")
            return {"CANCELLED"}

        target_path = normalize_collection_path_value(self.destination_path or "")
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
        sync_planned_rows(scene, state)
        refresh_preview(scene)
        self.report({"INFO"}, f"Re-routed {updated} object(s) to {target_path}")
        return {"FINISHED"}


__all__ = [
    "LIME_TB_OT_ai_asset_resolve_target",
    "LIME_TB_OT_ai_asset_set_target_for_item",
    "LIME_TB_OT_ai_asset_set_target_for_selected",
]
