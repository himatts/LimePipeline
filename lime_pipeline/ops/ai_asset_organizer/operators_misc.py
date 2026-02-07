"""Misc/debug operators for AI Asset Organizer."""

from __future__ import annotations

import datetime

import bpy
from bpy.types import Operator

from ...core.ai_asset_prompt import schema_json_object
from ..ai_http import (
    OPENROUTER_CHAT_URL,
    OPENROUTER_MODELS_URL,
    extract_message_content,
    has_openrouter_api_key,
    http_get_json_with_status,
    http_post_json_with_status,
    openrouter_headers,
)
from .openrouter_client import DEFAULT_MODEL
from .planner import clear_preview_state


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
        state.last_used_collection_path = ""
        clear_preview_state(state)
        self.report({"INFO"}, "AI suggestions cleared")
        return {"FINISHED"}


class LIME_TB_OT_open_ai_asset_manager(Operator):
    bl_idname = "lime_tb.open_ai_asset_manager"
    bl_label = "Open AI Asset Manager"
    bl_description = "Open AI Asset Organizer in a larger popup window"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=885)

    def draw(self, context):
        from ...ui.ui_ai_asset_organizer import draw_ai_asset_organizer_content

        draw_ai_asset_organizer_content(self.layout, context, for_popup=True)

    def execute(self, context):
        self.report({"INFO"}, "AI Asset Manager opened")
        return {"FINISHED"}


class LIME_TB_OT_ai_asset_test_connection(Operator):
    bl_idname = "lime_tb.ai_asset_test_connection"
    bl_label = "AI: Test Connection"
    bl_description = "Verify OpenRouter connectivity for AI Asset Organizer"
    bl_options = {"REGISTER"}

    def execute(self, context):
        if not has_openrouter_api_key():
            self.report({"ERROR"}, "OpenRouter API key not found in .env")
            return {"CANCELLED"}

        prefs = context.preferences.addons[__package__.split(".")[0]].preferences
        headers = openrouter_headers(prefs)
        models_resp = http_get_json_with_status(OPENROUTER_MODELS_URL, headers=headers, timeout=15)
        data = models_resp.data if models_resp else None
        if not data or not isinstance(data, dict):
            detail = (models_resp.error or "No response body") if models_resp else "No response"
            status = models_resp.status if models_resp else None
            self.report({"ERROR"}, f"OpenRouter models check failed (status={status}): {detail[:220]}")
            return {"CANCELLED"}

        models = [m.get("id") for m in data.get("data", []) if isinstance(m, dict)] if "data" in data else []
        slug = (getattr(prefs, "openrouter_model", "") or "").strip()
        if slug and slug in models:
            self.report({"INFO"}, f"OpenRouter reachable. Model available: {slug}")
        elif slug:
            self.report({"WARNING"}, f"OpenRouter reachable. Model not found in provider list: {slug}")
        else:
            self.report({"INFO"}, "OpenRouter reachable.")

        payload = {
            "model": slug or DEFAULT_MODEL,
            "messages": [
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": '{"ping": true}'},
            ],
            "temperature": 0,
            "max_tokens": 128,
            "response_format": schema_json_object(),
        }
        chat_resp = http_post_json_with_status(OPENROUTER_CHAT_URL, payload, headers=headers, timeout=20)
        result = chat_resp.data if chat_resp else None
        content = extract_message_content(result or {}) if result else None
        if content:
            self.report({"INFO"}, "OpenRouter chat endpoint: OK")
        else:
            status = chat_resp.status if chat_resp else None
            detail = (chat_resp.error or "No response body") if chat_resp else "No response"
            self.report({"WARNING"}, f"OpenRouter chat endpoint incomplete (status={status}): {detail[:180]}")
        return {"FINISHED"}


class LIME_TB_OT_ai_asset_material_debug_report(Operator):
    bl_idname = "lime_tb.ai_asset_material_debug_report"
    bl_label = "AI: Material Debug Report"
    bl_description = "Export a material AI/normalization debug report to a Blender text block"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = getattr(context, "scene", None)
        state = getattr(scene, "lime_ai_assets", None) if scene is not None else None
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}

        rows = [row for row in list(getattr(state, "items", []) or []) if getattr(row, "item_type", "") == "MATERIAL"]
        if not rows:
            self.report({"INFO"}, "No material rows available for debug report")
            return {"CANCELLED"}

        lines = [
            "Lime Pipeline - AI Material Normalization Debug Report",
            f"Generated: {datetime.datetime.now().isoformat(timespec='seconds')}",
            f"Rows: {len(rows)}",
            "",
            "material_original | ai_output_raw | final_after_normalization | status | normalization_changed | notes",
        ]
        for row in rows:
            lines.append(
                " | ".join(
                    [
                        str(getattr(row, "original_name", "") or "").replace("\n", " ").strip(),
                        str(getattr(row, "ai_raw_name", "") or "").replace("\n", " ").strip(),
                        str(getattr(row, "suggested_name", "") or "").replace("\n", " ").strip(),
                        str(getattr(row, "status", "") or "").strip(),
                        str(bool(getattr(row, "normalization_changed", False))),
                        str(getattr(row, "normalization_notes", "") or "").replace("\n", " ").strip(),
                    ]
                )
            )

        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        text_name = f"AI_Material_Debug_{stamp}.txt"
        text_block = bpy.data.texts.new(text_name)
        text_block.write("\n".join(lines) + "\n")
        self.report({"INFO"}, f"Debug report created: {text_name}")
        return {"FINISHED"}


class LIME_TB_OT_ai_asset_collection_debug_report(Operator):
    bl_idname = "lime_tb.ai_asset_collection_debug_report"
    bl_label = "AI: Collection Debug Report"
    bl_description = "Export a collection target resolution debug report to a Blender text block"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = getattr(context, "scene", None)
        state = getattr(scene, "lime_ai_assets", None) if scene is not None else None
        if state is None:
            self.report({"ERROR"}, "AI Asset Organizer state is unavailable")
            return {"CANCELLED"}

        rows = [row for row in list(getattr(state, "items", []) or []) if getattr(row, "item_type", "") == "OBJECT"]
        if not rows:
            self.report({"INFO"}, "No object rows available for collection debug report")
            return {"CANCELLED"}

        lines = [
            "Lime Pipeline - AI Collection Resolution Debug Report",
            f"Generated: {datetime.datetime.now().isoformat(timespec='seconds')}",
            f"Rows: {len(rows)}",
            "",
            "object | selected_path | status | confidence | debug_json",
        ]
        for row in rows:
            lines.append(
                " | ".join(
                    [
                        str(getattr(row, "original_name", "") or "").replace("\n", " ").strip(),
                        str(getattr(row, "target_collection_path", "") or "").replace("\n", " ").strip(),
                        str(getattr(row, "target_status", "") or "").strip(),
                        f"{float(getattr(row, 'target_confidence', 0.0) or 0.0):.3f}",
                        str(getattr(row, "target_debug_json", "") or "").replace("\n", " ").strip(),
                    ]
                )
            )

        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        text_name = f"AI_Collection_Debug_{stamp}.txt"
        text_block = bpy.data.texts.new(text_name)
        text_block.write("\n".join(lines) + "\n")
        self.report({"INFO"}, f"Collection debug report created: {text_name}")
        return {"FINISHED"}


__all__ = [
    "LIME_TB_OT_ai_asset_clear",
    "LIME_TB_OT_open_ai_asset_manager",
    "LIME_TB_OT_ai_asset_test_connection",
    "LIME_TB_OT_ai_asset_material_debug_report",
    "LIME_TB_OT_ai_asset_collection_debug_report",
]
