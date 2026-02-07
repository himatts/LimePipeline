"""AI Asset Organizer properties and state.

Stores AI-generated rename proposals for selected objects and their materials.
This module is intentionally UI-agnostic; panels and operators consume the state.
"""

from __future__ import annotations

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


def _refresh_preview(scene) -> None:
    try:
        ops_module = import_module("lime_pipeline.ops.ops_ai_asset_organizer")
    except Exception:
        return
    if getattr(ops_module, "_AI_ASSET_PREVIEW_SUSPENDED", False):
        return
    try:
        ops_module.refresh_ai_asset_preview(scene)
    except Exception:
        pass


def _selected_for_apply_update(self, context) -> None:
    scene = getattr(context, "scene", None) if context else None
    if scene is None:
        try:
            scene = bpy.context.scene  # type: ignore[attr-defined]
        except Exception:
            scene = None
    if scene is None:
        return
    _refresh_preview(scene)


def _scope_update(self, context) -> None:
    scene = getattr(context, "scene", None) if context else None
    if scene is None:
        try:
            scene = bpy.context.scene  # type: ignore[attr-defined]
        except Exception:
            scene = None
    if scene is None:
        return
    try:
        ops_module = import_module("lime_pipeline.ops.ops_ai_asset_organizer")
    except Exception:
        _refresh_preview(scene)
        return
    if getattr(ops_module, "_AI_ASSET_PREVIEW_SUSPENDED", False):
        return
    try:
        ops_module.sync_ai_asset_row_selection(scene)
    except Exception:
        _refresh_preview(scene)


class LimeAIAssetItem(PropertyGroup):
    item_type: EnumProperty(
        name="Type",
        items=[
            ("OBJECT", "Object", "Rename an object"),
            ("MATERIAL", "Material", "Rename a material"),
            ("COLLECTION", "Collection", "Rename a collection"),
        ],
        default="OBJECT",
    )
    object_ref: PointerProperty(type=bpy.types.Object)
    material_ref: PointerProperty(type=bpy.types.Material)
    collection_ref: PointerProperty(type=bpy.types.Collection)
    item_id: StringProperty(name="Item ID", default="")
    original_name: StringProperty(name="Original", default="")
    suggested_name: StringProperty(name="Suggested", default="")
    selected_for_apply: BoolProperty(name="Apply", default=True, update=_selected_for_apply_update)
    read_only: BoolProperty(name="Read Only", default=False)
    status: StringProperty(name="Status", default="")
    target_collection_path: StringProperty(name="Target Collection Path", default="")
    target_status: EnumProperty(
        name="Target Status",
        items=[
            ("NONE", "None", "No target destination"),
            ("AUTO", "Auto", "Destination selected automatically"),
            ("AMBIGUOUS", "Ambiguous", "Multiple valid destinations"),
            ("CONFIRMED", "Confirmed", "Destination manually confirmed"),
            ("SKIPPED", "Skipped", "Destination skipped"),
        ],
        default="NONE",
    )
    target_confidence: FloatProperty(name="Target Confidence", default=0.0, min=0.0, max=1.0)
    target_candidates_json: StringProperty(name="Target Candidates", default="")


class LimeAIAssetState(PropertyGroup):
    items: CollectionProperty(type=LimeAIAssetItem)
    active_index: IntProperty(name="Active Row", default=0)
    context: StringProperty(
        name="Context",
        description="Optional context to improve AI naming suggestions",
        default="",
        maxlen=500,
    )
    use_image_context: BoolProperty(
        name="Use Image Context",
        description="Include an image as extra context for AI suggestions",
        default=False,
    )
    image_path: StringProperty(
        name="Image",
        description="Image file to send as extra context (local path)",
        subtype="FILE_PATH",
        default="",
    )
    include_collections: BoolProperty(
        name="Include Collections",
        description="Include relevant non-SHOT collections used by the current object selection",
        default=True,
    )
    organize_collections: BoolProperty(
        name="Organize Collections on Apply",
        description="Move selected objects to safer category/group collections after applying names",
        default=False,
    )
    apply_scope_objects: BoolProperty(
        name="Apply Objects",
        description="Include object rename and organization operations in Apply",
        default=True,
        update=_scope_update,
    )
    apply_scope_materials: BoolProperty(
        name="Apply Materials",
        description="Include material rename operations in Apply",
        default=True,
        update=_scope_update,
    )
    apply_scope_collections: BoolProperty(
        name="Apply Collections",
        description="Include collection rename operations in Apply",
        default=True,
        update=_scope_update,
    )
    preview_summary: StringProperty(name="Preview", default="")
    preview_dirty: BoolProperty(name="Preview Dirty", default=False)
    planned_renames_objects: IntProperty(name="Planned Object Renames", default=0)
    planned_renames_materials: IntProperty(name="Planned Material Renames", default=0)
    planned_renames_collections: IntProperty(name="Planned Collection Renames", default=0)
    planned_collections_created: IntProperty(name="Planned Collections Created", default=0)
    planned_objects_moved: IntProperty(name="Planned Objects Moved", default=0)
    planned_ambiguities_objects: IntProperty(name="Planned Ambiguous Objects", default=0)
    planned_objects_skipped_ambiguous: IntProperty(name="Planned Skipped Ambiguous Objects", default=0)
    last_used_collection_path: StringProperty(name="Last Used Collection Path", default="")
    is_busy: BoolProperty(name="Busy", default=False)
    last_error: StringProperty(name="Last Error", default="")


def register():
    bpy.utils.register_class(LimeAIAssetItem)
    bpy.utils.register_class(LimeAIAssetState)
    bpy.types.Scene.lime_ai_assets = PointerProperty(type=LimeAIAssetState)


def unregister():
    del bpy.types.Scene.lime_ai_assets
    bpy.utils.unregister_class(LimeAIAssetState)
    bpy.utils.unregister_class(LimeAIAssetItem)
