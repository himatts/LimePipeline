"""AI Render Converter lab package.

This feature is intentionally excluded from the active addon registration.
Import and register it manually for lab use.
"""

from __future__ import annotations

import bpy

from .ops import (
    LIME_OT_ai_render_add_to_sequencer,
    LIME_OT_ai_render_cancel,
    LIME_OT_ai_render_delete_batch,
    LIME_OT_ai_render_delete_selected,
    LIME_OT_ai_render_frame,
    LIME_OT_ai_render_generate,
    LIME_OT_ai_render_import_style,
    LIME_OT_ai_render_open_outputs_folder,
    LIME_OT_ai_render_open_preview,
    LIME_OT_ai_render_refresh,
    LIME_OT_ai_render_retry,
    LIME_OT_ai_render_test_connection,
    refresh_ai_render_assets,
    refresh_ai_render_state,
    register_ai_render_handlers,
    unregister_ai_render_handlers,
)
from .props import register as register_props
from .props import unregister as unregister_props
from .ui import LIME_PT_ai_render_converter

CLASSES = (
    LIME_OT_ai_render_refresh,
    LIME_OT_ai_render_frame,
    LIME_OT_ai_render_generate,
    LIME_OT_ai_render_retry,
    LIME_OT_ai_render_cancel,
    LIME_OT_ai_render_test_connection,
    LIME_OT_ai_render_add_to_sequencer,
    LIME_OT_ai_render_open_outputs_folder,
    LIME_OT_ai_render_delete_selected,
    LIME_OT_ai_render_delete_batch,
    LIME_OT_ai_render_open_preview,
    LIME_OT_ai_render_import_style,
    LIME_PT_ai_render_converter,
)


def register() -> None:
    register_props()
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    register_ai_render_handlers()
    try:
        refresh_ai_render_state(bpy.context, force=True)
        refresh_ai_render_assets(bpy.context, force=True)
    except Exception:
        pass


def unregister() -> None:
    try:
        unregister_ai_render_handlers()
    except Exception:
        pass
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    unregister_props()


__all__ = [
    "CLASSES",
    "LIME_PT_ai_render_converter",
    "refresh_ai_render_assets",
    "refresh_ai_render_state",
    "register",
    "unregister",
]
