"""
Addon Preferences and Configuration

This module defines the Lime Pipeline addon preferences interface and configuration
options. It provides user-configurable settings for project paths, validation rules,
and feature toggles that customize the addon behavior for different studio environments.

The preferences system integrates with Blender's addon preferences framework and
provides persistent storage for user settings across Blender sessions. Settings
include project root paths, validation thresholds, feature toggles, and API
configurations for external services.

Key Features:
- Project root path configuration for production and development environments
- Validation thresholds for path length warnings and errors
- Scene numbering step configuration for consistent numbering
- Feature toggles for optional functionality (dimension utilities, auto-normalization)
- API configuration for external services (OpenRouter for AI features)
- Render preset storage and management
- Integration with Blender's native preferences system
"""

from pathlib import Path

import bpy
from bpy.types import AddonPreferences
from bpy.props import StringProperty, IntProperty, BoolProperty, CollectionProperty

from .props import LimeRenderPresetSlot


ADDON_PKG = __package__
DEFAULT_DESKTOP = str((Path.home() / "Desktop").resolve())


class LimePipelinePrefs(AddonPreferences):
    bl_idname = ADDON_PKG

    default_projects_root: StringProperty(
        name="Default Projects Root",
        subtype='DIR_PATH',
        default=r"G:\\Unidades compartidas\\2. EX-Projects",
        description="Production projects root used in the studio",
    )
    dev_test_root: StringProperty(
        name="Dev/Test Root",
        subtype='DIR_PATH',
        default=r"D:\\Lime Testing",
        description="Local path used as initial directory for folder picker",
    )
    local_projects_root: StringProperty(
        name="Local Projects Root",
        subtype='DIR_PATH',
        default=DEFAULT_DESKTOP,
        description="Base directory used when working in Local Project mode (defaults to Desktop)",
    )
    scene_step: IntProperty(
        name="Scene Step",
        default=10,
        min=1,
        max=100,
        description="Step used when suggesting scene numbers (multiples)",
    )
    path_warn_len: IntProperty(name="Warn at length", default=200, min=50, max=400, description="Show a warning when target path exceeds this length")
    path_block_len: IntProperty(name="Block at length", default=240, min=60, max=400, description="Block saving when target path exceeds this length")
    remember_last_rev: BoolProperty(name="Remember last Rev", default=True, description="Remember last used revision letter across sessions")
    libraries_override_dir: StringProperty(
        name="Libraries Override",
        subtype='DIR_PATH',
        default="",
        description=(
            "Optional: override path for Lime library .blend files. "
            "If set, 'lime_pipeline_lib.blend' is read from here"
        ),
    )
    enable_dimension_utilities: BoolProperty(
        name="Enable Dimension Utilities",
        description="Toggle the Dimension Utilities panel (Dimension Checker and measurement presets).",
        default=True,
    )
    auto_normalize_materials_after_duplicate: BoolProperty(
        name="Auto-Normalize Materials After Duplicate",
        description="Automatically scan and rename materials after duplicating a scene.",
        default=False,
    )
    # --- AI Material Renamer (OpenRouter) ---
    openrouter_api_key: StringProperty(
        name="OpenRouter API Key",
        subtype='PASSWORD',
        default="",
        description="API key for OpenRouter (used by AI Material Renamer)",
    )
    openrouter_model: StringProperty(
        name="OpenRouter Model",
        default="google/gemini-2.5-flash-lite-preview-09-2025",
        description="Default model slug for AI Material Renamer",
    )
    http_referer: StringProperty(
        name="HTTP-Referer (optional)",
        default="",
        description="Optional HTTP-Referer header for OpenRouter attribution",
    )
    x_title: StringProperty(
        name="X-Title (optional)",
        default="",
        description="Optional X-Title header for OpenRouter attribution",
    )
    global_render_presets: CollectionProperty(type=LimeRenderPresetSlot, options={'HIDDEN'})
    defaults_render_presets: CollectionProperty(type=LimeRenderPresetSlot, options={'HIDDEN'})


    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "default_projects_root")
        col.prop(self, "dev_test_root")
        col.prop(self, "local_projects_root")
        col.separator()
        col.prop(self, "scene_step")
        col.prop(self, "path_warn_len")
        col.prop(self, "path_block_len")
        col.prop(self, "remember_last_rev")
        col.prop(self, "enable_dimension_utilities")
        col.prop(self, "auto_normalize_materials_after_duplicate")
        col.separator()
        col.prop(self, "libraries_override_dir")
        col.separator()
        box = col.box()
        box.label(text="AI Material Renamer (OpenRouter)")
        box.prop(self, "openrouter_api_key")
        box.prop(self, "openrouter_model")
        row = box.row()
        row.prop(self, "http_referer")
        row.prop(self, "x_title")
        box.separator()
        box.operator("lime_tb.ai_test_connection", text="Test Connection")


