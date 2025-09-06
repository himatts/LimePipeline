import bpy
from bpy.types import Panel

from ..core import validate_scene
from ..data.templates import C_UTILS_CAM


CAT = "Lime Pipeline"


class LIME_PT_proposal_view(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Proposal Views"
    bl_idname = "LIME_PT_proposal_view"
    bl_order = 2

    @classmethod
    def poll(cls, ctx):
        st = getattr(ctx.window_manager, "lime_pipeline", None)
        if st is None:
            return False
        if getattr(st, "project_type", None) != 'PV':
            return False
        if not bpy.data.is_saved:
            return False
        return True

    def draw(self, ctx):
        wm = ctx.window_manager
        st = wm.lime_pipeline
        layout = self.layout

        box = layout.box()
        box.label(text="Proposal View Tools")
        box.operator("lime.proposal_view_config", text="Proposal View Config", icon='SETTINGS')

        layout.separator()

        shot = validate_scene.active_shot_context(ctx)
        col = layout.column(align=True)
        if shot is None:
            col.enabled = False
            col.label(text="No SHOT active", icon='INFO')
        else:
            col.label(text="Capture Current Shot:")
            row = col.row(align=True)
            row.prop(st, "selected_camera", text="Camera")

            has_cam = False
            try:
                cam_coll = validate_scene.get_shot_child_by_basename(shot, C_UTILS_CAM)
                has_cam = bool(cam_coll and any(o.type == 'CAMERA' for o in cam_coll.objects))
            except Exception:
                has_cam = False

            row2 = col.row(align=True)
            row2.enabled = has_cam
            row2.operator("lime.take_pv_shot", text="Take PV Shot", icon='OUTLINER_DATA_CAMERA')
            if not has_cam:
                col.label(text="(No cameras in shot)", icon='ERROR')

        layout.separator()
        layout.operator("lime.take_all_pv_shots", text="Take All PV Shots", icon='RENDER_RESULT')


__all__ = [
    "LIME_PT_proposal_view",
]


