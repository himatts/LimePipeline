"""
Lime Pipeline Operators Package

This package contains all the operator classes for the Lime Pipeline addon.
Operators are organized by functionality and provide the main user-facing
actions available in the Lime Pipeline interface.

The operators handle various aspects of pipeline management including:
- Animation parameters and keyframe styling
- Scene organization and collection management
- Camera operations and rig management
- Material and alpha management
- Backup and file operations
- Rendering and dimension utilities

Each operator follows Blender's operator conventions with proper bl_idname,
bl_label, and poll/execute methods for integration with Blender's UI system.
"""

# Operators package for Lime Pipeline

from .ops_shots import (
    LIME_OT_new_shot,
    LIME_OT_duplicate_shot,
    LIME_OT_render_shots_from_markers,
)
from .ops_duplicate_scene import (
    LIME_OT_duplicate_scene_sequential,
)
from .ops_scene_continuity import (
    LIME_OT_stage_create_next_scene_file,
)
from .ops_view_layers import (
    LIME_OT_create_view_layers,
)
from .ops_comp_view_layer_outputs import (
    LIME_OT_setup_view_layer_outputs,
)
from .ops_linked_collections import (
    LIME_OT_localize_linked_collection,
    LIME_OT_resync_object_materials_from_data,
)
from .ai_asset_organizer import (
    LIME_TB_OT_ai_asset_test_connection,
    LIME_TB_OT_ai_asset_suggest_names,
    LIME_TB_OT_ai_asset_apply_names,
    LIME_TB_OT_ai_asset_scope_preset,
    LIME_TB_OT_ai_asset_refresh_targets,
    LIME_TB_OT_ai_asset_resolve_target,
    LIME_TB_OT_ai_asset_set_target_for_item,
    LIME_TB_OT_ai_asset_set_target_for_selected,
    LIME_TB_OT_ai_asset_clear,
    LIME_TB_OT_open_ai_asset_manager,
    LIME_TB_OT_ai_asset_material_debug_report,
    LIME_TB_OT_ai_asset_collection_debug_report,
)
from .ops_texture_scan import (
    LIME_OT_texture_scan_report,
)
from .ops_texture_adopt import (
    LIME_OT_texture_adopt,
)
from .ops_texture_manifest_cleanup import (
    LIME_OT_texture_manifest_cleanup,
)
from .ops_cameras import (
    LIME_OT_duplicate_active_camera,
    LIME_OT_rename_shot_cameras,
    LIME_OT_move_camera_list_item,
    LIME_OT_sync_camera_list,
)
from .ops_ai_textures_organizer import (
    LIME_OT_texture_analyze,
    LIME_OT_texture_refine,
    LIME_OT_texture_apply,
    LIME_OT_texture_clear_session,
)

__all__ = [
    "LIME_OT_new_shot",
    "LIME_OT_duplicate_shot",
    "LIME_OT_render_shots_from_markers",
    "LIME_OT_duplicate_scene_sequential",
    "LIME_OT_stage_create_next_scene_file",
    "LIME_OT_create_view_layers",
    "LIME_OT_setup_view_layer_outputs",
    "LIME_OT_localize_linked_collection",
    "LIME_OT_resync_object_materials_from_data",
    "LIME_TB_OT_ai_asset_test_connection",
    "LIME_TB_OT_ai_asset_suggest_names",
    "LIME_TB_OT_ai_asset_apply_names",
    "LIME_TB_OT_ai_asset_scope_preset",
    "LIME_TB_OT_ai_asset_refresh_targets",
    "LIME_TB_OT_ai_asset_resolve_target",
    "LIME_TB_OT_ai_asset_set_target_for_item",
    "LIME_TB_OT_ai_asset_set_target_for_selected",
    "LIME_TB_OT_ai_asset_clear",
    "LIME_TB_OT_open_ai_asset_manager",
    "LIME_TB_OT_ai_asset_material_debug_report",
    "LIME_TB_OT_ai_asset_collection_debug_report",
    "LIME_OT_texture_scan_report",
    "LIME_OT_texture_adopt",
    "LIME_OT_texture_manifest_cleanup",
    "LIME_OT_duplicate_active_camera",
    "LIME_OT_rename_shot_cameras",
    "LIME_OT_move_camera_list_item",
    "LIME_OT_sync_camera_list",
    "LIME_OT_texture_analyze",
    "LIME_OT_texture_refine",
    "LIME_OT_texture_apply",
    "LIME_OT_texture_clear_session",
]



