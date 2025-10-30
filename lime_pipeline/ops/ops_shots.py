"""
SHOT Management Operators

This module provides comprehensive functionality for creating, managing, and organizing
SHOT scenes within the Lime Pipeline workflow. SHOTs represent individual scene files
that are organized sequentially for production pipelines.

The operators handle SHOT lifecycle including creation, duplication, validation, and
maintenance of proper SHOT naming conventions and collection structures.

Key Features:
- Automated SHOT creation with proper numbering and naming
- SHOT duplication with intelligent renaming and structure preservation
- Integration with Lime Pipeline project naming conventions
- Validation of SHOT contexts and prerequisites
- Collection tree management for SHOT organization
- Sequential SHOT numbering and tracking
- Error handling and user feedback for SHOT operations
"""

import bpy
from bpy.types import Operator
from bpy.props import StringProperty

from ..core import validate_scene
from ..core.naming import resolve_project_name
from ..scene.scene_utils import create_shot, duplicate_shot, ensure_shot_tree


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



class LIME_OT_jump_to_first_shot_marker(Operator):
    bl_idname = "lime.jump_to_first_shot_marker"
    bl_label = "Jump to First Shot Camera Marker"
    bl_description = "Set current frame to the first timeline marker whose camera belongs to the target SHOT"
    bl_options = {'REGISTER'}

    shot_name: StringProperty(name="Shot Name", default="")

    @classmethod
    def poll(cls, ctx):
        return True

    def execute(self, context):
        scene = context.scene
        # Resolve shot by name or from context
        shot = None
        name = (self.shot_name or '').strip()
        if name:
            shot = bpy.data.collections.get(name)
        if shot is None:
            shot = validate_scene.active_shot_context(context)
        if shot is None:
            self.report({'WARNING'}, "No SHOT context to jump to markers")
            return {'CANCELLED'}

        # Collect cameras that belong to the SHOT subtree
        def _iter_coll_tree(root):
            stack = [root]
            seen = set()
            while stack:
                c = stack.pop()
                ident = c.as_pointer() if hasattr(c, 'as_pointer') else id(c)
                if ident in seen:
                    continue
                seen.add(ident)
                yield c
                try:
                    stack.extend(list(c.children))
                except Exception:
                    pass

        cameras = []
        for coll in _iter_coll_tree(shot):
            try:
                for obj in coll.objects:
                    if getattr(obj, 'type', None) == 'CAMERA':
                        cameras.append(obj)
            except Exception:
                pass

        if not cameras:
            self.report({'WARNING'}, f"No cameras found in SHOT '{shot.name}'")
            return {'CANCELLED'}

        allowed = set(cameras)
        # Build camera name prefixes for this SHOT (02d and 03d width)
        try:
            from ..core import validate_scene as _vs
            idx = _vs.parse_shot_index(getattr(shot, 'name', '') or '') or 0
        except Exception:
            idx = 0
        prefixes = []
        if idx > 0:
            prefixes = [f"SHOT_{idx:02d}_CAMERA_", f"SHOT_{idx:03d}_CAMERA_"]

        # Gather candidate frames: markers with camera in allowed or matching name prefixes
        try:
            markers = sorted(scene.timeline_markers, key=lambda m: m.frame)
        except Exception:
            markers = list(scene.timeline_markers)

        current = int(getattr(scene, 'frame_current', 0) or 0)
        future_frames = []
        all_frames = []
        for marker in markers:
            cam = getattr(marker, 'camera', None)
            if not cam:
                continue
            ok = cam in allowed
            if not ok and prefixes:
                try:
                    n = getattr(cam, 'name', '') or ''
                    ok = any(n.startswith(p) for p in prefixes)
                except Exception:
                    ok = False
            if not ok:
                continue
            f = int(marker.frame)
            all_frames.append(f)
            if f >= current:
                future_frames.append(f)

        target_frame = None
        if future_frames:
            target_frame = min(future_frames)
        elif all_frames:
            target_frame = min(all_frames)

        if target_frame is None:
            self.report({'WARNING'}, f"No camera markers for SHOT '{shot.name}'")
            return {'CANCELLED'}

        try:
            scene.frame_set(target_frame)
        except Exception:
            self.report({'ERROR'}, "Failed to set frame")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Jumped to frame {target_frame} for '{shot.name}'")
        return {'FINISHED'}

