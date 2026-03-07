"""
UI for render shortcuts and output utilities.

Purpose: Provide fast render/output controls without exposing the deprecated
global preset workflow in the main production panel.
Key classes: LIME_PT_render_configs, LIME_PT_render_outputs.
Depends on: core naming/paths helpers.
Notes: UI-only; reads scene settings and pipeline state.
"""

import bpy
from bpy.types import Panel
from bpy.props import BoolProperty
from pathlib import Path

from ..core.paths import paths_for_type
from ..core.naming import hydrate_state_from_filepath


CAT = "Lime Pipeline"

RESOLUTION_SHORTCUTS = (
    ("16:9", 1920, 1080),
    ("9:16", 1080, 1920),
    ("3:4", 1080, 1440),
    ("4:3", 1440, 1080),
    ("1:1", 1920, 1920),
)


class LIME_PT_render_configs(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Render Configs"
    bl_idname = "LIME_PT_render_configs"
    bl_order = 3
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, ctx):
        layout = self.layout
        scene = ctx.scene
        render = scene.render

        shortcuts_box = layout.box()
        shortcuts_box.label(text="Render Shortcuts")
        shortcuts_row = shortcuts_box.row(align=True)
        shortcuts_row.use_property_decorate = False
        for label, base_x, base_y in RESOLUTION_SHORTCUTS:
            op = shortcuts_row.operator("lime.render_apply_resolution_shortcut", text=label)
            op.base_x = base_x
            op.base_y = base_y
            op.label = label

        uhd_toggle = shortcuts_row.row(align=True)
        uhd_toggle.prop(scene, "lime_render_shortcut_use_uhd", text="UHD", toggle=True)

        filepath_row = shortcuts_box.row(align=True)
        filepath_row.prop(render, "filepath", text="")

        layout.separator()

        anim_box = layout.box()
        local_mode = bool(getattr(ctx.window_manager.lime_pipeline, "use_local_project", False))
        anim_title = "Output Files (Animation)"
        if local_mode:
            anim_title = "Output Files (Animation, Local)"
        anim_box.label(text=anim_title)
        anim_row_top = anim_box.row(align=True)
        anim_row_top.operator("lime.set_anim_output_test", text="Set Anim Output: Test", icon='FILE_CACHE')
        anim_row_top.operator("lime.set_anim_output_final", text="Set Anim Output: Final", icon='RENDER_ANIMATION')
        if not local_mode:
            anim_row_bottom = anim_box.row(align=True)
            anim_row_bottom.operator("lime.set_anim_output_test_local", text="Set Anim Output: Test (Local)", icon='FILE_CACHE')
            anim_row_bottom.operator("lime.set_anim_output_final_local", text="Set Anim Output: Final (Local)", icon='RENDER_ANIMATION')

        render_box = layout.box()
        render_box.label(text="Render Settings")

        checkbox_row = render_box.row(align=True)
        checkbox_row.prop(render, "use_persistent_data", text="Persistent Data")
        checkbox_row.prop(render, "use_motion_blur", text="Motion Blur")
        checkbox_row.prop(render, "film_transparent", text="Transparency Fill")

        output_box = layout.box()
        output_box.label(text="Output Properties")
        out_row = output_box.row(align=True)
        out_row.prop(render, "resolution_x", text="X")
        out_row.prop(render, "resolution_y", text="Y")

        out_row = output_box.row(align=True)
        out_row.prop(render, "resolution_percentage", text="Scale")
        out_row.prop(render, "fps", text="FPS")
        out_row.menu("RENDER_MT_framerate_presets", text="", icon='DOWNARROW_HLT')

        color_box = layout.box()
        color_box.label(text="Color Management")
        vs = scene.view_settings
        color_row = color_box.row(align=True)
        color_row.prop(vs, "view_transform", text="")
        color_row.prop(vs, "look", text="")


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
            local_mode = bool(getattr(st, "use_local_project", False))
            _ramv, folder_type, _scenes, _target, _backups = paths_for_type(
                root,
                'PV',
                rev,
                sc,
                local=local_mode,
            )
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
            local_mode = bool(getattr(st, "use_local_project", False))
            _ramv, folder_type, _scenes, _target, _backups = paths_for_type(
                root,
                'REND',
                rev,
                sc,
                local=local_mode,
            )
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


def _update_uhd_resolution(self, context):
    """Update resolution when UHD toggle changes"""
    try:
        if context is None:
            return

        scene = context.scene
        render = scene.render

        # Get stored base resolution values
        wm_state = getattr(context.window_manager, 'lime_pipeline', None)
        if wm_state is None:
            return

        # Get base resolution values, defaulting to 1920x1080 if not set
        base_x = getattr(wm_state, 'lime_shortcut_base_x', 1920)
        base_y = getattr(wm_state, 'lime_shortcut_base_y', 1080)

        # Ensure base values are reasonable (at least 1px)
        if base_x < 1:
            base_x = 1920
            wm_state.lime_shortcut_base_x = base_x
        if base_y < 1:
            base_y = 1080
            wm_state.lime_shortcut_base_y = base_y

        # Apply UHD scaling - only update if values are different to avoid loops
        current_uhd = getattr(scene, 'lime_render_shortcut_use_uhd', False)

        if current_uhd:
            target_x = base_x * 2
            target_y = base_y * 2
        else:
            target_x = base_x
            target_y = base_y

        # Only update if values are actually different
        if render.resolution_x != target_x or render.resolution_y != target_y:
            render.resolution_x = target_x
            render.resolution_y = target_y

    except Exception:
        # Silently handle any errors during update
        pass


def register_render_shortcut_props():
    bpy.types.Scene.lime_render_shortcut_use_uhd = BoolProperty(
        name="UHD",
        description="Apply 2x resolution scaling when using shortcut buttons.",
        default=False,
        options={"HIDDEN"},
        update=_update_uhd_resolution,
    )


def unregister_render_shortcut_props():
    if hasattr(bpy.types.Scene, "lime_render_shortcut_use_uhd"):
        del bpy.types.Scene.lime_render_shortcut_use_uhd


__all__ = [
    "LIME_PT_render_configs",
    "LIME_PT_render_outputs",
    "register_render_shortcut_props",
    "unregister_render_shortcut_props",
]
