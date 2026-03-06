"""Animation Parameters lab package.

This feature is intentionally excluded from the active addon registration.
Import and register it manually for lab use.
"""

from __future__ import annotations

import bpy

from .ops import LIME_TB_OT_apply_keyframe_style
from .ui import (
    LIME_TB_PT_animation_params,
    register_anim_params_props,
    unregister_anim_params_props,
)

CLASSES = (
    LIME_TB_OT_apply_keyframe_style,
    LIME_TB_PT_animation_params,
)


def register() -> None:
    register_anim_params_props()
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    unregister_anim_params_props()


__all__ = [
    "CLASSES",
    "LIME_TB_OT_apply_keyframe_style",
    "LIME_TB_PT_animation_params",
    "register",
    "unregister",
]
