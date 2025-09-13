bl_info = {
    "name": "Lime Pipeline",
    "author": "Lime",
    "version": (0, 1, 0),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar (N) > Lime Pipeline",
    "description": "Project organization, naming, and first save/backup helpers",
    "category": "System",
}

import bpy
from bpy.app.handlers import persistent

# Registration is centralized here to keep imports stable for future growth
from .prefs import LimePipelinePrefs
from .props import register as register_props, unregister as unregister_props
from .ui import LIME_PT_project_org
from .ui import LIME_PT_shots, LIME_PT_shots_list, LIME_PT_shots_tools
from .ui import LIME_PT_render_configs, LIME_PT_render_settings, LIME_PT_render_cameras, LIME_PT_render_camera_list, LIME_PT_render_outputs
from .ui import LIME_PT_stage_setup
from .ui import LIME_PT_image_save_as
from .ops.ops_select_root import LIME_OT_pick_root
from .ops.ops_folders import LIME_OT_ensure_folders, LIME_OT_open_folder
from .ops.ops_folders import LIME_OT_open_output_folder
from .ops.ops_create_file import LIME_OT_create_file
from .ops.ops_backup import LIME_OT_create_backup
from .ops.ops_tooltips import LIME_OT_show_text
from .ops.ops_tooling_presets import LIME_OT_apply_preset_placeholder
from .ops.ops_shots import (
    LIME_OT_new_shot,
    LIME_OT_shot_instance,
    LIME_OT_duplicate_shot,
    LIME_OT_activate_shot,
    LIME_OT_delete_shot,
)
from .ops.ops_add_missing import (
    LIME_OT_add_missing_collections,
)
from .ops.ops_proposal_view import (
    LIME_OT_proposal_view_config,
    LIME_OT_take_pv_shot,
    LIME_OT_take_all_pv_shots,
    LIME_OT_add_camera_rig,
)
from .ops.ops_import_layout import (
    LIME_OT_import_layout,
)
from .ops.ops_renders import (
    LIME_OT_render_config,
    LIME_OT_render_shot,
    LIME_OT_render_all,
)
from .ops.ops_stage import (
    LIME_OT_stage_main_light,
    LIME_OT_stage_aux_light,
)
from .ops.ops_rev import (
    LIME_OT_rev_prev,
    LIME_OT_rev_next,
)
from .ops.ops_save import (
    LIME_OT_set_active_camera,
    LIME_OT_render_invoke,
    LIME_OT_save_as_with_template,
    LIME_OT_duplicate_active_camera,
)


classes = (
    LimePipelinePrefs,
    LIME_OT_pick_root,
    LIME_OT_ensure_folders,
    LIME_OT_open_folder,
    LIME_OT_open_output_folder,
    LIME_OT_create_file,
    LIME_OT_create_backup,
    LIME_OT_show_text,
    LIME_OT_apply_preset_placeholder,
    LIME_OT_proposal_view_config,
    LIME_OT_take_pv_shot,
    LIME_OT_take_all_pv_shots,
    LIME_OT_add_camera_rig,
    LIME_OT_import_layout,
    LIME_OT_render_config,
    LIME_OT_render_shot,
    LIME_OT_render_all,
    LIME_OT_stage_main_light,
    LIME_OT_stage_aux_light,
    LIME_PT_project_org,
    LIME_PT_shots,
    LIME_PT_shots_list,
    LIME_PT_shots_tools,
    LIME_PT_render_configs,
    LIME_PT_render_settings,
    LIME_PT_render_cameras,
    LIME_PT_render_camera_list,
    LIME_PT_render_outputs,
    LIME_PT_stage_setup,
    LIME_PT_image_save_as,
    LIME_OT_new_shot,
    LIME_OT_shot_instance,
    LIME_OT_duplicate_shot,
    LIME_OT_activate_shot,
    LIME_OT_delete_shot,
    LIME_OT_add_missing_collections,
    LIME_OT_rev_prev,
    LIME_OT_rev_next,
    LIME_OT_set_active_camera,
    LIME_OT_duplicate_active_camera,
    LIME_OT_render_invoke,
    LIME_OT_save_as_with_template,
)


def register():
    register_props()
    for cls in classes:
        bpy.utils.register_class(cls)
    # Register load handler to hydrate state on file load
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    unregister_props()
    try:
        bpy.app.handlers.load_post.remove(_on_load_post)
    except Exception:
        pass


@persistent
def _on_load_post(dummy):
    try:
        st = bpy.context.window_manager.lime_pipeline
    except Exception:
        st = None
    if st is None:
        return
    try:
        # Forcefully hydrate from the current .blend filepath
        from .core.naming import hydrate_state_from_filepath
        hydrate_state_from_filepath(st, force=True)
    except Exception:
        pass


