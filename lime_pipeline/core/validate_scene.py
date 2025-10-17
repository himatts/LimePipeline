"""
Scene and SHOT Validation Utilities

This module provides comprehensive utilities for validating Blender scene structure
and managing SHOT collections within the Lime Pipeline workflow. It handles SHOT
detection, indexing, hierarchy validation, and scene organization according to
Lime Pipeline conventions.

The SHOT system provides scene organization with numbered collections (SHOT 001,
SHOT 002, etc.) that contain all assets for individual shots or sequences. The
validation system ensures proper SHOT structure, active shot detection, and
hierarchical relationships between collections.

Key Features:
- SHOT collection detection and parsing with numeric indexing
- Active SHOT context resolution from selection and camera data
- Collection hierarchy validation and traversal utilities
- SHOT duplication and creation support with proper naming
- Scene isolation for focused SHOT processing
- Integration with Blender's collection and layer systems
- Comprehensive error handling for malformed scene structures
- Support for complex nested collection hierarchies
"""

from __future__ import annotations

import re
from typing import Optional, Tuple, List
import re

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
    max_idx = 0
    try:
        all_scenes = list(bpy.data.scenes)
    except Exception:
        all_scenes = [scene]
    for sc in all_scenes:
        try:
            for _shot, idx in list_shot_roots(sc):
                if idx is not None:
                    max_idx = max(max_idx, idx)
        except Exception:
            pass
    try:
        for coll in bpy.data.collections:
            idx = parse_shot_index(getattr(coll, 'name', '') or '')
            if idx is not None:
                max_idx = max(max_idx, idx)
    except Exception:
        pass
    return (max_idx + 1) if max_idx else 1


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

    # Priority 3: scene's active camera (for cases like duplicated cameras in Image Editor context)
    try:
        active_cam = getattr(scene, "camera", None)
        if active_cam is not None and getattr(active_cam, "type", None) == 'CAMERA':
            # Find all valid shots that contain collections where the camera resides
            candidate_shots = []
            for c in active_cam.users_collection:
                for shot, _ in shots:
                    if _collection_contains(shot, c):
                        candidate_shots.append(shot)

            # If we found candidate shots, return the one with highest index (most recent)
            if candidate_shots:
                # Sort by shot index (highest first) and return the first
                candidate_shots_with_idx = [(shot, parse_shot_index(shot.name) or 0) for shot in candidate_shots]
                candidate_shots_with_idx.sort(key=lambda x: x[1], reverse=True)
                return candidate_shots_with_idx[0][0]
    except Exception:
        pass

    return None


def can_create_new_shot(scene: bpy.types.Scene) -> Tuple[bool, str]:
    return True, ""




def can_duplicate_shot(ctx) -> Tuple[bool, str]:
    if active_shot_context(ctx) is not None:
        return True, ""
    return False, "Activate a collection inside a 'SHOT ##' to duplicate."


def get_shot_child_by_basename(shot: bpy.types.Collection, base_name: str) -> Optional[bpy.types.Collection]:
    """Return direct child collection of shot whose name matches base_name ignoring numeric suffixes.

    Example: base_name='00_CAM' will match children named '00_CAM', '00_CAM.001', etc.
    """
    if shot is None or not base_name:
        return None
    for child in shot.children:
        name = child.name or ""
        # Strip numeric suffix like ".001"
        core = name.split('.', 1)[0]
        # If prefixed with SH##_ remove it
        if core.startswith("SH") and '_' in core:
            try:
                after = core.split('_', 1)[1]
            except Exception:
                after = core
            core = after
        if core == base_name:
            return child
    return None



def isolate_shots_temporarily(scene: bpy.types.Scene, target_shot: bpy.types.Collection | None, include_all: bool = False):
    """Temporarily hide other SHOTs while processing the target shot.

    Returns a restore() function that reverts visibility/exclusion state.
    If include_all is True or target_shot is None, it's a no-op.
    """
    try:
        if include_all or target_shot is None:
            return lambda: None

        def _find_layer_collection(layer: bpy.types.LayerCollection | None, coll: bpy.types.Collection | None):
            if layer is None or coll is None:
                return None
            if layer.collection == coll:
                return layer
            for ch in getattr(layer, 'children', []) or []:
                found = _find_layer_collection(ch, coll)
                if found:
                    return found
            return None

        def _iter_coll_subtree(root: bpy.types.Collection):
            stack = [root]
            while stack:
                c = stack.pop()
                yield c
                try:
                    stack.extend(list(c.children))
                except Exception:
                    pass

        def _iter_layer_subtree(root_layer: bpy.types.LayerCollection | None):
            if root_layer is None:
                return
            stack = [root_layer]
            while stack:
                lc = stack.pop()
                yield lc
                try:
                    stack.extend(list(lc.children))
                except Exception:
                    pass

        shots = list_shot_roots(scene)
        others = [s for s, _ in shots if s != target_shot]

        # Save and hide other shots (root level only)
        saved_others_coll = []
        for c in others:
            try:
                saved_others_coll.append((c, bool(getattr(c, 'hide_viewport', False)), bool(getattr(c, 'hide_render', False))))
                c.hide_viewport = True
            except Exception:
                pass
            try:
                c.hide_render = True
            except Exception:
                pass

        saved_others_layers = []
        try:
            vl = bpy.context.view_layer
            base = vl.layer_collection if vl else None
            for c in others:
                lc = _find_layer_collection(base, c)
                if lc is not None:
                    saved_others_layers.append((lc, bool(getattr(lc, 'exclude', False)), bool(getattr(lc, 'hide_viewport', False))))
                    try:
                        lc.exclude = True
                    except Exception:
                        pass
                    try:
                        lc.hide_viewport = True
                    except Exception:
                        pass
        except Exception:
            pass

        # Ensure target shot subtree is visible/unexcluded
        saved_target_coll = []
        try:
            for c in _iter_coll_subtree(target_shot):
                saved_target_coll.append((c, bool(getattr(c, 'hide_viewport', False)), bool(getattr(c, 'hide_render', False))))
                try:
                    c.hide_viewport = False
                except Exception:
                    pass
                try:
                    c.hide_render = False
                except Exception:
                    pass
        except Exception:
            pass

        saved_target_layers = []
        try:
            vl = bpy.context.view_layer
            base = vl.layer_collection if vl else None
            target_lc = _find_layer_collection(base, target_shot)
            if target_lc is not None:
                for lc in _iter_layer_subtree(target_lc):
                    saved_target_layers.append((lc, bool(getattr(lc, 'exclude', False)), bool(getattr(lc, 'hide_viewport', False))))
                    try:
                        lc.exclude = False
                    except Exception:
                        pass
                    try:
                        lc.hide_viewport = False
                    except Exception:
                        pass
        except Exception:
            pass

        def _restore():
            # Restore other shots
            for c, hv, hr in saved_others_coll:
                try:
                    c.hide_viewport = hv
                except Exception:
                    pass
                try:
                    c.hide_render = hr
                except Exception:
                    pass
            for lc, ex, hv in saved_others_layers:
                try:
                    lc.exclude = ex
                except Exception:
                    pass
                try:
                    lc.hide_viewport = hv
                except Exception:
                    pass
            # Restore target shot subtree
            for c, hv, hr in saved_target_coll:
                try:
                    c.hide_viewport = hv
                except Exception:
                    pass
                try:
                    c.hide_render = hr
                except Exception:
                    pass
            for lc, ex, hv in saved_target_layers:
                try:
                    lc.exclude = ex
                except Exception:
                    pass
                try:
                    lc.hide_viewport = hv
                except Exception:
                    pass

        return _restore
    except Exception:
        return lambda: None


