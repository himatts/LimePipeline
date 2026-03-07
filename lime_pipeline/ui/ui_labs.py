"""
UI panels for experimental or deprecated workflows kept out of the main pipeline.

Purpose: Host lower-priority tooling without cluttering production panels.
Key classes: LIME_TB_PT_labs, LIME_TB_PT_global_render_presets_lab.
Depends on: render preset operators and addon preferences.
Notes: UI-only; no heavy work in draw.
"""

import bpy
from bpy.types import Panel

from ..ops.ops_render_presets import PRESET_SLOT_COUNT


CAT = "Lime Toolbox"
ADDON_ID = __package__.split('.')[0]


def _addon_prefs(context):
    try:
        addon = context.preferences.addons.get(ADDON_ID)
    except Exception:
        addon = None
    return getattr(addon, "preferences", None) if addon else None


class LIME_TB_PT_labs(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Labs"
    bl_idname = "LIME_TB_PT_labs"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 90

    def draw(self, _ctx):
        layout = self.layout
        box = layout.box()
        box.alert = True
        box.label(text="Experimental and low-priority tools.", icon='EXPERIMENTAL')


class LIME_TB_PT_global_render_presets_lab(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Global Render Presets"
    bl_idname = "LIME_TB_PT_global_render_presets_lab"
    bl_parent_id = "LIME_TB_PT_labs"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 1

    def draw(self, ctx):
        layout = self.layout
        prefs = _addon_prefs(ctx)
        global_slots = getattr(prefs, 'global_render_presets', []) if prefs else []

        if prefs is None:
            layout.label(text="Addon preferences not available.", icon='ERROR')
            return

        intro = layout.box()
        intro.label(text="Deprecated from Render Configs.", icon='INFO')

        grid = layout.grid_flow(
            row_major=True,
            columns=PRESET_SLOT_COUNT,
            even_columns=True,
            align=True,
        )

        for idx in range(PRESET_SLOT_COUNT):
            slot = global_slots[idx] if idx < len(global_slots) else None
            has_data = bool(slot and not slot.is_empty and (slot.data_json or '').strip())

            cell = grid.column(align=True)
            cell.use_property_decorate = False

            apply_col = cell.column(align=True)
            apply_col.enabled = has_data
            apply_btn = apply_col.operator("lime.render_preset_apply", text=str(idx + 1), icon='PRESET')
            apply_btn.slot_index = idx

            actions = cell.split(factor=0.5, align=True)
            save_col = actions.column(align=True)
            save_btn = save_col.operator("lime.render_preset_save", text="", icon='FILE_TICK')
            save_btn.slot_index = idx

            delete_col = actions.column(align=True)
            delete_col.enabled = has_data
            delete_btn = delete_col.operator("lime.render_preset_clear", text="", icon='TRASH')
            delete_btn.slot_index = idx

        layout.separator()

        maintenance = layout.column(align=True)
        maintenance.operator("lime.render_preset_reset_all", text="Reset Presets", icon='TRASH')
        maintenance.operator("lime.render_preset_restore_defaults", text="Restore Defaults", icon='LOOP_BACK')
        maintenance.operator("lime.render_preset_update_defaults", text="Update Defaults", icon='FILE_REFRESH')


__all__ = [
    "LIME_TB_PT_labs",
    "LIME_TB_PT_global_render_presets_lab",
]
