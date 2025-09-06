import bpy
from bpy.types import Panel

from ..core import validate_scene


CAT = "Lime Pipeline"


class LIME_PT_stage_setup(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Escenario"
    bl_idname = "LIME_PT_stage_setup"
    bl_order = 3

    @classmethod
    def poll(cls, ctx):
        return validate_scene.active_shot_context(ctx) is not None

    def draw(self, ctx):
        layout = self.layout
        layout.label(text="Crear elementos de escena")
        col = layout.column(align=True)
        col.operator("lime.add_camera_rig", text="Crear Cámara (Rig)", icon='OUTLINER_DATA_CAMERA')
        # Placeholders para futuras utilidades
        row = layout.row(align=True)
        row.enabled = False
        row.operator("wm.call_menu", text="Background para Cámara", icon='IMAGE_DATA')
        row = layout.row(align=True)
        row.enabled = False
        row.operator("wm.call_menu", text="Set básico", icon='MESH_GRID')
        row = layout.row(align=True)
        row.enabled = False
        row.operator("wm.call_menu", text="Luz Main", icon='LIGHT')
        row = layout.row(align=True)
        row.enabled = False
        row.operator("wm.call_menu", text="Luz Aux", icon='LIGHT')


__all__ = [
    "LIME_PT_stage_setup",
]


