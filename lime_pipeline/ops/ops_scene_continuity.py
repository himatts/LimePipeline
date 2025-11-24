"""
Scene Continuity Operator

Creates the next scene .blend using the current file's naming, freezing the pose of a
selected SHOT collection and the active camera at a chosen handoff frame. The operator
keeps the original file untouched by saving a copy, undoing local changes, and finally
opening the new file.
"""

from __future__ import annotations

from pathlib import Path

import bpy
from bpy.types import Operator

from ..core import validate_scene
from ..core.naming import build_next_scene_path, hydrate_state_from_filepath
from ..scene.scene_utils import _format_shot_name
from .ops_duplicate_scene import _replace_sh_tokens


def _ensure_unique_action(id_block):
    ad = getattr(id_block, "animation_data", None)
    if ad is None:
        return None
    action = getattr(ad, "action", None)
    if action is None:
        return None
    try:
        if getattr(action, "users", 0) > 1:
            ad.action = action.copy()
            action = ad.action
    except Exception:
        pass
    return action


def _clear_fcurves(action, prefixes: tuple[str, ...]) -> None:
    if action is None:
        return
    try:
        for fc in list(getattr(action, "fcurves", []) or []):
            path = getattr(fc, "data_path", "") or ""
            if any(path.startswith(pref) for pref in prefixes):
                try:
                    action.fcurves.remove(fc)
                except Exception:
                    pass
    except Exception:
        pass


def _clear_all_fcurves(action) -> None:
    if action is None:
        return
    try:
        for fc in list(getattr(action, "fcurves", []) or []):
            action.fcurves.remove(fc)
    except Exception:
        pass


def _clear_animation_container(id_block):
    action = _ensure_unique_action(id_block)
    _clear_all_fcurves(action)
    try:
        ad = getattr(id_block, "animation_data", None)
        nla_tracks = getattr(ad, "nla_tracks", None) if ad else None
        if nla_tracks:
            for track in list(nla_tracks) or []:
                try:
                    nla_tracks.remove(track)
                except Exception:
                    pass
    except Exception:
        pass
    return action


def _has_subtarget_constraints(obj: bpy.types.Object) -> bool:
    try:
        for con in getattr(obj, "constraints", []) or []:
            if getattr(con, "target", None) is not None and getattr(con, "subtarget", ""):
                return True
    except Exception:
        pass
    return False


def _freeze_pose_bones(obj: bpy.types.Object, frame: int) -> None:
    pose = getattr(obj, "pose", None)
    bones = getattr(pose, "bones", None) if pose else None
    if not bones:
        return
    for bone in bones:
        try:
            bone.keyframe_insert(data_path="location", frame=frame)
        except Exception:
            pass
        mode = getattr(bone, "rotation_mode", "XYZ") or "XYZ"
        if mode == 'QUATERNION':
            try:
                bone.keyframe_insert(data_path="rotation_quaternion", frame=frame)
            except Exception:
                pass
        elif mode == 'AXIS_ANGLE':
            try:
                bone.keyframe_insert(data_path="rotation_axis_angle", frame=frame)
            except Exception:
                pass
        else:
            try:
                bone.keyframe_insert(data_path="rotation_euler", frame=frame)
            except Exception:
                pass
        try:
            bone.keyframe_insert(data_path="scale", frame=frame)
        except Exception:
            pass


def _freeze_shape_keys(obj: bpy.types.Object, frame: int) -> None:
    try:
        data = getattr(obj, "data", None)
        sk = getattr(data, "shape_keys", None)
    except Exception:
        sk = None
    if sk is None:
        return
    if not _is_local_id(sk):
        return
    try:
        action = _ensure_unique_action(sk)
        if action:
            _clear_fcurves(action, ("key_blocks",))
    except Exception:
        pass
    try:
        for block in getattr(sk, "key_blocks", []) or []:
            try:
                block.keyframe_insert(data_path="value", frame=frame)
            except Exception:
                pass
    except Exception:
        pass


def _evaluated_matrix(obj: bpy.types.Object, depsgraph) -> bpy.types.Matrix | None:
    matrix = None
    try:
        if depsgraph is not None:
            eval_obj = obj.evaluated_get(depsgraph)
            matrix = eval_obj.matrix_world.copy()
    except Exception:
        matrix = None
    if matrix is None:
        try:
            matrix = obj.matrix_world.copy()
        except Exception:
            matrix = None
    return matrix


def _is_local_id(id_block) -> bool:
    try:
        if id_block is None:
            return False
        if getattr(id_block, "library", None) is not None:
            return False
        if getattr(id_block, "override_library", None) is not None:
            return False
    except Exception:
        return False
    return True


def _key_object_transform(obj: bpy.types.Object, matrix_world, frame: int) -> None:
    try:
        obj.matrix_world = matrix_world
    except Exception:
        pass
    try:
        obj.keyframe_insert(data_path="location", frame=frame)
    except Exception:
        pass
    rot_mode = getattr(obj, "rotation_mode", "XYZ") or "XYZ"
    if rot_mode == 'QUATERNION':
        try:
            obj.keyframe_insert(data_path="rotation_quaternion", frame=frame)
        except Exception:
            pass
    elif rot_mode == 'AXIS_ANGLE':
        try:
            obj.keyframe_insert(data_path="rotation_axis_angle", frame=frame)
        except Exception:
            pass
    else:
        try:
            obj.keyframe_insert(data_path="rotation_euler", frame=frame)
        except Exception:
            pass
    try:
        obj.keyframe_insert(data_path="scale", frame=frame)
    except Exception:
        pass


def _camera_has_dof_subtarget(cam_obj: bpy.types.Object) -> bool:
    try:
        data = getattr(cam_obj, "data", None)
        dof = getattr(data, "dof", None)
        focus_obj = getattr(dof, "focus_object", None) if dof else None
        focus_subtarget = getattr(dof, "focus_subtarget", "") if dof else ""
        return focus_obj is not None and bool(focus_subtarget)
    except Exception:
        return False


def _freeze_camera_params(cam_obj: bpy.types.Object, frame: int) -> None:
    cam_data = getattr(cam_obj, "data", None)
    if cam_data is None:
        return
    if not _is_local_id(cam_data):
        return
    lens = getattr(cam_data, "lens", None)
    dof = getattr(cam_data, "dof", None)
    focus_distance = getattr(dof, "focus_distance", None) if dof else None
    uses_dof_subtarget = _camera_has_dof_subtarget(cam_obj)

    action = _ensure_unique_action(cam_data) if not uses_dof_subtarget else None
    if action:
        _clear_fcurves(action, ("lens", "dof.focus_distance"))

    try:
        if lens is not None:
            cam_data.lens = lens
            cam_data.keyframe_insert(data_path="lens", frame=frame)
    except Exception:
        pass
    try:
        if focus_distance is not None and dof is not None:
            dof.focus_distance = focus_distance
            cam_data.keyframe_insert(data_path="dof.focus_distance", frame=frame)
    except Exception:
        pass


def _rename_shot_subtree(shot: bpy.types.Collection, origin_idx: int | None, new_idx: int) -> None:
    """Rename SH/SHOT tokens inside the shot subtree to the new index using the shared helper."""
    if origin_idx is None or origin_idx == new_idx:
        return

    def _iter_collections(root: bpy.types.Collection):
        stack = [root]
        while stack:
            col = stack.pop()
            yield col
            try:
                stack.extend(list(col.children))
            except Exception:
                pass

    for col in _iter_collections(shot):
        try:
            col.name = _replace_sh_tokens(col.name, origin_idx, new_idx)
        except Exception:
            pass
    try:
        for obj in shot.all_objects:
            try:
                obj.name = _replace_sh_tokens(obj.name, origin_idx, new_idx)
            except Exception:
                pass
            try:
                data = getattr(obj, "data", None)
                if data is not None and hasattr(data, "name"):
                    data.name = _replace_sh_tokens(data.name, origin_idx, new_idx)
            except Exception:
                pass
    except Exception:
        pass


class LIME_OT_stage_create_next_scene_file(Operator):
    bl_idname = "lime.stage_create_next_scene_file"
    bl_label = "Create Next Scene File"
    bl_description = "Create the next scene .blend continuing from a selected SHOT at the chosen handoff frame"
    bl_options = {"REGISTER"}

    def _resolve_context(self, context):
        st = getattr(context.window_manager, "lime_pipeline", None)
        if st is None:
            raise ValueError("Lime Pipeline state not available. Open 'Project Organization' first.")

        try:
            hydrate_state_from_filepath(st)
        except Exception:
            pass

        blend_path = Path(getattr(bpy.data, "filepath", "") or "")
        if not blend_path.name:
            raise ValueError("Save the current .blend before creating the next scene file.")

        scene = context.scene
        if scene is None:
            raise ValueError("No active scene found.")

        camera = getattr(scene, "camera", None)
        if camera is None or getattr(camera, "type", None) != 'CAMERA':
            raise ValueError("The scene needs an active camera to capture continuity.")

        shot_root = None
        shot_name = getattr(st, "scene_continuity_shot_name", "NONE")
        if shot_name and shot_name != "NONE":
            try:
                shot_root = bpy.data.collections.get(shot_name)
            except Exception:
                shot_root = None
        if shot_root is None:
            continuity_coll = getattr(st, "scene_continuity_shot", None)
            if continuity_coll is None:
                raise ValueError("Select a SHOT collection to continue from.")
            shot_root = validate_scene.find_shot_root_for_collection(continuity_coll, scene)
            if shot_root is None and validate_scene.is_shot_name(getattr(continuity_coll, "name", "")):
                shot_root = continuity_coll
        if shot_root is None:
            raise ValueError("The selected collection is not inside a 'SHOT ##' root.")

        frame_mode = getattr(st, "scene_continuity_frame_mode", "CURRENT")
        if frame_mode == "SCENE_END":
            frame_handoff = int(getattr(scene, "frame_end", scene.frame_current))
        else:
            frame_handoff = int(getattr(scene, "frame_current", 1))

        local_mode = bool(getattr(st, "use_local_project", False))
        root_override = getattr(st, "project_root", None) or None
        try:
            addon_key = (__package__ or "lime_pipeline").split(".", 1)[0]
            prefs = context.preferences.addons[addon_key].preferences
        except Exception:
            prefs = None

        target_path, info = build_next_scene_path(
            blend_path,
            project_root=root_override,
            local_mode=local_mode,
            state=st,
            prefs=prefs,
        )
        if target_path.exists():
            raise ValueError(f"Target file already exists:\n{target_path}")

        return {
            "state": st,
            "scene": scene,
            "shot_root": shot_root,
            "frame_handoff": frame_handoff,
            "camera": camera,
            "target_path": target_path,
            "info": info,
        }

    def _prepare_scene_snapshot(
        self,
        scene: bpy.types.Scene,
        shot_root: bpy.types.Collection,
        camera: bpy.types.Object,
        frame_handoff: int,
    ) -> None:
        # Evaluate at handoff frame
        try:
            scene.frame_set(frame_handoff)
            if hasattr(bpy.context, "view_layer"):
                bpy.context.view_layer.update()
        except Exception:
            pass

        depsgraph = None
        try:
            depsgraph = bpy.context.evaluated_depsgraph_get()
        except Exception:
            depsgraph = None

        # Limit processing to the target shot + active camera to avoid touching unrelated rigs
        objects = set()
        try:
            for obj in shot_root.all_objects:
                objects.add(obj)
        except Exception:
            pass
        objects.add(camera)

        for obj in objects:
            if obj is None:
                continue
            # Capture evaluated world matrix
            matrix = _evaluated_matrix(obj, depsgraph)
            is_local = _is_local_id(obj)
            if not is_local:
                continue
            has_subtargets = _has_subtarget_constraints(obj)
            if obj.type != 'CAMERA' and not has_subtargets:
                _clear_animation_container(obj)
            _key_object_transform(obj, matrix, 1)
            _freeze_pose_bones(obj, 1)
            if not has_subtargets:
                _freeze_shape_keys(obj, 1)
            data_block = getattr(obj, "data", None)
            if (
                data_block is not None
                and _is_local_id(data_block)
                and obj.type != 'CAMERA'
                and not has_subtargets
            ):
                _clear_animation_container(data_block)

        _freeze_camera_params(camera, 1)
        _clear_animation_container(scene)
        if _is_local_id(getattr(scene, "world", None)):
            _clear_animation_container(getattr(scene, "world", None))

        # Remove camera markers and switchers; keep only active camera
        try:
            markers = getattr(scene, "timeline_markers", None)
            if markers is not None:
                for marker in list(markers):
                    try:
                        marker.camera = camera
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            other_cams = [obj for obj in scene.objects if getattr(obj, "type", None) == 'CAMERA' and obj != camera]
        except Exception:
            other_cams = []
        for cam in other_cams:
            try:
                cam.hide_viewport = True
            except Exception:
                pass
            try:
                cam.hide_render = True
            except Exception:
                pass
            try:
                cam.hide_select = True
            except Exception:
                pass

        # Hide other SHOT roots to keep the new file focused on the handoff
        try:
            others = [
                col
                for col, _idx in validate_scene.list_shot_roots(scene)
                if col is not None and col != shot_root
            ]
        except Exception:
            others = []
        for col in others:
            try:
                col.hide_viewport = True
            except Exception:
                pass
            try:
                col.hide_render = True
            except Exception:
                pass

        # Reset timeline range for the new scene
        try:
            scene.frame_start = 1
        except Exception:
            pass
        try:
            scene.frame_end = 250
        except Exception:
            pass
        try:
            scene.frame_set(1)
        except Exception:
            pass

    def _rename_shot(self, scene: bpy.types.Scene, shot_root: bpy.types.Collection) -> None:
        origin_idx = validate_scene.parse_shot_index(getattr(shot_root, "name", ""))
        desired_name = _format_shot_name(1)

        # If another collection already uses SHOT 01, move it out of the way to a free index
        conflict = bpy.data.collections.get(desired_name)
        if conflict is not None and conflict != shot_root:
            try:
                spare_idx = validate_scene.next_shot_index(scene)
                conflict.name = _format_shot_name(spare_idx)
            except Exception:
                pass

        try:
            shot_root.name = desired_name
        except Exception:
            pass

        _rename_shot_subtree(shot_root, origin_idx, 1)

    def execute(self, context):
        try:
            ctx = self._resolve_context(context)
        except ValueError as ex:
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}
        except Exception as ex:
            self.report({"ERROR"}, f"Scene continuity failed: {ex}")
            return {"CANCELLED"}

        scene = ctx["scene"]
        shot_root = ctx["shot_root"]
        camera = ctx["camera"]
        frame_handoff = ctx["frame_handoff"]
        target_path = ctx["target_path"]
        info = ctx["info"]

        # Ensure undo stack snapshot before mutating the scene
        undo_started = False
        try:
            bpy.ops.ed.undo_push(message="Lime Scene Continuity (prepare)")
            undo_started = True
        except Exception:
            pass

        try:
            self._prepare_scene_snapshot(scene, shot_root, camera, frame_handoff)
            self._rename_shot(scene, shot_root)

            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

            bpy.ops.wm.save_as_mainfile(filepath=str(target_path), copy=True)
        except Exception as ex:
            if undo_started:
                try:
                    bpy.ops.ed.undo()
                except Exception:
                    pass
            self.report({"ERROR"}, f"Could not prepare continuity scene: {ex}")
            return {"CANCELLED"}

        # Revert original file to its previous state
        if undo_started:
            try:
                bpy.ops.ed.undo()
            except Exception:
                pass

        try:
            bpy.ops.wm.open_mainfile(filepath=str(target_path))
        except Exception as ex:
            self.report(
                {"WARNING"},
                f"New scene saved at {target_path}, but opening it failed: {ex}",
            )
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            f"Created next scene file (SC{info.get('next_sc'):03d}) at {target_path}",
        )
        return {"FINISHED"}


__all__ = [
    "LIME_OT_stage_create_next_scene_file",
]
