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
            self.report({'INFO'}, f"El Workspace '{TARGET_WORKSPACE_NAME}' ya existe; activado.")
            return {'FINISHED'}

        # Resolve library path
        lib_path = self._library_path(context)
        if lib_path is None or not lib_path.exists():
            self.report({'ERROR'}, f"No se encontró la librería: {lib_path}")
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
            self.report({'ERROR'}, f"Error al importar Workspace: {ex}")
            return {'CANCELLED'}

        # Verify and activate
        ws = bpy.data.workspaces.get(TARGET_WORKSPACE_NAME)
        if ws is None:
            self.report({'ERROR'}, "El Workspace no se encontró tras importar.")
            return {'CANCELLED'}

        try:
            context.window.workspace = ws
        except Exception:
            pass

        self.report({'INFO'}, f"Importado el Workspace '{TARGET_WORKSPACE_NAME}'.")
        return {'FINISHED'}


__all__ = [
    "LIME_OT_import_layout",
]

