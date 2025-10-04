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


class LimeAIMatRow(PropertyGroup):
    material_name: StringProperty(name="Material ID")
    proposed_name: StringProperty(name="Proposed")
    family: StringProperty(name="Family", default="Plastic")
    finish: StringProperty(name="Finish", default="Generic")
    version: StringProperty(name="V##", default="V01")
    similar_group_id: StringProperty(name="Group")
    status: StringProperty(name="Status", default="")
    read_only: BoolProperty(name="Read Only", default=False)
    needs_rename: BoolProperty(name="Needs Rename", default=True)


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


