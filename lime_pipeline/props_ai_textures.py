"""AI Textures Organizer properties and state."""

from __future__ import annotations

import bpy
from bpy.types import PropertyGroup
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)


_SCAN_SCOPE_ITEMS = (
    ("ALL_SCENE", "All Scene", "Analyze textures used by all scene materials"),
    ("SELECTED_ONLY", "Selected Only", "Analyze textures used by selected objects"),
)

_ITEM_STATUS_ITEMS = (
    ("ANALYZED", "Analyzed", "Item analyzed"),
    ("AI_BLOCKED", "AI Blocked", "AI request failed or is unavailable"),
    ("REFINED", "Refined", "Item refined with AI and hint"),
    ("READY", "Ready", "Item is ready to apply"),
    ("APPLIED", "Applied", "Item was applied"),
    ("ERROR", "Error", "Item hit an error"),
    ("SKIPPED", "Skipped", "Item was skipped"),
)

_PHASE_ITEMS = (
    ("IDLE", "Idle", "No scan session yet"),
    ("ANALYZED", "Analyzed", "Analysis completed"),
    ("REFINED", "Refined", "Suggestions refined"),
    ("READY_TO_APPLY", "Ready to Apply", "At least one selected item is ready to apply"),
    ("APPLIED", "Applied", "Apply operation was completed"),
)


class LimeAITextureItem(PropertyGroup):
    item_id: StringProperty(name="Item ID", default="")
    selected_for_apply: BoolProperty(name="Apply", default=False)
    image_ref: PointerProperty(type=bpy.types.Image)
    image_name: StringProperty(name="Image Name", default="")
    raw_filepath: StringProperty(name="Raw Filepath", default="")
    abs_filepath: StringProperty(name="Absolute Filepath", default="")
    classification: StringProperty(name="Classification", default="")
    issue_summary: StringProperty(name="Issue Summary", default="")
    map_type: StringProperty(name="Map Type", default="Generic")
    materials_summary: StringProperty(name="Materials Summary", default="")
    socket_targets_json: StringProperty(name="Socket Targets", default="")
    hint_text: StringProperty(name="Hint", default="")
    initial_suggestion: StringProperty(name="Initial Suggestion", default="")
    refined_suggestion: StringProperty(name="Refined Suggestion", default="")
    final_filename: StringProperty(name="Final Filename", default="")
    dest_preview_path: StringProperty(name="Destination Preview", default="")
    status: EnumProperty(name="Status", items=_ITEM_STATUS_ITEMS, default="ANALYZED")
    last_error: StringProperty(name="Last Error", default="")
    read_only: BoolProperty(name="Read Only", default=True)


class LimeAITextureState(PropertyGroup):
    items: CollectionProperty(type=LimeAITextureItem)
    active_index: IntProperty(name="Active Row", default=0)
    scan_scope: EnumProperty(name="Scan Scope", items=_SCAN_SCOPE_ITEMS, default="ALL_SCENE")
    ai_include_preview: BoolProperty(
        name="AI Include Preview (low-res)",
        description="Send low-res preview content to OpenRouter when suggesting texture names",
        default=False,
    )
    phase: EnumProperty(name="Phase", items=_PHASE_ITEMS, default="IDLE")
    ai_blocked: BoolProperty(name="AI Blocked", default=False)
    is_busy: BoolProperty(name="Busy", default=False)
    last_error: StringProperty(name="Last Error", default="")

    total_count: IntProperty(name="Total", default=0)
    adoptable_count: IntProperty(name="Adoptable", default=0)
    protected_count: IntProperty(name="Protected", default=0)
    missing_count: IntProperty(name="Missing", default=0)
    selected_ready_count: IntProperty(name="Selected Ready", default=0)

    analysis_report_path: StringProperty(name="Analysis Report", default="")
    refine_report_path: StringProperty(name="Refine Report", default="")
    apply_manifest_path: StringProperty(name="Apply Manifest", default="")


def register():
    bpy.utils.register_class(LimeAITextureItem)
    bpy.utils.register_class(LimeAITextureState)
    bpy.types.Scene.lime_ai_textures = PointerProperty(type=LimeAITextureState)


def unregister():
    del bpy.types.Scene.lime_ai_textures
    bpy.utils.unregister_class(LimeAITextureState)
    bpy.utils.unregister_class(LimeAITextureItem)

