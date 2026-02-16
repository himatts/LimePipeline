"""
AI Render Converter Operators

Implements the render-to-style conversion workflow using Krea (Nano Banana)
and optional prompt rewriting via OpenRouter.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
from pathlib import Path
import re
import hashlib
import json
import shutil
import time
import urllib.request
from typing import Dict, Iterable, List, Optional

import bpy
from bpy.types import Operator, Scene
from bpy.props import BoolProperty, EnumProperty, StringProperty

from ..core import validate_scene
from ..ops.ops_save_templates import _ensure_editables_dir, _resolve_prj_rev_sc, _camera_index_for_shot
from ..prefs import LimePipelinePrefs
from ..props_ai_renders import update_ai_render_asset_cache
from .ai_http import (
    has_krea_api_key,
    has_openrouter_api_key,
    openrouter_headers,
    OPENROUTER_CHAT_URL,
    http_post_json,
    http_get_json_with_status,
    http_post_json_with_status,
    http_post_multipart_with_status,
    http_delete_json_with_status,
    krea_headers,
)


KREA_GENERATE_PATH = "/generate/image"
KREA_ASSETS_PATH = "/assets"
KREA_JOBS_PATH = "/jobs"

STYLE_PROMPT = (
    "Generate a storyboard style black and white illustration based on the analyzed object and the provided "
    "concept. The image must be schematic, clear, and highly readable, using clean line work as the primary "
    "visual language. Focus on accurately representing the object proportions, silhouette, and key features "
    "identified in the analysis, while interpreting the concept to define the scene context and action. "
    "Use minimal shading only to support depth and form. The result should look like a technical storyboard "
    "frame intended to communicate function, usage, or interaction, not an artistic or stylized drawing. "
    "Avoid photorealistic rendering, surface materials, or color; render only black-and-white linework."
)
STYLE_CONTINUITY_PROMPT = (
    "Match the style reference image closely: preserve its sketch line quality, simplification, and lack of "
    "fills. Do not keep the original materials or colors from the source render."
)
SOURCE_BASE_PROMPT = (
    "Convert the source render image into a storyboard sketch. The source render is the image to transform."
)
STYLE_GUIDE_PROMPT = (
    "Convert the source render image into a storyboard sketch. The source render is the image to transform. "
    "The style reference image is only a style guide."
)
PRESERVE_PROMPT = (
    "Preserve the original composition, camera angle, proportions, and silhouette. "
    "Do not change the main shapes or perspective."
)

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".exr"}
_SOURCE_FRAME_RE = re.compile(r"_F(\d{1,6})_", re.IGNORECASE)


@dataclass
class FrameContext:
    project_name: str
    sc_number: int
    rev: str
    shot_idx: int
    cam_idx: int
    frame: int


@dataclass
class AiRenderPaths:
    ai_root: Path
    sources_dir: Path
    styles_dir: Path
    outputs_dir: Path
    tmp_dir: Path
    manifests_dir: Path


def _addon_prefs(context) -> LimePipelinePrefs | None:
    try:
        return context.preferences.addons[__package__.split(".")[0]].preferences
    except Exception:
        return None


def _krea_base_url(prefs: LimePipelinePrefs) -> str:
    base = (getattr(prefs, "krea_base_url", "") or "").strip()
    if not base:
        return "https://api.krea.ai"
    return base.rstrip("/")


def _krea_model_path(prefs: LimePipelinePrefs) -> str:
    raw = (getattr(prefs, "krea_model", "") or "").strip().strip("/")
    return raw or "google/nano-banana"


def _krea_generate_url(prefs: LimePipelinePrefs) -> str:
    return f"{_krea_base_url(prefs)}{KREA_GENERATE_PATH}/{_krea_model_path(prefs)}"


def _krea_status_url(prefs: LimePipelinePrefs, job_id: str) -> str:
    return f"{_krea_base_url(prefs)}{KREA_JOBS_PATH}/{job_id}"


def _krea_cancel_url(prefs: LimePipelinePrefs, job_id: str) -> str:
    return f"{_krea_base_url(prefs)}{KREA_JOBS_PATH}/{job_id}"


def _debug_log(prefs: LimePipelinePrefs | None, message: str) -> None:
    try:
        if not prefs or not getattr(prefs, "krea_debug", False):
            return
        print(f"[Krea Debug] {message}")
    except Exception:
        pass


def _ensure_ai_dirs(state) -> AiRenderPaths:
    sb_editables = Path(_ensure_editables_dir(state, "SB"))
    ai_root = sb_editables / "AI"
    sources_dir = ai_root / "sources"
    styles_dir = ai_root / "styles"
    outputs_dir = ai_root / "outputs"
    tmp_dir = ai_root / "tmp"
    manifests_dir = ai_root / "manifests"
    for folder in (ai_root, sources_dir, styles_dir, outputs_dir, tmp_dir, manifests_dir):
        folder.mkdir(parents=True, exist_ok=True)
    return AiRenderPaths(
        ai_root=ai_root,
        sources_dir=sources_dir,
        styles_dir=styles_dir,
        outputs_dir=outputs_dir,
        tmp_dir=tmp_dir,
        manifests_dir=manifests_dir,
    )


def _frame_context(context) -> FrameContext:
    scene = context.scene
    project_name, sc_number, rev = _resolve_prj_rev_sc(context.window_manager.lime_pipeline)
    shot = validate_scene.active_shot_context(context)
    shot_idx = validate_scene.parse_shot_index(shot.name) if shot else 0
    cam_idx = _camera_index_for_shot(shot, scene.camera) if shot and scene.camera else 1
    frame = int(getattr(scene, "frame_current", 0) or 0)
    if sc_number <= 0:
        raise RuntimeError("Scene number not configured. Set SC in Project Organization.")
    if not rev:
        raise RuntimeError("Revision letter not configured. Set Rev in Project Organization.")
    if not project_name:
        raise RuntimeError("Project name not resolved. Check Project Organization settings.")
    return FrameContext(
        project_name=project_name,
        sc_number=int(sc_number),
        rev=rev,
        shot_idx=int(shot_idx or 0),
        cam_idx=int(cam_idx or 1),
        frame=int(frame or 0),
    )


def _mode_token(mode: str) -> str:
    return "SKETCHPLUS" if mode == "SKETCH_PLUS" else "SKETCH"


def _build_source_filename(ctx: FrameContext) -> str:
    return (
        f"{ctx.project_name}_Render_SC{ctx.sc_number:03d}_SH{ctx.shot_idx:02d}"
        f"C{ctx.cam_idx}_F{ctx.frame:04d}_Rev_{ctx.rev}.png"
    )


def _build_output_stem(ctx: FrameContext, mode_token: str) -> str:
    return (
        f"{ctx.project_name}_SB_SC{ctx.sc_number:03d}_SH{ctx.shot_idx:02d}"
        f"C{ctx.cam_idx}_F{ctx.frame:04d}_{mode_token}"
    )


def _manifest_path(paths: AiRenderPaths, ctx: FrameContext) -> Path:
    name = (
        f"{ctx.project_name}_SB_SC{ctx.sc_number:03d}_SH{ctx.shot_idx:02d}"
        f"C{ctx.cam_idx}_F{ctx.frame:04d}_AI_manifest.json"
    )
    return paths.manifests_dir / name


def _build_prompt(mode: str, detail_text: str, has_style: bool, use_style_continuity: bool) -> str:
    prefix = STYLE_GUIDE_PROMPT if has_style else SOURCE_BASE_PROMPT
    style_hint = STYLE_CONTINUITY_PROMPT if (has_style and use_style_continuity) else ""
    if mode == "SKETCH_PLUS":
        detail_block = detail_text.strip()
        if detail_block:
            if style_hint:
                return f"{prefix} {STYLE_PROMPT}. {style_hint} {PRESERVE_PROMPT}. Add: {detail_block}."
            return f"{prefix} {STYLE_PROMPT}. {PRESERVE_PROMPT}. Add: {detail_block}."
    if style_hint:
        return f"{prefix} {STYLE_PROMPT}. {style_hint} {PRESERVE_PROMPT}."
    return f"{prefix} {STYLE_PROMPT}. {PRESERVE_PROMPT}."


def _rewrite_details_with_llm(prefs: LimePipelinePrefs, raw_text: str, image_path: Optional[Path] = None) -> str:
    _debug_log(prefs, f"LLM detail input: {raw_text}")
    vision_parts: List[Dict[str, object]] = [{"type": "text", "text": raw_text}]
    image_attached = False
    if image_path and image_path.exists():
        try:
            encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
            mime = _guess_mimetype(image_path)
            vision_parts.append(
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}
            )
            image_attached = True
            _debug_log(prefs, f"LLM detail image attached: {image_path.name}")
        except Exception as ex:
            _debug_log(prefs, f"LLM detail image attach failed: {ex}")
    else:
        _debug_log(prefs, "LLM detail image skipped: source image missing")
    payload = {
        "model": prefs.openrouter_model or "google/gemini-3-flash-preview",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Using all provided information, generate a single, refined image prompt in English that "
                    "clearly describes a storyboard-style illustration. "
                    "The prompt must follow an illustration-based structure: clearly describe the main subject "
                    "first, then place it within its environment, followed by composition, framing, and visual "
                    "emphasis. The object described must remain the primary focus, preserving its identity, "
                    "structure, and function exactly as provided, while secondary elements and context derived "
                    "from the scene concept are integrated coherently. "
                    "The illustration should be described as black and white, storyboard-oriented, with "
                    "simplified shapes, strong silhouettes, clean linework, and high contrast lighting. "
                    "Emphasize cinematic framing, camera angle, and visual clarity suitable for sequential "
                    "storytelling. If a style reference image is provided, briefly describe its visual style "
                    "and integrate those cues into the prompt while preserving the main subject. Avoid "
                    "decorative language; focus on visual intent, composition, and readable action."
                ),
            },
            {"role": "user", "content": vision_parts},
        ],
    }
    result = http_post_json(OPENROUTER_CHAT_URL, payload, headers=openrouter_headers(prefs), timeout=40)
    if not result:
        _debug_log(prefs, "LLM detail output: (no response, using raw text)")
        return raw_text
    try:
        choices = result.get("choices", [])
        if not choices:
            _debug_log(prefs, "LLM detail output: (empty choices, using raw text)")
            return raw_text
        message = choices[0].get("message", {})
        content = (message.get("content") or "").strip()
        _debug_log(prefs, f"LLM detail output: {content or '(empty, using raw text)'}")
        _debug_log(prefs, f"LLM detail image attached flag: {image_attached}")
        return content or raw_text
    except Exception:
        _debug_log(prefs, "LLM detail output: (exception, using raw text)")
        return raw_text


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _persist_style_image(src_path: Path, dest_dir: Path) -> Path:
    if dest_dir in src_path.parents:
        return src_path
    try:
        src_size = src_path.stat().st_size
    except Exception:
        src_size = -1
    src_hash = ""
    try:
        src_hash = _file_sha256(src_path)
    except Exception:
        src_hash = ""
    if src_hash:
        try:
            for existing in dest_dir.iterdir():
                if not existing.is_file():
                    continue
                if existing.suffix.lower() not in _IMAGE_EXTS:
                    continue
                try:
                    if src_size > 0 and existing.stat().st_size != src_size:
                        continue
                except Exception:
                    pass
                try:
                    if _file_sha256(existing) == src_hash:
                        return existing
                except Exception:
                    continue
        except Exception:
            pass
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"Style_{stamp}{src_path.suffix or '.png'}"
    shutil.copy2(src_path, dest)
    return dest


def _read_manifest(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_manifest(path: Path, data: Dict[str, object]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False), encoding="utf-8")


def _append_generation(manifest: Dict[str, object], entry: Dict[str, object]) -> None:
    generations = manifest.get("generations")
    if not isinstance(generations, list):
        generations = []
    generations.append(entry)
    manifest["generations"] = generations


def _guess_mimetype(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext in {".tif", ".tiff"}:
        return "image/tiff"
    if ext in {".webp"}:
        return "image/webp"
    if ext == ".exr":
        return "image/exr"
    return "image/png"


def _list_images(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    try:
        return [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in _IMAGE_EXTS]
    except Exception:
        return []


def _list_manifests(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    try:
        return [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".json"]
    except Exception:
        return []


def _frame_from_source(path: Path) -> int | None:
    match = _SOURCE_FRAME_RE.search(path.stem)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _sort_sources(paths: List[Path]) -> List[Path]:
    def sort_key(path: Path):
        frame = _frame_from_source(path)
        if frame is None:
            return (1, path.name.lower())
        return (0, frame, path.name.lower())

    return sorted(paths, key=sort_key)


def _sort_by_mtime(paths: List[Path]) -> List[Path]:
    def sort_key(path: Path):
        try:
            return float(path.stat().st_mtime)
        except Exception:
            return 0.0

    return sorted(paths, key=sort_key, reverse=True)


def refresh_ai_render_assets(context, *, force: bool = False) -> None:
    scene = context.scene
    state = getattr(scene, "lime_ai_render", None)
    if state is None:
        return
    now = time.monotonic()
    if not force and (now - float(getattr(state, "assets_last_scan", 0.0) or 0.0)) < 0.75:
        return
    try:
        paths = _ensure_ai_dirs(context.window_manager.lime_pipeline)
    except Exception:
        return
    sources = _sort_sources(_list_images(paths.sources_dir))
    styles = _sort_by_mtime(_list_images(paths.styles_dir))
    results = _sort_by_mtime(_list_images(paths.outputs_dir))
    try:
        update_ai_render_asset_cache(state, sources, styles, results, force_reload=force)
        state.assets_last_scan = now
    except Exception:
        pass


def _upload_krea_asset(prefs: LimePipelinePrefs, path: Path) -> Dict[str, str]:
    url = f"{_krea_base_url(prefs)}{KREA_ASSETS_PATH}"
    _debug_log(prefs, f"Upload asset: {path.name} -> {url}")
    data = path.read_bytes()
    files = {"file": (path.name, data, _guess_mimetype(path))}
    resp = http_post_multipart_with_status(
        url,
        fields={},
        files=files,
        headers=krea_headers(prefs, content_type=None),
        timeout=90,
    )
    _debug_log(prefs, f"Upload response status={resp.status} error={bool(resp.error)}")
    if resp.error:
        raise RuntimeError(f"Krea asset upload failed: {resp.error}")
    if not resp.data:
        raise RuntimeError("Krea asset upload returned no data")
    return _parse_asset_ref(resp.data)


def _parse_asset_ref(data: Dict[str, object]) -> Dict[str, str]:
    asset_id = ""
    asset_url = ""
    for key in ("id", "asset_id"):
        val = data.get(key)
        if isinstance(val, str):
            asset_id = val
            break
    for key in ("image_url", "url", "asset_url"):
        val = data.get(key)
        if isinstance(val, str):
            asset_url = val
            break
    nested = data.get("data")
    if isinstance(nested, dict):
        if not asset_id and isinstance(nested.get("id"), str):
            asset_id = nested.get("id")
        for key in ("image_url", "url", "asset_url"):
            val = nested.get(key)
            if isinstance(val, str):
                asset_url = val
                break
    return {"id": asset_id, "url": asset_url}


def _clamp_strength(value: float) -> float:
    try:
        return max(-2.0, min(2.0, float(value)))
    except Exception:
        return 0.0


def _resolve_source_size(source_path: Optional[Path]) -> tuple[int, int]:
    if source_path is None or not source_path.exists():
        return 0, 0
    try:
        for img in bpy.data.images:
            fp = getattr(img, "filepath", "")
            if fp and Path(fp) == source_path:
                size = getattr(img, "size", None)
                if size and len(size) >= 2:
                    return int(size[0]), int(size[1])
    except Exception:
        pass
    try:
        img = bpy.data.images.load(source_path.as_posix(), check_existing=True)
        size = getattr(img, "size", None)
        if size and len(size) >= 2:
            return int(size[0]), int(size[1])
    except Exception:
        pass
    return 0, 0


def _build_style_images(
    source_url: str,
    style_url: str,
    source_strength: float,
    style_strength: float,
) -> List[Dict[str, object]]:
    style_images: List[Dict[str, object]] = []
    if source_url:
        # Use the source render as a strong style reference to preserve composition.
        style_images.append({"url": source_url, "strength": _clamp_strength(source_strength)})
    if style_url:
        style_images.append({"url": style_url, "strength": _clamp_strength(style_strength)})
    return style_images


def _create_krea_job(
    prefs: LimePipelinePrefs,
    prompt: str,
    source_url: str,
    style_url: str,
    source_path: Optional[Path] = None,
    source_strength: float = 1.6,
    style_strength: float = 0.6,
) -> tuple[str, str]:
    url = _krea_generate_url(prefs)
    _debug_log(prefs, f"Create job: {url}")
    payload: Dict[str, object] = {
        "prompt": prompt,
        "batchSize": 1,
        "numImages": 1,
    }
    if prefs and getattr(prefs, "krea_debug", False):
        snippet = prompt.replace("\n", " ").strip()
        if len(snippet) > 200:
            snippet = f"{snippet[:200]}..."
        _debug_log(prefs, f"Prompt chars={len(prompt)} preview='{snippet}'")
    style_images = _build_style_images(source_url, style_url, source_strength, style_strength)
    if style_images:
        payload["styleImages"] = style_images
        strengths = [img.get("strength") for img in style_images]
        _debug_log(prefs, f"Style images: {len(style_images)} strengths={strengths} source_first={bool(source_url)}")
    width, height = _resolve_source_size(source_path)
    if width > 0 and height > 0:
        payload["width"] = width
        payload["height"] = height

    resp = http_post_json_with_status(url, payload=payload, headers=krea_headers(prefs), timeout=90)
    _debug_log(prefs, f"Create job response status={resp.status} error={bool(resp.error)}")

    if resp.error:
        raise RuntimeError(f"Krea job creation failed: {resp.error}")
    if not resp.data:
        raise RuntimeError("Krea job creation returned no data")
    job_id = _extract_job_id(resp.data)
    if not job_id:
        raise RuntimeError("Krea job creation missing job id")
    status_raw = _extract_status(resp.data)
    return job_id, status_raw


def _extract_job_id(data: Dict[str, object]) -> str:
    for key in ("job_id", "id"):
        val = data.get(key)
        if isinstance(val, str):
            return val
    nested = data.get("data")
    if isinstance(nested, dict):
        for key in ("job_id", "id"):
            val = nested.get(key)
            if isinstance(val, str):
                return val
    return ""


def _krea_job_status(prefs: LimePipelinePrefs, job_id: str) -> Dict[str, object]:
    url = _krea_status_url(prefs, job_id)
    _debug_log(prefs, f"Poll status: {url}")
    resp = http_get_json_with_status(url, headers=krea_headers(prefs), timeout=30)
    _debug_log(prefs, f"Poll response status={resp.status} error={bool(resp.error)}")
    if resp.error:
        return {"status": "error", "error": resp.error, "http_status": resp.status}
    data = resp.data or {}
    status_raw = _extract_status(data)
    urls = _extract_urls(data)
    return {"status": status_raw, "urls": urls, "data": data, "http_status": resp.status}


def _extract_status(data: Dict[str, object]) -> str:
    for key in ("status", "state"):
        val = data.get(key)
        if isinstance(val, str):
            return val
    nested = data.get("data")
    if isinstance(nested, dict):
        for key in ("status", "state"):
            val = nested.get(key)
            if isinstance(val, str):
                return val
    return "processing"


def _extract_urls(data: Dict[str, object]) -> List[str]:
    urls: List[str] = []

    def collect(value):
        if isinstance(value, str):
            if value.startswith("http://") or value.startswith("https://"):
                urls.append(value)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            for item in value.values():
                collect(item)

    for key in ("urls", "output", "outputs", "result", "results", "images", "image", "image_url", "result_url"):
        if key in data:
            collect(data.get(key))

    if not urls:
        # Fallback: scan full payload when no obvious outputs are present.
        collect(data)

    # Deduplicate while preserving order
    seen = set()
    ordered = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered


def _download_url(url: str, dest_path: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "LimePipeline"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        dest_path.write_bytes(resp.read())


def _next_version(outputs_dir: Path, base_stem: str, rev: str) -> int:
    max_version = 0
    for path in outputs_dir.glob(f"{base_stem}_V*_Rev_{rev}.png"):
        stem = path.stem
        parts = stem.split("_")
        for part in parts:
            if part.startswith("V") and part[1:].isdigit():
                max_version = max(max_version, int(part[1:]))
    return max_version + 1


def _normalized_status(status_raw: str) -> str:
    val = (status_raw or "").strip().lower()
    if val in {"queued", "pending", "backlogged", "scheduled"}:
        return "QUEUED"
    if val in {"running", "processing", "in_progress", "sampling", "intermediate-complete"}:
        return "PROCESSING"
    if val in {"completed", "succeeded", "finished", "done"}:
        return "COMPLETED"
    if val in {"failed", "error"}:
        return "FAILED"
    if val in {"cancelled", "canceled"}:
        return "CANCELLED"
    return "PROCESSING"


def refresh_ai_render_state(context, *, force: bool = False) -> None:
    scene = context.scene
    state = getattr(scene, "lime_ai_render", None)
    if state is None:
        return
    if not getattr(state, "auto_refresh_source", True):
        return
    frame = int(getattr(scene, "frame_current", 0) or 0)
    if not force and getattr(state, "cached_frame", -1) == frame:
        return
    try:
        ctx = _frame_context(context)
        paths = _ensure_ai_dirs(context.window_manager.lime_pipeline)
        source_path = paths.sources_dir / _build_source_filename(ctx)
        new_path = source_path.as_posix()
        if source_path.exists():
            if state.source_image_path != new_path:
                state.source_image_path = new_path
        else:
            if state.source_image_path:
                state.source_image_path = ""
            try:
                state.source_exists = False
                state.source_image = None
            except Exception:
                pass
        state.cached_frame = frame
    except Exception:
        # Keep previous state if context cannot be resolved
        pass


def _frame_change_handler(scene: Scene) -> None:
    try:
        ctx = bpy.context
    except Exception:
        return
    if getattr(ctx, "scene", None) != scene:
        return
    try:
        refresh_ai_render_state(ctx)
    except Exception:
        pass


def register_ai_render_handlers() -> None:
    if _frame_change_handler not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(_frame_change_handler)


def unregister_ai_render_handlers() -> None:
    try:
        bpy.app.handlers.frame_change_post.remove(_frame_change_handler)
    except Exception:
        pass


class LIME_OT_ai_render_refresh(Operator):
    bl_idname = "lime.ai_render_refresh"
    bl_label = "AI: Refresh Source"
    bl_options = {"REGISTER"}

    def execute(self, context):
        refresh_ai_render_state(context, force=True)
        refresh_ai_render_assets(context, force=True)
        self.report({"INFO"}, "Source render refreshed for current frame")
        return {"FINISHED"}


class LIME_OT_ai_render_frame(Operator):
    bl_idname = "lime.ai_render_frame"
    bl_label = "AI: Render Current Frame"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_render", None)
        if state is None:
            self.report({"ERROR"}, "AI Render state not available")
            return {"CANCELLED"}
        try:
            ctx = _frame_context(context)
            paths = _ensure_ai_dirs(context.window_manager.lime_pipeline)
            source_path = paths.sources_dir / _build_source_filename(ctx)
        except Exception as ex:
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}

        prev_path = scene.render.filepath
        try:
            source_path.parent.mkdir(parents=True, exist_ok=True)
            scene.render.filepath = source_path.as_posix()
            result = bpy.ops.render.render(write_still=True)
            if result == {"CANCELLED"} or ("CANCELLED" in result and "FINISHED" not in result):
                self.report({"ERROR"}, "Render cancelled")
                return {"CANCELLED"}
        except Exception as ex:
            self.report({"ERROR"}, f"Render failed: {ex}")
            return {"CANCELLED"}
        finally:
            scene.render.filepath = prev_path

        if not source_path.exists():
            self.report({"ERROR"}, "Render completed but output file was not found")
            return {"CANCELLED"}

        new_path = source_path.as_posix()
        if state.source_image_path != new_path:
            state.source_image_path = new_path
        state.cached_frame = int(ctx.frame)
        refresh_ai_render_assets(context, force=True)
        self.report({"INFO"}, f"Rendered frame to {source_path.name}")
        return {"FINISHED"}


class LIME_OT_ai_render_generate(Operator):
    bl_idname = "lime.ai_render_generate"
    bl_label = "AI: Generate Storyboard"
    bl_options = {"REGISTER"}

    use_last_settings: BoolProperty(default=False)

    _timer = None
    _job_id: str = ""
    _poll_interval = 1.0
    _last_poll_time = 0.0
    _paths: Optional[AiRenderPaths] = None
    _ctx: Optional[FrameContext] = None
    _output_paths: List[Path] = []
    _model_path: str = ""
    _prompt_used: str = ""
    _source_path: Optional[Path] = None
    _style_path: Optional[Path] = None
    _generation_id: str = ""
    _asset_urls: Dict[str, str] = {}
    _last_status_raw: str = ""

    def _set_status(self, state, status: str, message: str = "") -> None:
        try:
            if state.job_status != status:
                state.job_status = status
        except Exception:
            pass
        if message:
            try:
                if state.job_message != message:
                    state.job_message = message
            except Exception:
                pass

    def invoke(self, context, event):
        scene = context.scene
        state = getattr(scene, "lime_ai_render", None)
        if state is None:
            self.report({"ERROR"}, "AI Render state not available")
            return {"CANCELLED"}
        if state.is_busy:
            self.report({"WARNING"}, "AI job already running")
            return {"CANCELLED"}

        prefs = _addon_prefs(context)
        if prefs is None:
            self.report({"ERROR"}, "Addon preferences unavailable")
            return {"CANCELLED"}
        if not has_krea_api_key():
            self.report({"ERROR"}, "Krea API key not found in .env")
            return {"CANCELLED"}

        try:
            self._ctx = _frame_context(context)
            self._paths = _ensure_ai_dirs(context.window_manager.lime_pipeline)
        except Exception as ex:
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}

        if self.use_last_settings:
            prompt = (state.last_prompt or "").strip()
            if not prompt:
                self.report({"ERROR"}, "No previous prompt to retry")
                return {"CANCELLED"}
            self._prompt_used = prompt
            mode = state.last_mode or state.mode
            source_path = Path(state.last_source_path or state.source_image_path or "")
            style_path = Path(state.last_style_path or state.style_image_path or "") if (state.last_style_path or state.style_image_path) else None
        else:
            mode = state.mode
            detail_text = (state.detail_text or "").strip()
            if mode == "SKETCH_PLUS" and not detail_text:
                self.report({"ERROR"}, "Details are required for Sketch + Details mode")
                return {"CANCELLED"}
            source_path = Path(state.source_image_path or "")
            if mode == "SKETCH_PLUS" and getattr(state, "rewrite_with_llm", True):
                if has_openrouter_api_key():
                    use_style = bool(getattr(state, "llm_use_style_reference", False))
                    style_for_llm = Path(state.style_image_path or "") if use_style else None
                    detail_opt = _rewrite_details_with_llm(prefs, detail_text, source_path)
                else:
                    detail_opt = detail_text
            else:
                detail_opt = detail_text
            state.detail_text_optimized = detail_opt
            has_style = bool((getattr(state, "style_image_path", "") or "").strip())
            use_style = bool(getattr(state, "llm_use_style_reference", False))
            prompt = _build_prompt(mode, detail_opt, has_style, use_style)
            _debug_log(prefs, f"Final prompt sent to Krea: {prompt}")
            state.prompt_final = prompt
            self._prompt_used = prompt
            style_path = Path(state.style_image_path or "") if (state.style_image_path or "").strip() else None

        if not source_path or not source_path.exists():
            self.report({"ERROR"}, "Source render not found for current frame")
            return {"CANCELLED"}

        self._source_path = source_path
        self._style_path = style_path
        self._model_path = _krea_model_path(prefs)
        self._generation_id = time.strftime("%Y%m%d_%H%M%S")
        self._asset_urls = {}
        self._last_status_raw = ""

        state.is_busy = True
        state.cancel_requested = False
        self._set_status(state, "UPLOADING", "Uploading assets to Krea")

        try:
            source_asset = _upload_krea_asset(prefs, source_path)
            source_url = source_asset.get("url", "")
            style_url = ""
            if style_path and style_path.exists():
                style_saved = _persist_style_image(style_path, self._paths.styles_dir)
                self._style_path = style_saved
                style_asset = _upload_krea_asset(prefs, style_saved)
                style_url = style_asset.get("url", "")
            self._asset_urls = {
                "source_url": source_url,
                "style_url": style_url,
            }
            job_id, status_raw = _create_krea_job(
                prefs,
                prompt,
                source_url,
                style_url,
                source_path=source_path,
                source_strength=getattr(state, "source_strength", 1.6),
                style_strength=getattr(state, "style_strength", 0.6),
            )
        except Exception as ex:
            state.is_busy = False
            state.last_error = str(ex)
            self._set_status(state, "FAILED", str(ex))
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}

        state.job_id = job_id
        state.last_prompt = prompt
        state.last_mode = mode
        state.last_detail_input = state.detail_text or ""
        state.last_detail_optimized = state.detail_text_optimized or ""
        state.last_source_path = source_path.as_posix()
        if self._style_path:
            state.last_style_path = self._style_path.as_posix()

        self._job_id = job_id
        status = _normalized_status(str(status_raw))
        self._set_status(state, status, f"Job created: {job_id}")

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        scene = context.scene
        state = getattr(scene, "lime_ai_render", None)
        if state is None:
            return {"CANCELLED"}

        if getattr(state, "cancel_requested", False):
            state.cancel_requested = False
            state.is_busy = False
            self._set_status(state, "CANCELLED", "Cancelled by user")
            self._finish(context)
            return {"CANCELLED"}

        if event.type in {"ESC"}:
            state.is_busy = False
            self._set_status(state, "CANCELLED", "Cancelled by user")
            self._finish(context)
            return {"CANCELLED"}

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        now = time.monotonic()
        if now - self._last_poll_time < self._poll_interval:
            return {"PASS_THROUGH"}

        self._last_poll_time = now
        prefs = _addon_prefs(context)
        if prefs is None:
            state.is_busy = False
            self._set_status(state, "FAILED", "Preferences unavailable during polling")
            self._finish(context)
            return {"CANCELLED"}

        info = _krea_job_status(prefs, self._job_id)
        status_raw = info.get("status", "processing")
        if status_raw != self._last_status_raw:
            _debug_log(prefs, f"Job status raw='{status_raw}' http={info.get('http_status')}")
            self._last_status_raw = str(status_raw)
        http_status = info.get("http_status")
        if status_raw == "error" and int(http_status or 0) == 429:
            self._set_status(state, "PROCESSING", "Rate limited, retrying")
            self._poll_interval = min(30.0, self._poll_interval + 5.0)
            return {"PASS_THROUGH"}
        status = _normalized_status(str(status_raw))

        if status in {"QUEUED", "PROCESSING"}:
            self._set_status(state, status, f"{status.title()} on Krea")
            self._poll_interval = min(15.0, self._poll_interval + 1.5)
            return {"PASS_THROUGH"}

        if status == "FAILED":
            state.is_busy = False
            err = info.get("error") or "Krea job failed"
            state.last_error = str(err)
            self._set_status(state, "FAILED", str(err))
            self._finish(context)
            return {"CANCELLED"}

        if status == "CANCELLED":
            state.is_busy = False
            self._set_status(state, "CANCELLED", "Krea job cancelled")
            self._finish(context)
            return {"CANCELLED"}

        # Completed
        urls = info.get("urls") or []
        if not urls:
            state.is_busy = False
            self._set_status(state, "FAILED", "Krea job completed with no outputs")
            self._finish(context)
            return {"CANCELLED"}

        try:
            self._output_paths = _save_results(self._paths, self._ctx, state, urls)
        except Exception as ex:
            state.is_busy = False
            self._set_status(state, "FAILED", f"Download failed: {ex}")
            self._finish(context)
            return {"CANCELLED"}

        if self._output_paths:
            new_path = self._output_paths[0].as_posix()
            if state.result_image_path != new_path:
                state.result_image_path = new_path
            state.last_result_path = state.result_image_path
            refresh_ai_render_assets(context, force=True)

        state.is_busy = False
        self._set_status(state, "COMPLETED", "AI render completed")
        _record_manifest(
            self._paths,
            self._ctx,
            state,
            self._generation_id,
            self._model_path,
            urls,
            self._output_paths,
            asset_urls=self._asset_urls,
        )
        self._finish(context)
        return {"FINISHED"}

    def _finish(self, context):
        wm = context.window_manager
        if self._timer is not None:
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None


def _save_results(
    paths: AiRenderPaths,
    ctx: FrameContext,
    state,
    urls: Iterable[str],
) -> List[Path]:
    mode_token = _mode_token(state.last_mode or state.mode)
    base_stem = _build_output_stem(ctx, mode_token)
    results: List[Path] = []
    version = None
    if state.retry_strategy == "VERSION":
        version = _next_version(paths.outputs_dir, base_stem, ctx.rev)
    for idx, url in enumerate(urls, 1):
        if version is not None:
            stem = f"{base_stem}_V{version:02d}_Rev_{ctx.rev}"
        else:
            stem = f"{base_stem}_Rev_{ctx.rev}"
        if len(urls) > 1:
            stem = f"{stem}_{idx:02d}"
        output_path = paths.outputs_dir / f"{stem}.png"
        _download_url(url, output_path)
        results.append(output_path)
    return results


def _record_manifest(
    paths: AiRenderPaths,
    ctx: FrameContext,
    state,
    generation_id: str,
    model_slug: str,
    urls: Iterable[str],
    output_paths: Iterable[Path],
    asset_urls: Optional[Dict[str, str]] = None,
) -> None:
    manifest_path = _manifest_path(paths, ctx)
    manifest = _read_manifest(manifest_path)
    manifest.setdefault("frame", ctx.frame)
    manifest.setdefault(
        "context",
        {
            "project_name": ctx.project_name,
            "sc_number": ctx.sc_number,
            "rev": ctx.rev,
            "shot_idx": ctx.shot_idx,
            "cam_idx": ctx.cam_idx,
        },
    )
    source_path = Path(state.last_source_path or state.source_image_path or "")
    style_path = Path(state.last_style_path or state.style_image_path or "") if (state.last_style_path or state.style_image_path) else None
    source_info = {
        "path": source_path.as_posix() if source_path else "",
        "hash": _file_sha256(source_path) if source_path and source_path.exists() else "",
    }
    style_info = {
        "path": style_path.as_posix() if style_path else "",
        "hash": _file_sha256(style_path) if style_path and style_path.exists() else "",
    }
    manifest["source"] = source_info
    if style_info["path"]:
        manifest["style"] = style_info

    entry = {
        "generation_id": generation_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": state.last_mode or state.mode,
        "prompt_final": state.last_prompt or state.prompt_final or "",
        "model": model_slug,
        "job_id": state.job_id,
        "status": state.job_status,
        "result_urls": list(urls),
        "output_paths": [p.as_posix() for p in output_paths],
    }
    if asset_urls:
        entry["asset_urls"] = asset_urls
    _append_generation(manifest, entry)
    manifest["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write_manifest(manifest_path, manifest)


class LIME_OT_ai_render_retry(Operator):
    bl_idname = "lime.ai_render_retry"
    bl_label = "AI: Retry Generation"
    bl_options = {"REGISTER"}

    def execute(self, context):
        result = bpy.ops.lime.ai_render_generate("INVOKE_DEFAULT", use_last_settings=True)
        if result == {"CANCELLED"}:
            self.report({"ERROR"}, "Retry failed to start")
            return {"CANCELLED"}
        return {"FINISHED"}


class LIME_OT_ai_render_cancel(Operator):
    bl_idname = "lime.ai_render_cancel"
    bl_label = "AI: Cancel Job"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_render", None)
        if state is None or not state.job_id:
            self.report({"WARNING"}, "No active job to cancel")
            return {"CANCELLED"}
        prefs = _addon_prefs(context)
        if prefs is None:
            self.report({"ERROR"}, "Preferences unavailable")
            return {"CANCELLED"}
        cancel_url = _krea_cancel_url(prefs, state.job_id)
        resp = http_delete_json_with_status(cancel_url, headers=krea_headers(prefs), timeout=30)
        _debug_log(prefs, f"Cancel response status={resp.status} error={bool(resp.error)}")
        if resp.error:
            self.report({"WARNING"}, f"Cancel request failed: {resp.error}")
        state.job_status = "CANCELLED"
        state.is_busy = False
        state.cancel_requested = True
        state.job_message = "Cancel requested"
        self.report({"INFO"}, "Cancel requested")
        return {"FINISHED"}


class LIME_OT_ai_render_test_connection(Operator):
    bl_idname = "lime.ai_render_test_connection"
    bl_label = "AI: Test Krea Connection"
    bl_options = {"REGISTER"}

    def execute(self, context):
        prefs = _addon_prefs(context)
        if prefs is None:
            self.report({"ERROR"}, "Preferences unavailable")
            return {"CANCELLED"}
        if not has_krea_api_key():
            self.report({"ERROR"}, "Krea API key not found in .env")
            return {"CANCELLED"}

        url = f"{_krea_base_url(prefs)}{KREA_JOBS_PATH}?limit=1"
        _debug_log(prefs, f"Test connection: {url}")
        resp = http_get_json_with_status(url, headers=krea_headers(prefs), timeout=20)
        _debug_log(prefs, f"Test response status={resp.status} error={bool(resp.error)}")

        status = int(resp.status or 0)
        if status in {401, 403}:
            self.report({"ERROR"}, "Krea auth failed (401/403). Check API key.")
            return {"CANCELLED"}
        if status == 402:
            self.report({"ERROR"}, "Krea credits exhausted (402).")
            return {"CANCELLED"}
        if status == 404:
            self.report({"ERROR"}, "Krea endpoint not found (404). Check base URL.")
            return {"CANCELLED"}
        if resp.error:
            self.report({"ERROR"}, f"Krea test failed: {resp.error}")
            return {"CANCELLED"}

        self.report({"INFO"}, "Krea connection OK")
        return {"FINISHED"}


class LIME_OT_ai_render_add_to_sequencer(Operator):
    bl_idname = "lime.ai_render_add_to_sequencer"
    bl_label = "AI: Add Result to Sequencer"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_render", None)
        if state is None:
            self.report({"ERROR"}, "AI Render state not available")
            return {"CANCELLED"}
        path = Path(state.result_image_path or "")
        if not path.exists():
            self.report({"ERROR"}, "No AI result image available")
            return {"CANCELLED"}
        seq = scene.sequence_editor
        if seq is None:
            seq = scene.sequence_editor_create()

        frame_start = 1
        target_channel = 1
        try:
            last_end = 0
            for s in seq.sequences_all:
                if int(getattr(s, "channel", 0) or 0) != target_channel:
                    continue
                end = int(getattr(s, "frame_final_end", 0) or 0)
                last_end = max(last_end, end)
            if last_end > 0:
                frame_start = last_end
        except Exception:
            frame_start = 1

        try:
            strip = seq.sequences.new_image(
                name=path.stem,
                filepath=path.as_posix(),
                channel=target_channel,
                frame_start=frame_start,
            )
            try:
                strip.frame_final_duration = 12
            except Exception:
                try:
                    strip.frame_final_end = frame_start + 12
                except Exception:
                    pass
            try:
                width = int(strip.elements[0].orig_width or 0)
                height = int(strip.elements[0].orig_height or 0)
            except Exception:
                width = 0
                height = 0
            if width > 0 and height > 0:
                scale_x = 1920.0 / float(width)
                scale_y = 1080.0 / float(height)
                try:
                    strip.transform.scale_x = scale_x
                    strip.transform.scale_y = scale_y
                except Exception:
                    pass
        except Exception as ex:
            self.report({"ERROR"}, f"Failed to add strip: {ex}")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Added AI result to Sequencer (channel {target_channel})")
        return {"FINISHED"}


class LIME_OT_ai_render_open_outputs_folder(Operator):
    bl_idname = "lime.ai_render_open_outputs_folder"
    bl_label = "AI: Open Outputs Folder"
    bl_options = {"REGISTER"}
    bl_description = "Open the AI outputs folder in the system file browser"

    def execute(self, context):
        try:
            paths = _ensure_ai_dirs(context.window_manager.lime_pipeline)
        except Exception as ex:
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}
        try:
            bpy.ops.wm.path_open(filepath=paths.outputs_dir.as_posix())
        except Exception as ex:
            self.report({"ERROR"}, f"Failed to open folder: {ex}")
            return {"CANCELLED"}
        return {"FINISHED"}


class LIME_OT_ai_render_delete_selected(Operator):
    bl_idname = "lime.ai_render_delete_selected"
    bl_label = "AI: Delete Selected Image"
    bl_options = {"REGISTER"}
    bl_description = "Delete the selected image from disk"

    target: EnumProperty(
        name="Target",
        items=[
            ("SOURCE", "Source Render", "Delete selected source render"),
            ("STYLE", "Style Reference", "Delete selected style image"),
            ("RESULT", "AI Result", "Delete selected AI result"),
        ],
        default="RESULT",
    )

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_render", None)
        if state is None:
            self.report({"ERROR"}, "AI Render state not available")
            return {"CANCELLED"}
        if self.target == "STYLE":
            path = Path(state.style_image_path or "")
        elif self.target == "RESULT":
            path = Path(state.result_image_path or "")
        else:
            path = Path(state.source_image_path or "")
        if not path.exists():
            self.report({"WARNING"}, "Selected image not found on disk")
            return {"CANCELLED"}
        try:
            path.unlink()
        except Exception as ex:
            self.report({"ERROR"}, f"Failed to delete image: {ex}")
            return {"CANCELLED"}
        if self.target == "STYLE":
            state.style_image_path = ""
        elif self.target == "RESULT":
            state.result_image_path = ""
            state.result_exists = False
        else:
            state.source_image_path = ""
            state.source_exists = False
        refresh_ai_render_assets(context, force=True)
        self.report({"INFO"}, f"Deleted {path.name}")
        return {"FINISHED"}


class LIME_OT_ai_render_delete_batch(Operator):
    bl_idname = "lime.ai_render_delete_batch"
    bl_label = "AI: Delete Image Batch"
    bl_options = {"REGISTER"}
    bl_description = "Delete all images from the selected AI folder (double confirmation)"

    target: EnumProperty(
        name="Target",
        items=[
            ("SOURCES", "Sources", "Delete all source renders"),
            ("STYLES", "Styles", "Delete all style references"),
            ("RESULTS", "Results", "Delete all AI results"),
            ("MANIFESTS", "Manifests", "Delete all AI manifests"),
        ],
        default="RESULTS",
    )

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_render", None)
        if state is None:
            self.report({"ERROR"}, "AI Render state not available")
            return {"CANCELLED"}
        now = time.monotonic()
        confirm_window = 10.0
        if state.delete_confirm_action != self.target or (now - state.delete_confirm_time) > confirm_window:
            state.delete_confirm_action = self.target
            state.delete_confirm_time = now
            self.report({"WARNING"}, "Run again within 10 seconds to confirm batch delete")
            return {"CANCELLED"}

        try:
            paths = _ensure_ai_dirs(context.window_manager.lime_pipeline)
        except Exception as ex:
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}

        if self.target == "SOURCES":
            folder = paths.sources_dir
        elif self.target == "STYLES":
            folder = paths.styles_dir
        elif self.target == "MANIFESTS":
            folder = paths.manifests_dir
        else:
            folder = paths.outputs_dir

        removed = 0
        targets = _list_manifests(folder) if self.target == "MANIFESTS" else _list_images(folder)
        for path in targets:
            try:
                path.unlink()
                removed += 1
            except Exception:
                continue

        if self.target == "SOURCES":
            state.source_image_path = ""
            state.source_exists = False
        elif self.target == "STYLES":
            state.style_image_path = ""
        elif self.target == "RESULTS":
            state.result_image_path = ""
            state.result_exists = False

        state.delete_confirm_action = ""
        state.delete_confirm_time = 0.0
        refresh_ai_render_assets(context, force=True)
        self.report({"INFO"}, f"Deleted {removed} image(s)")
        return {"FINISHED"}


def _find_image_editor_area(window) -> Optional[bpy.types.Area]:
    try:
        for area in window.screen.areas:
            if area.type == "IMAGE_EDITOR":
                return area
    except Exception:
        return None
    return None


def _ensure_window_region(area) -> Optional[bpy.types.Region]:
    try:
        for reg in area.regions:
            if reg.type == "WINDOW":
                return reg
    except Exception:
        return None
    return None


def _open_new_image_editor_area(context) -> tuple[Optional[bpy.types.Window], Optional[bpy.types.Area]]:
    wm = context.window_manager
    before = set(wm.windows)
    try:
        bpy.ops.wm.window_new("EXEC_DEFAULT")
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
    except Exception:
        return None, None
    after = set(wm.windows)
    new_windows = [w for w in after if w not in before]
    if not new_windows and wm.windows:
        new_windows = [wm.windows[-1]]
    if not new_windows:
        return None, None
    win = new_windows[0]
    if not win.screen.areas:
        return win, None
    area = win.screen.areas[0]
    try:
        area.type = "IMAGE_EDITOR"
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
    except Exception:
        return win, None
    return win, area


class LIME_OT_ai_render_open_preview(Operator):
    bl_idname = "lime.ai_render_open_preview"
    bl_label = "AI: Open Image Preview"
    bl_options = {"REGISTER"}
    bl_description = "Open the selected image in a large Image Editor view"

    target: EnumProperty(
        name="Target",
        items=[
            ("SOURCE", "Source Render", "Open selected source render"),
            ("STYLE", "Style Reference", "Open selected style reference"),
            ("RESULT", "AI Result", "Open selected AI result"),
        ],
        default="SOURCE",
    )

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_render", None)
        if state is None:
            self.report({"ERROR"}, "AI Render state not available")
            return {"CANCELLED"}
        if self.target == "STYLE":
            path = Path(state.style_image_path or "")
        elif self.target == "RESULT":
            path = Path(state.result_image_path or "")
        else:
            path = Path(state.source_image_path or "")
        if not path.exists():
            self.report({"ERROR"}, "Image not available")
            return {"CANCELLED"}
        try:
            image = bpy.data.images.load(path.as_posix(), check_existing=True)
        except Exception as ex:
            self.report({"ERROR"}, f"Failed to load image: {ex}")
            return {"CANCELLED"}
        win, area = _open_new_image_editor_area(context)
        if win is None or area is None:
            self.report({"ERROR"}, "Could not create an Image Editor window")
            return {"CANCELLED"}
        region = _ensure_window_region(area)
        if region is None:
            self.report({"ERROR"}, "Image Editor region not available")
            return {"CANCELLED"}
        try:
            with context.temp_override(window=win, screen=win.screen, area=area, region=region):
                space = area.spaces.active
                space.image = image
                space.use_image_pin = True
                area.tag_redraw()
        except Exception as ex:
            self.report({"ERROR"}, f"Failed to assign image: {ex}")
            return {"CANCELLED"}
        return {"FINISHED"}


class LIME_OT_ai_render_import_style(Operator):
    bl_idname = "lime.ai_render_import_style"
    bl_label = "AI: Import Style Image"
    bl_options = {"REGISTER"}
    bl_description = "Import a style reference image into the styles library"

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.webp;*.exr", options={"HIDDEN"})

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_render", None)
        if state is None:
            self.report({"ERROR"}, "AI Render state not available")
            return {"CANCELLED"}
        if not self.filepath:
            self.report({"ERROR"}, "No file selected")
            return {"CANCELLED"}
        src = Path(self.filepath)
        if not src.exists():
            self.report({"ERROR"}, "Selected file not found")
            return {"CANCELLED"}
        try:
            paths = _ensure_ai_dirs(context.window_manager.lime_pipeline)
        except Exception as ex:
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}
        try:
            saved = _persist_style_image(src, paths.styles_dir)
        except Exception as ex:
            self.report({"ERROR"}, f"Failed to import style: {ex}")
            return {"CANCELLED"}
        state.style_image_path = saved.as_posix()
        refresh_ai_render_assets(context, force=True)
        self.report({"INFO"}, f"Imported style: {saved.name}")
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


__all__ = [
    "register_ai_render_handlers",
    "unregister_ai_render_handlers",
    "LIME_OT_ai_render_refresh",
    "LIME_OT_ai_render_frame",
    "LIME_OT_ai_render_generate",
    "LIME_OT_ai_render_retry",
    "LIME_OT_ai_render_cancel",
    "LIME_OT_ai_render_test_connection",
    "LIME_OT_ai_render_add_to_sequencer",
    "LIME_OT_ai_render_open_outputs_folder",
    "LIME_OT_ai_render_delete_selected",
    "LIME_OT_ai_render_delete_batch",
    "LIME_OT_ai_render_open_preview",
    "LIME_OT_ai_render_import_style",
    "refresh_ai_render_assets",
]
