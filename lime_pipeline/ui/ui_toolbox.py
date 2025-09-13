# lime_pipeline/ui/ui_toolbox.py
import bpy
from bpy.types import Panel, Operator

CAT = "Lime Toolbox"  # creates the new tab in the Sidebar


class LIME_TB_OT_placeholder(Operator):
    bl_idname = "lime.tb_placeholder"
    bl_label = "Do Nothing (WIP)"
    bl_description = "Placeholder button (no real logic yet)"

    def execute(self, ctx):
        self.report({'INFO'}, "Lime Toolbox: placeholder clicked")
        return {'FINISHED'}


class LIME_TB_PT_root(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Animation & Materials (preview)"
    bl_idname = "LIME_TB_PT_root"

    def draw(self, ctx):
        col = self.layout.column(align=True)
        col.operator("lime.tb_placeholder", text="Do Nothing (WIP)")


__all__ = ["LIME_TB_PT_root", "LIME_TB_OT_placeholder"]
