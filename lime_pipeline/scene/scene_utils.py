from __future__ import annotations

from typing import Dict, List, Tuple

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


def _apply_tree(parent: bpy.types.Collection, node: dict, project_name: str) -> None:
    raw_name = node.get("name", "")
    name = raw_name.format(ProjectName=project_name)
    coll = _ensure_child(parent, name)
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
        _apply_tree(coll, child, project_name)


def ensure_shot_tree(root: bpy.types.Collection, project_name: str) -> None:
    for node in SHOT_TREE:
        _apply_tree(root, node, project_name)


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

    # Phase 1: replicate collection tree exactly from source
    coll_map: Dict[bpy.types.Collection, bpy.types.Collection] = {src_shot: dst_shot}

    def clone_tree(src: bpy.types.Collection):
        dst_parent = coll_map[src]
        for child in src.children:
            new_child = bpy.data.collections.new(child.name)
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


