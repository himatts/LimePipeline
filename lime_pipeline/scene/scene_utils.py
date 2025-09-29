from __future__ import annotations

from typing import Dict, List, Tuple
import re

import bpy

from ..core.validate_scene import parse_shot_index, get_shot_child_by_basename
from ..data import SHOT_TREE, C_CAM


def _ensure_child(parent: bpy.types.Collection, name: str) -> bpy.types.Collection:
    for c in parent.children:
        if c.name == name:
            return c
    new = bpy.data.collections.new(name)
    parent.children.link(new)
    return new


def make_collection(parent: bpy.types.Collection, name: str) -> bpy.types.Collection:
    return _ensure_child(parent, name)


def _apply_tree(parent: bpy.types.Collection, node: dict, project_name: str, shot_idx: int) -> None:
    raw_name = node.get("name", "")
    name = raw_name.format(ProjectName=project_name)
    # Prefix with SH##_ for ALL subtree levels using provided root shot index
    prefixed = f"SH{shot_idx:02d}_{name}" if shot_idx else name
    coll = _ensure_child(parent, prefixed)
    color = node.get("color_tag")
    if color:
        try:
            coll.color_tag = color
        except Exception:
            pass
    if node.get("is_placeholder"):
        try:
            coll["lp_is_placeholder"] = True
        except Exception:
            pass
    for child in node.get("children", []) or []:
        _apply_tree(coll, child, project_name, shot_idx)


def ensure_shot_tree(root: bpy.types.Collection, project_name: str) -> None:
    shot_idx = parse_shot_index(root.name) or 0
    for node in SHOT_TREE:
        _apply_tree(root, node, project_name, shot_idx)


def _format_shot_name(index: int) -> str:
    if index >= 100:
        return f"SHOT {index:03d}"
    return f"SHOT {index:02d}"


def _find_child_by_name(parent: bpy.types.Collection, name: str) -> bpy.types.Collection | None:
    for c in parent.children:
        if c.name == name:
            return c
    return None


def create_shot(scene: bpy.types.Scene, index: int, project_name: str) -> bpy.types.Collection:
    name = _format_shot_name(index)
    if _find_child_by_name(scene.collection, name):
        raise ValueError(f"Collection '{name}' already exists")
    shot = bpy.data.collections.new(name)
    scene.collection.children.link(shot)
    ensure_shot_tree(shot, project_name)
    return shot


def instance_shot(scene: bpy.types.Scene, src_shot: bpy.types.Collection, dst_index: int) -> bpy.types.Collection:
    # Crear solo el root del SHOT destino sin prepopular subcolecciones
    name = _format_shot_name(dst_index)
    if _find_child_by_name(scene.collection, name):
        raise ValueError(f"Collection '{name}' already exists")
    dst_shot = bpy.data.collections.new(name)
    scene.collection.children.link(dst_shot)
    # Instanciar el SHOT origen entero
    inst_name = f"{src_shot.name}_Instance"
    inst = bpy.data.objects.new(inst_name, None)
    inst.instance_type = 'COLLECTION'
    inst.instance_collection = src_shot
    dst_shot.objects.link(inst)
    return dst_shot


def _project_name_for_scene(scene: bpy.types.Scene) -> str:
    # Best-effort: from WindowManager state if available
    try:
        st = bpy.context.window_manager.lime_pipeline
        from ..core.naming import resolve_project_name

        return resolve_project_name(st)
    except Exception:
        return "Project"


def duplicate_shot(scene: bpy.types.Scene, src_shot: bpy.types.Collection, dst_index: int) -> bpy.types.Collection:
    # Crear solo el root del SHOT destino sin prepopular subcolecciones
    name = _format_shot_name(dst_index)
    if _find_child_by_name(scene.collection, name):
        raise ValueError(f"Collection '{name}' already exists")
    dst_shot = bpy.data.collections.new(name)
    scene.collection.children.link(dst_shot)

    # Phase 1: replicate collection tree from source, but rename subcollections to new SH## prefix
    coll_map: Dict[bpy.types.Collection, bpy.types.Collection] = {src_shot: dst_shot}

    _SH_PREFIX_RE = re.compile(r"^SH(\d{2,3})_(.+)$")

    def _renamed_for_idx(name: str, idx: int) -> str:
        """Return name with leading SH##_ prefix replaced by new index; preserve numeric suffix like .001.

        Examples:
        - 'SH01_00_CAM' -> 'SH02_00_CAM'
        - 'SH12_01_Project_MAIN.001' -> 'SH02_01_Project_MAIN.001'
        """
        core, dot, rest = name.partition('.')
        m = _SH_PREFIX_RE.match(core or "")
        if m:
            base = m.group(2)
        else:
            base = core
        new_core = f"SH{idx:02d}_{base}" if base else f"SH{idx:02d}_"
        return new_core + (dot + rest if dot else "")

    def clone_tree(src: bpy.types.Collection):
        dst_parent = coll_map[src]
        for child in src.children:
            # New child name must adopt destination SH## prefix
            new_name = _renamed_for_idx(child.name, dst_index)
            new_child = bpy.data.collections.new(new_name)
            # Copy color tag if present
            try:
                new_child.color_tag = child.color_tag
            except Exception:
                pass
            dst_parent.children.link(new_child)
            coll_map[child] = new_child
            clone_tree(child)

    # Copy color tag for root too
    try:
        dst_shot.color_tag = src_shot.color_tag
    except Exception:
        pass

    clone_tree(src_shot)

    # Phase 2: duplicate objects once and link to mirrored collections
    obj_map: Dict[bpy.types.Object, bpy.types.Object] = {}

    def visit_objects_in(coll: bpy.types.Collection, out: List[Tuple[bpy.types.Collection, bpy.types.Object]]):
        for obj in coll.objects:
            out.append((coll, obj))
        for child in coll.children:
            visit_objects_in(child, out)

    pairs: List[Tuple[bpy.types.Collection, bpy.types.Object]] = []
    visit_objects_in(src_shot, pairs)

    # Group objects by identity to avoid multiple copies
    from collections import defaultdict

    obj_to_colls: Dict[bpy.types.Object, List[bpy.types.Collection]] = defaultdict(list)
    for coll, obj in pairs:
        obj_to_colls[obj].append(coll)

    # Create duplicates (duplicate data for isolation: cameras/lights/rigs y otros)
    _CAM_NAME_RE = re.compile(r"^SHOT_(\d{2,3})_CAMERA_(\d+)$")
    _SHOBJ_PREFIX_RE = re.compile(r"^SH(\d{2,3})_(.+)$")

    def _split_suffix(n: str) -> tuple[str, str]:
        """Split Blender numeric suffix like '.001'. Return (core, suffix_with_dot_or_empty)."""
        if not n:
            return "", ""
        core, dot, rest = n.rpartition('.')
        if dot and rest.isdigit() and len(rest) == 3:
            return core, "." + rest
        return n, ""
    for src_obj, colls in obj_to_colls.items():
        dup = src_obj.copy()
        # Duplicate data for cameras/lights/rigs; duplicate others as well to keep shots isolated
        if src_obj.data is not None:
            try:
                dup.data = src_obj.data.copy()
            except Exception:
                pass
        obj_map[src_obj] = dup
        # Link duplicate to each mirrored collection
        for c in colls:
            mirrored = coll_map.get(c)
            if mirrored is not None:
                mirrored.objects.link(dup)
        # Update name to reflect new SHOT index, preserving numeric suffix when applicable
        try:
            raw = dup.name or ""
            core, suffix = _split_suffix(raw)
            if getattr(dup, "type", None) == 'CAMERA':
                m = _CAM_NAME_RE.match(core)
                if m:
                    cam_idx = int(m.group(2))
                    new_name = f"SHOT_{dst_index:02d}_CAMERA_{cam_idx}"
                    dup.name = new_name
                    if getattr(dup, "data", None) is not None:
                        dup.data.name = new_name + ".Data"
                else:
                    # Fall back to generic SH##_ rename if matches that scheme
                    m2 = _SHOBJ_PREFIX_RE.match(core)
                    if m2:
                        base = m2.group(2)
                        new_name = f"SH{dst_index:02d}_{base}{suffix}"
                        dup.name = new_name
                        if getattr(dup, "data", None) is not None:
                            dup.data.name = new_name + ".Data"
            else:
                m2 = _SHOBJ_PREFIX_RE.match(core)
                if m2:
                    base = m2.group(2)
                    new_name = f"SH{dst_index:02d}_{base}{suffix}"
                    dup.name = new_name
                    if getattr(dup, "data", None) is not None:
                        dup.data.name = new_name + ".Data"
        except Exception:
            pass

    # Phase 3: remap parenting, constraints and common modifier targets to point inside the duplicated shot
    # Preserve world transforms while reparenting/retargeting
    from mathutils import Matrix

    # Save desired world matrices from source objects (duplicates inherit same world initially)
    desired_world: Dict[bpy.types.Object, Matrix] = {}
    for src_obj, dup_obj in obj_map.items():
        try:
            desired_world[dup_obj] = src_obj.matrix_world.copy()
        except Exception:
            pass

    def _parent_ref_world_matrix(ob: bpy.types.Object) -> Matrix:
        """Effective parent space in world coordinates (supports Object and Bone parenting)."""
        try:
            if ob is None:
                return Matrix.Identity(4)
        except Exception:
            return Matrix.Identity(4)
        p = ob.parent
        if p is None:
            return Matrix.Identity(4)
        try:
            if ob.parent_type == 'BONE' and getattr(ob, 'parent_bone', ''):
                pb = p.pose.bones.get(ob.parent_bone)
                if pb is not None:
                    return p.matrix_world @ pb.matrix
        except Exception:
            pass
        try:
            return p.matrix_world
        except Exception:
            return Matrix.Identity(4)

    # Known modifier object pointer attributes by type
    _MOD_TARGET_ATTRS = {
        'ARMATURE': ['object'],
        'MIRROR': ['mirror_object'],
        'ARRAY': ['offset_object'],
        'SHRINKWRAP': ['target', 'auxiliary_target'],
        'HOOK': ['object'],
        'LATTICE': ['object'],
        'CURVE': ['object'],
        'SIMPLE_DEFORM': ['origin'],
        'SURFACE_DEFORM': ['target'],
        'MESH_DEFORM': ['object'],
        'CAST': ['object'],
        'BOOLEAN': ['object'],
        'WARP': ['object_from', 'object_to'],
    }

    for src_obj, dup_obj in obj_map.items():
        # Reparent within duplicated set if needed, preserving world transform
        if src_obj.parent and src_obj.parent in obj_map:
            try:
                # Set new parent first
                dup_obj.parent = obj_map[src_obj.parent]
                dup_obj.parent_type = src_obj.parent_type
                if src_obj.parent_type == 'BONE':
                    dup_obj.parent_bone = src_obj.parent_bone
            except Exception:
                pass
        # After parenting, restore world transform by adjusting parent inverse
        try:
            mw = desired_world.get(dup_obj)
            if mw is not None:
                pw = _parent_ref_world_matrix(dup_obj)
                try:
                    dup_obj.matrix_parent_inverse = pw.inverted() @ mw
                except Exception:
                    pass
                try:
                    dup_obj.matrix_world = mw
                except Exception:
                    pass
        except Exception:
            pass

        # Constraints remap (targets and Child Of inverse)
        for con in list(getattr(dup_obj, 'constraints', []) or []):
            try:
                tgt = getattr(con, "target", None)
                if tgt and tgt in obj_map:
                    con.target = obj_map[tgt]
                # Child Of: recompute inverse to preserve world matrix
                if getattr(con, 'type', '') == 'CHILD_OF':
                    try:
                        mw = desired_world.get(dup_obj) or dup_obj.matrix_world
                        pt = getattr(con, 'target', None)
                        if pt is not None:
                            # If subtarget (bone) exists, use bone world matrix
                            sub = getattr(con, 'subtarget', '')
                            if sub and getattr(pt, 'pose', None):
                                pb = pt.pose.bones.get(sub)
                                if pb is not None:
                                    pw = pt.matrix_world @ pb.matrix
                                else:
                                    pw = pt.matrix_world
                            else:
                                pw = pt.matrix_world
                            con.inverse_matrix = pw.inverted() @ mw
                    except Exception:
                        pass
            except Exception:
                pass

        # Modifier targets remap (best-effort common cases)
        for mod in list(getattr(dup_obj, 'modifiers', []) or []):
            try:
                attrs = _MOD_TARGET_ATTRS.get(getattr(mod, 'type', ''), [])
                for attr in attrs:
                    try:
                        o = getattr(mod, attr, None)
                        if o and o in obj_map:
                            setattr(mod, attr, obj_map[o])
                    except Exception:
                        pass
            except Exception:
                pass

    # Phase 4: ensure camera names in destination shot follow SHOT_##_CAMERA_N convention
    try:
        cam_coll = get_shot_child_by_basename(dst_shot, C_CAM)
        if cam_coll is not None:
            cameras = [obj for obj in cam_coll.objects if getattr(obj, "type", None) == 'CAMERA']
            if cameras:
                # Stable ordering
                try:
                    cameras.sort(key=lambda o: o.name)
                except Exception:
                    pass
                # Avoid name collisions: temp names first
                temp_map = {}
                for cam in cameras:
                    base = f"__TMP_CAM__{cam.name}"
                    tmp = base
                    guard = 1
                    try:
                        while tmp in bpy.data.objects.keys():
                            if bpy.data.objects[tmp] is cam:
                                break
                            guard += 1
                            tmp = f"{base}_{guard}"
                        cam.name = tmp
                        if getattr(cam, 'data', None) is not None:
                            try:
                                cam.data.name = tmp + ".Data"
                            except Exception:
                                pass
                        temp_map[cam] = tmp
                    except Exception:
                        temp_map[cam] = cam.name
                # Final names
                for i, cam in enumerate(cameras, 1):
                    target = f"SHOT_{dst_index:02d}_CAMERA_{i}"
                    final = target
                    guard = 1
                    try:
                        while final in bpy.data.objects.keys() and bpy.data.objects[final] is not cam:
                            guard += 1
                            final = f"{target}_{guard}"
                        cam.name = final
                        if getattr(cam, 'data', None) is not None:
                            try:
                                cam.data.name = final + ".Data"
                            except Exception:
                                pass
                    except Exception:
                        pass
    except Exception:
        pass

    return dst_shot




