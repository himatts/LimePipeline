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


def _on_selected_camera_update(self, context):
    try:
        name = getattr(self, "selected_camera", "") or ""
        if name and name != "NONE":
            cam = bpy.data.objects.get(name)
            if cam is not None and getattr(cam, "type", None) == 'CAMERA':
                context.scene.camera = cam
    except Exception:
        pass


class LimePipelineState(PropertyGroup):
    project_root: StringProperty(name="Project Root", subtype='DIR_PATH', description="Select the project root folder named 'XX-##### Project Name'")
    project_type: EnumProperty(name="Project Type", items=PROJECT_TYPES, default='REND', description="Type of project work: affects naming and target folders")
    # Sync helpers between letter and index
    def _on_rev_index_update(self, context):
        # Prevent recursive update loops when syncing with rev_letter
        if getattr(self, "_updating_rev", False):
            return
        try:
            setattr(self, "_updating_rev", True)
            idx = int(getattr(self, "rev_index", 1))
            if idx < 1:
                idx = 1
            if idx > 26:
                idx = 26
            self.rev_letter = chr(ord('A') + (idx - 1))
        except Exception:
            pass
        finally:
            setattr(self, "_updating_rev", False)

    # Note: rev_letter is the source-of-truth value used elsewhere in the addon.
    # We only update rev_letter when rev_index changes (one-way sync) to avoid
    # recursive update loops.

    rev_letter: StringProperty(name="Rev", default="A", maxlen=1, description="Revision letter A–Z")
    rev_index: IntProperty(name="Rev", default=1, min=1, max=26, step=1, description="Revision as stepper (A–Z)", update=_on_rev_index_update)
    sc_number: IntProperty(name="SC", default=10, min=1, max=999, step=10, description="Scene number (001–999). Suggested multiples of Scene Step")
    free_scene_numbering: BoolProperty(name="Free SC numbering", default=False, description="Allow any scene number; ignore Scene Step multiple rule")
    use_custom_name: BoolProperty(name="Use Custom Name", default=False, description="Override project name derived from root folder")
    custom_name: StringProperty(name="Custom Project Name", description="Letters/digits only; will be normalized to TitleCase")
    preview_name: StringProperty(name="Preview Name", options={'HIDDEN'})
    preview_path: StringProperty(name="Preview Path", subtype='FILE_PATH', options={'HIDDEN'})
    # Dynamic camera selection for Proposal Views
    def _camera_items(self, context):
        try:
            from .core import validate_scene
            from .data import templates
        except Exception:
            return [("NONE", "No Camera", "", 0)]
        items = []
        try:
            shot = validate_scene.active_shot_context(context)
            if shot is not None:
                base = getattr(templates, "C_UTILS_CAM", "00_UTILS_CAM")
                cam_coll = validate_scene.get_shot_child_by_basename(shot, base)
                if cam_coll is not None:
                    cams = [obj for obj in cam_coll.objects if getattr(obj, "type", None) == 'CAMERA']
                    # Stable order by name
                    cams.sort(key=lambda o: o.name)
                    for idx, cam in enumerate(cams, 1):
                        items.append((cam.name, f"Cam {idx}: {cam.name}", "", idx))
        except Exception:
            pass
        return items or [("NONE", "No Camera", "", 0)]

    selected_camera: EnumProperty(name="Camera", items=_camera_items, update=_on_selected_camera_update)


def register():
    bpy.utils.register_class(LimePipelineState)
    bpy.types.WindowManager.lime_pipeline = PointerProperty(type=LimePipelineState)


def unregister():
    del bpy.types.WindowManager.lime_pipeline
    bpy.utils.unregister_class(LimePipelineState)


