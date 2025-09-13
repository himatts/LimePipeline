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
            # One row: Noise Threshold, Samples, Denoise (checkbox without label)
            row = col.row(align=True)
            try:
                row.prop(cy, "preview_adaptive_threshold", text="Noise Threshold")
            except Exception:
                pass
            try:
                row.prop(cy, "preview_samples", text="Samples")
            except Exception:
                pass
            # Denoise toggle (prefer Cycles viewport prop; fallback to View Layer Cycles)
            added = False
            try:
                row.prop(cy, "use_preview_denoising", text="")
                added = True
            except Exception:
                pass
            if not added:
                try:
                    row.prop(ctx.view_layer.cycles, "use_denoising", text="")
                    added = True
                except Exception:
                    pass
            if not added:
                try:
                    row.prop(cy, "use_denoising", text="")
                except Exception:
                    pass

            col.separator()
            col.label(text="Render")
            # One row: Noise Threshold, Samples, Denoise (checkbox without label)
            row = col.row(align=True)
            try:
                row.prop(cy, "adaptive_threshold", text="Noise Threshold")
            except Exception:
                pass
            try:
                row.prop(cy, "samples", text="Samples")
            except Exception:
                pass
            added = False
            try:
                row.prop(ctx.view_layer.cycles, "use_denoising", text="")
                added = True
            except Exception:
                pass
            if not added:
                try:
                    row.prop(cy, "use_denoising", text="")
                except Exception:
                    pass

        # Color Management
        box = layout.box()
        box.label(text="Color Management")
        vs = scene.view_settings
        row = box.row(align=True)
        # Two dropdowns in one row; no labels (tooltips suffice)
        row.prop(vs, "view_transform", text="")
        row.prop(vs, "look", text="")


class LIME_PT_render_cameras(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Cameras"
    bl_parent_id = "LIME_PT_render_configs"

    def draw(self, ctx):
        layout = self.layout
        scene = ctx.scene

        # Controls: single row so buttons are tightly grouped
        row = layout.row(align=True)
        row.enabled = validate_scene.active_shot_context(ctx) is not None
        row.operator("lime.add_camera_rig", text="Create Camera (Rig)", icon='OUTLINER_DATA_CAMERA')
        row.operator("lime.duplicate_active_camera", text="", icon='DUPLICATE')

        # Rename cameras in active SHOT's camera collection
        row = layout.row(align=True)
        row.enabled = validate_scene.active_shot_context(ctx) is not None
        row.operator("lime.rename_shot_cameras", text="Rename Cameras", icon='FILE_REFRESH')

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
            # Left icon: delete camera + rig
            del_op = row.operator("lime.delete_camera_rig", text="", icon='TRASH')
            del_op.camera_name = cam.name
            # Middle: set active camera (label button)
            icon = 'CHECKMARK' if scene.camera == cam else 'OUTLINER_DATA_CAMERA'
            op = row.operator("lime.set_active_camera", text=cam.name, icon=icon)
            op.camera_name = cam.name
            # Right icon: go to rig pose mode
            pose_op = row.operator("lime.pose_camera_rig", text="", icon='POSE_HLT')
            pose_op.camera_name = cam.name


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
        # Use two tight rows (align=True) to avoid the wide grid spacing
        # and keep buttons visually grouped without extra margins.

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
        row_top = layout.row(align=True)
        pv_col = row_top.column(align=True)
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
        rd_col = row_top.column(align=True)
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

        # Second row
        row_bottom = layout.row(align=True)

        # SB (placeholder disabled)
        sb_col = row_bottom.column(align=True)
        row = sb_col.row(align=True)
        row.enabled = False
        row.operator("lime.open_output_folder", text="Storyboard", icon='FILE_FOLDER')

        # ANIM (placeholder disabled)
        an_col = row_bottom.column(align=True)
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
