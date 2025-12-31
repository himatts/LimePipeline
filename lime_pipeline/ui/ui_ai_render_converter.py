"""
UI panel for AI Render Converter.
"""

from __future__ import annotations

from pathlib import Path
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

        source_row = source_box.row(align=True)
        source_row.label(text="Found" if state.source_exists else "Missing", icon="CHECKMARK" if state.source_exists else "ERROR")

        source_path = (state.source_image_path or "").strip()
        if source_path:
            source_row.label(text=Path(source_path).name)

        render_row = source_box.row(align=True)
        render_text = "Re-render Frame" if state.source_exists else "Render Current Frame"
        render_row.operator("lime.ai_render_frame", text=render_text, icon="RENDER_STILL")

        if state.source_image:
            source_box.template_ID_preview(state, "source_image", hide_buttons=True)
        else:
            source_box.label(text="No preview available", icon="IMAGE_DATA")

        style_box = layout.box()
        style_box.label(text="Style Reference", icon="IMAGE_DATA")
        style_box.prop(state, "style_image_path", text="")
        if state.style_image:
            style_box.template_ID_preview(state, "style_image", hide_buttons=True)
        else:
            style_box.label(text="No style image selected", icon="IMAGE_DATA")

        mode_box = layout.box()
        mode_box.label(text="Conversion Mode", icon="MODIFIER")
        mode_box.prop(state, "mode", expand=True)
        if state.mode == "SKETCH_PLUS":
            mode_box.prop(state, "detail_text", text="Details")
            mode_box.prop(state, "rewrite_with_llm", text="Rewrite with LLM")
            if state.detail_text_optimized:
                mode_box.label(text=f"Optimized: {state.detail_text_optimized[:60]}")

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

        test_row = actions.row(align=True)
        test_row.operator("lime.ai_render_test_connection", text="Test Krea Connection", icon="CHECKMARK")

        status_box = layout.box()
        status_box.label(text="Status", icon="INFO")
        status_box.label(text=f"{state.job_status}: {state.job_message or ''}".strip())
        if state.last_error:
            status_box.label(text=state.last_error, icon="ERROR")

        result_box = layout.box()
        result_box.label(text="AI Result", icon="IMAGE_DATA")
        if state.result_image:
            result_box.template_ID_preview(state, "result_image", hide_buttons=True)
        else:
            result_box.label(text="No result yet", icon="IMAGE_DATA")

        add_row = result_box.row(align=True)
        add_row.enabled = bool(state.result_exists)
        add_row.operator("lime.ai_render_add_to_sequencer", text="Add to Sequencer", icon="IMAGE_DATA")


__all__ = [
    "LIME_PT_ai_render_converter",
]
