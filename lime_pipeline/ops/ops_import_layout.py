"""
Layout Import Operators

This module provides functionality for importing layout assets and workspaces from
Lime Pipeline libraries. It handles the import of pre-configured layouts and workspace
setups that accelerate project setup and maintain consistency.

The import system supports configurable library paths, workspace creation, and
integration with Lime Pipeline project structures for rapid scene setup.

Key Features:
- Import of pre-configured layout workspaces from libraries
- Configurable library paths with user preference overrides
- Automatic workspace creation and configuration
- Integration with Lime Pipeline project structure conventions
- Error handling for missing libraries and import failures
- Support for multiple layout configurations
"""

from __future__ import annotations

from pathlib import Path
import bpy
from bpy.types import Operator

from ..prefs import ADDON_PKG


TARGET_WORKSPACE_NAME = "Layout Lime 1"


class LIME_OT_import_layout(Operator):
    bl_idname = "lime.import_layout"
    bl_label = "Import Layout"
    bl_options = {"REGISTER", "UNDO"}

    def _library_path(self, context) -> Path | None:
        # Prefer user override in Add-on Preferences
        addon = bpy.context.preferences.addons.get(ADDON_PKG)
        if addon is not None:
            prefs = addon.preferences
            override_dir = getattr(prefs, "libraries_override_dir", "") or ""
            if override_dir:
                return Path(override_dir) / "lime_pipeline_lib.blend"

        # Fallback to packaged data path: lime_pipeline/data/libraries/lime_pipeline_lib.blend
        base = Path(__file__).resolve().parents[1]
        return base / "data" / "libraries" / "lime_pipeline_lib.blend"

    def execute(self, context):
        # If the workspace already exists, just activate and inform
        existing_ws = bpy.data.workspaces.get(TARGET_WORKSPACE_NAME)
        if existing_ws is not None:
            try:
                context.window.workspace = existing_ws
            except Exception:
                pass
            self.report({'INFO'}, f"Workspace '{TARGET_WORKSPACE_NAME}' already exists; activated.")
            return {'FINISHED'}

        # Resolve library path
        lib_path = self._library_path(context)
        if lib_path is None or not lib_path.exists():
            self.report({'ERROR'}, f"Library not found: {lib_path}")
            return {'CANCELLED'}

        # Append the workspace from the .blend
        directory = lib_path.as_posix() + "/WorkSpace/"  # Blender expects .../file.blend/WorkSpace/
        try:
            bpy.ops.wm.append(
                directory=directory,
                filename=TARGET_WORKSPACE_NAME,
                link=False,
            )
        except Exception as ex:
            self.report({'ERROR'}, f"Error importing Workspace: {ex}")
            return {'CANCELLED'}

        # Verify and activate
        ws = bpy.data.workspaces.get(TARGET_WORKSPACE_NAME)
        if ws is None:
            self.report({'ERROR'}, "Workspace not found after import.")
            return {'CANCELLED'}

        try:
            context.window.workspace = ws
        except Exception:
            pass

        self.report({'INFO'}, f"Imported Workspace '{TARGET_WORKSPACE_NAME}'.")
        return {'FINISHED'}


__all__ = [
    "LIME_OT_import_layout",
]

