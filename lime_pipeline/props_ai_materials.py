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
    material_type: StringProperty(name="Material Type", default="Plastic")
    finish: StringProperty(name="Finish", default="Generic")
    version_token: StringProperty(name="Version", default="V01")
    similar_group_id: StringProperty(name="Group")
    status: StringProperty(name="Status", default="")
    read_only: BoolProperty(name="Read Only", default=False)
    needs_rename: BoolProperty(name="Needs Rename", default=True)
    selected_for_apply: BoolProperty(name="Selected", default=True, update=_selected_for_apply_update)


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


def register():
    bpy.utils.register_class(LimeAIMatRow)
    bpy.utils.register_class(LimeAIMatState)
    bpy.types.Scene.lime_ai_mat = PointerProperty(type=LimeAIMatState)


def unregister():
    del bpy.types.Scene.lime_ai_mat
    bpy.utils.unregister_class(LimeAIMatState)
    bpy.utils.unregister_class(LimeAIMatRow)


