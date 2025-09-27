from __future__ import annotations

import re
import string
from typing import Iterator, Sequence

import bpy
from bpy.types import Collection, Object, Operator, Scene

from ..core import validate_scene
from ..core.validate_scene import get_shot_child_by_basename


_SH_TOKEN_RE = re.compile(r"\b(SHOT|SH)([_\s]?)(\d{2,3})\b", re.IGNORECASE)


def _ensure_child(parent: bpy.types.Collection, name: str) -> bpy.types.Collection:
    for c in parent.children:
        if c.name == name:
            return c
    new = bpy.data.collections.new(name)
    parent.children.link(new)
    return new


def _ensure_lights_target(shot: bpy.types.Collection, shot_idx: int, target_base: str) -> bpy.types.Collection:
    # Deprecated: lights utilities removed
    return get_shot_child_by_basename(shot, target_base)


def _is_in_shot(coll: bpy.types.Collection, shot: bpy.types.Collection) -> bool:
    # Reuse public helper to check ancestry by comparing resolved root
    try:
        return validate_scene.find_shot_root_for_collection(coll) == shot
    except Exception:
        return False


def _assign_selected_lights(context, target_base: str) -> tuple[set, set]:
    # Deprecated feature
    return set(), set()


def _strip_numeric_suffix(name: str) -> str:
    if not name:
        return name
    head, sep, tail = name.rpartition('.')
    if sep and len(tail) == 3 and tail.isdigit():
        return head
    return name


def _match_shot_root(name: str) -> tuple[str, str] | None:
    base = _strip_numeric_suffix(name).strip()
    if not base:
        return None
    parts = base.split()
    if len(parts) != 2:
        return None
    prefix, digits = parts
    if prefix.lower() != "shot" or not digits.isdigit():
        return None
    return prefix, digits


def _match_sh_prefixed(name: str) -> tuple[str, str] | None:
    base = _strip_numeric_suffix(name).strip()
    if len(base) < 4 or base[:2].upper() != "SH":
        return None
    head, _, rest = base.partition('_')
    digits = head[2:]
    if not digits.isdigit():
        return None
    return digits, rest


def _shot_index_width(index: int) -> int:
    return 3 if index >= 100 else 2


def _adjust_width(existing: int, index: int) -> int:
    width = max(existing, 2)
    if index >= 100 and width < 3:
        width = 3
    return width


def _format_sh_prefix(index: int, width: int) -> str:
    return f"SH{index:0{width}d}"


def _format_sh_root(prefix_word: str, width: int, index: int) -> str:
    if prefix_word.isupper():
        word = "SHOT"
    elif prefix_word.islower():
        word = "shot"
    else:
        word = "Shot"
    return f"{word} {index:0{width}d}"


def _normalize_descriptor(raw: str) -> str:
    if not raw:
        return ""
    tokens = [re.sub(r"[^0-9A-Za-z]+", "", token) for token in re.split(r"[_\s]+", raw)]
    filtered = [tok.upper() for tok in tokens if tok]
    return "_".join(filtered)


def _create_prefixed_collection_name(raw: str, index: int) -> str:
    parts = [p for p in re.split(r"[_\s]+", _strip_numeric_suffix(raw).strip()) if p]
    code = "00"
    descriptor_tokens = parts
    if parts and parts[0].isdigit():
        code = parts[0].zfill(2)[-2:]
        descriptor_tokens = parts[1:]
    descriptor = _normalize_descriptor("_".join(descriptor_tokens)) or "COLLECTION"
    width = _shot_index_width(index)
    return f"{_format_sh_prefix(index, width)}_{code}_{descriptor}"


def _replace_sh_tokens(text: str, source_index: int | None, new_index: int) -> str:
    if source_index is None:
        return text

    def repl(match: re.Match[str]) -> str:
        prefix = match.group(1)
        sep = match.group(2)
        digits = match.group(3)
        try:
            value = int(digits)
        except ValueError:
            return match.group(0)
        if value != source_index:
            return match.group(0)
        width_local = _adjust_width(len(digits), new_index)
        if prefix.upper() == "SHOT":
            if prefix.isupper():
                word = "SHOT"
            elif prefix.islower():
                word = "shot"
            else:
                word = "Shot"
            sep_final = sep if sep else "_"
            return f"{word}{sep_final}{new_index:0{width_local}d}"
        word = "SH" if prefix.isupper() else ("sh" if prefix.islower() else "Sh")
        return f"{word}{sep}{new_index:0{width_local}d}"

    return _SH_TOKEN_RE.sub(repl, text)


def _ensure_unique(datablocks, owner, desired: str) -> str:
    base = _strip_numeric_suffix(desired).strip()
    if not base:
        return owner.name
    if _is_available(datablocks, owner, base):
        return base
    for suffix in _suffix_sequence():
        candidate = f"{base}{suffix}"
        if _is_available(datablocks, owner, candidate):
            return candidate
    return base


def _is_available(datablocks, owner, name: str) -> bool:
    try:
        existing = datablocks.get(name)
    except AttributeError:
        existing = None
        for item in datablocks:
            if getattr(item, "name", None) == name:
                existing = item
                break
    return existing is None or existing == owner


def _suffix_sequence() -> Iterator[str]:
    for letter in string.ascii_uppercase:
        yield f"_{letter}"
    idx = 1
    while True:
        yield f"_{idx}"
        idx += 1


def _iter_collection_tree(root: Collection) -> Iterator[Collection]:
    stack: list[Collection] = [root]
    seen: set[int] = set()
    while stack:
        coll = stack.pop()
        key = id(coll)
        if key in seen:
            continue
        seen.add(key)
        yield coll
        stack.extend(list(coll.children))


def _collect_objects_from_collections(collections: Sequence[Collection]) -> list[Object]:
    objects: dict[int, Object] = {}
    for coll in collections:
        for obj in coll.objects:
            objects[id(obj)] = obj
    return list(objects.values())


def _resolve_rig_prefix(name: str) -> str | None:
    base = _strip_numeric_suffix(name).upper()
    for prefix in ("CAM_RIG", "ARM_RIG", "RIG"):
        if base.startswith(prefix):
            return prefix
    return None


def _find_max_shot_index() -> int:
    max_idx = 0
    for scene in bpy.data.scenes:
        match = _match_shot_root(scene.name)
        if match:
            max_idx = max(max_idx, int(match[1]))
        try:
            for _shot_coll, idx in validate_scene.list_shot_roots(scene):
                max_idx = max(max_idx, idx)
        except Exception:
            pass
        root = getattr(scene, "collection", None)
        if root is not None:
            base_name = _strip_numeric_suffix(root.name)
            match_root = _match_shot_root(base_name)
            if match_root:
                max_idx = max(max_idx, int(match_root[1]))
            for child in root.children:
                child_base = _strip_numeric_suffix(child.name)
                match_child = _match_shot_root(child_base)
                if match_child:
                    max_idx = max(max_idx, int(match_child[1]))
                sh_match = _match_sh_prefixed(child_base)
                if sh_match:
                    max_idx = max(max_idx, int(sh_match[0]))
    for coll in bpy.data.collections:
        base = _strip_numeric_suffix(coll.name)
        match = _match_shot_root(base)
        if match:
            max_idx = max(max_idx, int(match[1]))
        sh_match = _match_sh_prefixed(base)
        if sh_match:
            max_idx = max(max_idx, int(sh_match[0]))
    return max_idx


def _target_collection_name(name: str, new_index: int, source_index: int | None) -> str:
    base = _strip_numeric_suffix(name).strip()
    shot_match = _match_shot_root(base)
    if shot_match:
        prefix, digits = shot_match
        width = _adjust_width(len(digits), new_index)
        return _format_sh_root(prefix, width, new_index)
    sh_match = _match_sh_prefixed(base)
    if sh_match:
        digits, rest = sh_match
        width = _adjust_width(len(digits), new_index)
        descriptor = _normalize_descriptor(rest) or "COLLECTION"
        return f"{_format_sh_prefix(new_index, width)}_{descriptor}"
    replaced = _replace_sh_tokens(base, source_index, new_index)
    if replaced != base:
        return replaced
    return _create_prefixed_collection_name(base, new_index)

def _target_object_name(name: str, new_index: int, source_index: int | None) -> str:
    base = _strip_numeric_suffix(name).strip()
    if not base:
        return name
    sh_match = _match_sh_prefixed(base)
    if sh_match:
        digits, rest = sh_match
        width = _adjust_width(len(digits), new_index)
        descriptor = _normalize_descriptor(rest) or "OBJECT"
        return f"{_format_sh_prefix(new_index, width)}_{descriptor}"
    replaced = _replace_sh_tokens(base, source_index, new_index)
    if replaced != base:
        return replaced
    return base

_DATA_COLLECTION_BY_TYPE = {
    'MESH': 'meshes',
    'CURVE': 'curves',
    'SURFACE': 'surfaces',
    'META': 'metaballs',
    'FONT': 'curves',
    'ARMATURE': 'armatures',
    'LATTICE': 'lattices',
    'LIGHT': 'lights',
    'LIGHT_PROBE': 'lightprobes',
    'CAMERA': 'cameras',
    'SPEAKER': 'speakers',
    'GPENCIL': 'grease_pencils',
    'VOLUME': 'volumes',
    'POINTCLOUD': 'pointclouds',
    'CURVES': 'curves',
}

def _data_blocks_for_object(obj: Object):
    attr = _DATA_COLLECTION_BY_TYPE.get(getattr(obj, 'type', ''), None)
    if not attr:
        return None
    return getattr(bpy.data, attr, None)


def _detect_scene_shot_index(scene: Scene) -> int | None:
    match = _match_shot_root(scene.name)
    if match:
        return int(match[1])
    root = getattr(scene, "collection", None)
    if root is not None:
        match = _match_shot_root(root.name)
        if match:
            return int(match[1])
        for coll in root.children:
            child_base = _strip_numeric_suffix(coll.name)
            match_child = _match_shot_root(child_base)
            if match_child:
                return int(match_child[1])
            sh_match = _match_sh_prefixed(child_base)
            if sh_match:
                return int(sh_match[0])
    return None


class _ShotSceneRenamer:
    def __init__(self, source_scene: Scene, new_scene: Scene, new_index: int) -> None:
        self.source_scene = source_scene
        self.new_scene = new_scene
        self.new_index = new_index
        self.source_index = _detect_scene_shot_index(source_scene)
        self.collections = list(_iter_collection_tree(new_scene.collection))
        self.scene_objects = _collect_objects_from_collections(self.collections)
        self.log: list[tuple[str, str, str]] = []

    def run(self) -> list[tuple[str, str, str]]:
        self._rename_collections()
        self._rename_cameras()
        self._rename_rigs()
        self._rename_misc_objects()
        return self.log

    def flush_log(self) -> None:
        if not self.log:
            return
        print("[LimePipeline] Scene duplicate rename log:")
        for kind, old, new in self.log:
            print(f"  {kind}: '{old}' -> '{new}'")

    def _log(self, kind: str, before: str, after: str) -> None:
        self.log.append((kind, before, after))

    def _rename_collections(self) -> None:
        for coll in self.collections:
            if coll == self.new_scene.collection:
                continue
            desired = _target_collection_name(coll.name, self.new_index, self.source_index)
            unique = _ensure_unique(bpy.data.collections, coll, desired)
            if unique != coll.name:
                old = coll.name
                try:
                    coll.name = unique
                except Exception:
                    continue
                self._log("COLLECTION", old, unique)

    def _rename_cameras(self) -> None:
        cameras = [obj for obj in self.scene_objects if obj.type == 'CAMERA']
        if not cameras:
            return
        cameras.sort(key=lambda o: _strip_numeric_suffix(o.name).lower())
        width = _shot_index_width(self.new_index)
        for idx, cam in enumerate(cameras, 1):
            target = f"SHOT_{self.new_index:0{width}d}_CAMERA_{idx}"
            self._rename_object(cam, target, bpy.data.cameras)

    def _rename_rigs(self) -> None:
        rig_groups: dict[str, list[Object]] = {}
        for obj in self.scene_objects:
            prefix = _resolve_rig_prefix(obj.name)
            if not prefix:
                continue
            rig_groups.setdefault(prefix, []).append(obj)
        if not rig_groups:
            return
        width = _shot_index_width(self.new_index)
        for prefix in sorted(rig_groups):
            objs = rig_groups[prefix]
            objs.sort(key=lambda o: _strip_numeric_suffix(o.name).lower())
            for idx, obj in enumerate(objs, 1):
                target = f"{prefix}_SH{self.new_index:0{width}d}_{idx}"
                data_blocks = bpy.data.armatures if obj.type == 'ARMATURE' else None
                self._rename_object(obj, target, data_blocks)

    def _rename_misc_objects(self) -> None:
        for obj in self.scene_objects:
            if obj.type == 'CAMERA':
                continue
            if _resolve_rig_prefix(obj.name):
                continue
            target = _target_object_name(obj.name, self.new_index, self.source_index)
            base = _strip_numeric_suffix(obj.name).strip()
            if not target or target == base:
                continue
            data_blocks = _data_blocks_for_object(obj)
            self._rename_object(obj, target, data_blocks)

    def _rename_object(self, obj: Object, desired: str, data_blocks) -> None:
        unique = _ensure_unique(bpy.data.objects, obj, desired)
        if unique != obj.name:
            old = obj.name
            try:
                obj.name = unique
            except Exception:
                return
            self._log("OBJECT", old, unique)
        if data_blocks is not None and getattr(obj, "data", None) is not None:
            data_target = f"{unique}.Data"
            unique_data = _ensure_unique(data_blocks, obj.data, data_target)
            if unique_data != obj.data.name:
                old_data = obj.data.name
                try:
                    obj.data.name = unique_data
                except Exception:
                    return
                self._log("DATA", old_data, unique_data)

class LIME_OT_duplicate_scene_sequential(Operator):
    bl_idname = "lime.duplicate_scene_sequential"
    bl_label = "Duplicate Scene Sequential"
    bl_description = "Duplicate the active scene and renames shot collections and key objects sequentially"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        source_scene = context.scene
        if source_scene is None:
            self.report({'ERROR'}, "No active scene to duplicate")
            return {'CANCELLED'}
        next_idx = max(1, _find_max_shot_index() + 1)
        try:
            result = bpy.ops.scene.new(type='FULL_COPY')
        except Exception as exc:
            self.report({'ERROR'}, f"Failed to duplicate scene: {exc}")
            return {'CANCELLED'}
        if 'FINISHED' not in result:
            self.report({'ERROR'}, "Scene duplication cancelled")
            return {'CANCELLED'}
        new_scene = context.scene
        if new_scene == source_scene:
            self.report({'ERROR'}, "Scene duplication did not create a new scene")
            return {'CANCELLED'}
        renamer = _ShotSceneRenamer(source_scene, new_scene, next_idx)
        try:
            changes = renamer.run()
        except Exception as exc:
            self.report({'ERROR'}, f"Failed to normalize duplicated scene: {exc}")
            return {'CANCELLED'}
        shot_label = _format_sh_root("Shot", _shot_index_width(next_idx), next_idx)
        self.report({'INFO'}, f"Scene duplicated as {new_scene.name}; assigned {shot_label} ({len(changes)} rename(s))")
        renamer.flush_log()
        return {'FINISHED'}


class LIME_OT_stage_main_light(Operator):
    bl_idname = "lime.stage_main_light"
    bl_label = "Assign Main Light"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        self.report({'WARNING'}, "Main Light tool removed")
        return {'CANCELLED'}


class LIME_OT_stage_aux_light(Operator):
    bl_idname = "lime.stage_aux_light"
    bl_label = "Assign Aux Light"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        self.report({'WARNING'}, "Aux Light tool removed")
        return {'CANCELLED'}


__all__ = [
    "LIME_OT_duplicate_scene_sequential",
    "LIME_OT_stage_main_light",
    "LIME_OT_stage_aux_light",
]

