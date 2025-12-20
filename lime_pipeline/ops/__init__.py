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

__all__ = [
    "LIME_OT_new_shot",
    "LIME_OT_duplicate_shot",
    "LIME_OT_render_shots_from_markers",
    "LIME_OT_duplicate_scene_sequential",
    "LIME_OT_stage_create_next_scene_file",
    "LIME_OT_create_view_layers",
    "LIME_OT_setup_view_layer_outputs",
]


