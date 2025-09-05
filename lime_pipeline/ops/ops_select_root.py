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
        st.project_root = self.directory
        return {'FINISHED'}


