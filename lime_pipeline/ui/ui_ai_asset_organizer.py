"""UI panel for AI-assisted asset naming in Lime Toolbox."""

from __future__ import annotations

import re

import bpy
from bpy.types import Panel, UIList


_SHOT_ROOT_RE = re.compile(r"^SHOT \d{2,3}$")
_SHOT_CHILD_RE = re.compile(r"^SH\d{2,3}_")


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

        if item_type == "OBJECT":
            type_icon = "OBJECT_DATA"
        elif item_type == "COLLECTION":
            type_icon = "OUTLINER_COLLECTION"
        else:
            type_icon = "MATERIAL"
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
            proposal_col.label(text=getattr(item, "suggested_name", "") or "-")
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
        else:
            selected_objects = list(getattr(context, "selected_objects", None) or [])
            selected_mats = set()
            selected_cols = set()
            scene_root = getattr(scene, "collection", None)
            for obj in selected_objects:
                for slot in getattr(obj, "material_slots", []) or []:
                    mat = getattr(slot, "material", None)
                    if mat is not None:
                        selected_mats.add(mat)
                for coll in list(getattr(obj, "users_collection", []) or []):
                    if coll is None:
                        continue
                    if scene_root is not None and coll == scene_root:
                        continue
                    name = getattr(coll, "name", "") or ""
                    if _SHOT_ROOT_RE.match(name) or _SHOT_CHILD_RE.match(name):
                        continue
                    selected_cols.add(coll)

            summary = f"Selection: {len(selected_objects)} object(s), {len(selected_mats)} material(s)"
            if getattr(state, "include_collections", True):
                summary += f", {len(selected_cols)} collection(s)"
            layout.label(text=summary, icon="RESTRICT_SELECT_OFF")

            layout.prop(state, "context", text="Context")
            layout.prop(state, "use_image_context", text="Use Image Context")
            if getattr(state, "use_image_context", False):
                layout.prop(state, "image_path", text="Image")
            layout.prop(state, "include_collections", text="Include Collections")
            layout.prop(state, "organize_collections", text="Organize Collections on Apply")
            layout.label(text="Note: names and context are sent to OpenRouter.", icon="INFO")

            if getattr(state, "last_error", ""):
                box = layout.box()
                box.alert = True
                box.label(text=str(state.last_error), icon="ERROR")

            if getattr(state, "is_busy", False):
                layout.label(text="Working...", icon="TIME")

            row = layout.row(align=True)
            row.enabled = not getattr(state, "is_busy", False)
            row.operator("lime_tb.ai_asset_suggest_names", text="Suggest Names (AI)", icon="FILE_REFRESH")
            row.operator("lime_tb.ai_asset_clear", text="Clear", icon="TRASH")

            apply_row = layout.row()
            apply_row.enabled = bool(getattr(state, "items", None)) and not getattr(state, "is_busy", False)
            apply_row.operator("lime_tb.ai_asset_apply_names", text="Apply Selected", icon="CHECKMARK")

            if getattr(state, "items", None):
                preview_box = layout.box()
                preview_box.label(
                    text=(
                        f"Will rename {getattr(state, 'planned_renames_objects', 0)} objects, "
                        f"{getattr(state, 'planned_renames_materials', 0)} materials, "
                        f"{getattr(state, 'planned_renames_collections', 0)} collections"
                    ),
                    icon="INFO",
                )
                preview_box.label(
                    text=(
                        f"Will create {getattr(state, 'planned_collections_created', 0)} collections, "
                        f"move {getattr(state, 'planned_objects_moved', 0)} objects"
                    ),
                    icon="OUTLINER_COLLECTION",
                )
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

        layout.separator()
        box_textures = layout.box()
        box_textures.label(text="Textures")
        wm_state = getattr(getattr(context, "window_manager", None), "lime_pipeline", None)
        if wm_state is None:
            box_textures.label(text="Texture tools unavailable", icon="ERROR")
            return
        box_textures.prop(wm_state, "texture_adopt_use_ai", text="Use AI naming")
        row_ai = box_textures.row(align=True)
        row_ai.enabled = bool(getattr(wm_state, "texture_adopt_use_ai", False))
        row_ai.prop(wm_state, "texture_adopt_ai_include_preview", text="AI include preview (low-res)")
        row_tex = box_textures.row(align=True)
        if hasattr(bpy.types, "LIME_OT_texture_scan_report"):
            row_tex.operator("lime.texture_scan_report", text="Scan / Report", icon='IMAGE_DATA')
        else:
            row_tex.alert = True
            row_tex.label(text="Texture Scan operator not registered", icon='ERROR')
        row_fix = box_textures.row(align=True)
        if hasattr(bpy.types, "LIME_OT_texture_adopt"):
            op = row_fix.operator("lime.texture_adopt", text="Adopt / Fix", icon='IMPORT')
            try:
                op.use_ai = bool(getattr(wm_state, "texture_adopt_use_ai", False))
            except Exception:
                pass
            try:
                op.include_ai_preview = bool(getattr(wm_state, "texture_adopt_ai_include_preview", False))
            except Exception:
                pass
        else:
            row_fix.alert = True
            row_fix.label(text="Texture Adopt operator not registered", icon='ERROR')

        row_clean = box_textures.row(align=True)
        if hasattr(bpy.types, "LIME_OT_texture_manifest_cleanup"):
            row_clean.operator("lime.texture_manifest_cleanup", text="Delete Manifests", icon='TRASH')
        else:
            row_clean.alert = True
            row_clean.label(text="Manifest cleanup operator not registered", icon='ERROR')


__all__ = [
    "LIME_TB_PT_ai_asset_organizer",
    "LIME_TB_UL_ai_asset_items",
]
