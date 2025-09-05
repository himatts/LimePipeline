from __future__ import annotations

import re
from typing import Optional, Tuple, List

import bpy


SHOT_ROOT_PATTERN = re.compile(r"^SHOT (\d{2,3})$")


def is_shot_name(name: str) -> bool:
    return bool(SHOT_ROOT_PATTERN.match(name or ""))


def parse_shot_index(name: str) -> Optional[int]:
    m = SHOT_ROOT_PATTERN.match(name or "")
    return int(m.group(1)) if m else None


def _collection_contains(ancestor: bpy.types.Collection, descendant: bpy.types.Collection) -> bool:
    if ancestor == descendant:
        return True
    # BFS search over children
    stack = list(ancestor.children)
    while stack:
        child = stack.pop()
        if child == descendant:
            return True
        stack.extend(child.children)
    return False


def list_shot_roots(scene: bpy.types.Scene) -> List[tuple[bpy.types.Collection, int]]:
    roots: List[tuple[bpy.types.Collection, int]] = []
    for coll in scene.collection.children:
        idx = parse_shot_index(coll.name)
        if idx is not None:
            roots.append((coll, idx))
    roots.sort(key=lambda t: t[1])
    return roots


def next_shot_index(scene: bpy.types.Scene) -> int:
    roots = list_shot_roots(scene)
    return (roots[-1][1] + 1) if roots else 1


def find_shot_root_for_collection(coll: bpy.types.Collection, scene: Optional[bpy.types.Scene] = None) -> Optional[bpy.types.Collection]:
    scene = scene or bpy.context.scene
    for shot, _idx in list_shot_roots(scene):
        if _collection_contains(shot, coll):
            return shot
    return None


def active_shot_context(ctx) -> Optional[bpy.types.Collection]:
    scene = ctx.scene
    shots = list_shot_roots(scene)
    if not shots:
        return None

    # Priority 1: active layer collection (if a collection is selected in Outliner)
    try:
        alc = ctx.view_layer.active_layer_collection
        if alc and alc.collection:
            c = alc.collection
            for shot, _ in shots:
                if _collection_contains(shot, c):
                    return shot
    except Exception:
        pass

    # Priority 2: active object and selected objects' collections
    check_objs = []
    try:
        if getattr(ctx, "selected_objects", None):
            check_objs.extend(list(ctx.selected_objects))
    except Exception:
        pass
    obj = getattr(ctx, "active_object", None)
    if obj is not None and obj not in check_objs:
        check_objs.append(obj)

    for ob in check_objs:
        for c in ob.users_collection:
            for shot, _ in shots:
                if _collection_contains(shot, c):
                    return shot

    return None


def can_create_new_shot(scene: bpy.types.Scene) -> Tuple[bool, str]:
    return True, ""


def can_instance_shot(ctx) -> Tuple[bool, str]:
    if active_shot_context(ctx) is not None:
        return True, ""
    return False, "Active una colección dentro de un 'SHOT ##' para instanciar."


def can_duplicate_shot(ctx) -> Tuple[bool, str]:
    if active_shot_context(ctx) is not None:
        return True, ""
    return False, "Active una colección dentro de un 'SHOT ##' para duplicar."


