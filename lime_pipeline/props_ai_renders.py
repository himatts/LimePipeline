"""
AI Render Converter Properties

State storage for the AI render conversion workflow (source render, style reference,
prompt details, job status, and previews).
"""

from __future__ import annotations

from pathlib import Path
import bpy
from bpy.types import PropertyGroup, Image
from bpy.props import (
    BoolProperty,
    EnumProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)


def _load_image_from_path(path_str: str) -> Image | None:
    path = (path_str or "").strip()
    if not path:
        return None
    try:
        path_obj = Path(path)
        if not path_obj.exists():
            return None
        return bpy.data.images.load(path_obj.as_posix(), check_existing=True)
    except Exception:
        return None


_PREVIEW_PENDING: set[tuple[int, str]] = set()


def _schedule_preview(state, path_attr: str, image_attr: str, exists_attr: str | None = None) -> None:
    path_str = (getattr(state, path_attr, "") or "").strip()
    exists = False
    try:
        exists = bool(path_str and Path(path_str).exists())
    except Exception:
        exists = False
    if exists_attr:
        try:
            setattr(state, exists_attr, exists)
        except Exception:
            pass
    if not exists:
        try:
            setattr(state, image_attr, None)
        except Exception:
            pass
        return

    key = (id(state), image_attr)
    if key in _PREVIEW_PENDING:
        return
    _PREVIEW_PENDING.add(key)

    def _load():
        _PREVIEW_PENDING.discard(key)
        img = _load_image_from_path(path_str)
        if img is None:
            return None
        try:
            setattr(state, image_attr, img)
            if exists_attr:
                setattr(state, exists_attr, True)
        except Exception:
            pass
        return None

    bpy.app.timers.register(_load, first_interval=0.15)


def _update_style_path(self, context):
    _schedule_preview(self, "style_image_path", "style_image")


def _update_source_path(self, context):
    _schedule_preview(self, "source_image_path", "source_image", "source_exists")


def _update_result_path(self, context):
    _schedule_preview(self, "result_image_path", "result_image", "result_exists")


class LimeAIRenderState(PropertyGroup):
    mode: EnumProperty(
        name="Mode",
        items=[
            ("SKETCH", "Sketch / Storyboard", "Convert to storyboard sketch style"),
            ("SKETCH_PLUS", "Sketch + Details", "Convert and add imagined details"),
        ],
        default="SKETCH",
    )
    detail_text: StringProperty(
        name="Details to Add",
        description="Describe extra props, mood, or scene details to add",
        default="",
    )
    rewrite_with_llm: BoolProperty(
        name="Rewrite Details with LLM",
        description="Use OpenRouter to improve the details prompt",
        default=True,
    )
    detail_text_optimized: StringProperty(default="", options={"HIDDEN"})
    prompt_final: StringProperty(default="", options={"HIDDEN"})
    last_prompt: StringProperty(default="", options={"HIDDEN"})
    last_mode: StringProperty(default="", options={"HIDDEN"})
    last_detail_input: StringProperty(default="", options={"HIDDEN"})
    last_detail_optimized: StringProperty(default="", options={"HIDDEN"})
    last_source_path: StringProperty(default="", options={"HIDDEN"})
    last_style_path: StringProperty(default="", options={"HIDDEN"})
    last_result_path: StringProperty(default="", options={"HIDDEN"})

    source_image_path: StringProperty(
        name="Source Render",
        subtype="FILE_PATH",
        default="",
        update=_update_source_path,
    )
    source_image: PointerProperty(type=Image)
    source_exists: BoolProperty(default=False, options={"HIDDEN"})

    style_image_path: StringProperty(
        name="Style Reference",
        subtype="FILE_PATH",
        default="",
        update=_update_style_path,
    )
    style_image: PointerProperty(type=Image)

    result_image_path: StringProperty(
        name="AI Result",
        subtype="FILE_PATH",
        default="",
        update=_update_result_path,
    )
    result_image: PointerProperty(type=Image)
    result_exists: BoolProperty(default=False, options={"HIDDEN"})

    job_id: StringProperty(default="", options={"HIDDEN"})
    job_status: EnumProperty(
        name="Job Status",
        items=[
            ("IDLE", "Idle", "No job running"),
            ("UPLOADING", "Uploading", "Uploading assets"),
            ("QUEUED", "Queued", "Job queued"),
            ("PROCESSING", "Processing", "Job running"),
            ("COMPLETED", "Completed", "Job completed"),
            ("FAILED", "Failed", "Job failed"),
            ("CANCELLED", "Cancelled", "Job cancelled"),
        ],
        default="IDLE",
    )
    job_message: StringProperty(default="", options={"HIDDEN"})
    last_error: StringProperty(default="", options={"HIDDEN"})
    is_busy: BoolProperty(default=False, options={"HIDDEN"})
    cancel_requested: BoolProperty(default=False, options={"HIDDEN"})

    retry_strategy: EnumProperty(
        name="Retry Strategy",
        items=[
            ("OVERWRITE", "Overwrite", "Replace the previous output"),
            ("VERSION", "Version", "Write a new versioned file"),
        ],
        default="VERSION",
    )

    cached_frame: IntProperty(name="Cached Frame", default=-1, options={"HIDDEN"})
    auto_refresh_source: BoolProperty(
        name="Auto Refresh Source",
        description="Auto-detect the source render for the current frame",
        default=True,
    )


def register():
    bpy.utils.register_class(LimeAIRenderState)
    bpy.types.Scene.lime_ai_render = PointerProperty(type=LimeAIRenderState)


def unregister():
    del bpy.types.Scene.lime_ai_render
    bpy.utils.unregister_class(LimeAIRenderState)
