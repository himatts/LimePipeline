"""Properties for the Scene Continuity lab feature."""

from __future__ import annotations

import bpy
from bpy.props import EnumProperty, PointerProperty
from bpy.types import PropertyGroup


class LimeSceneContinuityState(PropertyGroup):
    scene_continuity_frame_mode: EnumProperty(
        name="Handoff Frame",
        description="Frame to sample when creating the next scene file",
        items=(
            ("CURRENT", "Current Frame", "Use the current frame as handoff"),
            ("SCENE_END", "Scene End", "Use scene frame_end as handoff"),
        ),
        default="CURRENT",
    )

    def _shot_enum_items(self, context):
        try:
            from ...core import validate_scene as _vs
        except Exception:
            return [("NONE", "No SHOTs found", "", 0)]
        scene = getattr(context, "scene", None)
        if scene is None:
            return [("NONE", "No SHOTs found", "", 0)]
        try:
            items = [("NONE", "No SHOTs found", "", 0)]
            for idx, (coll, sh_idx) in enumerate(_vs.list_shot_roots(scene), 1):
                name = getattr(coll, "name", f"SHOT {sh_idx:02d}") or f"SHOT {sh_idx:02d}"
                items.append((name, name, "", idx))
            return items
        except Exception:
            return [("NONE", "No SHOTs found", "", 0)]

    scene_continuity_shot_name: EnumProperty(
        name="Continuity Shot",
        description="SHOT root (top-level) whose pose will seed the next scene",
        items=_shot_enum_items,
        default=0,
    )


def register() -> None:
    bpy.utils.register_class(LimeSceneContinuityState)
    bpy.types.WindowManager.lime_scene_continuity = PointerProperty(type=LimeSceneContinuityState)


def unregister() -> None:
    if hasattr(bpy.types.WindowManager, "lime_scene_continuity"):
        del bpy.types.WindowManager.lime_scene_continuity
    bpy.utils.unregister_class(LimeSceneContinuityState)


__all__ = [
    "LimeSceneContinuityState",
    "register",
    "unregister",
]
