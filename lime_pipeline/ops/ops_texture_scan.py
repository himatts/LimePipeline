"""Legacy wrapper for texture scan operator.

The old `lime.texture_scan_report` operator now redirects to
`lime.texture_analyze` in AI Textures Organizer.
"""

from __future__ import annotations

import bpy
from bpy.types import Operator


class LIME_OT_texture_scan_report(Operator):
    bl_idname = "lime.texture_scan_report"
    bl_label = "Analyze Textures (Legacy Alias)"
    bl_description = "Legacy alias: redirects to Analyze Textures in AI Textures Organizer"
    bl_options = {"REGISTER"}

    def execute(self, context):
        result = bpy.ops.lime.texture_analyze("INVOKE_DEFAULT")
        if "CANCELLED" in result:
            self.report({"ERROR"}, "Texture analyze did not start")
            return {"CANCELLED"}
        self.report({"INFO"}, "Redirected to Analyze Textures")
        return result


__all__ = [
    "LIME_OT_texture_scan_report",
]

