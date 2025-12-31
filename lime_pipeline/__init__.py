"""
Lime Pipeline - Blender Addon for Project Organization and Standardization

This addon provides tools for standardizing Blender project structure, naming conventions,
and workflow automation for content creation pipelines. It handles SHOT collections,
render outputs, material normalization, camera rigs with margins, and backup management.

Main features:
- Project naming and file organization
- SHOT collection management with automatic scene setup
- Camera rigs with configurable margin backgrounds
- AI-assisted material renaming and normalization
- Render preset management and proposal outputs
- Automated folder structure creation
- Backup system with versioning

UI Location: View3D > Sidebar (N) > Lime Pipeline
"""

bl_info = {
    "name": "Lime Pipeline",
    "author": "Lime",
    "version": (0, 4, 0),  # AI Render Converter added
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar (N) > Lime Pipeline",
    "description": "Project organization, naming, and first save/backup helpers",
    "category": "System",
}

import bpy
try:
    from bpy.app.handlers import persistent
except ImportError:
    # Fallback for newer Blender versions
    def persistent(func):
        return func

# Registration is centralized here to keep imports stable for future growth
from .prefs import LimePipelinePrefs
from .props import register as register_props, unregister as unregister_props
from .ui import LIME_PT_project_org
from .ui import LIME_PT_shots
from .ui import (
    LIME_PT_render_configs,
    LIME_PT_render_preset_actions,
    LIME_PT_render_outputs,
    LIME_PT_render_cameras,
)
from .ui import LIME_PT_ai_render_converter
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
from .ops.ops_material_alpha_mix import (
    LIME_OT_apply_object_alpha_mix,
)
from .ui import (
    LIME_TB_PT_animation_params,
)
from .ui import LIME_TB_PT_noisy_movement
from .ui import (
    LIME_TB_PT_alpha_manager,
    LIME_TB_UL_alpha_events,
)
from .ui import LIME_TB_PT_ai_material_renamer, LIME_TB_UL_ai_mat_rows
from .ui import LIME_TB_PT_experimental
from .ops.ops_ai_material_renamer import (
    LIME_TB_OT_ai_test_connection,
    LIME_TB_OT_ai_rename_single,
    LIME_TB_OT_ai_scan_materials,
    LIME_TB_OT_ai_apply_materials,
    LIME_TB_OT_ai_test_state,
    LIME_TB_OT_ai_clear_materials,
    LIME_TB_OT_ai_select_all,
    LIME_TB_OT_ai_select_none,
    LIME_TB_OT_ai_normalize_to_closest,
    LIME_TB_OT_ai_keep_proposal,
    LIME_TB_OT_ai_toggle_review,
    LIME_TB_OT_open_ai_material_manager,
)
from .ops.ops_ai_render_converter import (
    register_ai_render_handlers,
    unregister_ai_render_handlers,
    refresh_ai_render_state,
    LIME_OT_ai_render_refresh,
    LIME_OT_ai_render_frame,
    LIME_OT_ai_render_generate,
    LIME_OT_ai_render_retry,
    LIME_OT_ai_render_cancel,
    LIME_OT_ai_render_test_connection,
    LIME_OT_ai_render_add_to_sequencer,
)
from .props_ai_materials import register as register_ai_props, unregister as unregister_ai_props
from .props_ai_renders import register as register_ai_render_props, unregister as unregister_ai_render_props
from .ui import register_camera_list_props, unregister_camera_list_props
from .ui import register_render_shortcut_props, unregister_render_shortcut_props
from .ui import register_shot_list_props, unregister_shot_list_props
from .ops.ops_select_root import LIME_OT_pick_root
from .ops.ops_folders import LIME_OT_ensure_folders, LIME_OT_open_folder
from .ops.ops_folders import LIME_OT_open_output_folder
from .ops.ops_anim_output import (
    LIME_OT_set_anim_output_test,
    LIME_OT_set_anim_output_final,
    LIME_OT_set_anim_output_test_local,
    LIME_OT_set_anim_output_final_local,
)
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
    LIME_OT_toggle_denoising_property,
    LIME_OT_toggle_preview_denoising_property,
    LIME_OT_render_apply_resolution_shortcut,
    ensure_preset_slots,
)
from .ops.ops_animation_params import LIME_TB_OT_apply_keyframe_style
from .ops.ops_step_clean import LIME_OT_clean_step
from .ops.ops_dimensions import (
    LIME_OT_dimension_envelope,
    disable_dimension_overlay_guard,
    enable_dimension_live_updates,
    disable_dimension_live_updates,
)
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
from .ops.ops_alpha_manager import (
    register_alpha_props,
    unregister_alpha_props,
)

from .ops.ops_shots import (
    LIME_OT_new_shot,
    LIME_OT_duplicate_shot,
    LIME_OT_activate_shot,
    LIME_OT_delete_shot,
    LIME_OT_jump_to_first_shot_marker,
    LIME_OT_render_shots_from_markers,
)
from .ops.ops_add_missing import (
    LIME_OT_add_missing_collections,
)
## Removed deprecated proposal view operators; camera rig operator now lives in ops_cameras
from .ops.ops_import_layout import (
    LIME_OT_import_layout,
)
from .ops.ops_duplicate_scene import (
    LIME_OT_duplicate_scene_sequential,
)
from .ops.ops_rev import (
    LIME_OT_rev_prev,
    LIME_OT_rev_next,
)
from .ops.ops_save_templates import (
    LIME_OT_save_as_with_template,
    LIME_OT_save_as_with_template_raw,
)
from .ops.ops_cameras import (
    LIME_OT_set_active_camera,
    LIME_OT_render_invoke,
    LIME_OT_duplicate_active_camera,
    LIME_OT_rename_shot_cameras,
    LIME_OT_sync_camera_list,
    LIME_OT_add_camera_rig,
    LIME_OT_delete_camera_rig,
    LIME_OT_delete_camera_rig_and_sync,
    LIME_OT_pose_camera_rig,
    LIME_OT_retry_camera_margin_backgrounds,
    LIME_OT_reset_margin_alpha,
)
from .ops.ops_auto_camera_bg import (
    LIME_OT_auto_camera_background,
    LIME_OT_auto_camera_background_refresh,
    LIME_OT_auto_camera_background_toggle_live,
    LIME_OT_auto_camera_background_bake,
    LIME_OT_auto_camera_background_cleanup,
    ensure_auto_bg_live_updates,
)
from .ops.ops_stage_hdri import (
    LIME_OT_stage_set_hdri,
)
from .ops.ops_scene_continuity import (
    LIME_OT_stage_create_next_scene_file,
)
from .ops.ops_view_layers import (
    LIME_OT_create_view_layers,
)
from .ops.ops_comp_view_layer_outputs import (
    LIME_OT_setup_view_layer_outputs,
)
from .ops.ops_linked_collections import (
    LIME_OT_localize_linked_collection,
)


# Class collections for organized registration
NON_PANEL_CLASSES = (
    # Preferences and core utilities
    LimePipelinePrefs,
    LIME_TB_UL_alpha_events,
    LIME_OT_pick_root,
    LIME_OT_ensure_folders,
    LIME_OT_open_folder,
    LIME_OT_open_output_folder,
    LIME_OT_set_anim_output_test,
    LIME_OT_set_anim_output_final,
    LIME_OT_set_anim_output_test_local,
    LIME_OT_set_anim_output_final_local,
    LIME_OT_create_file,
    LIME_OT_create_backup,
    LIME_OT_show_text,
    LIME_OT_render_preset_save,
    LIME_OT_render_preset_apply,
    LIME_OT_render_preset_clear,
    LIME_OT_render_preset_reset_all,
    LIME_OT_render_preset_restore_defaults,
    LIME_OT_render_preset_update_defaults,
    LIME_OT_toggle_denoising_property,
    LIME_OT_toggle_preview_denoising_property,
    LIME_OT_render_apply_resolution_shortcut,
    LIME_OT_clean_step,
    LIME_OT_dimension_envelope,
    LIME_OT_add_camera_rig,
    LIME_OT_import_layout,
    LIME_OT_duplicate_scene_sequential,
    LIME_OT_stage_create_next_scene_file,
    LIME_OT_group_selection_empty,
    LIME_OT_move_controller,
    LIME_OT_apply_scene_deltas,
    LIME_OT_colorize_parent_groups,
    LIME_OT_apply_object_alpha_mix,
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
    LIME_OT_duplicate_shot,
    LIME_OT_activate_shot,
    LIME_OT_delete_shot,
    LIME_OT_jump_to_first_shot_marker,
    LIME_OT_render_shots_from_markers,
    LIME_OT_add_missing_collections,
    LIME_OT_rev_prev,
    LIME_OT_rev_next,
    LIME_OT_set_active_camera,
    LIME_OT_duplicate_active_camera,
    LIME_OT_rename_shot_cameras,
    LIME_OT_sync_camera_list,
    LIME_OT_delete_camera_rig,
    LIME_OT_delete_camera_rig_and_sync,
    LIME_OT_pose_camera_rig,
    LIME_OT_render_invoke,
    LIME_OT_retry_camera_margin_backgrounds,
    LIME_OT_reset_margin_alpha,
    LIME_OT_save_as_with_template,
    LIME_OT_save_as_with_template_raw,
    LIME_OT_auto_camera_background,
    LIME_OT_auto_camera_background_refresh,
    LIME_OT_auto_camera_background_toggle_live,
    LIME_OT_auto_camera_background_bake,
    LIME_OT_auto_camera_background_cleanup,
    LIME_OT_stage_set_hdri,
    LIME_OT_create_view_layers,
    LIME_OT_setup_view_layer_outputs,
    LIME_OT_localize_linked_collection,
    LIME_TB_OT_ai_test_connection,
    LIME_TB_OT_ai_rename_single,
    LIME_TB_OT_ai_scan_materials,
    LIME_TB_OT_ai_apply_materials,
    LIME_TB_OT_ai_test_state,
    LIME_TB_OT_ai_clear_materials,
    LIME_TB_OT_ai_select_all,
    LIME_TB_OT_ai_select_none,
    LIME_TB_OT_ai_normalize_to_closest,
    LIME_TB_OT_ai_keep_proposal,
    LIME_TB_OT_ai_toggle_review,
    LIME_TB_OT_open_ai_material_manager,
    LIME_TB_UL_ai_mat_rows,
    LIME_OT_ai_render_refresh,
    LIME_OT_ai_render_frame,
    LIME_OT_ai_render_generate,
    LIME_OT_ai_render_retry,
    LIME_OT_ai_render_cancel,
    LIME_OT_ai_render_test_connection,
    LIME_OT_ai_render_add_to_sequencer,
)

PIPELINE_PANEL_CLASSES = (
    LIME_PT_project_org,
    LIME_PT_render_configs,
    LIME_PT_render_preset_actions,
    LIME_PT_render_outputs,
    LIME_PT_ai_render_converter,
    LIME_PT_shots,
    LIME_PT_stage_setup,
    LIME_PT_render_cameras,
)

OTHER_PANEL_CLASSES = (
    LIME_PT_image_save_as,
)

TOOLBOX_CATEGORY_PANELS = (
    LIME_PT_model_organizer,
    LIME_PT_dimension_utilities,
    LIME_TB_PT_animation_params,
    LIME_TB_PT_noisy_movement,
    LIME_TB_PT_alpha_manager,
    LIME_TB_PT_ai_material_renamer,
    LIME_TB_PT_experimental,
)

TOOLBOX_PANEL_CLASSES = (
    LIME_PT_model_organizer,
    LIME_PT_dimension_utilities,
    LIME_TB_PT_animation_params,
    LIME_TB_PT_noisy_movement,
    LIME_TB_PT_alpha_manager,
    LIME_TB_PT_ai_material_renamer,
    LIME_TB_PT_experimental,
)

def _panel_is_child(cls) -> bool:
    """Check if a panel class is a child panel by examining bl_parent_id attribute.

    Args:
        cls: Panel class to check

    Returns:
        bool: True if panel has a parent (is a child panel)
    """
    return bool(getattr(cls, 'bl_parent_id', '') or '')


def _panel_order(cls, default: int = 0) -> int:
    """Get the panel ordering value from bl_order attribute.

    Args:
        cls: Panel class to get order from
        default: Default order value if bl_order is not set or invalid

    Returns:
        int: Panel order value, or default if invalid
    """
    try:
        value = getattr(cls, 'bl_order', default)
    except Exception:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _panel_sort_tuple(cls):
    """Create a sorting tuple for panel classes.

    Used for consistent panel ordering during registration.
    Order: (bl_order, bl_label, class_name)

    Args:
        cls: Panel class to create sort tuple for

    Returns:
        tuple: (order_int, label_str, class_name_str) for sorting
    """
    return (_panel_order(cls), getattr(cls, 'bl_label', '') or '', cls.__name__)


# Global list to track registered classes for proper cleanup
REGISTERED_CLASSES = []

def register():
    """Register all Lime Pipeline classes, properties, and handlers.

    This function performs the complete addon registration:
    1. Registers all property groups (WindowManager, Scene, etc.)
    2. Sets up panel categories ("Lime Pipeline", "Lime Toolbox")
    3. Registers classes in hierarchical order (parents before children)
    4. Adds load_post handler for automatic state hydration
    5. Initializes render presets and default values

    Called automatically by Blender when the addon is enabled.
    """
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
    register_alpha_props()
    register_ai_props()
    register_ai_render_props()
    register_camera_list_props()
    register_shot_list_props()
    register_render_shortcut_props()

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
        ensure_auto_bg_live_updates(scene=bpy.context.scene, force_update=False)
    except Exception:
        pass

    try:
        register_ai_render_handlers()
    except Exception:
        pass
    try:
        refresh_ai_render_state(bpy.context, force=True)
    except Exception:
        pass

    try:
        enable_dimension_live_updates()
    except Exception:
        pass

    try:
        ensure_preset_slots(bpy.context, ensure_scene=True)
        # Initialize UHD shortcut base resolution values
        try:
            wm_state = getattr(bpy.context.window_manager, 'lime_pipeline', None)
            if wm_state and not hasattr(wm_state, 'lime_shortcut_base_x'):
                wm_state.lime_shortcut_base_x = 1920
                wm_state.lime_shortcut_base_y = 1080
        except Exception:
            pass
    except Exception:
        pass

def unregister():
    """Unregister all Lime Pipeline classes, properties, and handlers.

    Performs cleanup in reverse order:
    1. Removes load_post handler
    2. Unregisters all classes in reverse registration order
    3. Cleans up all property groups

    Called automatically by Blender when the addon is disabled.
    """
    global REGISTERED_CLASSES
    disable_dimension_overlay_guard()
    try:
        disable_dimension_live_updates()
    except Exception:
        pass
    for cls in reversed(REGISTERED_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    REGISTERED_CLASSES = []
    from .ui import unregister_anim_params_props, unregister_noise_props
    unregister_anim_params_props()
    unregister_noise_props()
    unregister_alpha_props()
    unregister_ai_props()
    unregister_ai_render_props()
    unregister_camera_list_props()
    unregister_shot_list_props()
    unregister_render_shortcut_props()
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

    try:
        unregister_ai_render_handlers()
    except Exception:
        pass


@persistent
def _on_load_post(dummy):
    """Persistent handler called after loading a .blend file.

    Automatically hydrates the addon state from the current file path:
    1. Parses filename to extract project settings (type, revision, scene)
    2. Updates WindowManager properties to match the loaded file
    3. Initializes render preset slots if needed
    4. Sets up default UHD resolution values

    This ensures the UI reflects the current project state without manual setup.

    Args:
        dummy: Required by Blender handler signature but unused
    """
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
        # Initialize UHD shortcut base resolution values on file load
        try:
            wm_state = getattr(bpy.context.window_manager, 'lime_pipeline', None)
            if wm_state and not hasattr(wm_state, 'lime_shortcut_base_x'):
                wm_state.lime_shortcut_base_x = 1920
                wm_state.lime_shortcut_base_y = 1080
        except Exception:
            pass
    except Exception:
        pass

    try:
        ensure_auto_bg_live_updates(scene=bpy.context.scene)
    except Exception:
        pass

    try:
        refresh_ai_render_state(bpy.context, force=True)
    except Exception:
        pass

