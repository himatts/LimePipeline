import bpy
from bpy.types import Panel

from ..core.naming import detect_ptype_from_filename, hydrate_state_from_filepath, parse_blend_details
from ..core.paths import paths_for_type
from ..core import validate_scene
from ..data.templates import C_UTILS_CAM


CAT = "Lime Pipeline"


class LIME_PT_renders(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Renders"
    bl_idname = "LIME_PT_renders"
    bl_order = 2

    @classmethod
    def poll(cls, ctx):
        # Only visible for saved files of type REND
        try:
            is_saved = bool(bpy.data.filepath)
        except Exception:
            is_saved = False
        if not is_saved:
            return False
        return detect_ptype_from_filename(bpy.data.filepath) == 'REND'

    def draw(self, ctx):
        wm = ctx.window_manager
        st = wm.lime_pipeline
        layout = self.layout

        box = layout.box()
        box.label(text="Render Tools")
        box.operator("lime.render_config", text="Render Config", icon='SETTINGS')

        layout.separator()

        shot = validate_scene.active_shot_context(ctx)
        col = layout.column(align=True)
        if shot is None:
            col.enabled = False
            col.label(text="No SHOT active", icon='INFO')
        else:
            col.label(text="Render Current Shot:")
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
            row2.operator("lime.render_shot", text="Render", icon='RENDER_STILL')
            if not has_cam:
                col.label(text="(No cameras in shot)", icon='ERROR')

            # Open output folder (editables)
            try:
                from pathlib import Path
                blend_path = Path(bpy.data.filepath or "")
                root = None
                for parent in blend_path.parents:
                    if parent.name == '2. Graphic & Media':
                        root = parent.parent
                        break
                info = parse_blend_details(blend_path.name) if blend_path else None
                rev = (info.get('rev') if info else None) or (getattr(st, 'rev_letter', '') or '').upper()
                sc = (info.get('sc') if info else None)
                if root is None:
                    hydrate_state_from_filepath(st)
                    root = Path(getattr(st, 'project_root', '') or '')
                _ramv, folder_type, _scenes, _target, _backups = paths_for_type(Path(root), 'REND', rev, sc)
                out_dir = folder_type / 'editables'
                row3 = col.row(align=True)
                row3.enabled = out_dir.exists()
                op = row3.operator("lime.open_output_folder", text="Open Output Folder", icon='FILE_FOLDER')
                op.ptype = 'REND'
            except Exception:
                pass

        layout.separator()
        layout.operator("lime.render_all", text="Render All", icon='RENDER_RESULT')


__all__ = [
    "LIME_PT_renders",
]
