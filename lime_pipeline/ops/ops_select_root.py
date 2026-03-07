"""
Project Root Selection Operators

This module provides functionality for selecting and setting the project root directory
within the Lime Pipeline workflow. It handles folder picker dialogs and automatic
detection of project root directories based on naming conventions.

The root selection system integrates with Lime Pipeline preferences and provides
intelligent project root detection by walking up directory trees to find matching
project folder structures.

Key Features:
- Interactive folder picker for project root selection
- Automatic project root detection using naming conventions
- Integration with Lime Pipeline preferences and settings
- Validation of selected directory paths
- Error handling for invalid or inaccessible paths
- Support for development and production project structures
"""

import bpy
from bpy.types import Operator
from bpy.props import StringProperty


class LIME_OT_pick_root(Operator):
    bl_idname = "lime.pick_root"
    bl_label = "Pick Project Root"
    bl_options = {'INTERNAL'}
    bl_description = "Open a folder picker to set the Project Root"

    directory: StringProperty(subtype='DIR_PATH')

    def invoke(self, context, event):
        prefs = context.preferences.addons[__package__.split('.')[0]].preferences
        self.directory = prefs.dev_test_root or prefs.default_projects_root
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        st = context.window_manager.lime_pipeline
        # Auto-detect the actual project root (walk up to matching folder)
        try:
            from ..core.naming import find_project_root
            detected = find_project_root(self.directory)
            st.project_root = str(detected) if detected is not None else self.directory
        except Exception:
            st.project_root = self.directory
        return {'FINISHED'}


class LIME_OT_reload_current_project_data(Operator):
    bl_idname = "lime.reload_current_project_data"
    bl_label = "Reload Current Data"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Reload project data from the saved blend filepath"

    def execute(self, context):
        filepath = getattr(bpy.data, "filepath", "") or ""
        if not filepath:
            self.report({'ERROR'}, "Save the .blend file first to reload data from its path.")
            return {'CANCELLED'}

        st = context.window_manager.lime_pipeline
        try:
            from ..core.naming import hydrate_state_from_filepath

            hydrate_state_from_filepath(st, force=True)
        except Exception as ex:
            self.report({'ERROR'}, f"Failed to reload project data: {ex}")
            return {'CANCELLED'}

        if not getattr(st, "project_root", ""):
            self.report({'ERROR'}, "Could not infer project data from the current filepath.")
            return {'CANCELLED'}

        self.report({'INFO'}, "Project data reloaded from the current blend path.")
        return {'FINISHED'}


class LIME_OT_clear_project_data(Operator):
    bl_idname = "lime.clear_project_data"
    bl_label = "Clear Project Data"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Clear project fields so they can be entered or reloaded again"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        st = context.window_manager.lime_pipeline
        st.use_local_project = False
        st.project_root = ""
        st.shared_root_snapshot = ""
        st.local_project_name = ""
        st.project_type = 'REND'
        st.rev_letter = 'A'
        try:
            st.rev_index = 1
        except Exception:
            pass
        st.sc_number = 10
        st.use_custom_name = False
        st.custom_name = ""
        st.preview_name = ""
        st.preview_path = ""
        self.report({'INFO'}, "Project data cleared.")
        return {'FINISHED'}


