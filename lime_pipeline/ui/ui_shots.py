import bpy
from bpy.types import Panel

from ..core import validate_scene


CAT = "Lime Pipeline"


class LIME_PT_shots(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Shots"
    bl_idname = "LIME_PT_shots"
    bl_order = 1

    def draw(self, ctx):
        layout = self.layout

        # Status block
        box = layout.box()
        box.label(text="Shot Tools")
        active = validate_scene.active_shot_context(ctx)
        if active is not None:
            box.label(text=f"Active SHOT: {active.name}", icon='CHECKMARK')
        else:
            box.label(text="No SHOT context", icon='INFO')

        # Actions
        col = layout.column(align=True)
        col.operator("lime.new_shot", text="New Shot", icon='ADD')

        row = layout.row(align=True)
        can_instance, msg_i = validate_scene.can_instance_shot(ctx)
        row.enabled = can_instance
        row.operator("lime.shot_instance", text="Shot Instance", icon='OUTLINER_COLLECTION')
        if not can_instance and msg_i:
            hint = layout.row(align=True)
            hint.label(text=msg_i, icon='INFO')

        row = layout.row(align=True)
        can_dup, msg_d = validate_scene.can_duplicate_shot(ctx)
        row.enabled = can_dup
        row.operator("lime.duplicate_shot", text="Duplicate Shot", icon='DUPLICATE')
        if not can_dup and msg_d:
            hint = layout.row(align=True)
            hint.label(text=msg_d, icon='INFO')

        # Add Missing Collections
        row = layout.row(align=True)
        row.enabled = validate_scene.active_shot_context(ctx) is not None
        row.operator("lime.add_missing_collections", text="Add Missing Collections", icon='FILE_REFRESH')


