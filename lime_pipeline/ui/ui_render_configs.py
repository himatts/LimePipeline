import bpy
from bpy.types import Panel
from pathlib import Path

from ..core.paths import paths_for_type
from ..core.naming import hydrate_state_from_filepath


CAT = "Lime Pipeline"
ADDON_ID = __package__.split('.')[0]
from ..ops.ops_render_presets import PRESET_SLOT_COUNT


class LIME_PT_render_configs(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Render Configs"
    bl_options = {"DEFAULT_CLOSED"}
    bl_idname = "LIME_PT_render_configs"
    bl_order = 3

    def draw(self, ctx):
        layout = self.layout
        prefs = None
        try:
            prefs = ctx.preferences.addons[ADDON_ID].preferences
        except Exception:
            prefs = None

        global_col = layout.column(align=True)
        global_col.label(text="Global Presets")
        global_slots = getattr(prefs, 'global_render_presets', []) if prefs else []

        grid = global_col.grid_flow(row_major=True, columns=PRESET_SLOT_COUNT, even_columns=True, align=True)

        for idx in range(PRESET_SLOT_COUNT):
            slot = global_slots[idx] if idx < len(global_slots) else None
            has_data = bool(slot and not slot.is_empty and (slot.data_json or '').strip())

            cell = grid.column(align=True)
            cell.use_property_decorate = False

            apply_col = cell.column(align=True)
            apply_col.enabled = has_data
            apply_btn = apply_col.operator("lime.render_preset_apply", text=str(idx + 1), icon='PRESET')
            apply_btn.slot_index = idx

            actions = cell.split(factor=0.5, align=True)
            save_col = actions.column(align=True)
            save_btn = save_col.operator("lime.render_preset_save", text="", icon='FILE_TICK')
            save_btn.slot_index = idx

            delete_col = actions.column(align=True)
            delete_col.enabled = has_data
            delete_btn = delete_col.operator("lime.render_preset_clear", text="", icon='TRASH')
            delete_btn.slot_index = idx

        global_col.separator()


class LIME_PT_render_preset_actions(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Preset Maintenance"
    bl_options = {"DEFAULT_CLOSED"}
    bl_parent_id = "LIME_PT_render_configs"
    bl_order = 2

    def draw(self, ctx):
        layout = self.layout
        col = layout.column(align=True)
        col.operator("lime.render_preset_reset_all", text="Reset Presets", icon='TRASH')
        col.operator("lime.render_preset_restore_defaults", text="Restore Defaults", icon='LOOP_BACK')
        col.operator("lime.render_preset_update_defaults", text="Update Defaults", icon='FILE_REFRESH')


class LIME_PT_render_settings(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Settings"
    bl_options = {"DEFAULT_CLOSED"}
    bl_parent_id = "LIME_PT_render_configs"
    bl_order = 0

    def draw(self, ctx):
        layout = self.layout
        scene = ctx.scene
        render = scene.render
        cy = getattr(scene, 'cycles', None)

        box = layout.box()
        box.label(text="Render Settings")
        row = box.row(align=True)
        row.prop(render, "engine", text="")

        if cy is None:
            col = box.column()
            col.enabled = False
            col.label(text="Cycles not available", icon='INFO')
        else:
            col = box.column(align=True)
            viewport_row = col.row(align=True)
            try:
                viewport_row.prop(cy, "preview_adaptive_threshold", text="Noise Threshold")
            except Exception:
                pass
            try:
                viewport_row.prop(cy, "preview_samples", text="Samples")
            except Exception:
                pass
            added = False
            try:
                viewport_row.prop(cy, "use_preview_denoising", text="")
                added = True
            except Exception:
                pass
            if not added:
                try:
                    viewport_row.prop(ctx.view_layer.cycles, "use_denoising", text="")
                    added = True
                except Exception:
                    pass
            if not added:
                try:
                    viewport_row.prop(cy, "use_denoising", text="")
                except Exception:
                    pass

            col.separator()
            render_row = col.row(align=True)
            try:
                render_row.prop(cy, "adaptive_threshold", text="Noise Threshold")
            except Exception:
                pass
            try:
                render_row.prop(cy, "samples", text="Samples")
            except Exception:
                pass
            added = False
            try:
                render_row.prop(ctx.view_layer.cycles, "use_denoising", text="")
                added = True
            except Exception:
                pass
            if not added:
                try:
                    render_row.prop(cy, "use_denoising", text="")
                except Exception:
                    pass

        checkbox_row = box.row(align=True)
        checkbox_row.prop(render, "use_persistent_data", text="Persistent Data")
        checkbox_row.prop(render, "film_transparent", text="Transparent Film")

        output_box = layout.box()
        output_box.label(text="Output Properties")
        row = output_box.row(align=True)
        row.prop(render, "resolution_x", text="X")
        row.prop(render, "resolution_y", text="Y")

        row = output_box.row(align=True)
        row.prop(render, "resolution_percentage", text="Scale")
        row.prop(render, "resolution_percentage", text="", slider=True)

        color_box = layout.box()
        color_box.label(text="Color Management")
        vs = scene.view_settings
        row = color_box.row(align=True)
        row.prop(vs, "view_transform", text="")
        row.prop(vs, "look", text="")

class LIME_PT_render_outputs(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Output Files"
    bl_options = {"DEFAULT_CLOSED"}
    bl_parent_id = "LIME_PT_render_configs"
    bl_order = 1

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
    "LIME_PT_render_outputs",
    "LIME_PT_render_preset_actions",
]
