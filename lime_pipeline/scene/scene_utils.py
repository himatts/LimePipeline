from __future__ import annotations

from typing import Dict, List, Tuple
import re

import bpy

from ..core.validate_scene import parse_shot_index
from ..data import SHOT_TREE


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
        - 'SH01_00_UTILS_CAM' -> 'SH02_00_UTILS_CAM'
        - 'SH12_01_Project_MAIN.001' -> 'SH02_01_Project_MAIN.001'
        - '00_UTILS_LIGHTS' -> 'SH02_00_UTILS_LIGHTS'
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

    # Phase 3: remap parenting and constraints to point inside the duplicated shot
    for src_obj, dup_obj in obj_map.items():
        if src_obj.parent and src_obj.parent in obj_map:
            dup_obj.parent = obj_map[src_obj.parent]
            dup_obj.parent_type = src_obj.parent_type
        # Constraints remap
        for con in dup_obj.constraints:
            tgt = getattr(con, "target", None)
            if tgt and tgt in obj_map:
                con.target = obj_map[tgt]

    return dst_shot


