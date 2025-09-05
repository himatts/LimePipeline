import bpy
from bpy.types import PropertyGroup
from bpy.props import (
    StringProperty,
    BoolProperty,
    IntProperty,
    EnumProperty,
    PointerProperty,
)


PROJECT_TYPES = [
    ('BASE', "3D Base Model", "Single base .blend, no SC", 0),
    ('PV',   "Proposal Views", "Scenes under Revision", 1),
    ('REND', "Renders",        "Scenes under Revision", 2),
    ('SB',   "Storyboard",     "Scenes under Revision", 3),
    ('ANIM', "Animation",      "Scenes under Revision", 4),
    ('TMP',  "Temporal",       "Tmp under Revision",    5),
]


class LimePipelineState(PropertyGroup):
    project_root: StringProperty(name="Project Root", subtype='DIR_PATH', description="Select the project root folder named 'XX-##### Project Name'")
    project_type: EnumProperty(name="Project Type", items=PROJECT_TYPES, default='REND', description="Type of project work: affects naming and target folders")
    rev_letter: StringProperty(name="Rev", maxlen=1, description="Revision letter A–Z")
    sc_number: IntProperty(name="SC", default=10, min=1, max=999, step=10, description="Scene number (001–999). Suggested multiples of Scene Step")
    free_scene_numbering: BoolProperty(name="Free SC numbering", default=False, description="Allow any scene number; ignore Scene Step multiple rule")
    use_custom_name: BoolProperty(name="Use Custom Name", default=False, description="Override project name derived from root folder")
    custom_name: StringProperty(name="Custom Project Name", description="Letters/digits only; will be normalized to TitleCase")
    preview_name: StringProperty(name="Preview Name", options={'HIDDEN'})
    preview_path: StringProperty(name="Preview Path", subtype='FILE_PATH', options={'HIDDEN'})


def register():
    bpy.utils.register_class(LimePipelineState)
    bpy.types.WindowManager.lime_pipeline = PointerProperty(type=LimePipelineState)


def unregister():
    del bpy.types.WindowManager.lime_pipeline
    bpy.utils.unregister_class(LimePipelineState)


