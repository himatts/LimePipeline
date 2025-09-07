import os
import sys
import subprocess
from pathlib import Path

import bpy
from bpy.types import Operator
from bpy.props import StringProperty

from ..core.paths import paths_for_type
from ..core.naming import hydrate_state_from_filepath


class LIME_OT_ensure_folders(Operator):
    bl_idname = "lime.ensure_folders"
    bl_label = "Create critical folders"
    bl_description = "Create RAMV critical directories under the selected Project Root"

    def execute(self, context):
        st = context.window_manager.lime_pipeline
        if not st.project_root:
            try:
                hydrate_state_from_filepath(st)
            except Exception:
                pass
        if not st.project_root:
            self.report({'ERROR'}, "Set Project Root first")
            return {'CANCELLED'}
        root = Path(st.project_root)
        ramv = root / r"2. Graphic & Media" / r"3. Rendering-Animation-Video"
        ramv.mkdir(parents=True, exist_ok=True)
        self.report({'INFO'}, f"Ensured: {ramv}")
        return {'FINISHED'}


class LIME_OT_open_folder(Operator):
    bl_idname = "lime.open_folder"
    bl_label = "Open folder"
    bl_description = "Open the target directory where the .blend will be saved"

    def execute(self, context):
        st = context.window_manager.lime_pipeline
        if not st.project_root:
            try:
                hydrate_state_from_filepath(st)
            except Exception:
                pass
        if not st.project_root:
            self.report({'ERROR'}, "Set Project Root first")
            return {'CANCELLED'}
        rev = (st.rev_letter or '').strip().upper()
        try:
            _, folder_type, scenes, target_dir, backups = paths_for_type(Path(st.project_root), st.project_type, rev, st.sc_number)
        except Exception as ex:
            self.report({'ERROR'}, f"Invalid state: {ex}")
            return {'CANCELLED'}

        to_open = str(target_dir if target_dir else folder_type)
        try:
            if os.name == "nt":
                os.startfile(to_open)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.call(["open", to_open])
            else:
                subprocess.call(["xdg-open", to_open])
        except Exception as ex:
            self.report({'ERROR'}, f"Failed to open folder: {ex}")
            return {'CANCELLED'}
        return {'FINISHED'}


class LIME_OT_open_output_folder(Operator):
    bl_idname = "lime.open_output_folder"
    bl_label = "Open output folder"
    bl_description = "Open the 'editables' output directory for the given project type"

    ptype: StringProperty(name="Project Type", description="Override project type (e.g., PV, REND)", default="")

    def execute(self, context):
        st = context.window_manager.lime_pipeline
        if not st.project_root:
            try:
                hydrate_state_from_filepath(st)
            except Exception:
                pass
        if not st.project_root:
            self.report({'ERROR'}, "Set Project Root first")
            return {'CANCELLED'}
        root = Path(st.project_root)
        rev = (st.rev_letter or '').strip().upper()
        sc = getattr(st, 'sc_number', None)
        ptype = (self.ptype or '').strip().upper() or (st.project_type or '').strip().upper()
        try:
            _, folder_type, _scenes, _target_dir, _backups = paths_for_type(root, ptype, rev, sc)
        except Exception as ex:
            self.report({'ERROR'}, f"Invalid state: {ex}")
            return {'CANCELLED'}

        editables = folder_type / "editables"
        if not editables.exists():
            self.report({'ERROR'}, f"Folder does not exist: {editables}")
            return {'CANCELLED'}

        to_open = str(editables)
        try:
            if os.name == "nt":
                os.startfile(to_open)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.call(["open", to_open])
            else:
                subprocess.call(["xdg-open", to_open])
        except Exception as ex:
            self.report({'ERROR'}, f"Failed to open folder: {ex}")
            return {'CANCELLED'}
        return {'FINISHED'}


