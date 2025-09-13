import os
from pathlib import Path

import bpy
from bpy.types import Operator
from bpy.props import StringProperty, IntProperty

from ..core.paths import paths_for_type
from ..core.naming import resolve_project_name, hydrate_state_from_filepath, parse_blend_details
from ..core import validate_scene
from ..data.templates import C_UTILS_CAM


IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.exr', '.tif', '.tiff'}


def _ensure_editables_dir(state, ptype: str) -> Path:
    hydrate_state_from_filepath(state)
    root_str = getattr(state, "project_root", "") or ""
    if not root_str:
        raise RuntimeError("Project Root not configured. Go to Project Org and select the root folder.")
    root = Path(root_str)
    rev = (getattr(state, "rev_letter", "") or "").upper()
    sc = getattr(state, "sc_number", None)
    _ramv, folder_type, _scenes, _target, _backups = paths_for_type(root, ptype, rev, sc)
    editables_dir = folder_type / "editables"
    editables_dir.mkdir(parents=True, exist_ok=True)
    return editables_dir


def _resolve_prj_rev_sc(state):
    project_name = None
    rev = None
    sc = None
    try:
        info = parse_blend_details(bpy.data.filepath or "")
        if info:
            project_name = info.get('project_name') or None
            rev = info.get('rev') or None
            sc = info.get('sc') if info.get('sc') is not None else None
    except Exception:
        pass
    if not project_name:
        try:
            project_name = resolve_project_name(state)
        except Exception:
            project_name = "Project"
    if rev is None:
        try:
            rev = (getattr(state, "rev_letter", "") or "").upper() or None
        except Exception:
            rev = None
    if sc is None:
        try:
            sc = int(getattr(state, "sc_number", 0) or 0)
        except Exception:
            sc = 0
    return project_name, sc, (rev or "")


def _camera_index_for_shot(shot, camera_obj) -> int:
    try:
        cam_coll = validate_scene.get_shot_child_by_basename(shot, C_UTILS_CAM)
        if not cam_coll:
            return 1
        cameras = [obj for obj in cam_coll.objects if getattr(obj, "type", None) == 'CAMERA']
        if not cameras:
            return 1
        cameras.sort(key=lambda o: o.name)
        for i, c in enumerate(cameras, 1):
            if c == camera_obj:
                return i
    except Exception:
        pass
    return 1


class LIME_OT_set_active_camera(Operator):
    bl_idname = "lime.set_active_camera"
    bl_label = "Set Active Camera"
    bl_options = {'REGISTER', 'UNDO'}

    camera_name: StringProperty(name="Camera Name", default="")

    def execute(self, context):
        name = (self.camera_name or "").strip()
        cam = bpy.data.objects.get(name)
        if cam is None or getattr(cam, "type", None) != 'CAMERA':
            self.report({'ERROR'}, f"Invalid camera: {name}")
            return {'CANCELLED'}
        context.scene.camera = cam
        self.report({'INFO'}, f"Active camera: {cam.name}")
        return {'FINISHED'}


class LIME_OT_render_invoke(Operator):
    bl_idname = "lime.render_invoke"
    bl_label = "Render"
    bl_description = "Open Blender's standard render window (F12)"

    def execute(self, context):
        try:
            bpy.ops.render.render('INVOKE_DEFAULT')
            return {'FINISHED'}
        except Exception as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}


class LIME_OT_save_as_with_template(Operator):
    bl_idname = "lime.save_as_with_template"
    bl_label = "Save As (Template)"
    bl_description = "Open file browser with suggested path and filename"

    ptype: StringProperty(name="Project Type", default="REND")
    filepath: StringProperty(name="File Path", subtype='FILE_PATH')

    def _build_suggested_path(self, context) -> str:
        wm = context.window_manager
        st = wm.lime_pipeline
        ptype = (self.ptype or '').strip().upper()
        try:
            editables_dir = _ensure_editables_dir(st, ptype)
        except Exception:
            # Fallback to home if not configured; dialog still opens
            editables_dir = Path.home()
        project_name, sc_number, rev = _resolve_prj_rev_sc(st)
        scene = context.scene
        shot = validate_scene.active_shot_context(context)
        camera_obj = scene.camera
        if ptype == 'REND':
            shot_idx = validate_scene.parse_shot_index(shot.name) if shot else 0
            cam_idx = _camera_index_for_shot(shot, camera_obj) if shot and camera_obj else 1
            filename = f"{project_name}_Render_SH{shot_idx:02d}C{cam_idx}_SC{sc_number:03d}_Rev_{rev}.png"
        elif ptype == 'PV':
            shot_idx = validate_scene.parse_shot_index(shot.name) if shot else 0
            cam_idx = _camera_index_for_shot(shot, camera_obj) if shot and camera_obj else 1
            filename = f"{project_name}_PV_SH{shot_idx:02d}C{cam_idx}_SC{sc_number:03d}_Rev_{rev}.png"
        elif ptype == 'SB':
            filename = f"{project_name}_SB_SC{sc_number:03d}_Rev_{rev}.png"
        else:
            filename = f"{project_name}_TMP_SC{sc_number:03d}_Rev_{rev}.png"
        return (editables_dir / filename).as_posix()

    def invoke(self, context, event):
        # Compute suggested path and open the file browser via fileselect_add
        try:
            self.filepath = self._build_suggested_path(context)
        except Exception as ex:
            # Still attempt to open the browser; user can choose a path
            self.filepath = str(Path.home() / "render.png")
            self.report({'WARNING'}, str(ex))
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        # Save the image selected by user path
        path = (self.filepath or '').strip()
        if not path:
            self.report({'ERROR'}, "No file path provided")
            return {'CANCELLED'}
        # Prefer Render Result, then Viewer Node, then active image in any Image Editor
        img = bpy.data.images.get("Render Result") or bpy.data.images.get("Viewer Node")
        if img is None:
            # Try active image
            try:
                for area in context.window.screen.areas:
                    if area.type == 'IMAGE_EDITOR':
                        sp = area.spaces.active
                        if sp and getattr(sp, 'image', None) is not None:
                            img = sp.image
                            break
            except Exception:
                img = None
        if img is None:
            self.report({'ERROR'}, "No image to save")
            return {'CANCELLED'}
        # Try save_render first (works for Render Result/Viewer Node), then fallback to image.save
        saved = False
        try:
            img.save_render(path, scene=context.scene)
            saved = True
        except Exception:
            try:
                img.save(filepath=path)
                saved = True
            except Exception as ex:
                self.report({'ERROR'}, f"Failed to save: {ex}")
                return {'CANCELLED'}
        if saved:
            self.report({'INFO'}, f"Saved: {Path(path).name}")
        return {'FINISHED'}


class LIME_OT_duplicate_active_camera(Operator):
    bl_idname = "lime.duplicate_active_camera"
    bl_label = "Duplicate Camera"
    bl_description = "Duplicate the active scene camera in place and remove all keyframes from the copy"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        cam = getattr(getattr(ctx, 'scene', None), 'camera', None)
        return cam is not None

    def execute(self, context):
        scene = context.scene
        cam = scene.camera
        if cam is None:
            self.report({'ERROR'}, "No active camera in the scene")
            return {'CANCELLED'}

        try:
            # Find rig root (top-most parent); if none, duplicate only the camera
            root = cam
            try:
                while getattr(root, 'parent', None) is not None:
                    root = root.parent
            except Exception:
                root = cam

            # Collect hierarchy under root (including root)
            if root is cam and not getattr(cam, 'children', None):
                rig_objects = [cam]
            else:
                rig_objects = []
                queue = [root]
                seen = set()
                while queue:
                    ob = queue.pop(0)
                    if ob in seen:
                        continue
                    seen.add(ob)
                    rig_objects.append(ob)
                    try:
                        for ch in getattr(ob, 'children', []) or []:
                            queue.append(ch)
                    except Exception:
                        pass

            # Duplicate all objects and link to the same collections
            original_to_copy = {}
            for ob in rig_objects:
                try:
                    new_ob = ob.copy()
                    if getattr(ob, 'data', None) is not None:
                        try:
                            new_ob.data = ob.data.copy()
                        except Exception:
                            pass
                    # Link to the same collections; fallback to scene collection
                    linked = False
                    try:
                        for c in list(getattr(ob, 'users_collection', []) or []):
                            try:
                                c.objects.link(new_ob)
                                linked = True
                            except Exception:
                                pass
                    except Exception:
                        pass
                    if not linked:
                        try:
                            scene.collection.objects.link(new_ob)
                        except Exception:
                            pass
                    original_to_copy[ob] = new_ob
                except Exception:
                    pass

            # Restore parenting among duplicates
            for ob, new_ob in list(original_to_copy.items()):
                par = getattr(ob, 'parent', None)
                if par is not None and par in original_to_copy:
                    try:
                        new_ob.parent = original_to_copy[par]
                    except Exception:
                        pass
                    try:
                        new_ob.parent_type = ob.parent_type
                    except Exception:
                        pass
                    if getattr(ob, 'parent_type', None) == 'BONE':
                        try:
                            new_ob.parent_bone = ob.parent_bone
                        except Exception:
                            pass
                    try:
                        new_ob.matrix_parent_inverse = ob.matrix_parent_inverse.copy()
                    except Exception:
                        pass

            # Retarget constraints inside the duplicated rig to use duplicates
            for ob, new_ob in list(original_to_copy.items()):
                try:
                    for con in getattr(new_ob, 'constraints', []) or []:
                        try:
                            if hasattr(con, 'target') and con.target in original_to_copy:
                                con.target = original_to_copy[con.target]
                        except Exception:
                            pass
                        try:
                            if hasattr(con, 'object') and con.object in original_to_copy:
                                con.object = original_to_copy[con.object]
                        except Exception:
                            pass
                except Exception:
                    pass

            # Clear animation on duplicates (object and data)
            for new_ob in list(original_to_copy.values()):
                try:
                    if getattr(new_ob, 'animation_data', None):
                        new_ob.animation_data_clear()
                except Exception:
                    pass
                try:
                    data = getattr(new_ob, 'data', None)
                    if data is not None and getattr(data, 'animation_data', None):
                        data.animation_data_clear()
                except Exception:
                    pass

            # Report
            if root is cam and len(original_to_copy) == 1:
                self.report({'INFO'}, f"Duplicated camera: {original_to_copy[cam].name}")
            else:
                self.report({'INFO'}, f"Duplicated camera rig with {len(original_to_copy)} objects")
            return {'FINISHED'}
        except Exception as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}


__all__ = [
    "LIME_OT_set_active_camera",
    "LIME_OT_render_invoke",
    "LIME_OT_save_as_with_template",
    "LIME_OT_duplicate_active_camera",
]


