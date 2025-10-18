"""
AI Material Properties and State Management

This module defines the property groups and state management for the AI Material
Renamer feature within Lime Pipeline. It handles material scanning results,
rename proposals, and user selection state for batch material operations.

The AI material system provides a complete workflow for analyzing existing materials,
proposing improved names based on AI analysis, and applying the approved changes.
The property system manages material metadata, rename proposals, and user selection
states throughout the renaming workflow.

Key Features:
- Material scan results storage with rename proposals and status tracking
- Selection management for batch operations on large material sets
- Integration with Lime Pipeline naming conventions and validation
- Status categorization (VALID, NEEDS_RENAME, etc.) for workflow management
- Read-only material detection for library and linked materials
- Dynamic selection updates with automatic preview refresh
- Support for material type and finish classification
"""

import bpy
from importlib import import_module
from bpy.types import PropertyGroup
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)


def _selected_for_apply_update(self, context):
    try:
        ops_module = import_module("lime_pipeline.ops.ops_ai_material_renamer")
    except Exception:
        return

    if getattr(ops_module, "_SELECTION_REFRESH_SUSPENDED", False):
        return

    scene = getattr(context, "scene", None) if context else None
    if scene is None:
        try:
            scene = bpy.context.scene  # type: ignore[attr-defined]
        except Exception:
            scene = None
    if scene is None:
        return

    try:
        ops_module.refresh_selection_preview(scene)
    except Exception:
        pass


class LimeAIMatRow(PropertyGroup):
    material_name: StringProperty(name="Material ID")
    proposed_name: StringProperty(name="Proposed")
    original_proposal: StringProperty(name="Original Proposal", default="", description="Original AI proposal before any normalization")
    material_type: StringProperty(name="Material Type", default="Plastic")
    finish: StringProperty(name="Finish", default="Generic")
    version_token: StringProperty(name="Version", default="V01")
    similar_group_id: StringProperty(name="Group")
    status: StringProperty(name="Status", default="")
    read_only: BoolProperty(name="Read Only", default=False)
    needs_rename: BoolProperty(name="Needs Rename", default=True)
    selected_for_apply: BoolProperty(name="Selected", default=True, update=_selected_for_apply_update)
    confidence: bpy.props.FloatProperty(
        name="Confidence",
        description="Confidence score from AI (0-1)",
        default=0.5,
        min=0.0,
        max=1.0,
    )
    is_indexed: BoolProperty(
        name="Is Indexed",
        description="True if proposal matches taxonomy standard",
        default=False,
    )
    taxonomy_match: StringProperty(
        name="Taxonomy Match",
        description="Detected taxonomy type/finish or empty if not indexed",
        default="",
    )
    is_normalized: BoolProperty(
        name="Is Normalized",
        description="True if proposal was normalized to taxonomy (not original AI proposal)",
        default=False,
    )
    reconciliation_action: bpy.props.EnumProperty(
        name="Reconciliation Action",
        items=[
            ("ACCEPT", "Accept", "Accept proposal as-is"),
            ("NORMALIZE", "Normalize", "Normalize to closest taxonomy match"),
            ("MANUAL", "Manual", "Requires manual review"),
        ],
        default="ACCEPT",
    )
    quality_score: FloatProperty(
        name="Quality Score",
        description="Heuristic score of current material name (0-1)",
        default=0.0,
        min=0.0,
        max=1.0,
    )
    quality_label: StringProperty(
        name="Quality Label",
        description="Quality tier of the current material name (excellent/good/fair/poor/invalid)",
        default="invalid",
    )
    quality_issues: StringProperty(
        name="Quality Issues",
        description="Concise summary of detected issues or improvement hints",
        default="",
    )
    review_requested: BoolProperty(
        name="Review Requested",
        description="User requested AI re-analysis for this material even if name is already good",
        default=False,
    )


class LimeAIMatState(PropertyGroup):
    rows: CollectionProperty(type=LimeAIMatRow)
    active_index: IntProperty(name="Active Row", default=0)
    incorrect_count: IntProperty(name="Incorrect Count", default=0)
    total_count: IntProperty(name="Total Count", default=0)
    view_filter: EnumProperty(
        name="View",
        items=[
            ("ALL", "All", "Show all materials"),
            ("NEEDS", "Needs attention", "Show items requiring action"),
            ("CORRECT", "Correct", "Show valid items only"),
        ],
        default="NEEDS",
    )
    scene_context: StringProperty(
        name="Scene Context",
        description="Optional context about the scene (e.g. 'kitchen interior, marble, brushed metal')",
        default="",
        maxlen=500,
    )
    allow_non_indexed: BoolProperty(
        name="Allow Non-Indexed Proposals",
        description="If True, accept AI proposals outside taxonomy as experimental; if False, normalize to closest match",
        default=False,
    )
    force_reanalysis: BoolProperty(
        name="Force Re-analysis",
        description="If True, include correctly named materials for re-analysis by AI; if False, only analyze incorrectly named materials",
        default=False,
    )


def register():
    bpy.utils.register_class(LimeAIMatRow)
    bpy.utils.register_class(LimeAIMatState)
    bpy.types.Scene.lime_ai_mat = PointerProperty(type=LimeAIMatState)


def unregister():
    del bpy.types.Scene.lime_ai_mat
    bpy.utils.unregister_class(LimeAIMatState)
    bpy.utils.unregister_class(LimeAIMatRow)

