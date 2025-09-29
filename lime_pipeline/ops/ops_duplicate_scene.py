from __future__ import annotations

from typing import Dict, Iterator, Sequence
from uuid import uuid4

import bpy
import re
import string
from bpy.types import Collection, Object, Operator, Scene

from ..core import validate_scene
from ..data.templates import C_CAM
from .ops_alpha_manager import ensure_event_tracks, rebuild_all_drivers
from .ops_cameras import _rename_parent_armature_for_camera  # reuse rig rename helper
_SH_TOKEN_RE = re.compile(r"\b(SHOT|SH)([_\s]?)(\d{2,3})\b", re.IGNORECASE)



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


def _replace_sh_tokens(text: str, origin_index: int | None, new_index: int) -> str:
    if origin_index is None:
        return text

    def repl(match: re.Match[str]) -> str:
        prefix = match.group(1)
        sep = match.group(2)
        digits = match.group(3)
        try:
            value = int(digits)
        except ValueError:
            return match.group(0)
        if value != origin_index:
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


def _target_collection_name(name: str, new_index: int, origin_index: int | None) -> str:
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
    replaced = _replace_sh_tokens(base, origin_index, new_index)
    if replaced != base:
        return replaced
    return _create_prefixed_collection_name(base, new_index)

def _target_object_name(name: str, new_index: int, origin_index: int | None) -> str:
    base = _strip_numeric_suffix(name).strip()
    if not base:
        return name
    sh_match = _match_sh_prefixed(base)
    if sh_match:
        digits, rest = sh_match
        width = _adjust_width(len(digits), new_index)
        descriptor = _normalize_descriptor(rest) or "OBJECT"
        return f"{_format_sh_prefix(new_index, width)}_{descriptor}"
    replaced = _replace_sh_tokens(base, origin_index, new_index)
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
    def __init__(
        self,
        source_scene: Scene,
        new_scene: Scene,
        start_index: int,
        index_map: dict[int, int] | None = None,
    ) -> None:
        self.source_scene = source_scene
        self.new_scene = new_scene
        self.start_index = start_index
        self.index_map: dict[int, int] = {int(k): int(v) for k, v in (index_map or {}).items()}
        self.source_index = _detect_scene_shot_index(source_scene)
        max_existing = max(self.index_map.values(), default=self.start_index - 1)
        self._next_available_index = max(max_existing + 1, self.start_index)
        self.used_new_indices: set[int] = set()
        if self.source_index is not None and self.source_index not in self.index_map:
            self.index_map[self.source_index] = self._allocate_new_index()
        self.default_new_index = (
            self.index_map[self.source_index]
            if self.source_index is not None and self.source_index in self.index_map
            else (min(self.index_map.values()) if self.index_map else self.start_index)
        )
        self.collections = list(_iter_collection_tree(new_scene.collection))
        self.scene_objects = _collect_objects_from_collections(self.collections)
        self.log: list[tuple[str, str, str]] = []
        self._collection_cache: dict[int, tuple[int | None, int]] = {}
        self._prime_collection_cache()

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

    def _allocate_new_index(self) -> int:
        new_idx = max(self._next_available_index, self.start_index)
        self._next_available_index = new_idx + 1
        return new_idx

    def _resolve_new_index(self, old_index: int | None) -> int:
        if old_index is not None:
            mapped = self.index_map.get(old_index)
            if mapped is not None:
                self.used_new_indices.add(mapped)
                return mapped
            mapped = self._allocate_new_index()
            self.index_map[old_index] = mapped
            self.used_new_indices.add(mapped)
            return mapped
        self.used_new_indices.add(self.default_new_index)
        return self.default_new_index

    def _prime_collection_cache(self) -> None:
        try:
            shot_roots = validate_scene.list_shot_roots(self.new_scene)
        except Exception:
            shot_roots = []
        for shot_coll, old_idx in shot_roots:
            new_idx = self._resolve_new_index(old_idx)
            for coll in _iter_collection_tree(shot_coll):
                self._collection_cache[id(coll)] = (old_idx, new_idx)

    def _resolve_collection_indices(self, coll: Collection) -> tuple[int | None, int]:
        cached = self._collection_cache.get(id(coll))
        if cached:
            return cached
        name = _strip_numeric_suffix(getattr(coll, "name", "")).strip()
        old_idx = None
        match = _match_shot_root(name)
        if match:
            old_idx = int(match[1])
        else:
            sh_match = _match_sh_prefixed(name)
            if sh_match:
                try:
                    old_idx = int(sh_match[0])
                except ValueError:
                    old_idx = None
        new_idx = self._resolve_new_index(old_idx)
        result = (old_idx, new_idx)
        self._collection_cache[id(coll)] = result
        return result

    def _object_indices(self, obj: Object) -> tuple[int | None, int]:
        best: tuple[int | None, int] | None = None
        try:
            collections = list(obj.users_collection)
        except Exception:
            collections = []
        for coll in collections:
            indices = self._resolve_collection_indices(coll)
            if indices[0] is not None:
                return indices
            if best is None:
                best = indices
        if best is not None:
            return best
        fallback_old = self.source_index
        fallback_new = self._resolve_new_index(fallback_old)
        return fallback_old, fallback_new

    def _rename_collections(self) -> None:
        for coll in self.collections:
            if coll == self.new_scene.collection:
                continue
            old_idx, new_idx = self._resolve_collection_indices(coll)
            desired = _target_collection_name(coll.name, new_idx, old_idx)
            unique = _ensure_unique(bpy.data.collections, coll, desired)
            if unique != coll.name:
                old_name = coll.name
                try:
                    coll.name = unique
                except Exception:
                    continue
                self._log("COLLECTION", old_name, unique)

    def _rename_cameras(self) -> None:
        cameras = [obj for obj in self.scene_objects if obj.type == 'CAMERA']
        if not cameras:
            return
        grouped: dict[int, list[Object]] = {}
        for cam in cameras:
            _, new_idx = self._object_indices(cam)
            grouped.setdefault(new_idx, []).append(cam)
        for new_idx in sorted(grouped):
            width = _shot_index_width(new_idx)
            ordered = sorted(grouped[new_idx], key=lambda o: _strip_numeric_suffix(o.name).lower())
            for idx, cam in enumerate(ordered, 1):
                target = f"SHOT_{new_idx:0{width}d}_CAMERA_{idx}"
                self._rename_object(cam, target, bpy.data.cameras)

    def _rename_rigs(self) -> None:
        rig_groups: dict[tuple[str, int], list[Object]] = {}
        for obj in self.scene_objects:
            prefix = _resolve_rig_prefix(obj.name)
            if not prefix:
                continue
            _, new_idx = self._object_indices(obj)
            rig_groups.setdefault((prefix, new_idx), []).append(obj)
        if not rig_groups:
            return
        for (prefix, new_idx) in sorted(rig_groups):
            objs = rig_groups[(prefix, new_idx)]
            objs.sort(key=lambda o: _strip_numeric_suffix(o.name).lower())
            width = _shot_index_width(new_idx)
            for idx, obj in enumerate(objs, 1):
                target = f"{prefix}_SH{new_idx:0{width}d}_{idx}"
                data_blocks = bpy.data.armatures if obj.type == 'ARMATURE' else None
                self._rename_object(obj, target, data_blocks)

    def _rename_misc_objects(self) -> None:
        for obj in self.scene_objects:
            if obj.type == 'CAMERA':
                continue
            if _resolve_rig_prefix(obj.name):
                continue
            old_idx, new_idx = self._object_indices(obj)
            target = _target_object_name(obj.name, new_idx, old_idx)
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
        try:
            source_shot_roots = validate_scene.list_shot_roots(source_scene)
        except Exception:
            source_shot_roots = []
        index_mapping: Dict[int, int] = {}
        current_idx = next_idx
        for _coll, old_idx in source_shot_roots:
            if old_idx not in index_mapping:
                index_mapping[old_idx] = current_idx
                current_idx += 1
        source_scene_idx = _detect_scene_shot_index(source_scene)
        if source_scene_idx is not None and source_scene_idx not in index_mapping:
            index_mapping[source_scene_idx] = current_idx
            current_idx += 1
        renamer = _ShotSceneRenamer(source_scene, new_scene, next_idx, index_mapping)
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


        used_indices = sorted(renamer.used_new_indices) or [next_idx]
        if len(used_indices) == 1:
            shot_label = _format_sh_root("Shot", _shot_index_width(used_indices[0]), used_indices[0])
        else:
            first_label = _format_sh_root("Shot", _shot_index_width(used_indices[0]), used_indices[0])
            last_label = _format_sh_root("Shot", _shot_index_width(used_indices[-1]), used_indices[-1])
            shot_label = f"{first_label} - {last_label}"
        self.report({'INFO'}, f"Scene duplicated as {new_scene.name}; assigned {shot_label} ({len(changes)} rename(s))")
        renamer.flush_log()
        return {'FINISHED'}


__all__ = [
    "LIME_OT_duplicate_scene_sequential",
]


