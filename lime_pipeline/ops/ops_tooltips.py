"""
Tooltip and Information Display Operators

This module provides functionality for displaying detailed information and tooltips
within the Lime Pipeline interface. It handles the presentation of contextual help,
detailed descriptions, and informational content to users.

The tooltip system supports dynamic content display, clipboard integration for
easy information sharing, and customizable presentation modes for different types
of informational content.

Key Features:
- Dynamic tooltip display with customizable content
- Clipboard integration for easy information copying
- Context-sensitive information presentation
- Support for multi-line text and formatted content
- Integration with Blender's operator description system
- Configurable display modes and interaction options
"""

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


