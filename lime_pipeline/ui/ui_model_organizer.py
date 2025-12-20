"""
UI panel to organize imported 3D models and scene controllers.

Purpose: Provide actions to import STEP, clean geometry, create controller empties,
apply deltas, colorize parent groups, and manage library linking/override/relocate.
Key classes: LIME_PT_model_organizer.
Depends on: ops.ops_model_organizer and related operators.
Notes: UI-only; shows status for location offsets and actions availability.
"""

import bpy
from bpy.types import Panel

from ..ops.ops_model_organizer import objects_with_location_offset


CAT = "Lime Toolbox"


class LIME_PT_model_organizer(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "3D Model Organizer"
    bl_idname = "LIME_PT_model_organizer"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 0

    def draw(self, ctx):
        layout = self.layout

        layout.operator("import_scene.occ_import_step", text="Import STEP (.step)", icon='IMPORT')
        layout.operator("lime.clean_step", text="Clean .STEP", icon='FILE_REFRESH')

        offsets = objects_with_location_offset(ctx.scene)
        status_box = layout.box()
        status_row = status_box.row()
        status_row.alignment = 'CENTER'
        status_row.alert = bool(offsets)
        if offsets:
            status_row.label(text=f"{len(offsets)} object(s) with offsets", icon='ERROR')
        else:
            status_row.label(text="All object locations zeroed", icon='CHECKMARK')
        apply_row = layout.row()
        apply_row.enabled = bool(offsets)
        apply_row.operator("lime.apply_scene_deltas", text="Apply Deltas", icon='DRIVER_DISTANCE')

        state = getattr(ctx.window_manager, "lime_pipeline", None)
        if state is not None:
            toggle_row = layout.row(align=True)
            toggle_row.prop(state, "auto_select_hierarchy", text="Auto Select Children", toggle=True, icon='SELECT_SET')

        layout.separator()
        layout.operator("lime.group_selection_empty", text="Create Controller", icon='OUTLINER_OB_EMPTY')
        layout.operator("lime.move_controller", text="Move Controller", icon='EMPTY_ARROWS')
        layout.separator()
        layout.operator("lime.colorize_parent_groups", text="Color Parent Groups", icon='COLOR')
        layout.operator("lime.apply_object_alpha_mix", text="Alpha Material Config", icon='SHADING_RENDERED')
        layout.separator()

        box_linked = layout.box()
        box_linked.label(text="Linked Collections")
        box_linked.operator("lime.localize_linked_collection", icon='LIBRARY_DATA_DIRECT')


__all__ = [
    "LIME_PT_model_organizer",
]
