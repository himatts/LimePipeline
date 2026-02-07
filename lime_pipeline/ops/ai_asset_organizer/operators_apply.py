"""Apply/scope operators for AI Asset Organizer."""

from __future__ import annotations

from typing import List

from bpy.props import EnumProperty
from bpy.types import Operator

from .planner import (
    apply_collection_reorganization,
    apply_preview_from_plan,
    build_unified_plan,
    update_preview_state,
)
from .runtime_api import refresh_preview, sync_planned_rows, sync_row_selection
from .target_resolver import resolve_object_targets_for_state


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

        plan = build_unified_plan(scene, state)
        apply_preview_from_plan(state, plan)
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
            created_collections, moved_objects, skipped_ambiguous, ambiguous_names = apply_collection_reorganization(
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
        update_preview_state(context, state)
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

        sync_row_selection(scene)
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

        resolve_object_targets_for_state(scene, state, preserve_confirmed=True)
        sync_planned_rows(scene, state)
        refresh_preview(scene)
        self.report(
            {"INFO"},
            f"Targets refreshed. Ambiguous: {getattr(state, 'planned_ambiguities_objects', 0)}",
        )
        return {"FINISHED"}


__all__ = [
    "LIME_TB_OT_ai_asset_apply_names",
    "LIME_TB_OT_ai_asset_scope_preset",
    "LIME_TB_OT_ai_asset_refresh_targets",
]
