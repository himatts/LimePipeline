from __future__ import annotations

from typing import Dict
from uuid import uuid4

import bpy
from bpy.types import Operator

from ..core import validate_scene
from ..data.templates import C_UTILS_CAM
from .ops_alpha_manager import ensure_event_tracks, rebuild_all_drivers
from .ops_cameras import _rename_parent_armature_for_camera  # reuse rig rename helper
from .ops_stage import (
    _ShotSceneRenamer,
    _find_max_shot_index,
    _format_sh_root,
    _shot_index_width,
)


_TAG_KEY = "_lp_src_uid"


def _tag_source_objects(scene: bpy.types.Scene) -> None:
    for obj in scene.objects:
        try:
            if getattr(obj, "library", None) is not None:
                continue
            if getattr(obj, "override_library", None) is not None:
                continue
            obj[_TAG_KEY] = uuid4().hex
        except Exception:
            pass


def _build_obj_map(scene: bpy.types.Scene) -> Dict[str, bpy.types.Object]:
    mapping: Dict[str, bpy.types.Object] = {}
    for obj in scene.objects:
        try:
            uid = obj.get(_TAG_KEY, "")
            if uid:
                mapping[uid] = obj
        except Exception:
            pass
    return mapping


def _make_object_data_single_user(obj: bpy.types.Object) -> None:
    data = getattr(obj, "data", None)
    if data is None:
        return
    try:
        if getattr(data, "library", None) is None and getattr(data, "users", 1) > 1:
            obj.data = data.copy()
    except Exception:
        pass


def _ensure_node_group_single_user(node_tree: bpy.types.NodeTree, node_group_cache: Dict[bpy.types.NodeTree, bpy.types.NodeTree]) -> None:
    if node_tree is None:
        return
    nodes = getattr(node_tree, 'nodes', None)
    if not nodes:
        return
    for node in list(nodes) or []:
        try:
            if getattr(node, 'type', '') != 'GROUP':
                continue
            sub_tree = getattr(node, 'node_tree', None)
            if sub_tree is None or getattr(sub_tree, 'library', None) is not None:
                continue
            replacement = node_group_cache.get(sub_tree)
            if replacement is None:
                try:
                    replacement = sub_tree.copy()
                except Exception:
                    replacement = None
                if replacement is None:
                    continue
                node_group_cache[sub_tree] = replacement
                _ensure_node_group_single_user(replacement, node_group_cache)
            node.node_tree = replacement
        except Exception:
            pass


def _ensure_material_copy(
    mat: bpy.types.Material,
    material_cache: Dict[bpy.types.Material, bpy.types.Material],
    node_group_cache: Dict[bpy.types.NodeTree, bpy.types.NodeTree],
) -> bpy.types.Material | None:
    if mat is None:
        return None
    if getattr(mat, 'library', None) is not None:
        return mat
    cached = material_cache.get(mat)
    if cached is not None:
        return cached
    try:
        mat_copy = mat.copy()
    except Exception:
        material_cache[mat] = mat
        return mat
    material_cache[mat] = mat_copy
    try:
        node_tree = getattr(mat_copy, 'node_tree', None)
        if node_tree is not None:
            _ensure_node_group_single_user(node_tree, node_group_cache)
    except Exception:
        pass
    return mat_copy


def _make_materials_single_user(
    obj: bpy.types.Object,
    material_cache: Dict[bpy.types.Material, bpy.types.Material],
    node_group_cache: Dict[bpy.types.NodeTree, bpy.types.NodeTree],
) -> None:
    slots = getattr(obj, 'material_slots', None)
    if not slots:
        return
    for slot in list(slots):
        mat = getattr(slot, 'material', None)
        if mat is None:
            continue
        try:
            new_mat = _ensure_material_copy(mat, material_cache, node_group_cache)
            if new_mat is not None and new_mat is not mat:
                slot.material = new_mat
        except Exception:
            pass


def _make_geo_nodes_single_user(obj: bpy.types.Object) -> None:
    for mod in getattr(obj, "modifiers", []) or []:
        try:
            if getattr(mod, "type", "") == "NODES":
                ng = getattr(mod, "node_group", None)
                if ng and getattr(ng, "library", None) is None and getattr(ng, "users", 1) > 1:
                    mod.node_group = ng.copy()
        except Exception:
            pass


def _make_actions_single_user(obj: bpy.types.Object) -> None:
    try:
        ad = getattr(obj, "animation_data", None)
        if ad is not None and getattr(ad, "action", None) is not None:
            act = ad.action
            if getattr(act, "users", 1) > 1:
                ad.action = act.copy()
    except Exception:
        pass
    try:
        data = getattr(obj, "data", None)
        if data is not None:
            ad2 = getattr(data, "animation_data", None)
            if ad2 is not None and getattr(ad2, "action", None) is not None:
                act2 = ad2.action
                if getattr(act2, "users", 1) > 1:
                    ad2.action = act2.copy()
    except Exception:
        pass


def _make_world_single_user(scene: bpy.types.Scene) -> None:
    try:
        world = getattr(scene, "world", None)
        if world is not None and getattr(world, "library", None) is None and getattr(world, "users", 1) > 1:
            scene.world = world.copy()
    except Exception:
        pass


def _ensure_scene_alpha_action_single_user(scene: bpy.types.Scene) -> None:
    try:
        ad = getattr(scene, 'animation_data', None)
        if ad is None:
            return
        action = getattr(ad, 'action', None)
        if action is None:
            return
        if getattr(action, 'users', 1) > 1:
            ad.action = action.copy()
    except Exception:
        pass


def _remap_relations(scene: bpy.types.Scene, obj_map: Dict[str, bpy.types.Object]) -> None:
    def _maybe_remap(target: bpy.types.Object | None) -> bpy.types.Object | None:
        try:
            if target is None:
                return None
            uid = target.get(_TAG_KEY, "")
            if uid and uid in obj_map and obj_map[uid] is not target:
                return obj_map[uid]
        except Exception:
            pass
        return target

    for obj in scene.objects:
        try:
            for con in getattr(obj, "constraints", []) or []:
                try:
                    if hasattr(con, "target"):
                        con.target = _maybe_remap(getattr(con, "target", None))
                    if hasattr(con, "object"):
                        con.object = _maybe_remap(getattr(con, "object", None))
                except Exception:
                    pass
        except Exception:
            pass
        try:
            for mod in getattr(obj, "modifiers", []) or []:
                for attr in ("object", "target", "mirror_object"):
                    try:
                        if hasattr(mod, attr):
                            setattr(mod, attr, _maybe_remap(getattr(mod, attr, None)))
                    except Exception:
                        pass
        except Exception:
            pass


def _cleanup_tags(*scenes: bpy.types.Scene) -> None:
    for scene in scenes:
        if scene is None:
            continue
        for obj in scene.objects:
            try:
                if _TAG_KEY in obj:
                    del obj[_TAG_KEY]
            except Exception:
                pass


def _clone_alpha_events(src_scene: bpy.types.Scene, dst_scene: bpy.types.Scene) -> None:
    events = getattr(src_scene, "lime_tb_alpha_events", None)
    dst_events = getattr(dst_scene, "lime_tb_alpha_events", None)
    if events is None or dst_events is None:
        return
    src_index = getattr(src_scene, 'lime_tb_alpha_events_index', -1)
    try:
        try:
            dst_events.clear()
        except Exception:
            pass
        for evt in events:
            try:
                new_evt = dst_events.add()
                new_evt.name = evt.name
                new_evt.slug = evt.slug
                new_evt.frame_start = evt.frame_start
                new_evt.frame_end = evt.frame_end
                new_evt.invert = evt.invert
                ensure_event_tracks(dst_scene, new_evt, reset_keys=True)
            except Exception:
                pass
        count = len(dst_events)
        target_index = src_index if 0 <= src_index < count else (count - 1 if count else -1)
        try:
            dst_scene.lime_tb_alpha_events_index = target_index
        except Exception:
            pass
        rebuild_all_drivers(dst_scene)
    except Exception:
        pass


def _clone_noise_profiles(src_scene: bpy.types.Scene, dst_scene: bpy.types.Scene) -> None:
    src = getattr(src_scene, "lime_tb_noise_profiles", None)
    dst = getattr(dst_scene, "lime_tb_noise_profiles", None)
    if src is None or dst is None:
        return
    try:
        dst.clear()
    except Exception:
        pass
    for p in list(src):
        try:
            q = dst.add()
            for prop in p.bl_rna.properties:
                name = prop.identifier
                if name in {"rna_type", "prev_name"}:
                    continue
                try:
                    setattr(q, name, getattr(p, name))
                except Exception:
                    pass
        except Exception:
            pass


class LIME_OT_duplicate_scene_sequential(Operator):
    bl_idname = "lime.duplicate_scene_sequential"
    bl_label = "Duplicate Scene Sequential"
    bl_description = "Duplicate the active scene with isolated data and sequential renaming"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        source_scene = context.scene
        if source_scene is None:
            self.report({'ERROR'}, "No active scene to duplicate")
            return {'CANCELLED'}

        # Step 0: Tag source objects (locals only)
        _tag_source_objects(source_scene)

        # Step 1: Duplicate scene via FULL_COPY
        try:
            result = bpy.ops.scene.new(type='FULL_COPY')
        except Exception as exc:
            self.report({'ERROR'}, f"Failed to duplicate scene: {exc}")
            _cleanup_tags(source_scene)
            return {'CANCELLED'}
        if 'FINISHED' not in result:
            self.report({'ERROR'}, "Scene duplication cancelled")
            _cleanup_tags(source_scene)
            return {'CANCELLED'}

        new_scene = context.scene
        if new_scene == source_scene:
            self.report({'ERROR'}, "Scene duplication did not create a new scene")
            _cleanup_tags(source_scene)
            return {'CANCELLED'}

        _ensure_scene_alpha_action_single_user(new_scene)

        # Step 2: Build source->dest map from tags copied into new scene
        obj_map = _build_obj_map(new_scene)

        # Step 3: Deep single-user copies for objects/materials/geonodes/actions/world
        material_cache: Dict[bpy.types.Material, bpy.types.Material] = {}
        node_group_cache: Dict[bpy.types.NodeTree, bpy.types.NodeTree] = {}
        for obj in list(new_scene.objects):
            _make_object_data_single_user(obj)
            _make_materials_single_user(obj, material_cache, node_group_cache)
            _make_geo_nodes_single_user(obj)
            _make_actions_single_user(obj)
        _make_world_single_user(new_scene)

        # Step 4: Remap relations (constraints/modifiers) defensively
        _remap_relations(new_scene, obj_map)

        # Step 5: Clone Lime Toolbox state (Alpha Manager & Noise)
        _clone_alpha_events(source_scene, new_scene)
        _clone_noise_profiles(source_scene, new_scene)

        # Step 6: Sequential renaming for SHOT cameras/rigs and collections
        next_idx = max(1, _find_max_shot_index() + 1)
        renamer = _ShotSceneRenamer(source_scene, new_scene, next_idx)
        try:
            changes = renamer.run()
        except Exception as exc:
            self.report({'ERROR'}, f"Failed to normalize duplicated scene: {exc}")
            _cleanup_tags(source_scene, new_scene)
            return {'CANCELLED'}

        # Optional: ensure cameras/rigs follow conventions even after user edits
        try:
            for cam in [o for o in new_scene.objects if getattr(o, 'type', None) == 'CAMERA']:
                try:
                    _rename_parent_armature_for_camera(cam)
                except Exception:
                    pass
        except Exception:
            pass

        # Step 7: Cleanup temp tags and refresh
        _cleanup_tags(source_scene, new_scene)
        try:
            bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=False)
        except Exception:
            pass
        try:
            new_scene.frame_set(new_scene.frame_current)
        except Exception:
            pass
        try:
            if hasattr(bpy.context, "view_layer"):
                bpy.context.view_layer.update()
        except Exception:
            pass

        shot_label = _format_sh_root("Shot", _shot_index_width(next_idx), next_idx)
        self.report({'INFO'}, f"Scene duplicated as {new_scene.name}; assigned {shot_label} ({len(changes)} rename(s))")
        renamer.flush_log()
        return {'FINISHED'}


__all__ = [
    "LIME_OT_duplicate_scene_sequential",
]


