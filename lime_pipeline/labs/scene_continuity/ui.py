"""UI for the Scene Continuity lab feature."""

from bpy.types import Panel

from ...core import validate_scene


CAT = "Lime Toolbox"


class LIME_TB_PT_scene_continuity_lab(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Scene Continuity"
    bl_idname = "LIME_TB_PT_scene_continuity_lab"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, _ctx):
        return True

    def draw(self, ctx):
        layout = self.layout
        st = getattr(ctx.window_manager, "lime_scene_continuity", None)

        header = layout.box()
        header.alert = True
        header.label(text="Lab feature. Not registered by default.", icon='EXPERIMENTAL')

        box = layout.box()
        box.label(text="Scene Continuity", icon='OUTLINER_COLLECTION')
        if st is None:
            box.label(text="Scene Continuity lab state not available.", icon='INFO')
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
    "LIME_TB_PT_scene_continuity_lab",
]
