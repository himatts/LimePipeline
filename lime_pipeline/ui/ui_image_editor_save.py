import bpy
from bpy.types import Panel


CAT = "Lime Pipeline"


class LIME_PT_image_save_as(Panel):
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Save As"
    bl_idname = "LIME_PT_image_save_as"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, ctx):
        # Show only when there is an image in the editor (e.g., Render Result)
        try:
            sp = ctx.space_data
            return getattr(sp, 'image', None) is not None
        except Exception:
            return False

    def draw(self, ctx):
        layout = self.layout
        col = layout.column(align=True)
        col.operator("lime.save_as_with_template", text="Render", icon='RENDER_RESULT').ptype = 'REND'
        col.operator("lime.save_as_with_template", text="Proposal View", icon='OUTLINER_DATA_CAMERA').ptype = 'PV'
        col.operator("lime.save_as_with_template", text="Storyboard", icon='GREASEPENCIL').ptype = 'SB'
        col.operator("lime.save_as_with_template", text="Temporal", icon='TIME').ptype = 'TMP'


__all__ = [
    "LIME_PT_image_save_as",
]


