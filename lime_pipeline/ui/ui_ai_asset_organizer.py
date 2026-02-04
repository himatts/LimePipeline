"""UI panel for AI-assisted object/material naming in Lime Toolbox.

This panel is lightweight; network calls and rename logic live in operators.
"""

from __future__ import annotations

import bpy
from bpy.types import Panel, UIList


class LIME_TB_UL_ai_asset_items(UIList):
    bl_idname = "LIME_TB_UL_ai_asset_items"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if not item:
            return

        row_layout = layout.row(align=True)
        row_layout.use_property_split = False
        row_layout.use_property_decorate = False

        read_only = bool(getattr(item, "read_only", False))
        item_type = (getattr(item, "item_type", "OBJECT") or "OBJECT").upper()
        status = (getattr(item, "status", "") or "").upper()

        type_icon = "OBJECT_DATA" if item_type == "OBJECT" else "MATERIAL"
        if read_only:
            type_icon = "LIBRARY_DATA_DIRECT"

        status_icon = "BLANK1"
        if status == "INVALID":
            status_icon = "ERROR"
        elif status == "NORMALIZED":
            status_icon = "FILE_REFRESH"

        checkbox_col = row_layout.column(align=True)
        checkbox_col.ui_units_x = 1.0
        checkbox_col.enabled = not read_only
        checkbox_col.prop(item, "selected_for_apply", text="")

        name_col = row_layout.column(align=True)
        name_col.ui_units_x = 6.0
        name_col.label(text=getattr(item, "original_name", "") or "<no name>", icon=type_icon)

        status_col = row_layout.column(align=True)
        status_col.ui_units_x = 1.0
        status_col.label(text="", icon=status_icon)

        proposal_col = row_layout.column(align=True)
        proposal_col.ui_units_x = 10.0
        if read_only:
            proposal_col.label(text=getattr(item, "suggested_name", "") or "—")
        else:
            proposal_col.prop(item, "suggested_name", text="")


class LIME_TB_PT_ai_asset_organizer(Panel):
    bl_label = "AI Asset Organizer"
    bl_idname = "LIME_TB_PT_ai_asset_organizer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lime Toolbox"
    bl_order = 175

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)

        if state is None:
            layout.label(text="AI state unavailable", icon="ERROR")
            return

        selected_objects = list(getattr(context, "selected_objects", None) or [])
        selected_mats = set()
        for obj in selected_objects:
            for slot in getattr(obj, "material_slots", []) or []:
                mat = getattr(slot, "material", None)
                if mat is not None:
                    selected_mats.add(mat)

        summary = f"Selection: {len(selected_objects)} object(s), {len(selected_mats)} material(s)"
        layout.label(text=summary, icon="RESTRICT_SELECT_OFF")

        layout.prop(state, "context", text="Context")
        layout.prop(state, "use_image_context", text="Use Image Context")
        if getattr(state, "use_image_context", False):
            layout.prop(state, "image_path", text="Image")
        layout.label(text="Note: names and context are sent to OpenRouter.", icon="INFO")

        if getattr(state, "last_error", ""):
            box = layout.box()
            box.alert = True
            box.label(text=str(state.last_error), icon="ERROR")

        if getattr(state, "is_busy", False):
            layout.label(text="Working…", icon="TIME")

        row = layout.row(align=True)
        row.enabled = not getattr(state, "is_busy", False)
        row.operator("lime_tb.ai_asset_suggest_names", text="Suggest Names (AI)", icon="FILE_REFRESH")
        row.operator("lime_tb.ai_asset_clear", text="Clear", icon="TRASH")

        apply_row = layout.row()
        apply_row.enabled = bool(getattr(state, "items", None)) and not getattr(state, "is_busy", False)
        apply_row.operator("lime_tb.ai_asset_apply_names", text="Apply Selected", icon="CHECKMARK")

        if getattr(state, "items", None):
            layout.separator()
            layout.template_list(
                "LIME_TB_UL_ai_asset_items",
                "",
                state,
                "items",
                state,
                "active_index",
                rows=6,
            )


__all__ = [
    "LIME_TB_PT_ai_asset_organizer",
    "LIME_TB_UL_ai_asset_items",
]
