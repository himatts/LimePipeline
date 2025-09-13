import bpy
from bpy.types import Panel
from pathlib import Path

from ..core.paths import paths_for_type
from ..core.naming import hydrate_state_from_filepath
from ..core import validate_scene


CAT = "Lime Pipeline"


class LIME_PT_render_configs(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Render Configs"
    bl_idname = "LIME_PT_render_configs"
    bl_order = 2

    def draw(self, ctx):
        layout = self.layout
        # Presets row (placeholders 1–5)
        row = layout.row(align=True)
        for i in range(1, 6):
            op = row.operator("lime.apply_preset_placeholder", text=str(i), icon='PRESET')
            op.preset_index = i
            op.tooltip = f"Preset {i}"


class LIME_PT_render_settings(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Settings"
    bl_parent_id = "LIME_PT_render_configs"

    def draw(self, ctx):
        layout = self.layout
        scene = ctx.scene

        # Resolution
        box = layout.box()
        box.label(text="Resolution")
        row = box.row(align=True)
        row.prop(scene.render, "resolution_x", text="X")
        row.prop(scene.render, "resolution_y", text="Y")

        # Cycles
        box = layout.box()
        box.label(text="Cycles")
        cy = getattr(scene, 'cycles', None)
        if cy is None:
            col = box.column()
            col.enabled = False
            col.label(text="Cycles not available", icon='INFO')
        else:
            col = box.column(align=True)
            col.label(text="Viewport")
            try:
                col.prop(cy, "preview_adaptive_threshold", text="Noise Threshold")
            except Exception:
                pass
            try:
                col.prop(cy, "preview_samples", text="Samples")
            except Exception:
                pass
            try:
                col.prop(cy, "use_preview_denoising", text="Denoise")
            except Exception:
                try:
                    col.prop(ctx.view_layer.cycles, "use_denoising", text="Prev Denoise")
                except Exception:
                    pass
            col.separator()
            col.label(text="Render")
            try:
                col.prop(cy, "adaptive_threshold", text="Noise Threshold")
            except Exception:
                pass
            try:
                col.prop(cy, "samples", text="Samples")
            except Exception:
                pass
            done = False
            try:
                col.prop(ctx.view_layer.cycles, "use_denoising", text="Denoise")
                done = True
            except Exception:
                pass
            if not done:
                try:
                    col.prop(cy, "use_denoising", text="Denoise")
                except Exception:
                    pass

        # Color Management
        box = layout.box()
        box.label(text="Color Management")
        vs = scene.view_settings
        row = box.row(align=True)
        row.prop(vs, "view_transform", text="View Transform")
        row = box.row(align=True)
        row.prop(vs, "look", text="Look")


class LIME_PT_render_cameras(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Cameras"
    bl_parent_id = "LIME_PT_render_configs"

    def draw(self, ctx):
        layout = self.layout
        scene = ctx.scene

        # Controls: single row so buttons quedan pegados
        row = layout.row(align=True)
        row.enabled = validate_scene.active_shot_context(ctx) is not None
        row.operator("lime.add_camera_rig", text="Create Camera (Rig)", icon='OUTLINER_DATA_CAMERA')
        row.operator("lime.duplicate_active_camera", text="", icon='DUPLICATE')

        row = layout.row(align=True)
        row.enabled = False
        row.operator("wm.call_menu", text="Camera Background", icon='IMAGE_DATA')

        layout.separator()
        layout.operator("lime.render_invoke", text="Render (F12)", icon='RENDER_STILL')


class LIME_PT_render_camera_list(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Camera List"
    bl_parent_id = "LIME_PT_render_configs"

    def draw(self, ctx):
        layout = self.layout
        scene = ctx.scene
        cams = [o for o in bpy.data.objects if getattr(o, "type", None) == 'CAMERA']
        cams.sort(key=lambda o: o.name)
        if not cams:
            row = layout.row()
            row.enabled = False
            row.label(text="No cameras", icon='INFO')
            return
        for cam in cams:
            row = layout.row(align=True)
            icon = 'CHECKMARK' if scene.camera == cam else 'OUTLINER_DATA_CAMERA'
            op = row.operator("lime.set_active_camera", text=cam.name, icon=icon)
            op.camera_name = cam.name


class LIME_PT_render_outputs(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Output Files"
    bl_parent_id = "LIME_PT_render_configs"

    def draw(self, ctx):
        layout = self.layout
        wm = ctx.window_manager
        st = getattr(wm, 'lime_pipeline', None)
        grid = layout.grid_flow(columns=2, even_columns=True, even_rows=True)

        def _images_in(dirpath: Path) -> bool:
            try:
                if not dirpath.exists():
                    return False
                for p in dirpath.iterdir():
                    if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.exr', '.tif', '.tiff'}:
                        return True
            except Exception:
                pass
            return False

        # PV
        pv_col = grid.column(align=True)
        pv_dir = None
        try:
            hydrate_state_from_filepath(st)
            root = Path(getattr(st, 'project_root', '') or '')
            rev = (getattr(st, 'rev_letter', '') or '').upper()
            sc = getattr(st, 'sc_number', None)
            _ramv, folder_type, _scenes, _target, _backups = paths_for_type(root, 'PV', rev, sc)
            pv_dir = folder_type / 'editables'
        except Exception:
            pv_dir = None
        btn = pv_col.row(align=True)
        btn.enabled = bool(pv_dir and _images_in(pv_dir))
        op = btn.operator("lime.open_output_folder", text="Proposal Views", icon='FILE_FOLDER')
        op.ptype = 'PV'

        # REND
        rd_col = grid.column(align=True)
        rd_dir = None
        try:
            hydrate_state_from_filepath(st)
            root = Path(getattr(st, 'project_root', '') or '')
            rev = (getattr(st, 'rev_letter', '') or '').upper()
            sc = getattr(st, 'sc_number', None)
            _ramv, folder_type, _scenes, _target, _backups = paths_for_type(root, 'REND', rev, sc)
            rd_dir = folder_type / 'editables'
        except Exception:
            rd_dir = None
        btn = rd_col.row(align=True)
        btn.enabled = bool(rd_dir and _images_in(rd_dir))
        op = btn.operator("lime.open_output_folder", text="Render", icon='FILE_FOLDER')
        op.ptype = 'REND'

        # SB (placeholder disabled)
        sb_col = grid.column(align=True)
        row = sb_col.row(align=True)
        row.enabled = False
        row.operator("lime.open_output_folder", text="Storyboard", icon='FILE_FOLDER')

        # ANIM (placeholder disabled)
        an_col = grid.column(align=True)
        row = an_col.row(align=True)
        row.enabled = False
        row.operator("lime.open_output_folder", text="Animation", icon='FILE_FOLDER')


__all__ = [
    "LIME_PT_render_configs",
    "LIME_PT_render_settings",
    "LIME_PT_render_cameras",
    "LIME_PT_render_camera_list",
    "LIME_PT_render_outputs",
]


