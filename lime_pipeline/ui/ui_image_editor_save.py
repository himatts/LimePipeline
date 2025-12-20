"""
Image Editor panel to save outputs with normalized names and RAW variants.

Purpose: Provide quick buttons to save Render Result and images using project templates,
including RAW variants intended for post-production workflows.
Key classes: LIME_PT_image_save_as.
Depends on: operators lime.save_as_with_template and lime.save_as_with_template_raw.
Notes: UI-only; operators handle naming and path logic.
"""

import bpy
from bpy.types import Panel


CAT = "Lime Pipeline"


class LIME_PT_image_save_as(Panel):
    """Panel with save shortcuts for normalized outputs and RAW variants."""
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Save As"
    bl_idname = "LIME_PT_image_save_as"

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
        st = ctx.window_manager.lime_pipeline
        box = layout.box()
        box.prop(st, "render_version")
        box.prop(st, "render_descriptor", text="Descriptor")
        col = layout.column(align=True)
        col.operator("lime.save_as_with_template", text="Render", icon='RENDER_RESULT').ptype = 'REND'
        col.operator("lime.save_as_with_template", text="Proposal View", icon='OUTLINER_DATA_CAMERA').ptype = 'PV'
        col.operator("lime.save_as_with_template", text="Storyboard", icon='GREASEPENCIL').ptype = 'SB'
        col.operator("lime.save_as_with_template", text="Temporal", icon='TIME').ptype = 'TMP'
        
        # RAW variants (unchecked renders before post-production)
        layout.separator()
        col_raw = layout.column(align=True)
        col_raw.operator("lime.save_as_with_template_raw", text="RAW Render", icon='RENDER_RESULT').ptype = 'REND'
        col_raw.operator("lime.save_as_with_template_raw", text="RAW Proposal View", icon='OUTLINER_DATA_CAMERA').ptype = 'PV'
        col_raw.operator("lime.save_as_with_template_raw", text="RAW Storyboard", icon='GREASEPENCIL').ptype = 'SB'
        col_raw.operator("lime.save_as_with_template_raw", text="RAW Temporal", icon='TIME').ptype = 'TMP'


__all__ = [
    "LIME_PT_image_save_as",
]


