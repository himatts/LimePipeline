import bpy
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty


class LIME_OT_show_text(Operator):
    bl_idname = "lime.show_text"
    bl_label = "Info"
    bl_options = {'INTERNAL'}
    bl_description = "Show full text as tooltip; click to copy to clipboard"

    text: StringProperty(name="Text", default="")
    copy_on_click: BoolProperty(name="Copy on click", default=True)

    @classmethod
    def description(cls, context, properties):
        t = getattr(properties, "text", "")
        return t or "Info"

    def execute(self, context):
        if self.copy_on_click and self.text:
            context.window_manager.clipboard = self.text
            self.report({'INFO'}, "Copied to clipboard")
        return {'CANCELLED'}


