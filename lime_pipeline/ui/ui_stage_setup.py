"""
UI to set up stage elements for an active SHOT and auto camera backgrounds.

Purpose: Provide scene duplication for SHOTs, import layout helpers, and controls to
initialize, refresh and toggle live auto camera background planes.
Key classes: LIME_PT_stage_setup.
Depends on: lime_pipeline.core.validate_scene and ops for stage/background automation.
Notes: UI-only; disables actions when there is no active SHOT.
"""

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
        layout.operator("lime.duplicate_scene_sequential", text="Duplicate Shot Scene", icon='SCENE_DATA')
        layout.separator()
        layout.label(text="Create scene elements")
        col = layout.column(align=True)
        col.enabled = validate_scene.active_shot_context(ctx) is not None
        col.operator("lime.import_layout", text="Import Layout", icon='APPEND_BLEND')
        # Auto Camera Background
        layout.separator()
        shot_active = validate_scene.active_shot_context(ctx)
        has_bg_plane = bool(getattr(ctx, 'object', None) and getattr(ctx.object, 'get', lambda *_: None)("LP_AUTO_BG"))
        allow_bg_ops = bool(shot_active) or has_bg_plane

        row = layout.row(align=True)
        row.enabled = allow_bg_ops
        row.operator("lime.auto_camera_background", icon='IMAGE_BACKGROUND', text="Auto Camera Background")
        row.operator("lime.auto_camera_background_refresh", icon='FILE_REFRESH', text="")

        row2 = layout.row(align=True)
        row2.enabled = allow_bg_ops
        row2.operator("lime.auto_camera_background_toggle_live", icon='CHECKBOX_HLT', text="Live ON").enable = True
        row2.operator("lime.auto_camera_background_toggle_live", icon='CHECKBOX_DEHLT', text="Live OFF").enable = False

        plane = getattr(ctx, "object", None)
        if plane and plane.get("LP_AUTO_BG"):
            layout.separator()
            box = layout.box()
            box.label(text="Auto BG Settings")
            if "lpbg_distance" in plane.keys():
                box.prop(plane, '["lpbg_distance"]', text="Plane Distance")
            if "lpbg_padding" in plane.keys():
                box.prop(plane, '["lpbg_padding"]', text="Padding")
            if "lpbg_manual_scale" in plane.keys():
                box.prop(plane, '["lpbg_manual_scale"]', text="Manual Scale", toggle=True)
                if plane.get("lpbg_manual_scale"):
                    box.label(text="Adjust the object scale to control size", icon='INFO')
            if not {"lpbg_distance", "lpbg_padding", "lpbg_manual_scale"}.issubset(set(plane.keys())):
                box.label(text="Run Auto Camera Background to initialize settings", icon='INFO')

        # Utilities
        layout.separator()
        row = layout.row(align=True)
        row.enabled = False
        row.operator("wm.call_menu", text="Basic Set", icon='MESH_GRID')


__all__ = [
    "LIME_PT_stage_setup",
]

