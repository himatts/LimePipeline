import bpy
from bpy.types import Operator
from bpy.props import StringProperty, IntProperty, EnumProperty

from ..core import validate_scene
from ..data.templates import C_CAM


IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.exr', '.tif', '.tiff'}


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
        cam_coll = validate_scene.get_shot_child_by_basename(shot, C_CAM)
        if cam_coll is None:
            return False
        cams = [obj for obj in cam_coll.objects if getattr(obj, "type", None) == 'CAMERA']
        return len(cams) > 0

    def execute(self, context):
        shot = validate_scene.active_shot_context(context)
        if shot is None:
            self.report({'ERROR'}, "No active SHOT")
            return {'CANCELLED'}

        cam_coll = validate_scene.get_shot_child_by_basename(shot, C_CAM)
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
                cam_coll = validate_scene.get_shot_child_by_basename(shot, C_CAM)
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
            # Only cameras in active scene; prefer active SHOT camera collection when present
            from ..core import validate_scene
            from ..data.templates import C_CAM
            try:
                shot = validate_scene.active_shot_context(context)
            except Exception:
                shot = None
            if shot:
                try:
                    cam_coll = validate_scene.get_shot_child_by_basename(shot, C_CAM)
                except Exception:
                    cam_coll = None
                if cam_coll:
                    cams = [o for o in cam_coll.objects if getattr(o, 'type', None) == 'CAMERA']
                else:
                    cams = [o for o in scene.objects if getattr(o, 'type', None) == 'CAMERA']
            else:
                cams = [o for o in scene.objects if getattr(o, 'type', None) == 'CAMERA']
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


## Removed: LIME_OT_add_camera_rig_and_sync (merged into LIME_OT_add_camera_rig)


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


class LIME_OT_add_camera_rig(Operator):
    bl_idname = "lime.add_camera_rig"
    bl_label = "Create Camera (Rig)"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Add a camera rig to the SHOT's 00_CAM collection"

    rig_type: EnumProperty(
        name="Rig Type",
        items=(
            ('DOLLY', "Dolly", "Dolly rig"),
            ('CRANE', "Crane", "Crane rig"),
            ('2D', "2D", "2D rig"),
        ),
        default='DOLLY',
    )

    @classmethod
    def poll(cls, ctx):
        shot = validate_scene.active_shot_context(ctx)
        return shot is not None

    def execute(self, context):
        shot = validate_scene.active_shot_context(context)
        if shot is None:
            self.report({'ERROR'}, "No active SHOT")
            return {'CANCELLED'}

        cam_coll = validate_scene.get_shot_child_by_basename(shot, C_CAM)
        if cam_coll is None:
            self.report({'ERROR'}, "Active SHOT has no camera collection")
            return {'CANCELLED'}

        # Pre-info: number of existing cameras and SHOT number
        try:
            cams_before = [o for o in cam_coll.objects if getattr(o, "type", None) == 'CAMERA']
            existing_cam_count = len(cams_before)
            before_cam_names = set(o.name for o in cams_before)
        except Exception:
            existing_cam_count = 0
            before_cam_names = set()
        print(f"[LimePV] AddCameraRig: shot={shot.name}, existing_cam_count={existing_cam_count}, before_cam_names={sorted(list(before_cam_names))}")
        try:
            shot_idx = validate_scene.parse_shot_index(shot.name) or 0
        except Exception:
            shot_idx = 0

        # Activate the camera collection as target
        target_layer = None
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
            target_layer = _find_layer(root_layer, cam_coll)
            if target_layer is not None:
                context.view_layer.active_layer_collection = target_layer
        except Exception:
            pass

        # Confirmed operator: object.build_camera_rig(mode=...)
        created = False
        last_error = None
        mode = self.rig_type
        if mode == '2D':
            mode_candidates = ['TWO_D', '2D']
        else:
            mode_candidates = [mode]

        # Locate a VIEW_3D to run the operator
        win = None
        area = None
        region = None
        for w in context.window_manager.windows:
            for a in w.screen.areas:
                if a.type == 'VIEW_3D':
                    r = next((rg for rg in a.regions if rg.type == 'WINDOW'), None)
                    if r is not None:
                        win = w
                        area = a
                        region = r
                        break
            if win:
                break
        print(f"[LimePV] View3D located: win={bool(win)}, area={bool(area)}, region={bool(region)}")

        # Save objects before for detection of new ones (by name)
        before_objs = {obj.name for obj in bpy.data.objects}
        print(f"[LimePV] Objects before: {len(before_objs)}")

        # Ensure OBJECT mode in 3D context
        try:
            if win and area and region:
                with bpy.context.temp_override(window=win, area=area, region=region, scene=context.scene, view_layer=context.view_layer):
                    bpy.ops.object.mode_set(mode='OBJECT')
            else:
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

        # Verify operator availability
        build_op = getattr(bpy.ops.object, 'build_camera_rig', None)
        if build_op is None:
            last_error = "Operator object.build_camera_rig not found"
            print("[LimePV] build_camera_rig operator NOT found")
        else:
            print(f"[LimePV] build_camera_rig operator available, mode candidates={mode_candidates}")
            for m in mode_candidates:
                try:
                    if win and area and region:
                        with bpy.context.temp_override(window=win, area=area, region=region, scene=context.scene, view_layer=context.view_layer):
                            res = bpy.ops.object.build_camera_rig('EXEC_DEFAULT', mode=m)
                    else:
                        res = bpy.ops.object.build_camera_rig('EXEC_DEFAULT', mode=m)
                    print(f"[LimePV] build_camera_rig result for mode={m}: {res}")
                    if res == {'FINISHED'}:
                        created = True
                        break
                except Exception as ex:
                    last_error = str(ex)
                    print(f"[LimePV] build_camera_rig error for mode={m}: {last_error}")
                    continue

        if not created:
            msg = "Could not create camera. Is 'Add Camera Rigs' enabled?"
            if last_error:
                msg += f" ({last_error})"
            self.report({'ERROR'}, msg)
            print(f"[LimePV] Creation failed: {msg}")
            return {'CANCELLED'}

        # Rename only the new camera(s) directly (no relink or rig changes)
        try:
            after_names = {obj.name for obj in bpy.data.objects}
            new_obj_names = [name for name in after_names if name not in before_objs]
            new_objs = [bpy.data.objects[name] for name in new_obj_names]
            print(f"[LimePV] New objects: {[ (o.name, getattr(o,'type',None)) for o in new_objs ]}")
            new_cams = [o for o in new_objs if getattr(o, "type", None) == 'CAMERA']
            if not new_cams:
                print("[LimePV] No new camera objects detected; aborting rename")
            else:
                new_cams.sort(key=lambda o: o.name)
                next_idx = existing_cam_count + 1
                for cam in new_cams:
                    try:
                        target_name = f"SHOT_{shot_idx:02d}_CAMERA_{next_idx}"
                        while target_name in bpy.data.objects.keys():
                            next_idx += 1
                            target_name = f"SHOT_{shot_idx:02d}_CAMERA_{next_idx}"
                        print(f"[LimePV] Simple rename camera {cam.name} -> {target_name}")
                        cam.name = target_name
                        if getattr(cam, "data", None) is not None:
                            cam.data.name = target_name + ".Data"
                        # After camera rename, rename its parent Armature (rig)
                        try:
                            _rename_parent_armature_for_camera(cam, shot_idx_hint=shot_idx, cam_idx_hint=next_idx)
                        except Exception:
                            pass
                        next_idx += 1
                    except Exception as ex:
                        print(f"[LimePV] Simple rename error: {ex}")
        except Exception:
            pass

        self.report({'INFO'}, f"Camera created in {shot.name}/{C_CAM}")
        return {'FINISHED'}


__all__.append('LIME_OT_add_camera_rig')



