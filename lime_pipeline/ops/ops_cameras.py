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


# Helper: rename the parent Armature of a camera using Lime naming
import re
_CAM_NAME_RE = re.compile(r"^SHOT_(\d{2,3})_CAMERA_(\d+)")


def _rename_parent_armature_for_camera(cam_obj, shot_idx_hint: int | None = None, cam_idx_hint: int | None = None) -> None:
    try:
        import bpy as _bpy  # local import for safety
        if getattr(cam_obj, "type", None) != 'CAMERA':
            return
        shot_idx = shot_idx_hint
        cam_idx = cam_idx_hint
        if shot_idx is None or cam_idx is None:
            m = _CAM_NAME_RE.match(getattr(cam_obj, 'name', '') or '')
            if m:
                try:
                    shot_idx = int(m.group(1)) if shot_idx is None else shot_idx
                    cam_idx = int(m.group(2)) if cam_idx is None else cam_idx
                except Exception:
                    pass
        if shot_idx is None or cam_idx is None:
            return
        sh_token = f"SH{shot_idx:02d}" if shot_idx < 100 else f"SH{shot_idx:03d}"
        desired = f"CAM_RIG_{sh_token}_{cam_idx}"
        # Find highest Armature ancestor
        arm = None
        cur = getattr(cam_obj, 'parent', None)
        while cur is not None:
            try:
                if getattr(cur, 'type', None) == 'ARMATURE':
                    arm = cur
                cur = getattr(cur, 'parent', None)
            except Exception:
                break
        if arm is None:
            return
        final = desired
        guard = 1
        try:
            while final in _bpy.data.objects.keys() and _bpy.data.objects[final] is not arm:
                guard += 1
                final = f"{desired}_{guard}"
            arm.name = final
            if getattr(arm, 'data', None) is not None:
                try:
                    arm.data.name = final + ".Data"
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        pass


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
    # Image name captured at invoke-time from the Image Editor
    image_name: StringProperty(name="Image Name", default="")

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
        # Remember the image currently displayed in the Image Editor (panel lives there)
        try:
            if getattr(context, 'area', None) and getattr(context.area, 'type', '') == 'IMAGE_EDITOR':
                sp = getattr(context, 'space_data', None)
                img = getattr(sp, 'image', None) if sp else None
                if img is not None:
                    self.image_name = img.name
        except Exception:
            self.image_name = self.image_name or ""
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        # Save the image selected by user path
        path = (self.filepath or '').strip()
        if not path:
            self.report({'ERROR'}, "No file path provided")
            return {'CANCELLED'}
        # Strategy to choose the correct image to save:
        # 1) Use the image captured at invoke-time (from Image Editor panel)
        # 2) Look for an Image Editor in the current window showing an image (prefer Render Result/Viewer Node)
        # 3) Fallback to the latest Render Result.* or Viewer Node.* in bpy.data.images

        img = None

        # 1) Use captured name from invoke
        name = (getattr(self, 'image_name', '') or '').strip()
        if name:
            img = bpy.data.images.get(name)

        # 2) Search current window Image Editors if needed
        if img is None:
            try:
                preferred = None
                any_image = None
                for area in context.window.screen.areas:
                    if area.type == 'IMAGE_EDITOR':
                        sp = area.spaces.active
                        im = getattr(sp, 'image', None) if sp else None
                        if im is None:
                            continue
                        if any_image is None:
                            any_image = im
                        # Prefer Render Result / Viewer Node
                        if im.name.startswith("Render Result") or im.name.startswith("Viewer Node"):
                            preferred = im
                            break
                img = preferred or any_image or None
            except Exception:
                img = None

        # 3) Fallback to latest by prefix in bpy.data.images
        if img is None:
            try:
                def _latest_by_prefix(prefix: str):
                    candidates = [im for im in bpy.data.images if getattr(im, 'name', '').startswith(prefix)]
                    if not candidates:
                        return None
                    def _suffix_num(nm: str) -> int:
                        # Parse trailing .###; base name with no numeric suffix ranks lower
                        parts = nm.rsplit('.', 1)
                        if len(parts) == 2 and parts[1].isdigit():
                            try:
                                return int(parts[1])
                            except Exception:
                                return -1
                        return -1
                    candidates.sort(key=lambda im: _suffix_num(im.name))
                    return candidates[-1]
                img = _latest_by_prefix("Render Result") or _latest_by_prefix("Viewer Node")
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


class LIME_OT_rename_shot_cameras(Operator):
    bl_idname = "lime.rename_shot_cameras"
    bl_label = "Rename Cameras"
    bl_description = "Renames cameras in the active SHOT's camera collection to keep sequential order"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        shot = validate_scene.active_shot_context(ctx)
        if shot is None:
            return False
        cam_coll = validate_scene.get_shot_child_by_basename(shot, C_UTILS_CAM)
        if cam_coll is None:
            return False
        cams = [obj for obj in cam_coll.objects if getattr(obj, "type", None) == 'CAMERA']
        return len(cams) > 0

    def execute(self, context):
        shot = validate_scene.active_shot_context(context)
        if shot is None:
            self.report({'ERROR'}, "No active SHOT")
            return {'CANCELLED'}

        cam_coll = validate_scene.get_shot_child_by_basename(shot, C_UTILS_CAM)
        if cam_coll is None:
            self.report({'ERROR'}, "Active SHOT has no camera collection")
            return {'CANCELLED'}

        # Gather cameras in the SHOT camera collection
        cameras = [obj for obj in cam_coll.objects if getattr(obj, "type", None) == 'CAMERA']
        if not cameras:
            self.report({'WARNING'}, "No cameras found in SHOT camera collection")
            return {'CANCELLED'}

        # Stable ordering based on name; fallback to id if needed
        try:
            cameras.sort(key=lambda o: o.name)
        except Exception:
            pass

        # Determine shot numeric index for naming
        try:
            shot_idx = validate_scene.parse_shot_index(shot.name) or 0
        except Exception:
            shot_idx = 0

        # First pass: move all to unique temporary names to avoid collisions
        temp_names = {}
        for cam in cameras:
            base_tmp = f"__TMP_RENAME__{cam.name}"
            tmp = base_tmp
            suffix = 1
            try:
                while tmp in bpy.data.objects.keys():
                    suffix += 1
                    tmp = f"{base_tmp}_{suffix}"
                cam.name = tmp
                if getattr(cam, "data", None) is not None:
                    try:
                        cam.data.name = tmp + ".Data"
                    except Exception:
                        pass
                temp_names[cam] = tmp
            except Exception:
                temp_names[cam] = cam.name

        # Second pass: assign target sequential names
        renamed = 0
        for idx, cam in enumerate(cameras, 1):
            target = f"SHOT_{shot_idx:02d}_CAMERA_{idx}"
            final = target
            guard = 1
            try:
                # Avoid collisions with unrelated objects
                while final in bpy.data.objects.keys():
                    if bpy.data.objects[final] is cam:
                        break
                    guard += 1
                    final = f"{target}_{guard}"
                cam.name = final
                if getattr(cam, "data", None) is not None:
                    try:
                        cam.data.name = final + ".Data"
                    except Exception:
                        pass
                renamed += 1
                # After camera rename, rename parent Armature (rig)
                try:
                    _rename_parent_armature_for_camera(cam, shot_idx_hint=shot_idx, cam_idx_hint=idx)
                except Exception:
                    pass
            except Exception:
                pass

        self.report({'INFO'}, f"Renamed {renamed} cameras in {shot.name}")
        return {'FINISHED'}


__all__.append("LIME_OT_rename_shot_cameras")


class LIME_OT_delete_camera_rig(Operator):
    bl_idname = "lime.delete_camera_rig"
    bl_label = "Delete Camera (Rig)"
    bl_description = "Delete this camera and its rig, then rename remaining cameras in the SHOT"
    bl_options = {'REGISTER', 'UNDO'}

    camera_name: StringProperty(name="Camera Name", default="")

    @classmethod
    def poll(cls, ctx):
        name = getattr(cls, 'camera_name', '') or ''
        # Poll is static in Blender; rely on existence at execute time
        return True

    def execute(self, context):
        name = (self.camera_name or '').strip()
        cam = bpy.data.objects.get(name)
        if cam is None or getattr(cam, 'type', None) != 'CAMERA':
            self.report({'ERROR'}, f"Invalid camera: {name}")
            return {'CANCELLED'}

        # Determine SHOT for renaming later
        shot = None
        try:
            for c in getattr(cam, 'users_collection', []) or []:
                shot = validate_scene.find_shot_root_for_collection(c, context.scene)
                if shot is not None:
                    break
        except Exception:
            shot = None

        # Find rig root (top-most parent)
        root = cam
        try:
            while getattr(root, 'parent', None) is not None:
                root = root.parent
        except Exception:
            root = cam

        # Collect hierarchy (root + descendants)
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

        # Ensure OBJECT mode before removing
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

        # Remove children first, then parents
        removed = 0
        for ob in reversed(rig_objects):
            try:
                bpy.data.objects.remove(ob, do_unlink=True)
                removed += 1
            except Exception:
                pass

        # Rename remaining cameras in the shot
        if shot is not None:
            try:
                cam_coll = validate_scene.get_shot_child_by_basename(shot, C_UTILS_CAM)
                if cam_coll is not None:
                    cameras = [obj for obj in cam_coll.objects if getattr(obj, 'type', None) == 'CAMERA']
                    cameras.sort(key=lambda o: o.name)
                    # First pass: temp unique names to avoid collisions
                    for cam2 in cameras:
                        try:
                            tmp = f"__TMP_RENAME__{cam2.name}"
                            guard = 1
                            base = tmp
                            while tmp in bpy.data.objects.keys():
                                guard += 1
                                tmp = f"{base}_{guard}"
                            cam2.name = tmp
                            if getattr(cam2, 'data', None) is not None:
                                try:
                                    cam2.data.name = tmp + '.Data'
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    # Second pass: assign sequential names and rename rigs
                    try:
                        shot_idx = validate_scene.parse_shot_index(shot.name) or 0
                    except Exception:
                        shot_idx = 0
                    for idx, cam2 in enumerate(cameras, 1):
                        final = f"SHOT_{shot_idx:02d}_CAMERA_{idx}"
                        guard = 1
                        name_try = final
                        try:
                            while name_try in bpy.data.objects.keys() and bpy.data.objects[name_try] is not cam2:
                                guard += 1
                                name_try = f"{final}_{guard}"
                            cam2.name = name_try
                            if getattr(cam2, 'data', None) is not None:
                                try:
                                    cam2.data.name = name_try + '.Data'
                                except Exception:
                                    pass
                            # Rename its parent armature rig accordingly
                            try:
                                _rename_parent_armature_for_camera(cam2, shot_idx_hint=shot_idx, cam_idx_hint=idx)
                            except Exception:
                                pass
                        except Exception:
                            pass
            except Exception:
                pass

        self.report({'INFO'}, f"Deleted {removed} object(s)")
        return {'FINISHED'}


class LIME_OT_pose_camera_rig(Operator):
    bl_idname = "lime.pose_camera_rig"
    bl_label = "Pose Rig"
    bl_description = "Activate the camera's rig Armature and switch to Pose Mode"
    bl_options = {'REGISTER'}

    camera_name: StringProperty(name="Camera Name", default="")

    def execute(self, context):
        name = (self.camera_name or '').strip()
        cam = bpy.data.objects.get(name)
        if cam is None or getattr(cam, 'type', None) != 'CAMERA':
            self.report({'ERROR'}, f"Invalid camera: {name}")
            return {'CANCELLED'}
        # Find highest Armature ancestor
        arm = None
        cur = getattr(cam, 'parent', None)
        while cur is not None:
            try:
                if getattr(cur, 'type', None) == 'ARMATURE':
                    arm = cur
                cur = getattr(cur, 'parent', None)
            except Exception:
                break
        if arm is None:
            self.report({'WARNING'}, 'No Armature found for this camera')
            return {'CANCELLED'}

        # Select and activate the armature, switch to POSE mode
        try:
            for ob in context.selected_objects or []:
                try:
                    ob.select_set(False)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            arm.select_set(True)
        except Exception:
            pass
        try:
            context.view_layer.objects.active = arm
        except Exception:
            pass
        # Try to switch to POSE mode; use override if available
        switched = False
        try:
            bpy.ops.object.mode_set(mode='POSE')
            switched = True
        except Exception:
            pass
        if not switched:
            try:
                win = None; area = None; region = None
                for w in context.window_manager.windows:
                    for a in w.screen.areas:
                        if a.type == 'VIEW_3D':
                            r = next((rg for rg in a.regions if rg.type == 'WINDOW'), None)
                            if r is not None:
                                win = w; area = a; region = r
                                break
                    if win:
                        break
                if win and area and region:
                    with bpy.context.temp_override(window=win, area=area, region=region, scene=context.scene, view_layer=context.view_layer, active_object=arm):
                        bpy.ops.object.mode_set(mode='POSE')
                        switched = True
            except Exception:
                pass
        if not switched:
            self.report({'WARNING'}, 'Could not enter Pose Mode')
            return {'CANCELLED'}
        self.report({'INFO'}, f"Rig active: {arm.name}")
        return {'FINISHED'}





class LIME_OT_sync_camera_list(Operator):
    bl_idname = 'lime.sync_camera_list'
    bl_label = 'Refresh Cameras'
    bl_description = 'Refresh the camera list from the current .blend'
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        items = getattr(scene, 'lime_render_cameras', None)
        if items is None:
            self.report({'ERROR'}, 'Camera list storage not available')
            return {'CANCELLED'}
        try:
            items.clear()
            cams = [o for o in bpy.data.objects if getattr(o, 'type', None) == 'CAMERA']
            cams.sort(key=lambda o: o.name)
            for cam in cams:
                it = items.add()
                it.name = cam.name
            try:
                active_name = getattr(scene.camera, 'name', '') if getattr(scene, 'camera', None) else ''
                if active_name:
                    for i, it in enumerate(items):
                        if it.name == active_name:
                            scene.lime_render_cameras_index = i
                            break
            except Exception:
                pass
        except Exception:
            self.report({'WARNING'}, 'Could not refresh camera list')
            return {'CANCELLED'}
        self.report({'INFO'}, f'Cameras: {len(items)}')
        return {'FINISHED'}


__all__.append('LIME_OT_sync_camera_list')


class LIME_OT_add_camera_rig_and_sync(Operator):
    bl_idname = 'lime.add_camera_rig_and_sync'
    bl_label = 'Add Camera (Rig) and Refresh'
    bl_description = 'Create a camera rig using Lime operator and refresh the list'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            bpy.ops.lime.add_camera_rig('INVOKE_DEFAULT')
        except Exception:
            try:
                bpy.ops.lime.add_camera_rig()
            except Exception:
                self.report({'ERROR'}, 'Failed to add camera rig')
                return {'CANCELLED'}
        try:
            bpy.ops.lime.sync_camera_list()
        except Exception:
            pass
        try:
            import bpy as _bpy3
            def _delayed_sync():
                try:
                    _bpy3.ops.lime.sync_camera_list()
                except Exception:
                    pass
                return None
            _bpy3.app.timers.register(_delayed_sync, first_interval=0.1)
        except Exception:
            pass
        return {'FINISHED'}


__all__.append('LIME_OT_add_camera_rig_and_sync')


class LIME_OT_delete_camera_rig_and_sync(Operator):
    bl_idname = 'lime.delete_camera_rig_and_sync'
    bl_label = 'Delete Camera (Rig) and Refresh'
    bl_description = 'Delete the selected camera rig and refresh the list'
    bl_options = {'REGISTER', 'UNDO'}

    camera_name: StringProperty(name='Camera Name', default='')

    def execute(self, context):
        name = (self.camera_name or '').strip()
        if not name:
            self.report({'WARNING'}, 'No camera selected')
            return {'CANCELLED'}
        try:
            bpy.ops.lime.delete_camera_rig(camera_name=name)
        except Exception:
            self.report({'ERROR'}, f'Failed to delete camera rig: {name}')
            return {'CANCELLED'}
        try:
            bpy.ops.lime.sync_camera_list()
        except Exception:
            pass
        return {'FINISHED'}


__all__.append('LIME_OT_delete_camera_rig_and_sync')

__all__.append("LIME_OT_delete_camera_rig")
__all__.append("LIME_OT_pose_camera_rig")


