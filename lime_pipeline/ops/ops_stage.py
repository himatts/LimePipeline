import bpy
from bpy.types import Operator

from ..core import validate_scene
from ..core.validate_scene import parse_shot_index, get_shot_child_by_basename


def _ensure_child(parent: bpy.types.Collection, name: str) -> bpy.types.Collection:
    for c in parent.children:
        if c.name == name:
            return c
    new = bpy.data.collections.new(name)
    parent.children.link(new)
    return new


def _ensure_lights_target(shot: bpy.types.Collection, shot_idx: int, target_base: str) -> bpy.types.Collection:
    # Deprecated: lights utilities removed
    return get_shot_child_by_basename(shot, target_base)


def _is_in_shot(coll: bpy.types.Collection, shot: bpy.types.Collection) -> bool:
    # Reuse public helper to check ancestry by comparing resolved root
    try:
        return validate_scene.find_shot_root_for_collection(coll) == shot
    except Exception:
        return False


def _assign_selected_lights(context, target_base: str) -> tuple[set, set]:
    # Deprecated feature
    return set(), set()


class LIME_OT_stage_main_light(Operator):
    bl_idname = "lime.stage_main_light"
    bl_label = "Assign Main Light"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        self.report({'WARNING'}, "Main Light tool removed")
        return {'CANCELLED'}


class LIME_OT_stage_aux_light(Operator):
    bl_idname = "lime.stage_aux_light"
    bl_label = "Assign Aux Light"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        self.report({'WARNING'}, "Aux Light tool removed")
        return {'CANCELLED'}


__all__ = [
    "LIME_OT_stage_main_light",
    "LIME_OT_stage_aux_light",
]

