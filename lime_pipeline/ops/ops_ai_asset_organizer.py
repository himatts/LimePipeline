"""AI Asset Organizer Operators.

Suggests clear names for selected objects and their materials using OpenRouter.
The workflow is intentionally user-controlled: suggestions are reviewed in a panel
and only applied when the user confirms.
"""

from __future__ import annotations

import base64
import json
import os
import threading
from typing import Dict, List, Optional, Tuple, Any

import bpy
from bpy.types import Material, Object, Operator

from ..core.asset_naming import (
    bump_material_version_until_unique,
    ensure_unique_object_name,
    is_valid_object_name,
    normalize_object_name,
)
from ..core.material_naming import ALLOWED_MATERIAL_TYPES, parse_name as parse_material_name
from ..props_ai_assets import LimeAIAssetItem
from .ai_http import (
    OPENROUTER_CHAT_URL,
    extract_message_content,
    http_post_json,
    openrouter_headers,
    parse_json_from_text,
)


_DEFAULT_MODEL = "google/gemini-2.0-flash-lite-001"
_MAX_IMAGE_BYTES = 3 * 1024 * 1024


def _image_mime_for_path(path: str) -> Optional[str]:
    ext = (os.path.splitext(path)[1] or "").lower()
    if ext in {".png"}:
        return "image/png"
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext in {".webp"}:
        return "image/webp"
    return None


def _load_image_data_url(path: str) -> Tuple[Optional[str], Optional[str]]:
    if not path:
        return None, None
    mime = _image_mime_for_path(path)
    if not mime:
        return None, "Unsupported image format (use PNG/JPG/WebP)"
    try:
        size = os.path.getsize(path)
        if size <= 0:
            return None, "Image file is empty"
        if size > _MAX_IMAGE_BYTES:
            return None, f"Image too large ({size} bytes). Max {_MAX_IMAGE_BYTES} bytes."
    except Exception as ex:
        return None, f"Cannot read image size: {ex}"
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        if not raw:
            return None, "Image file is empty"
        encoded = base64.b64encode(raw).decode("ascii")
        return f"data:{mime};base64,{encoded}", None
    except Exception as ex:
        return None, f"Failed to read image: {ex}"


def _addon_prefs(context) -> Optional[Any]:
    try:
        return context.preferences.addons[__package__.split(".")[0]].preferences
    except Exception:
        return None


def _schema_json_object() -> Dict[str, object]:
    # Fallback for providers that don't support json_schema structured outputs
    return {"type": "json_object"}


def _schema_assets() -> Dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ai_asset_namer",
            "strict": True,
            "schema": {
                "type": "object",
                "required": ["items"],
                "additionalProperties": False,
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["id", "name"],
                            "additionalProperties": False,
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    }


def _is_object_read_only(obj: Object) -> bool:
    return bool(getattr(obj, "library", None) or getattr(obj, "override_library", None))


def _is_material_read_only(mat: Material) -> bool:
    return bool(getattr(mat, "library", None) or getattr(mat, "override_library", None))


def _collect_selection(context) -> Tuple[List[Object], List[Material]]:
    objects = list(getattr(context, "selected_objects", None) or [])
    materials: List[Material] = []
    seen = set()
    for obj in objects:
        for slot in getattr(obj, "material_slots", []) or []:
            mat = getattr(slot, "material", None)
            if mat is None:
                continue
            if mat.as_pointer() in seen:
                continue
            seen.add(mat.as_pointer())
            materials.append(mat)
    return objects, materials


def _build_prompt(context_text: str, objects: List[Dict[str, object]], materials: List[Dict[str, object]]) -> str:
    allowed_types = ", ".join(ALLOWED_MATERIAL_TYPES)
    context_block = (context_text or "").strip()
    if context_block:
        context_block = f"Context: {context_block}\n"

    payload = {
        "objects": objects,
        "materials": materials,
    }

    compact_json = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))

    return (
        "Return ONLY JSON per schema.\n"
        f"{context_block}"
        "Rules:\n"
        "- Objects: CamelCase ASCII alphanumeric, no spaces/underscores/dots/dashes, no shot/scene prefixes.\n"
        "- Materials: MAT_{SceneTag?}_{MaterialType}_{Finish}_{V##}. SceneTag optional.\n"
        f"- MaterialType must be one of: {allowed_types}.\n"
        "- Finish CamelCase alphanumeric; Version V01..V99.\n"
        "- Names must be unique per category.\n"
        "Items JSON:\n"
        f"{compact_json}\n"
    )


def _parse_items_from_response(parsed: Optional[Dict[str, object]]) -> Optional[List[Dict[str, object]]]:
    if not isinstance(parsed, dict):
        return None
    items = parsed.get("items")
    if isinstance(items, list):
        return items
    objects = parsed.get("objects")
    materials = parsed.get("materials")
    if isinstance(objects, list) or isinstance(materials, list):
        combined: List[Dict[str, object]] = []
        if isinstance(objects, list):
            combined.extend(objects)
        if isinstance(materials, list):
            combined.extend(materials)
        return combined if combined else None
    return None


def _openrouter_suggest(
    headers: Dict[str, str],
    model: str,
    prompt: str,
    *,
    timeout: int = 60,
    debug: bool = False,
    image_data_url: Optional[str] = None,
) -> Tuple[Optional[List[Dict[str, object]]], Optional[str], Optional[str]]:
    if image_data_url:
        user_content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]
    else:
        user_content = prompt

    messages = [
        {
            "role": "system",
            "content": "You rename Blender assets and must output strict JSON only.",
        },
        {"role": "user", "content": user_content},
    ]

    payload: Dict[str, object] = {
        "model": model or _DEFAULT_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 800,
        "response_format": _schema_assets(),
    }

    if debug:
        try:
            print("[AI Asset Organizer] OpenRouter model:", payload.get("model"))
            print("[AI Asset Organizer] Prompt chars:", len(prompt or ""))
            if image_data_url:
                print("[AI Asset Organizer] Image attached (data URL length):", len(image_data_url))
            print("[AI Asset Organizer] Prompt preview:\n", (prompt or "")[:2000])
            print("[AI Asset Organizer] Response format:", payload.get("response_format"))
        except Exception:
            pass

    result = http_post_json(OPENROUTER_CHAT_URL, payload, headers=headers, timeout=timeout)
    finish_reason = None
    try:
        finish_reason = (result or {}).get("choices", [{}])[0].get("finish_reason")
    except Exception:
        finish_reason = None
    if debug:
        try:
            print("[AI Asset Organizer] Raw response keys:", list((result or {}).keys()))
            print("[AI Asset Organizer] Raw response:", result)
        except Exception:
            pass
    text = extract_message_content(result or {}) if result else None
    if not text:
        try:
            choice = (result or {}).get("choices", [{}])[0]
            finish_reason = choice.get("finish_reason")
            if finish_reason:
                return None, f"Model returned no content (finish_reason={finish_reason}). Try a model that supports JSON output or reduce selection size."
        except Exception:
            pass
    parsed = parse_json_from_text(text or "") if text else None
    items = _parse_items_from_response(parsed) if parsed else None
    if items:
        return items, None, finish_reason

    # Fallback: request json_object and parse message text
    payload_fallback = dict(payload)
    payload_fallback["response_format"] = _schema_json_object()
    result2 = http_post_json(OPENROUTER_CHAT_URL, payload_fallback, headers=headers, timeout=timeout)
    finish_reason2 = None
    try:
        finish_reason2 = (result2 or {}).get("choices", [{}])[0].get("finish_reason")
    except Exception:
        finish_reason2 = None
    if debug:
        try:
            print("[AI Asset Organizer] Raw fallback response keys:", list((result2 or {}).keys()))
            print("[AI Asset Organizer] Raw fallback response:", result2)
        except Exception:
            pass
    text2 = extract_message_content(result2 or {}) if result2 else None
    parsed2 = parse_json_from_text(text2 or "") if text2 else None
    items2 = _parse_items_from_response(parsed2) if parsed2 else None
    if items2:
        return items2, None, finish_reason2

    return None, "AI response was not valid JSON for the expected schema", finish_reason2 or finish_reason


class LIME_TB_OT_ai_asset_suggest_names(Operator):
    bl_idname = "lime_tb.ai_asset_suggest_names"
    bl_label = "AI: Suggest Names"
    bl_description = "Suggest clearer names for selected objects and their materials using OpenRouter"
    bl_options = {"REGISTER"}

    _thread: Optional[threading.Thread] = None
    _timer = None
    _result: Optional[Dict[str, object]] = None
    _error: Optional[str] = None
    _id_map: Dict[str, Dict[str, object]] = {}

    def _finish(self, context) -> None:
        wm = context.window_manager
        try:
            if self._timer is not None:
                wm.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = None

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}

        prefs = _addon_prefs(context)
        if prefs is None:
            self.report({"ERROR"}, "Addon preferences unavailable")
            return {"CANCELLED"}

        if not (getattr(prefs, "openrouter_api_key", "") or "").strip():
            self.report({"ERROR"}, "OpenRouter API key not set in Preferences")
            return {"CANCELLED"}

        objects, materials = _collect_selection(context)
        if not objects:
            self.report({"ERROR"}, "No objects selected")
            return {"CANCELLED"}

        # Build request payload and ID mapping (no Blender API usage in the worker thread)
        obj_items: List[Dict[str, object]] = []
        mat_items: List[Dict[str, object]] = []
        self._id_map = {}

        for idx, obj in enumerate(objects[:60]):
            token = f"obj_{idx}"
            obj_items.append(
                {
                    "id": token,
                    "name": obj.name,
                    "type": getattr(obj, "type", ""),
                }
            )
            self._id_map[token] = {
                "item_type": "OBJECT",
                "object_ref": obj,
                "material_ref": None,
                "original_name": obj.name,
                "read_only": _is_object_read_only(obj),
            }

        mat_usage: Dict[int, List[str]] = {}
        for obj in objects:
            for slot in getattr(obj, "material_slots", []) or []:
                mat = getattr(slot, "material", None)
                if mat is None:
                    continue
                key = mat.as_pointer()
                mat_usage.setdefault(key, [])
                if obj.name not in mat_usage[key]:
                    mat_usage[key].append(obj.name)

        for idx, mat in enumerate(materials[:60]):
            token = f"mat_{idx}"
            used_on = mat_usage.get(mat.as_pointer(), [])
            entry = {
                "id": token,
                "name": mat.name,
            }
            if used_on:
                entry["used_on"] = used_on[:3]
            mat_items.append(entry)
            self._id_map[token] = {
                "item_type": "MATERIAL",
                "object_ref": None,
                "material_ref": mat,
                "original_name": mat.name,
                "read_only": _is_material_read_only(mat),
            }

        if len(objects) > 60 or len(materials) > 60:
            self.report({"WARNING"}, "Selection is large; only the first 60 objects/materials are sent to AI")

        prompt = _build_prompt(getattr(state, "context", ""), obj_items, mat_items)
        headers = openrouter_headers(prefs)
        model = (getattr(prefs, "openrouter_model", "") or "").strip() or _DEFAULT_MODEL
        debug = bool(getattr(prefs, "openrouter_debug", False))
        image_data_url = None
        if getattr(state, "use_image_context", False):
            raw_path = (getattr(state, "image_path", "") or "").strip()
            if raw_path:
                resolved = bpy.path.abspath(raw_path)
                image_data_url, image_err = _load_image_data_url(resolved)
                if image_err:
                    self.report({"WARNING"}, image_err)
                    if debug:
                        print("[AI Asset Organizer] Image skipped:", image_err)
            else:
                if debug:
                    print("[AI Asset Organizer] Image context enabled but no image path set")

        # Reset state (UI can show busy status)
        state.is_busy = True
        state.last_error = ""
        state.items.clear()

        self._result = None
        self._error = None

        def worker():
            try:
                total_items = len(obj_items) + len(mat_items)
                items, err, finish_reason = _openrouter_suggest(
                    headers,
                    model,
                    prompt,
                    timeout=60,
                    debug=debug,
                    image_data_url=image_data_url,
                )

                def _needs_chunking(item_list: Optional[List[Dict[str, object]]], reason: Optional[str]) -> bool:
                    if item_list is None:
                        return True
                    if reason and str(reason).lower() in {"length", "max_tokens", "stop_length"}:
                        return True
                    if len(item_list) < total_items:
                        return True
                    return False

                if err or _needs_chunking(items, finish_reason):
                    if debug:
                        print("[AI Asset Organizer] Falling back to chunked requests")
                    combined: List[Tuple[str, Dict[str, object]]] = []
                    for obj in obj_items:
                        combined.append(("objects", obj))
                    for mat in mat_items:
                        combined.append(("materials", mat))

                    chunk_size = 15
                    by_id: Dict[str, str] = {}
                    chunk_errors: List[str] = []
                    for i in range(0, len(combined), chunk_size):
                        chunk = combined[i : i + chunk_size]
                        chunk_objects = [item for kind, item in chunk if kind == "objects"]
                        chunk_materials = [item for kind, item in chunk if kind == "materials"]
                        chunk_prompt = _build_prompt(getattr(state, "context", ""), chunk_objects, chunk_materials)
                        chunk_items, chunk_err, _ = _openrouter_suggest(
                            headers,
                            model,
                            chunk_prompt,
                            timeout=60,
                            debug=debug,
                            image_data_url=image_data_url,
                        )
                        if chunk_err:
                            chunk_errors.append(chunk_err)
                            continue
                        if not chunk_items:
                            chunk_errors.append("Chunk returned no items")
                            continue
                        for entry in chunk_items:
                            if not isinstance(entry, dict):
                                continue
                            item_id = entry.get("id")
                            name = entry.get("name")
                            if isinstance(item_id, str) and isinstance(name, str):
                                by_id[item_id] = name

                    if by_id:
                        items = [{"id": k, "name": v} for k, v in by_id.items()]
                        err = None
                    else:
                        err = "; ".join(chunk_errors) if chunk_errors else err

                if err:
                    self._result = None
                    self._error = err
                    return

                self._result = {"items": items or []}
                self._error = None
            except Exception as ex:
                self._result = None
                self._error = str(ex)

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.2, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self._finish(context)
            return {"CANCELLED"}

        if event.type == "ESC":
            state.is_busy = False
            state.last_error = "Cancelled by user"
            self._finish(context)
            return {"CANCELLED"}

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if self._thread and self._thread.is_alive():
            return {"PASS_THROUGH"}

        # Thread completed
        self._finish(context)
        state.is_busy = False

        if self._error:
            state.last_error = str(self._error)
            self.report({"ERROR"}, str(self._error))
            return {"CANCELLED"}

        data = self._result or {}
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            state.last_error = "AI response did not include 'items'"
            self.report({"ERROR"}, state.last_error)
            return {"CANCELLED"}

        by_id: Dict[str, str] = {}
        for entry in items:
            if not isinstance(entry, dict):
                continue
            item_id = entry.get("id")
            name = entry.get("name")
            if isinstance(item_id, str) and isinstance(name, str):
                by_id[item_id] = name

        # Write rows in stable order
        for item_id, info in self._id_map.items():
            row: LimeAIAssetItem = state.items.add()
            row.item_type = str(info.get("item_type") or "OBJECT")
            row.object_ref = info.get("object_ref")
            row.material_ref = info.get("material_ref")
            row.original_name = str(info.get("original_name") or "")
            row.read_only = bool(info.get("read_only") or False)

            suggested_raw = (by_id.get(item_id) or "").strip()
            if row.item_type == "OBJECT":
                suggested_norm = normalize_object_name(suggested_raw) if suggested_raw else ""
                row.suggested_name = suggested_norm
                if suggested_raw and suggested_norm != suggested_raw:
                    row.status = "NORMALIZED"
                elif suggested_norm and not is_valid_object_name(suggested_norm):
                    row.status = "INVALID"
                else:
                    row.status = ""
            else:
                row.suggested_name = suggested_raw
                row.status = "" if (not suggested_raw or parse_material_name(suggested_raw)) else "INVALID"

            row.selected_for_apply = bool(not row.read_only and bool(row.suggested_name))

        self.report({"INFO"}, f"AI suggestions created: {len(state.items)} item(s)")
        return {"FINISHED"}


class LIME_TB_OT_ai_asset_apply_names(Operator):
    bl_idname = "lime_tb.ai_asset_apply_names"
    bl_label = "AI: Apply Names"
    bl_description = "Apply selected AI rename suggestions to objects and materials"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}

        if getattr(state, "is_busy", False):
            self.report({"WARNING"}, "AI request in progress")
            return {"CANCELLED"}

        obj_existing = {o.name for o in bpy.data.objects}
        mat_existing = {m.name for m in bpy.data.materials}

        renamed_objects = 0
        renamed_materials = 0
        skipped = 0

        for row in list(getattr(state, "items", []) or []):
            if not getattr(row, "selected_for_apply", False):
                continue
            if getattr(row, "read_only", False):
                skipped += 1
                continue

            suggested = (getattr(row, "suggested_name", "") or "").strip()
            if not suggested:
                skipped += 1
                continue

            if getattr(row, "item_type", "OBJECT") == "OBJECT":
                obj = getattr(row, "object_ref", None)
                if obj is None:
                    skipped += 1
                    continue
                old = obj.name
                obj_existing.discard(old)
                normalized = normalize_object_name(suggested)
                unique = ensure_unique_object_name(normalized, obj_existing)
                try:
                    obj.name = unique
                    obj_existing.add(unique)
                    renamed_objects += 1
                except Exception as ex:
                    obj_existing.add(old)
                    skipped += 1
                    self.report({"WARNING"}, f"Failed to rename object '{old}': {ex}")
            else:
                mat = getattr(row, "material_ref", None)
                if mat is None:
                    skipped += 1
                    continue
                old = mat.name
                mat_existing.discard(old)
                if not parse_material_name(suggested):
                    mat_existing.add(old)
                    skipped += 1
                    self.report({"WARNING"}, f"Invalid material name: '{suggested}'")
                    continue
                unique = bump_material_version_until_unique(mat_existing, suggested)
                try:
                    mat.name = unique
                    mat_existing.add(unique)
                    renamed_materials += 1
                except Exception as ex:
                    mat_existing.add(old)
                    skipped += 1
                    self.report({"WARNING"}, f"Failed to rename material '{old}': {ex}")

        self.report(
            {"INFO"},
            f"Applied: {renamed_objects} object(s), {renamed_materials} material(s). Skipped: {skipped}.",
        )
        return {"FINISHED"}


class LIME_TB_OT_ai_asset_clear(Operator):
    bl_idname = "lime_tb.ai_asset_clear"
    bl_label = "AI: Clear"
    bl_description = "Clear AI rename suggestions"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        state = getattr(scene, "lime_ai_assets", None)
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}
        if getattr(state, "is_busy", False):
            self.report({"WARNING"}, "AI request in progress")
            return {"CANCELLED"}
        state.items.clear()
        state.last_error = ""
        self.report({"INFO"}, "AI suggestions cleared")
        return {"FINISHED"}


__all__ = [
    "LIME_TB_OT_ai_asset_suggest_names",
    "LIME_TB_OT_ai_asset_apply_names",
    "LIME_TB_OT_ai_asset_clear",
]
