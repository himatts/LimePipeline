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
from ..ops.ops_linked_collections import (
    get_localize_linked_summary,
    get_material_resync_summary,
)


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

        selection = list(ctx.selected_objects or [])
        offsets = objects_with_location_offset(ctx.scene, selection)
        status_box = layout.box()
        status_row = status_box.row()
        status_row.alignment = 'CENTER'
        status_row.alert = bool(selection) and bool(offsets)
        if not selection:
            status_row.label(text="Select objects to check offsets", icon='INFO')
        elif offsets:
            status_row.label(text=f"{len(offsets)} selected object(s) with offsets", icon='ERROR')
        else:
            status_row.label(text="Selected objects already zeroed", icon='CHECKMARK')
        apply_row = layout.row()
        apply_row.enabled = bool(selection) and bool(offsets)
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
        box_linked.label(text="Linked Data Localization")

        linked_summary = get_localize_linked_summary(ctx)
        scope = linked_summary.get("scope", "none")
        scope_label = "Selection" if scope == "selection" else "Active Collection" if scope == "active collection" else "None"
        total_targets = int(linked_summary.get("targets", 0))
        is_available = bool(linked_summary.get("available", False))

        status_row = box_linked.row()
        status_row.alert = not is_available
        if is_available:
            status_row.label(text=f"Ready: {total_targets} candidate(s) from {scope_label}", icon='CHECKMARK')
        else:
            status_row.label(text="Unavailable: no linked targets found", icon='ERROR')
            reason_row = box_linked.row()
            reason_row.label(text=str(linked_summary.get("unavailable_reason", "")), icon='INFO')

        counts_row = box_linked.row(align=True)
        counts_row.label(text=f"Selection: {linked_summary.get('selection_candidates', 0)}")
        counts_row.label(text=f"Active: {linked_summary.get('active_collection_candidates', 0)}")

        details_col = box_linked.column(align=True)
        details_col.label(
            text=(
                f"Targets: Mesh {linked_summary.get('mesh_targets', 0)}, "
                f"Empty {linked_summary.get('empty_targets', 0)}, "
                f"Instances {linked_summary.get('instance_targets', 0)}"
            ),
            icon='OUTLINER_COLLECTION',
        )
        details_col.label(
            text=(
                f"Objects: Linked {linked_summary.get('linked_object_targets', 0)}, "
                f"Overrides {linked_summary.get('override_object_targets', 0)}"
            ),
            icon='LIBRARY_DATA_OVERRIDE',
        )
        details_col.label(
            text=(
                f"Mesh data linked: {linked_summary.get('mesh_data_linked_targets', 0)} | "
                f"External mats: {linked_summary.get('estimated_external_materials', 0)}"
            ),
            icon='MATERIAL',
        )

        action_row = box_linked.row()
        action_row.enabled = is_available
        action_row.operator("lime.localize_linked_collection", text="Localize Linked Data", icon='LIBRARY_DATA_DIRECT')

        resync_summary = get_material_resync_summary(ctx)
        resync_row = box_linked.row()
        resync_available = bool(resync_summary.get("available", False))
        resync_selection = int(resync_summary.get("selection_count", 0))
        resync_eligible = int(resync_summary.get("eligible_count", 0))
        resync_row.alert = resync_selection > 0 and not resync_available
        if resync_selection == 0:
            resync_row.label(text="Resync: select objects to evaluate", icon='INFO')
        elif resync_available:
            resync_row.label(
                text=f"Resync eligible: {resync_eligible}/{resync_selection} selected",
                icon='CHECKMARK',
            )
        else:
            resync_row.label(text="Resync unavailable for current selection", icon='ERROR')

        resync_action_row = box_linked.row()
        resync_action_row.enabled = resync_available
        resync_action_row.operator(
            "lime.resync_object_materials_from_data",
            text="Resync Object Materials",
            icon='FILE_REFRESH',
        )


__all__ = [
    "LIME_PT_model_organizer",
]
