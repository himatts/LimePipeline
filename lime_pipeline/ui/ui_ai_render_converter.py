"""
UI panel for AI Render Converter.
"""

from __future__ import annotations

from pathlib import Path
import time
import bpy
from bpy.types import Panel


class LIME_PT_ai_render_converter(Panel):
    bl_label = "AI Render Converter"
    bl_idname = "LIME_PT_ai_render_converter"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lime Pipeline"
    bl_order = 4
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        state = getattr(scene, "lime_ai_render", None)
        if state is None:
            layout.label(text="AI Render state not available", icon="ERROR")
            return

        header = layout.row(align=True)
        header.label(text=f"Frame: {int(getattr(scene, 'frame_current', 0) or 0)}")
        header.operator("lime.ai_render_refresh", text="", icon="FILE_REFRESH")

        source_box = layout.box()
        source_box.label(text="Source Render", icon="RENDER_STILL")

        render_row = source_box.row(align=True)
        render_text = "Re-render Frame" if state.source_exists else "Render Current Frame"
        render_row.operator("lime.ai_render_frame", text=render_text, icon="RENDER_STILL")

        source_row = source_box.row(align=True)
        source_row.label(text="Found" if state.source_exists else "Missing", icon="CHECKMARK" if state.source_exists else "ERROR")

        source_path = (state.source_image_path or "").strip()
        if source_path:
            source_row.label(text=Path(source_path).name)
            source_row.operator("lime.show_text", text="", icon="INFO").text = source_path

        source_grid = source_box.column(align=True)
        if getattr(state, "source_assets_count", 0) > 0:
            source_grid.template_icon_view(state, "source_pick", show_labels=False, scale=6)
        else:
            source_grid.label(text="No source renders found", icon="IMAGE_DATA")
        source_preview_row = source_box.row(align=True)
        source_preview_row.enabled = bool(state.source_image_path)
        source_preview_row.operator("lime.ai_render_open_preview", text="Open Large Preview", icon="FULLSCREEN_ENTER").target = "SOURCE"
        source_delete_row = source_box.row(align=True)
        source_delete_row.enabled = bool(state.source_image_path)
        source_delete_row.operator("lime.ai_render_delete_selected", text="Delete Selected", icon="TRASH").target = "SOURCE"

        style_box = layout.box()
        style_box.label(text="Style Reference", icon="IMAGE_DATA")
        style_import_row = style_box.row(align=True)
        style_import_row.operator("lime.ai_render_import_style", text="Import Style", icon="FILEBROWSER")
        style_grid = style_box.column(align=True)
        if getattr(state, "style_assets_count", 0) > 0:
            style_grid.template_icon_view(state, "style_pick", show_labels=False, scale=6)
        else:
            style_grid.label(text="No styles in library", icon="IMAGE_DATA")
        style_preview_row = style_box.row(align=True)
        style_preview_row.enabled = bool(state.style_image_path)
        style_preview_row.operator("lime.ai_render_open_preview", text="Open Large Preview", icon="FULLSCREEN_ENTER").target = "STYLE"
        style_delete_row = style_box.row(align=True)
        style_delete_row.enabled = bool(state.style_image_path)
        style_delete_row.operator("lime.ai_render_delete_selected", text="Delete Selected", icon="TRASH").target = "STYLE"
        style_box.prop(state, "style_image_path", text="Style Path")

        mode_box = layout.box()
        mode_box.label(text="Conversion Mode", icon="MODIFIER")
        mode_box.prop(state, "mode", expand=True)
        if state.mode == "SKETCH_PLUS":
            details_row = mode_box.row(align=True)
            details_row.prop(state, "detail_text", text="Details")
            if state.detail_text:
                details_row.operator("lime.show_text", text="", icon="INFO").text = state.detail_text
            mode_box.prop(state, "rewrite_with_llm", text="Rewrite with LLM")
            if state.rewrite_with_llm:
                mode_box.prop(state, "llm_use_style_reference", text="Use Style Reference in LLM")
            if state.detail_text_optimized:
                opt_row = mode_box.row(align=True)
                opt_row.label(text=f"Optimized: {state.detail_text_optimized[:60]}")
                opt_row.operator("lime.show_text", text="", icon="INFO").text = state.detail_text_optimized

        actions = layout.box()
        actions.label(text="Actions", icon="PLAY")
        actions.prop(state, "retry_strategy", text="Retry Strategy")

        btn_row = actions.row(align=True)
        btn_row.enabled = state.source_exists and not state.is_busy
        btn_row.operator("lime.ai_render_generate", text="Generate", icon="PLAY")

        retry_row = actions.row(align=True)
        retry_row.enabled = bool(state.last_prompt) and not state.is_busy
        retry_row.operator("lime.ai_render_retry", text="Retry", icon="FILE_REFRESH")

        cancel_row = actions.row(align=True)
        cancel_row.enabled = bool(state.is_busy)
        cancel_row.operator("lime.ai_render_cancel", text="Cancel Job", icon="CANCEL")

        status_box = layout.box()
        status_box.label(text="Status", icon="INFO")
        status = state.job_status
        status_icon_map = {
            "IDLE": "BLANK1",
            "UPLOADING": "IMPORT",
            "QUEUED": "TIME",
            "PROCESSING": "FILE_REFRESH",
            "COMPLETED": "CHECKMARK",
            "FAILED": "ERROR",
            "CANCELLED": "CANCEL",
        }
        status_icon = status_icon_map.get(status, "INFO")
        status_row = status_box.row(align=True)
        if status in {"FAILED", "CANCELLED"}:
            status_row.alert = True
        status_row.label(text=f"{status}: {state.job_message or ''}".strip(), icon=status_icon)
        if state.last_error:
            status_box.label(text=state.last_error, icon="ERROR")

        result_box = layout.box()
        result_box.label(text="AI Result", icon="IMAGE_DATA")
        result_grid = result_box.column(align=True)
        if getattr(state, "result_assets_count", 0) > 0:
            result_grid.template_icon_view(state, "result_pick", show_labels=False, scale=6)
        else:
            result_grid.label(text="No results yet", icon="IMAGE_DATA")
        result_preview_row = result_box.row(align=True)
        result_preview_row.enabled = bool(state.result_image_path)
        result_preview_row.operator("lime.ai_render_open_preview", text="Open Large Preview", icon="FULLSCREEN_ENTER").target = "RESULT"

        add_row = result_box.row(align=True)
        add_row.enabled = bool(state.result_exists)
        add_row.operator("lime.ai_render_add_to_sequencer", text="Add to Sequencer", icon="IMAGE_DATA")
        result_delete_row = result_box.row(align=True)
        result_delete_row.enabled = bool(state.result_image_path)
        result_delete_row.operator("lime.ai_render_delete_selected", text="Delete Selected", icon="TRASH").target = "RESULT"

        manage_box = layout.box()
        manage_box.label(text="Manage AI Images", icon="TRASH")
        now = time.monotonic()
        confirm_target = getattr(state, "delete_confirm_action", "") or ""
        confirm_time = float(getattr(state, "delete_confirm_time", 0.0) or 0.0)
        confirm_active = bool(confirm_target and (now - confirm_time) <= 10.0)
        if confirm_active:
            manage_box.label(text="Confirm batch delete (10s window)", icon="ERROR")
        batch_row = manage_box.row(align=True)
        batch_row.alert = confirm_active and confirm_target == "SOURCES"
        batch_row.operator("lime.ai_render_delete_batch", text="Delete All Sources", icon="TRASH").target = "SOURCES"
        batch_row = manage_box.row(align=True)
        batch_row.alert = confirm_active and confirm_target == "STYLES"
        batch_row.operator("lime.ai_render_delete_batch", text="Delete All Styles", icon="TRASH").target = "STYLES"
        batch_row = manage_box.row(align=True)
        batch_row.alert = confirm_active and confirm_target == "RESULTS"
        batch_row.operator("lime.ai_render_delete_batch", text="Delete All Results", icon="TRASH").target = "RESULTS"


__all__ = [
    "LIME_PT_ai_render_converter",
]
