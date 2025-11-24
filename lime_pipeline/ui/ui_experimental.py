"""
UI for experimental Lime Toolbox features.

Currently: exposes the Scene Continuity handoff operator in an isolated panel so it
can be used without cluttering stable tools. Marked experimental because the freeze
logic is still evolving.
"""

import bpy
from bpy.types import Panel

from ..core import validate_scene


CAT = "Lime Toolbox"


class LIME_TB_PT_experimental(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Experimental"
    bl_idname = "LIME_TB_PT_experimental"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, _ctx):
        return True

    def draw(self, ctx):
        layout = self.layout
        st = getattr(ctx.window_manager, "lime_pipeline", None)

        header = layout.box()
        header.alert = True
        header.label(text="Experimental features. Use with caution.", icon='EXPERIMENTAL')

        box = layout.box()
        box.label(text="Scene Continuity", icon='OUTLINER_COLLECTION')
        if st is None:
            box.label(text="Open Project Organization first.", icon='INFO')
            return

        box.prop(st, "scene_continuity_frame_mode", text="Handoff")
        box.prop(st, "scene_continuity_shot_name", text="Shot")
        row = box.row()
        valid_shot = getattr(st, "scene_continuity_shot_name", "NONE") != "NONE"
        # Also allow contextual detection of active SHOT to avoid hard disable
        if not valid_shot:
            valid_shot = validate_scene.active_shot_context(ctx) is not None
        row.enabled = valid_shot
        row.operator("lime.stage_create_next_scene_file", icon='FILE_NEW')


__all__ = [
    "LIME_TB_PT_experimental",
]
