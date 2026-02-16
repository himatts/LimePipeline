"""UI panel for AI Textures Organizer."""

from __future__ import annotations

import bpy
from bpy.types import Panel, UIList


def _status_icon(status: str) -> str:
    value = (status or "").upper()
    if value == "READY":
        return "CHECKMARK"
    if value in {"AI_BLOCKED", "ERROR"}:
        return "ERROR"
    if value == "APPLIED":
        return "IMPORT"
    if value == "SKIPPED":
        return "X"
    if value == "REFINED":
        return "FILE_REFRESH"
    return "INFO"


class LIME_TB_UL_ai_texture_items(UIList):
    bl_idname = "LIME_TB_UL_ai_texture_items"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if not item:
            return
        row = layout.row(align=True)
        row.use_property_split = False
        row.use_property_decorate = False

        checkbox_col = row.column(align=True)
        checkbox_col.ui_units_x = 1.0
        checkbox_col.enabled = not bool(getattr(item, "read_only", False))
        checkbox_col.prop(item, "selected_for_apply", text="")

        name_col = row.column(align=True)
        name_col.ui_units_x = 7.5
        name_col.label(text=getattr(item, "image_name", "") or "<unnamed image>", icon="IMAGE_DATA")

        class_col = row.column(align=True)
        class_col.ui_units_x = 4.5
        class_col.label(text=(getattr(item, "classification", "") or "-").replace("_", " "))

        status_col = row.column(align=True)
        status_col.ui_units_x = 1.0
        status_col.label(text="", icon=_status_icon(getattr(item, "status", "")))

        final_col = row.column(align=True)
        final_col.ui_units_x = 9.0
        final_col.label(text=getattr(item, "final_filename", "") or "-")

        hint_col = row.column(align=True)
        hint_col.ui_units_x = 8.5
        hint_col.enabled = not bool(getattr(item, "read_only", False))
        hint_col.prop(item, "hint_text", text="")


class LIME_TB_PT_ai_textures_organizer(Panel):
    bl_label = "AI Textures Organizer"
    bl_idname = "LIME_TB_PT_ai_textures_organizer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lime Toolbox"
    bl_order = 176

    def draw(self, context):
        layout = self.layout
        state = getattr(getattr(context, "scene", None), "lime_ai_textures", None)
        if state is None:
            layout.label(text="AI texture state unavailable", icon="ERROR")
            return

        header = layout.box()
        header.label(text=f"Phase: {getattr(state, 'phase', 'IDLE').replace('_', ' ').title()}", icon="SEQUENCE")
        header.label(
            text=(
                f"Items: {getattr(state, 'total_count', 0)} | "
                f"Adoptable: {getattr(state, 'adoptable_count', 0)} | "
                f"Selected Ready: {getattr(state, 'selected_ready_count', 0)}"
            ),
            icon="INFO",
        )
        if bool(getattr(state, "is_busy", False)):
            header.label(text="Working...", icon="TIME")
        if bool(getattr(state, "ai_blocked", False)):
            alert = layout.box()
            alert.alert = True
            alert.label(text="AI is blocked for naming/refine/apply", icon="ERROR")
            if getattr(state, "last_error", ""):
                alert.label(text=str(state.last_error))
        elif getattr(state, "last_error", ""):
            warn = layout.box()
            warn.alert = True
            warn.label(text=str(state.last_error), icon="ERROR")


class LIME_TB_PT_ai_textures_analyze(Panel):
    bl_label = "Analyze"
    bl_idname = "LIME_TB_PT_ai_textures_analyze"
    bl_parent_id = "LIME_TB_PT_ai_textures_organizer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lime Toolbox"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        state = getattr(getattr(context, "scene", None), "lime_ai_textures", None)
        if state is None:
            layout.label(text="State unavailable", icon="ERROR")
            return

        col = layout.column(align=True)
        col.enabled = not bool(getattr(state, "is_busy", False))
        col.prop(state, "scan_scope", text="Scope")
        col.prop(state, "ai_include_preview", text="AI include preview (low-res)")
        col.operator("lime.texture_analyze", text="Analyze Textures", icon="FILE_REFRESH")


class LIME_TB_PT_ai_textures_review(Panel):
    bl_label = "Review & Hints"
    bl_idname = "LIME_TB_PT_ai_textures_review"
    bl_parent_id = "LIME_TB_PT_ai_textures_organizer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lime Toolbox"

    def draw(self, context):
        layout = self.layout
        state = getattr(getattr(context, "scene", None), "lime_ai_textures", None)
        if state is None:
            layout.label(text="State unavailable", icon="ERROR")
            return
        if not getattr(state, "items", None):
            layout.label(text="Run Analyze to populate texture items", icon="INFO")
            return

        row = layout.row(align=True)
        row.enabled = not bool(getattr(state, "is_busy", False)) and not bool(getattr(state, "ai_blocked", False))
        row.operator("lime.texture_refine", text="Refine Suggestions (AI)", icon="SETTINGS")

        layout.template_list(
            "LIME_TB_UL_ai_texture_items",
            "",
            state,
            "items",
            state,
            "active_index",
            rows=7,
        )

        if 0 <= int(getattr(state, "active_index", -1)) < len(state.items):
            item = state.items[state.active_index]
            box = layout.box()
            box.label(text=f"Status: {getattr(item, 'status', '')}", icon=_status_icon(getattr(item, "status", "")))
            box.label(text=f"Issue: {getattr(item, 'issue_summary', '') or '-'}")
            box.label(text=f"Map Type: {getattr(item, 'map_type', '') or 'Generic'}")
            box.label(text=f"Initial Suggestion: {getattr(item, 'initial_suggestion', '') or '-'}")
            box.label(text=f"Refined Suggestion: {getattr(item, 'refined_suggestion', '') or '-'}")
            box.label(text=f"Final Filename: {getattr(item, 'final_filename', '') or '-'}")
            box.label(text=f"Destination Preview: {getattr(item, 'dest_preview_path', '') or '-'}")
            if getattr(item, "last_error", ""):
                err_box = layout.box()
                err_box.alert = True
                err_box.label(text=str(item.last_error), icon="ERROR")


class LIME_TB_PT_ai_textures_apply(Panel):
    bl_label = "Apply"
    bl_idname = "LIME_TB_PT_ai_textures_apply"
    bl_parent_id = "LIME_TB_PT_ai_textures_organizer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lime Toolbox"

    def draw(self, context):
        layout = self.layout
        state = getattr(getattr(context, "scene", None), "lime_ai_textures", None)
        if state is None:
            layout.label(text="State unavailable", icon="ERROR")
            return

        layout.label(
            text=(
                f"Selected Ready: {getattr(state, 'selected_ready_count', 0)} | "
                f"Protected: {getattr(state, 'protected_count', 0)} | "
                f"Missing: {getattr(state, 'missing_count', 0)}"
            ),
            icon="INFO",
        )
        row = layout.row()
        row.scale_y = 1.2
        row.enabled = (
            not bool(getattr(state, "is_busy", False))
            and not bool(getattr(state, "ai_blocked", False))
            and int(getattr(state, "selected_ready_count", 0)) > 0
        )
        row.operator("lime.texture_apply", text="Apply Texture Plan", icon="CHECKMARK")


class LIME_TB_PT_ai_textures_maintenance(Panel):
    bl_label = "Maintenance"
    bl_idname = "LIME_TB_PT_ai_textures_maintenance"
    bl_parent_id = "LIME_TB_PT_ai_textures_organizer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lime Toolbox"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        state = getattr(getattr(context, "scene", None), "lime_ai_textures", None)
        if state is None:
            layout.label(text="State unavailable", icon="ERROR")
            return
        row = layout.row(align=True)
        row.enabled = not bool(getattr(state, "is_busy", False))
        row.operator("lime.texture_clear_session", text="Clear Session", icon="TRASH")
        row.operator("lime.texture_manifest_cleanup", text="Delete Manifests", icon="TRASH")

        report_box = layout.box()
        report_box.label(text="Latest Files", icon="TEXT")
        report_box.label(text=f"Analyze: {getattr(state, 'analysis_report_path', '') or '-'}")
        report_box.label(text=f"Refine: {getattr(state, 'refine_report_path', '') or '-'}")
        report_box.label(text=f"Apply: {getattr(state, 'apply_manifest_path', '') or '-'}")


__all__ = [
    "LIME_TB_UL_ai_texture_items",
    "LIME_TB_PT_ai_textures_organizer",
    "LIME_TB_PT_ai_textures_analyze",
    "LIME_TB_PT_ai_textures_review",
    "LIME_TB_PT_ai_textures_apply",
    "LIME_TB_PT_ai_textures_maintenance",
]

