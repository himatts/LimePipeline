"""Scene Continuity lab package.

This feature is intentionally excluded from the active addon registration.
Import and register it manually for lab use.
"""

from __future__ import annotations

import bpy

from .ops import LIME_OT_stage_create_next_scene_file
from .props import register as register_props
from .props import unregister as unregister_props
from .ui import LIME_TB_PT_scene_continuity_lab

CLASSES = (
    LIME_OT_stage_create_next_scene_file,
    LIME_TB_PT_scene_continuity_lab,
)


def register() -> None:
    register_props()
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    unregister_props()


__all__ = [
    "CLASSES",
    "LIME_OT_stage_create_next_scene_file",
    "LIME_TB_PT_scene_continuity_lab",
    "register",
    "unregister",
]
