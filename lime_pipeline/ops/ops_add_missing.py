"""
Add Missing Collections Operator

This module provides functionality to add missing collections to maintain proper
scene organization according to Lime Pipeline conventions. It ensures that the
canonical SHOT tree structure exists for the current shot context.

The operator validates that there's an active SHOT context before proceeding,
resolves the project name, and ensures the shot tree exists by adding only
the missing collections rather than recreating the entire structure.

Key Features:
- Validates active SHOT context before execution
- Resolves project name from pipeline settings
- Adds only missing collections to avoid duplication
- Integrates with Lime Pipeline naming conventions
- Provides proper error reporting for invalid contexts
"""

import bpy
from bpy.types import Operator

from ..core import validate_scene
from ..core.naming import resolve_project_name
from ..scene.scene_utils import ensure_shot_tree


class LIME_OT_add_missing_collections(Operator):
    bl_idname = "lime.add_missing_collections"
    bl_label = "Add Missing Collections"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        return validate_scene.active_shot_context(ctx) is not None

    def execute(self, context):
        shot = validate_scene.active_shot_context(context)
        if shot is None:
            self.report({'ERROR'}, "No active SHOT context")
            return {'CANCELLED'}
        # Resolve project name and ensure the canonical tree exists (adds only missing ones)
        try:
            st = context.window_manager.lime_pipeline
            project_name = resolve_project_name(st)
        except Exception:
            project_name = "Project"
        try:
            ensure_shot_tree(shot, project_name)
        except Exception as ex:
            self.report({'ERROR'}, f"Failed ensuring collections: {ex}")
            return {'CANCELLED'}
        self.report({'INFO'}, "Missing collections added (if any)")
        return {'FINISHED'}


__all__ = [
    "LIME_OT_add_missing_collections",
]

