"""
AI Render Converter Properties

State storage for the AI render conversion workflow (source render, style reference,
prompt details, job status, and previews).
"""

from __future__ import annotations

from pathlib import Path
import json
import re
import bpy
from bpy.types import PropertyGroup, Image
from bpy.props import (
    BoolProperty,
    EnumProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
    FloatProperty,
)
import bpy.utils.previews


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
_ASSET_PREVIEWS = None
_FRAME_RE = re.compile(r"_F(\d{1,6})_", re.IGNORECASE)


def _ensure_asset_previews():
    global _ASSET_PREVIEWS
    if _ASSET_PREVIEWS is None:
        _ASSET_PREVIEWS = bpy.utils.previews.new()
    return _ASSET_PREVIEWS


def _clear_asset_previews() -> None:
    global _ASSET_PREVIEWS
    if _ASSET_PREVIEWS is None:
        return
    try:
        bpy.utils.previews.remove(_ASSET_PREVIEWS)
    except Exception:
        pass
    _ASSET_PREVIEWS = None


def _asset_preview_icon_id(key: str) -> int:
    pcoll = _ensure_asset_previews()
    if key in pcoll:
        try:
            return int(pcoll[key].icon_id)
        except Exception:
            return 0
    return 0


def _cached_entries(json_blob: str) -> list[dict[str, str]]:
    if not json_blob:
        return []
    try:
        data = json.loads(json_blob)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        path = (item.get("path") or "").strip()
        name = (item.get("name") or "").strip()
        if not path or not name:
            continue
        out.append({"path": path, "name": name})
    return out


def _path_in_cache(json_blob: str, path: str) -> bool:
    target = (path or "").strip()
    if not target:
        return False
    for item in _cached_entries(json_blob):
        if item.get("path") == target:
            return True
    return False


def _enum_items_from_cache(json_blob: str) -> list[tuple]:
    items = []
    for idx, item in enumerate(_cached_entries(json_blob)):
        key = item["path"]
        name = item["name"]
        icon_id = _asset_preview_icon_id(key)
        items.append((key, name, key, icon_id, idx))
    return items


def _items_source_assets(self, context):
    return _enum_items_from_cache(getattr(self, "source_assets_json", ""))


def _items_style_assets(self, context):
    return _enum_items_from_cache(getattr(self, "style_assets_json", ""))


def _items_result_assets(self, context):
    return _enum_items_from_cache(getattr(self, "result_assets_json", ""))


def _frame_from_path(path_str: str) -> int | None:
    try:
        name = Path(path_str).stem
    except Exception:
        name = ""
    match = _FRAME_RE.search(name)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


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
    if getattr(self, "assets_refreshing", False):
        return
    if _path_in_cache(getattr(self, "style_assets_json", ""), self.style_image_path):
        if self.style_pick != self.style_image_path:
            self.assets_refreshing = True
            try:
                self.style_pick = self.style_image_path
            finally:
                self.assets_refreshing = False


def _update_source_path(self, context):
    _schedule_preview(self, "source_image_path", "source_image", "source_exists")
    if not (getattr(self, "source_image_path", "") or "").strip():
        if getattr(self, "assets_refreshing", False):
            return
        if self.source_pick:
            self.assets_refreshing = True
            try:
                self.source_pick = ""
            finally:
                self.assets_refreshing = False
        return
    if getattr(self, "assets_refreshing", False):
        return
    if _path_in_cache(getattr(self, "source_assets_json", ""), self.source_image_path):
        if self.source_pick != self.source_image_path:
            self.assets_refreshing = True
            try:
                self.source_pick = self.source_image_path
            finally:
                self.assets_refreshing = False


def _update_result_path(self, context):
    _schedule_preview(self, "result_image_path", "result_image", "result_exists")
    if getattr(self, "assets_refreshing", False):
        return
    if _path_in_cache(getattr(self, "result_assets_json", ""), self.result_image_path):
        if self.result_pick != self.result_image_path:
            self.assets_refreshing = True
            try:
                self.result_pick = self.result_image_path
            finally:
                self.assets_refreshing = False


def _update_source_pick(self, context):
    if getattr(self, "assets_refreshing", False):
        return
    path = (self.source_pick or "").strip()
    if not path:
        return
    if self.source_image_path != path:
        self.source_image_path = path
    frame = _frame_from_path(path)
    if frame is not None and context and getattr(context, "scene", None):
        try:
            context.scene.frame_current = frame
        except Exception:
            pass


def _update_style_pick(self, context):
    if getattr(self, "assets_refreshing", False):
        return
    path = (self.style_pick or "").strip()
    if not path:
        return
    if self.style_image_path != path:
        self.style_image_path = path


def _update_result_pick(self, context):
    if getattr(self, "assets_refreshing", False):
        return
    path = (self.result_pick or "").strip()
    if not path:
        return
    if self.result_image_path != path:
        self.result_image_path = path


def update_ai_render_asset_cache(state, source_paths, style_paths, result_paths) -> None:
    pcoll = _ensure_asset_previews()
    asset_sets = {
        "source_assets_json": source_paths,
        "style_assets_json": style_paths,
        "result_assets_json": result_paths,
    }
    keep_keys = set()
    for paths in asset_sets.values():
        for path in paths:
            try:
                keep_keys.add(path.as_posix())
            except Exception:
                pass

    for key in list(pcoll.keys()):
        if key not in keep_keys:
            try:
                pcoll.remove(key)
            except Exception:
                pass

    for key in keep_keys:
        if key in pcoll:
            continue
        try:
            pcoll.load(key, key, "IMAGE")
        except Exception:
            pass

    try:
        state.assets_refreshing = True
        for json_attr, paths in asset_sets.items():
            entries = [{"path": p.as_posix(), "name": p.name} for p in paths]
            setattr(state, json_attr, json.dumps(entries))
            count_attr = json_attr.replace("_json", "_count")
            setattr(state, count_attr, len(entries))

        if state.source_image_path and _path_in_cache(state.source_assets_json, state.source_image_path):
            state.source_pick = state.source_image_path
        if state.style_image_path and _path_in_cache(state.style_assets_json, state.style_image_path):
            state.style_pick = state.style_image_path
        if state.result_image_path and _path_in_cache(state.result_assets_json, state.result_image_path):
            state.result_pick = state.result_image_path
    finally:
        state.assets_refreshing = False


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
    llm_use_style_reference: BoolProperty(
        name="Use Style Reference in LLM",
        description="Send the style reference image to the LLM to describe its look and context",
        default=False,
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
    source_assets_json: StringProperty(default="", options={"HIDDEN"})
    source_assets_count: IntProperty(default=0, options={"HIDDEN"})
    source_pick: EnumProperty(items=_items_source_assets, update=_update_source_pick)

    style_image_path: StringProperty(
        name="Style Reference",
        subtype="FILE_PATH",
        default="",
        update=_update_style_path,
    )
    style_image: PointerProperty(type=Image)
    style_assets_json: StringProperty(default="", options={"HIDDEN"})
    style_assets_count: IntProperty(default=0, options={"HIDDEN"})
    style_pick: EnumProperty(items=_items_style_assets, update=_update_style_pick)

    result_image_path: StringProperty(
        name="AI Result",
        subtype="FILE_PATH",
        default="",
        update=_update_result_path,
    )
    result_image: PointerProperty(type=Image)
    result_exists: BoolProperty(default=False, options={"HIDDEN"})
    result_assets_json: StringProperty(default="", options={"HIDDEN"})
    result_assets_count: IntProperty(default=0, options={"HIDDEN"})
    result_pick: EnumProperty(items=_items_result_assets, update=_update_result_pick)

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
    assets_refreshing: BoolProperty(default=False, options={"HIDDEN"})
    assets_last_scan: FloatProperty(default=0.0, options={"HIDDEN"})
    delete_confirm_action: StringProperty(default="", options={"HIDDEN"})
    delete_confirm_time: FloatProperty(default=0.0, options={"HIDDEN"})


def register():
    bpy.utils.register_class(LimeAIRenderState)
    bpy.types.Scene.lime_ai_render = PointerProperty(type=LimeAIRenderState)


def unregister():
    del bpy.types.Scene.lime_ai_render
    bpy.utils.unregister_class(LimeAIRenderState)
    _clear_asset_previews()
