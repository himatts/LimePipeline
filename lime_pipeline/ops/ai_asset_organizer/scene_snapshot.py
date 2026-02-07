"""Scene collection snapshot helpers for AI Asset Organizer."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

import bpy
from bpy.types import Collection, Object

from ...core.collection_resolver import CollectionCandidate, tokenize as tokenize_name


_SHOT_ROOT_RE = re.compile(r"^SHOT \d{2,3}$")


def is_collection_read_only(coll: Collection) -> bool:
    return bool(getattr(coll, "library", None) or getattr(coll, "override_library", None))


def join_collection_path(parent_path: str, name: str) -> str:
    if not parent_path:
        return name
    return f"{parent_path}/{name}"


def walk_layer_collections(layer_collection, out: Dict[int, Dict[str, bool]]) -> None:
    coll = getattr(layer_collection, "collection", None)
    if coll is not None:
        out[coll.as_pointer()] = {
            "exclude": bool(getattr(layer_collection, "exclude", False)),
            "hide_viewport_layer": bool(getattr(layer_collection, "hide_viewport", False)),
        }
    for child in list(getattr(layer_collection, "children", []) or []):
        walk_layer_collections(child, out)


def build_collection_activity_index(scene) -> Dict[int, Dict[str, bool]]:
    del scene
    index: Dict[int, Dict[str, bool]] = {}
    view_layer = getattr(bpy.context, "view_layer", None)
    layer_root = getattr(view_layer, "layer_collection", None)
    if layer_root is not None:
        walk_layer_collections(layer_root, index)
    return index


def build_scene_collection_snapshot(scene) -> Dict[str, object]:
    root = getattr(scene, "collection", None)
    path_to_collection: Dict[str, Collection] = {}
    collection_ptr_to_paths: Dict[int, List[str]] = {}
    candidates: List[CollectionCandidate] = []
    hierarchy_paths: List[str] = []

    if root is None:
        return {
            "path_to_collection": path_to_collection,
            "collection_ptr_to_paths": collection_ptr_to_paths,
            "candidates": candidates,
            "hierarchy_paths": hierarchy_paths,
        }

    def walk(parent: Collection, parent_path: str, shot_root: Optional[str], stack: set[int]) -> None:
        children = list(getattr(parent, "children", []) or [])
        for child in children:
            child_name = getattr(child, "name", "") or ""
            if not child_name:
                continue

            path = join_collection_path(parent_path, child_name)
            ptr = child.as_pointer()
            if path not in path_to_collection:
                path_to_collection[path] = child
                hierarchy_paths.append(path)
            collection_ptr_to_paths.setdefault(ptr, [])
            if path not in collection_ptr_to_paths[ptr]:
                collection_ptr_to_paths[ptr].append(path)

            child_shot_root = shot_root
            if _SHOT_ROOT_RE.match(child_name):
                child_shot_root = child_name

            candidates.append(
                CollectionCandidate(
                    path=path,
                    name=child_name,
                    depth=max(0, path.count("/")),
                    shot_root_name=child_shot_root,
                    is_shot_root=bool(_SHOT_ROOT_RE.match(child_name)),
                    is_read_only=is_collection_read_only(child),
                    object_count=len(list(getattr(child, "objects", []) or [])),
                    path_tokens=tuple(tokenize_name(path)),
                    name_tokens=tuple(tokenize_name(child_name)),
                    exists=True,
                )
            )

            if ptr in stack:
                continue
            child_stack = set(stack)
            child_stack.add(ptr)
            walk(child, path, child_shot_root, child_stack)

    walk(root, "", None, set())
    hierarchy_paths.sort(key=lambda p: (p.count("/"), p.lower()))
    activity = build_collection_activity_index(scene)
    return {
        "path_to_collection": path_to_collection,
        "collection_ptr_to_paths": collection_ptr_to_paths,
        "candidates": candidates,
        "hierarchy_paths": hierarchy_paths,
        "collection_activity": activity,
    }


def object_collection_paths(obj: Object, snapshot: Dict[str, object]) -> List[str]:
    pointer_to_paths = snapshot.get("collection_ptr_to_paths", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(pointer_to_paths, dict):
        pointer_to_paths = {}
    paths: List[str] = []
    for coll in list(getattr(obj, "users_collection", []) or []):
        if coll is None:
            continue
        ptr = coll.as_pointer()
        known_paths = pointer_to_paths.get(ptr, [])
        if isinstance(known_paths, list):
            for path in known_paths:
                if path and path not in paths:
                    paths.append(path)
    return paths


__all__ = [
    "build_scene_collection_snapshot",
    "build_collection_activity_index",
    "object_collection_paths",
    "is_collection_read_only",
]
