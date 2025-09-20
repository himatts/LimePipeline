bl_info = {
    "name": "Lime Pipeline",
    "author": "Lime",
    "version": (0, 2, 0),  # Render presets management (global + defaults)
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
from .ui import LIME_PT_render_configs, LIME_PT_render_preset_actions, LIME_PT_render_settings, LIME_PT_render_cameras, LIME_PT_render_camera_list, LIME_PT_render_outputs
from .ui import LIME_PT_stage_setup
from .ui import LIME_PT_image_save_as
from .ui import (
    LIME_PT_model_organizer,
    LIME_PT_dimension_utilities,
    LIME_OT_set_unit_preset,
)
from .ops.ops_model_organizer import (
    LIME_OT_group_selection_empty,
    LIME_OT_move_controller,
    LIME_OT_apply_scene_deltas,
    LIME_OT_colorize_parent_groups,
)
from .ui import (
    LIME_TB_PT_root,
    LIME_TB_OT_placeholder,
    LIME_TB_PT_animation_params,
    LIME_TB_PT_noisy_movement,
)
from .ui import register_camera_list_props, unregister_camera_list_props
from .ui import register_shot_list_props, unregister_shot_list_props
from .ops.ops_select_root import LIME_OT_pick_root
from .ops.ops_folders import LIME_OT_ensure_folders, LIME_OT_open_folder
from .ops.ops_folders import LIME_OT_open_output_folder
from .ops.ops_create_file import LIME_OT_create_file
from .ops.ops_backup import LIME_OT_create_backup
from .ops.ops_tooltips import LIME_OT_show_text
from .ops.ops_render_presets import (
    LIME_OT_render_preset_save,
    LIME_OT_render_preset_apply,
    LIME_OT_render_preset_clear,
    LIME_OT_render_preset_reset_all,
    LIME_OT_render_preset_restore_defaults,
    LIME_OT_render_preset_update_defaults,
    ensure_preset_slots,
)
from .ops.animation_params import LIME_TB_OT_apply_keyframe_style
from .ops.ops_step_clean import LIME_OT_clean_step
from .ops.ops_dimensions import LIME_OT_dimension_envelope, disable_dimension_overlay_guard
from .ops.ops_noise import (
    LIME_TB_OT_noise_add_profile,
    LIME_TB_OT_noise_sync,
    LIME_TB_OT_noise_apply_to_selected,
    LIME_TB_OT_noise_remove_from_object,
    LIME_TB_OT_noise_remove_selected,
    LIME_TB_OT_noise_rename_profile,
    LIME_TB_OT_noise_delete_profile,
    LIME_TB_OT_noise_group_randomize,
    LIME_TB_OT_noise_group_copy,
    LIME_TB_OT_noise_group_paste,
)
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
from .ops.ops_cameras import (
    LIME_OT_set_active_camera,
    LIME_OT_render_invoke,
    LIME_OT_save_as_with_template,
    LIME_OT_duplicate_active_camera,
    LIME_OT_rename_shot_cameras,
    LIME_OT_sync_camera_list,
    LIME_OT_add_camera_rig_and_sync,
    LIME_OT_delete_camera_rig,
    LIME_OT_delete_camera_rig_and_sync,
    LIME_OT_pose_camera_rig,
)


NON_PANEL_CLASSES = (
    LimePipelinePrefs,
    LIME_TB_OT_placeholder,
    LIME_OT_pick_root,
    LIME_OT_ensure_folders,
    LIME_OT_open_folder,
    LIME_OT_open_output_folder,
    LIME_OT_create_file,
    LIME_OT_create_backup,
    LIME_OT_show_text,
    LIME_OT_render_preset_save,
    LIME_OT_render_preset_apply,
    LIME_OT_render_preset_clear,
    LIME_OT_render_preset_reset_all,
    LIME_OT_render_preset_restore_defaults,
    LIME_OT_render_preset_update_defaults,
    LIME_OT_clean_step,
    LIME_OT_dimension_envelope,
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
    LIME_OT_group_selection_empty,
    LIME_OT_move_controller,
    LIME_OT_apply_scene_deltas,
    LIME_OT_colorize_parent_groups,
    LIME_OT_set_unit_preset,
    LIME_TB_OT_apply_keyframe_style,
    LIME_TB_OT_noise_add_profile,
    LIME_TB_OT_noise_sync,
    LIME_TB_OT_noise_apply_to_selected,
    LIME_TB_OT_noise_remove_from_object,
    LIME_TB_OT_noise_remove_selected,
    LIME_TB_OT_noise_rename_profile,
    LIME_TB_OT_noise_delete_profile,
    LIME_TB_OT_noise_group_randomize,
    LIME_TB_OT_noise_group_copy,
    LIME_TB_OT_noise_group_paste,
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
    LIME_OT_rename_shot_cameras,
    LIME_OT_sync_camera_list,
    LIME_OT_add_camera_rig_and_sync,
    LIME_OT_delete_camera_rig,
    LIME_OT_delete_camera_rig_and_sync,
    LIME_OT_pose_camera_rig,
    LIME_OT_render_invoke,
    LIME_OT_save_as_with_template,
)

PIPELINE_PANEL_CLASSES = (
    LIME_PT_model_organizer,
    LIME_PT_dimension_utilities,
    LIME_PT_project_org,
    LIME_PT_render_configs,
    LIME_PT_render_preset_actions,
    LIME_PT_render_settings,
    LIME_PT_render_outputs,
    LIME_PT_shots,
    LIME_PT_shots_list,
    LIME_PT_shots_tools,
    LIME_PT_stage_setup,
    LIME_PT_render_cameras,
    LIME_PT_render_camera_list,
)

OTHER_PANEL_CLASSES = (
    LIME_PT_image_save_as,
)

TOOLBOX_CATEGORY_PANELS = (
    LIME_TB_PT_root,
    LIME_TB_PT_animation_params,
    LIME_TB_PT_noisy_movement,
)

TOOLBOX_PANEL_CLASSES = (
    LIME_TB_PT_root,
    LIME_TB_PT_animation_params,
    LIME_TB_PT_noisy_movement,
)

def _panel_is_child(cls) -> bool:
    return bool(getattr(cls, 'bl_parent_id', '') or '')


def _panel_order(cls, default: int = 0) -> int:
    try:
        value = getattr(cls, 'bl_order', default)
    except Exception:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _panel_sort_tuple(cls):
    return (_panel_order(cls), getattr(cls, 'bl_label', '') or '', cls.__name__)


REGISTERED_CLASSES = []

def register():
    global REGISTERED_CLASSES
    # Helpful log to ensure the source path being loaded (detect duplicates/stale installs)
    try:
        print(f"[Lime Pipeline] Loading addon from: {__file__}")
    except Exception:
        pass

    register_props()
    from .ui import register_anim_params_props, register_noise_props
    register_anim_params_props()
    register_noise_props()
    register_camera_list_props()
    register_shot_list_props()

    try:
        st = getattr(bpy.context.window_manager, "lime_pipeline", None)
        if st and getattr(st, "auto_select_hierarchy", False):
            from .ops.ops_model_organizer import enable_auto_select_hierarchy
            enable_auto_select_hierarchy()
    except Exception:
        pass

    pipeline_root_panels = [cls for cls in PIPELINE_PANEL_CLASSES if not _panel_is_child(cls)]
    pipeline_children = {}
    for cls in PIPELINE_PANEL_CLASSES:
        parent_id = getattr(cls, 'bl_parent_id', '') or ''
        if parent_id:
            pipeline_children.setdefault(parent_id, []).append(cls)

    try:
        for cls in pipeline_root_panels:
            try:
                if getattr(cls, 'bl_space_type', None) == 'VIEW_3D':
                    cls.bl_category = 'Lime Pipeline'
            except Exception:
                pass
        for cls in TOOLBOX_CATEGORY_PANELS:
            try:
                if getattr(cls, 'bl_space_type', None) == 'VIEW_3D':
                    cls.bl_category = 'Lime Toolbox'
            except Exception:
                pass
    except Exception:
        pass

    REGISTERED_CLASSES = []
    for cls in NON_PANEL_CLASSES:
        bpy.utils.register_class(cls)
        REGISTERED_CLASSES.append(cls)

    for parent_cls in sorted(pipeline_root_panels, key=_panel_sort_tuple):
        bpy.utils.register_class(parent_cls)
        REGISTERED_CLASSES.append(parent_cls)
        parent_id = getattr(parent_cls, 'bl_idname', '') or parent_cls.__name__
        for child_cls in sorted(pipeline_children.get(parent_id, ()), key=_panel_sort_tuple):
            bpy.utils.register_class(child_cls)
            REGISTERED_CLASSES.append(child_cls)

    remaining = [cls for cls in PIPELINE_PANEL_CLASSES if cls not in REGISTERED_CLASSES]
    for cls in sorted(remaining, key=_panel_sort_tuple):
        bpy.utils.register_class(cls)
        REGISTERED_CLASSES.append(cls)

    for cls in OTHER_PANEL_CLASSES:
        bpy.utils.register_class(cls)
        REGISTERED_CLASSES.append(cls)

    for cls in TOOLBOX_PANEL_CLASSES:
        bpy.utils.register_class(cls)
        REGISTERED_CLASSES.append(cls)

    # Register load handler to hydrate state on file load
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)

    try:
        ensure_preset_slots(bpy.context, ensure_scene=True)
    except Exception:
        pass

def unregister():
    global REGISTERED_CLASSES
    disable_dimension_overlay_guard()
    for cls in reversed(REGISTERED_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    REGISTERED_CLASSES = []
    from .ui import unregister_anim_params_props, unregister_noise_props
    unregister_anim_params_props()
    unregister_noise_props()
    unregister_camera_list_props()
    unregister_shot_list_props()
    try:
        from .ops.ops_model_organizer import disable_auto_select_hierarchy
        disable_auto_select_hierarchy()
    except Exception:
        pass
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
    try:
        ensure_preset_slots(bpy.context, ensure_scene=True)
    except Exception:
        pass












