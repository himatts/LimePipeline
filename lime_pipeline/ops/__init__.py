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
from .ops_ai_asset_organizer import (
    LIME_TB_OT_ai_asset_suggest_names,
    LIME_TB_OT_ai_asset_apply_names,
    LIME_TB_OT_ai_asset_clear,
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

__all__ = [
    "LIME_OT_new_shot",
    "LIME_OT_duplicate_shot",
    "LIME_OT_render_shots_from_markers",
    "LIME_OT_duplicate_scene_sequential",
    "LIME_OT_stage_create_next_scene_file",
    "LIME_OT_create_view_layers",
    "LIME_OT_setup_view_layer_outputs",
    "LIME_TB_OT_ai_asset_suggest_names",
    "LIME_TB_OT_ai_asset_apply_names",
    "LIME_TB_OT_ai_asset_clear",
    "LIME_OT_texture_scan_report",
    "LIME_OT_texture_adopt",
    "LIME_OT_texture_manifest_cleanup",
]


