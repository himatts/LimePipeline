import bpy
from bpy.types import Panel
from pathlib import Path

from ..core.paths import paths_for_type
from ..core.naming import hydrate_state_from_filepath


CAT = "Lime Pipeline"


class LIME_PT_render_configs(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Render Configs"
    bl_idname = "LIME_PT_render_configs"
    bl_order = 2

    def draw(self, ctx):
        wm = ctx.window_manager
        st = getattr(wm, 'lime_pipeline', None)
        layout = self.layout
        scene = ctx.scene

        # --- Presets row (placeholders 1-5) ---
        row = layout.row(align=True)
        for i in range(1, 6):
            op = row.operator("lime.apply_preset_placeholder", text=str(i), icon='PRESET')
            op.preset_index = i
            op.tooltip = f"Preset {i}"

        layout.separator()

        # --- Section 1: Settings (Resolution, Cycles, Color Management) ---
        if st is not None:
            box = layout.box()
            header = box.row(align=True)
            icon = 'TRIA_DOWN' if getattr(st, 'ui_rc_show_settings', True) else 'TRIA_RIGHT'
            header.prop(st, "ui_rc_show_settings", text="", icon=icon, emboss=False)
            header.label(text="Settings")
            if getattr(st, 'ui_rc_show_settings', True):
                # Resolution
                sub = box.box()
                sub.label(text="Resolution")
                row = sub.row(align=True)
                row.prop(scene.render, "resolution_x", text="X")
                row.prop(scene.render, "resolution_y", text="Y")

                # Cycles
                sub = box.box()
                sub.label(text="Cycles")
                cy = getattr(scene, 'cycles', None)
                if cy is None:
                    col = sub.column()
                    col.enabled = False
                    col.label(text="Cycles not available", icon='INFO')
                else:
                    col = sub.column(align=True)
                    # Viewport
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
                    # Final render
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
                sub = box.box()
                sub.label(text="Color Management")
                vs = scene.view_settings
                row = sub.row(align=True)
                row.prop(vs, "view_transform", text="View Transform")
                row = sub.row(align=True)
                row.prop(vs, "look", text="Look")
        else:
            # Fallback when WM state is missing: render sections expanded
            box = layout.box()
            box.label(text="Resolution")
            row = box.row(align=True)
            row.prop(scene.render, "resolution_x", text="X")
            row.prop(scene.render, "resolution_y", text="Y")

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

            box = layout.box()
            box.label(text="Color Management")
            vs = scene.view_settings
            row = box.row(align=True)
            row.prop(vs, "view_transform", text="View Transform")
            row = box.row(align=True)
            row.prop(vs, "look", text="Look")

        layout.separator()

        # --- Section 2: Cameras (collapsible) ---
        if st is not None:
            box = layout.box()
            header = box.row(align=True)
            icon = 'TRIA_DOWN' if getattr(st, 'ui_rc_show_cameras', True) else 'TRIA_RIGHT'
            header.prop(st, "ui_rc_show_cameras", text="", icon=icon, emboss=False)
            header.label(text="Cameras")
            if getattr(st, 'ui_rc_show_cameras', True):
                cams = [o for o in bpy.data.objects if getattr(o, "type", None) == 'CAMERA']
                cams.sort(key=lambda o: o.name)
                if not cams:
                    row = box.row()
                    row.enabled = False
                    row.label(text="No cameras", icon='INFO')
                else:
                    for cam in cams:
                        row = box.row(align=True)
                        icon = 'CHECKMARK' if scene.camera == cam else 'OUTLINER_DATA_CAMERA'
                        op = row.operator("lime.set_active_camera", text=cam.name, icon=icon)
                        op.camera_name = cam.name
        else:
            box = layout.box()
            box.label(text="Cameras")
            cams = [o for o in bpy.data.objects if getattr(o, "type", None) == 'CAMERA']
            cams.sort(key=lambda o: o.name)
            if not cams:
                row = box.row()
                row.enabled = False
                row.label(text="No cameras", icon='INFO')
            else:
                for cam in cams:
                    row = box.row(align=True)
                    icon = 'CHECKMARK' if scene.camera == cam else 'OUTLINER_DATA_CAMERA'
                    op = row.operator("lime.set_active_camera", text=cam.name, icon=icon)
                    op.camera_name = cam.name

        # Render button always visible under Cameras
        layout.separator()
        layout.operator("lime.render_invoke", text="Render (F12)", icon='RENDER_STILL')

        layout.separator()

        # --- Section 3: Output Files (collapsible) ---
        if st is not None:
            box = layout.box()
            header = box.row(align=True)
            icon = 'TRIA_DOWN' if getattr(st, 'ui_rc_show_outputs', True) else 'TRIA_RIGHT'
            header.prop(st, "ui_rc_show_outputs", text="", icon=icon, emboss=False)
            header.label(text="Output Files")
            if getattr(st, 'ui_rc_show_outputs', True):
                grid = box.grid_flow(columns=2, even_columns=True, even_rows=True)

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

                # SB (placeholder desactivado)
                sb_col = grid.column(align=True)
                row = sb_col.row(align=True)
                row.enabled = False
                row.operator("lime.open_output_folder", text="Storyboard", icon='FILE_FOLDER')

                # ANIM (placeholder desactivado)
                an_col = grid.column(align=True)
                row = an_col.row(align=True)
                row.enabled = False
                row.operator("lime.open_output_folder", text="Animation", icon='FILE_FOLDER')
        else:
            # Fallback expanded
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

            # SB (placeholder desactivado)
            sb_col = grid.column(align=True)
            row = sb_col.row(align=True)
            row.enabled = False
            row.operator("lime.open_output_folder", text="Storyboard", icon='FILE_FOLDER')

            # ANIM (placeholder desactivado)
            an_col = grid.column(align=True)
            row = an_col.row(align=True)
            row.enabled = False
            row.operator("lime.open_output_folder", text="Animation", icon='FILE_FOLDER')


__all__ = [
    "LIME_PT_render_configs",
]


