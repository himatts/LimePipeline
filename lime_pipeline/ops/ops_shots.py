import bpy
from bpy.types import Operator
from bpy.props import StringProperty

from ..core import validate_scene
from ..core.naming import resolve_project_name
from ..scene.scene_utils import create_shot, instance_shot, duplicate_shot, ensure_shot_tree
import bpy


class LIME_OT_new_shot(Operator):
    bl_idname = "lime.new_shot"
    bl_label = "New Shot"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        ok, _ = validate_scene.can_create_new_shot(ctx.scene)
        return ok

    def execute(self, context):
        scene = context.scene
        st = context.window_manager.lime_pipeline
        project_name = resolve_project_name(st)
        idx = validate_scene.next_shot_index(scene)
        try:
            create_shot(scene, idx, project_name)
        except Exception as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        self.report({'INFO'}, f"Created SHOT {idx:02d}")
        return {'FINISHED'}


class LIME_OT_shot_instance(Operator):
    bl_idname = "lime.shot_instance"
    bl_label = "Shot Instance"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        ok, _ = validate_scene.can_instance_shot(ctx)
        return ok

    def execute(self, context):
        scene = context.scene
        src = validate_scene.active_shot_context(context)
        if src is None:
            self.report({'ERROR'}, "No SHOT context")
            return {'CANCELLED'}
        dst_idx = validate_scene.next_shot_index(scene)
        try:
            instance_shot(scene, src, dst_idx)
        except Exception as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        self.report({'INFO'}, f"Instanced SHOT {dst_idx:02d} from {src.name}")
        return {'FINISHED'}


class LIME_OT_delete_shot(Operator):
    bl_idname = "lime.delete_shot"
    bl_label = "Delete Shot"
    bl_description = "Delete the entire SHOT collection and its contents"
    bl_options = {'REGISTER', 'UNDO'}

    shot_name: StringProperty(name="Shot Name", default="")

    @classmethod
    def poll(cls, ctx):
        return True

    def _remove_collection_recursive(self, coll: bpy.types.Collection):
        # Remove all objects in this collection
        try:
            for obj in list(coll.objects):
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except Exception:
                    pass
        except Exception:
            pass
        # Recurse into children first
        try:
            for child in list(coll.children):
                self._remove_collection_recursive(child)
        except Exception:
            pass
        # Finally, remove the collection itself
        try:
            bpy.data.collections.remove(coll, do_unlink=True)
        except Exception:
            pass

    def execute(self, context):
        name = (self.shot_name or '').strip()
        if not name:
            self.report({'ERROR'}, "No SHOT name provided")
            return {'CANCELLED'}
        # Validate it's a shot root
        shot_coll = bpy.data.collections.get(name)
        if shot_coll is None:
            self.report({'ERROR'}, f"SHOT not found: {name}")
            return {'CANCELLED'}
        shots = [c for c, _ in validate_scene.list_shot_roots(context.scene)]
        if shot_coll not in shots:
            self.report({'ERROR'}, f"Not a SHOT root: {name}")
            return {'CANCELLED'}
        # Remove recursively
        try:
            self._remove_collection_recursive(shot_coll)
        except Exception as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        self.report({'INFO'}, f"Deleted SHOT: {name}")
        return {'FINISHED'}


class LIME_OT_duplicate_shot(Operator):
    bl_idname = "lime.duplicate_shot"
    bl_label = "Duplicate Shot"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        ok, _ = validate_scene.can_duplicate_shot(ctx)
        return ok

    def execute(self, context):
        scene = context.scene
        src = validate_scene.active_shot_context(context)
        if src is None:
            self.report({'ERROR'}, "No SHOT context")
            return {'CANCELLED'}
        dst_idx = validate_scene.next_shot_index(scene)
        try:
            duplicate_shot(scene, src, dst_idx)
        except Exception as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        self.report({'INFO'}, f"Duplicated {src.name} → SHOT {dst_idx:02d}")
        return {'FINISHED'}

class LIME_OT_activate_shot(Operator):
    bl_idname = "lime.activate_shot"
    bl_label = "Activate Shot"
    bl_options = {'REGISTER', 'UNDO'}

    shot_name: StringProperty(name="Shot Name", default="")

    def execute(self, context):
        name = (self.shot_name or '').strip()
        if not name:
            self.report({'ERROR'}, "Invalid SHOT name")
            return {'CANCELLED'}
        # Find collection and activate in Outliner/View Layer
        target = next((c for c in context.scene.collection.children if c.name == name), None)
        if target is None:
            self.report({'ERROR'}, f"SHOT not found: {name}")
            return {'CANCELLED'}
        # Activate corresponding layer collection
        try:
            def _find_layer(layer, wanted):
                if layer.collection == wanted:
                    return layer
                for ch in layer.children:
                    found = _find_layer(ch, wanted)
                    if found:
                        return found
                return None

            root_layer = context.view_layer.layer_collection
            lc = _find_layer(root_layer, target)
            if lc is not None:
                context.view_layer.active_layer_collection = lc
        except Exception:
            pass

        self.report({'INFO'}, f"Active: {name}")
        return {'FINISHED'}


