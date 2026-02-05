"""AI Asset Organizer properties and state.

Stores AI-generated rename proposals for selected objects and their materials.
This module is intentionally UI-agnostic; panels and operators consume the state.
"""

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
    original_name: StringProperty(name="Original", default="")
    suggested_name: StringProperty(name="Suggested", default="")
    selected_for_apply: BoolProperty(name="Apply", default=True)
    read_only: BoolProperty(name="Read Only", default=False)
    status: StringProperty(name="Status", default="")


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
    preview_summary: StringProperty(name="Preview", default="")
    preview_dirty: BoolProperty(name="Preview Dirty", default=False)
    planned_renames_objects: IntProperty(name="Planned Object Renames", default=0)
    planned_renames_materials: IntProperty(name="Planned Material Renames", default=0)
    planned_renames_collections: IntProperty(name="Planned Collection Renames", default=0)
    planned_collections_created: IntProperty(name="Planned Collections Created", default=0)
    planned_objects_moved: IntProperty(name="Planned Objects Moved", default=0)
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
