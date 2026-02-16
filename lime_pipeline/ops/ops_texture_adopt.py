"""Legacy wrapper for texture adopt operator.

The old `lime.texture_adopt` operator now redirects to
`lime.texture_apply` in AI Textures Organizer.
"""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty
from bpy.types import Operator


class LIME_OT_texture_adopt(Operator):
    bl_idname = "lime.texture_adopt"
    bl_label = "Apply Texture Plan (Legacy Alias)"
    bl_description = "Legacy alias: redirects to Apply Texture Plan in AI Textures Organizer"
    bl_options = {"REGISTER", "UNDO"}

    use_ai: BoolProperty(
        name="Use AI naming",
        description="Legacy option kept for compatibility; AI naming is now part of staged workflow",
        default=True,
        options={"HIDDEN"},
    )
    include_ai_preview: BoolProperty(
        name="AI include preview (low-res)",
        description="Legacy option kept for compatibility",
        default=False,
        options={"HIDDEN"},
    )

    def execute(self, context):
        state = getattr(getattr(context, "scene", None), "lime_ai_textures", None)
        if state is None:
            self.report({"ERROR"}, "AI Textures state is unavailable")
            return {"CANCELLED"}
        if bool(getattr(state, "ai_blocked", False)):
            self.report({"ERROR"}, "AI is blocked. Run Analyze again after fixing connectivity.")
            return {"CANCELLED"}
        if not any(
            bool(getattr(item, "selected_for_apply", False))
            and (getattr(item, "status", "") or "").upper() == "READY"
            and not bool(getattr(item, "read_only", False))
            for item in list(getattr(state, "items", None) or [])
        ):
            self.report({"ERROR"}, "No selected READY texture items in the current plan")
            return {"CANCELLED"}
        if bool(self.include_ai_preview):
            try:
                state.ai_include_preview = True
            except Exception:
                pass
        result = bpy.ops.lime.texture_apply("INVOKE_DEFAULT")
        if "CANCELLED" in result:
            self.report({"ERROR"}, "Texture apply did not start")
            return {"CANCELLED"}
        self.report({"INFO"}, "Redirected to Apply Texture Plan")
        return result


__all__ = [
    "LIME_OT_texture_adopt",
]

