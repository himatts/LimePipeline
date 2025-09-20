import bpy
from bpy.types import Panel

from ..core import validate_scene


CAT = "Lime Pipeline"


class LIME_PT_stage_setup(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Stage"
    bl_options = {"DEFAULT_CLOSED"}
    bl_idname = "LIME_PT_stage_setup"
    bl_order = 5

    @classmethod
    def poll(cls, ctx):
        # Always visible; actions are disabled if there is no active SHOT
        return True

    def draw(self, ctx):
        layout = self.layout
        layout.label(text="Create scene elements")
        col = layout.column(align=True)
        col.enabled = validate_scene.active_shot_context(ctx) is not None
        col.operator("lime.import_layout", text="Import Layout", icon='APPEND_BLEND')
        # Utilities
        row = layout.row(align=True)
        row.enabled = False
        row.operator("wm.call_menu", text="Basic Set", icon='MESH_GRID')


__all__ = [
    "LIME_PT_stage_setup",
]

