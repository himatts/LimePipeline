import bpy
from bpy.types import Operator

from ..core import validate_scene
from ..core.validate_scene import parse_shot_index, get_shot_child_by_basename
from ..data.templates import (
    C_UTILS_LIGHTS,
    C_LIGHTS_MAIN,
    C_LIGHTS_AUX,
)


def _ensure_child(parent: bpy.types.Collection, name: str) -> bpy.types.Collection:
    for c in parent.children:
        if c.name == name:
            return c
    new = bpy.data.collections.new(name)
    parent.children.link(new)
    return new


def _ensure_lights_target(shot: bpy.types.Collection, shot_idx: int, target_base: str) -> bpy.types.Collection:
    """Ensure and return the target lights subcollection under the shot.

    Structure:
        SH##_00_UTILS_LIGHTS/
            SH##_00_LIGHTS_MAIN
            SH##_00_LIGHTS_AUX
    """
    # Ensure lights utils root under shot
    lights_root = get_shot_child_by_basename(shot, C_UTILS_LIGHTS)
    if lights_root is None:
        lights_root = _ensure_child(shot, f"SH{shot_idx:02d}_{C_UTILS_LIGHTS}")

    # Ensure concrete target under lights root
    target = get_shot_child_by_basename(lights_root, target_base)
    if target is None:
        target = _ensure_child(lights_root, f"SH{shot_idx:02d}_{target_base}")
    return target


def _is_in_shot(coll: bpy.types.Collection, shot: bpy.types.Collection) -> bool:
    # Reuse public helper to check ancestry by comparing resolved root
    try:
        return validate_scene.find_shot_root_for_collection(coll) == shot
    except Exception:
        return False


def _assign_selected_lights(context, target_base: str) -> tuple[set, set]:
    """Assign selected LIGHT objects to the given lights subcollection and rename them.

    Returns (moved, skipped) sets of object names.
    """
    shot = validate_scene.active_shot_context(context)
    if shot is None:
        raise RuntimeError("No SHOT context active")

    shot_idx = parse_shot_index(shot.name) or 0
    if shot_idx <= 0:
        raise RuntimeError("Invalid SHOT index")

    target_coll = _ensure_lights_target(shot, shot_idx, target_base)
    base_name = f"SH{shot_idx:02d}_{target_base}"

    sel = list(getattr(context, "selected_objects", []) or [])
    lights = [o for o in sel if getattr(o, "type", None) == 'LIGHT']
    if not lights:
        raise RuntimeError("Seleccione al menos una luz (LIGHT)")

    moved: set[str] = set()
    skipped: set[str] = set()
    for ob in lights:
        try:
            # Rename object (Blender will append .001, .002... if needed)
            ob.name = base_name
            if getattr(ob, "data", None) is not None:
                try:
                    ob.data.name = base_name + ".Data"
                except Exception:
                    pass

            # Link to target collection if not already linked
            if target_coll not in ob.users_collection:
                target_coll.objects.link(ob)

            # Unlink from other collections inside the same SHOT to avoid duplicates
            for c in list(ob.users_collection):
                if c != target_coll and _is_in_shot(c, shot):
                    try:
                        c.objects.unlink(ob)
                    except Exception:
                        pass

            moved.add(ob.name)
        except Exception:
            skipped.add(ob.name)

    return moved, skipped


class LIME_OT_stage_main_light(Operator):
    bl_idname = "lime.stage_main_light"
    bl_label = "Assign Main Light"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        if validate_scene.active_shot_context(ctx) is None:
            return False
        try:
            sel = list(getattr(ctx, "selected_objects", []) or [])
            return any(getattr(o, "type", None) == 'LIGHT' for o in sel)
        except Exception:
            return False

    def execute(self, context):
        try:
            moved, skipped = _assign_selected_lights(context, C_LIGHTS_MAIN)
        except Exception as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}

        if moved:
            self.report({'INFO'}, f"Asignadas {len(moved)} luz(es) a MAIN")
        if skipped:
            self.report({'WARNING'}, f"Omitidas {len(skipped)} luz(es)")
        return {'FINISHED'}


class LIME_OT_stage_aux_light(Operator):
    bl_idname = "lime.stage_aux_light"
    bl_label = "Assign Aux Light"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        if validate_scene.active_shot_context(ctx) is None:
            return False
        try:
            sel = list(getattr(ctx, "selected_objects", []) or [])
            return any(getattr(o, "type", None) == 'LIGHT' for o in sel)
        except Exception:
            return False

    def execute(self, context):
        try:
            moved, skipped = _assign_selected_lights(context, C_LIGHTS_AUX)
        except Exception as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}

        if moved:
            self.report({'INFO'}, f"Asignadas {len(moved)} luz(es) a AUX")
        if skipped:
            self.report({'WARNING'}, f"Omitidas {len(skipped)} luz(es)")
        return {'FINISHED'}


__all__ = [
    "LIME_OT_stage_main_light",
    "LIME_OT_stage_aux_light",
]

