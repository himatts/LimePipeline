"""Material probing helpers for AI Asset Organizer."""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

import bpy
from bpy.types import Material

from ...core.material_naming import parse_name as parse_material_name


_MATERIAL_NAME_CONTEXT_LIMIT = 320
_MATERIAL_GROUP_CONTEXT_LIMIT = 280


def build_material_scene_context(selected_materials: Sequence[Material]) -> Dict[str, object]:
    selected_ptrs = {m.as_pointer() for m in list(selected_materials or []) if m is not None}
    all_names: List[str] = []
    non_selected_names: List[str] = []
    groups: Dict[Tuple[str, str, str], Dict[str, object]] = {}

    for mat in list(getattr(bpy.data, "materials", []) or []):
        if mat is None:
            continue
        name = (getattr(mat, "name", "") or "").strip()
        if not name:
            continue
        all_names.append(name)
        if mat.as_pointer() not in selected_ptrs:
            non_selected_names.append(name)

        parsed = parse_material_name(name)
        if not parsed:
            continue
        scene_tag = str(parsed.get("scene_tag") or "")
        material_type = str(parsed.get("material_type") or "Plastic")
        finish = str(parsed.get("finish") or "Generic")
        version_index = int(parsed.get("version_index") or 1)
        key = (scene_tag, material_type, finish)
        entry = groups.get(key)
        if entry is None:
            entry = {
                "scene_tag": scene_tag,
                "material_type": material_type,
                "finish": finish,
                "max_version_index": version_index,
                "count": 1,
            }
            groups[key] = entry
        else:
            entry["count"] = int(entry.get("count", 0) or 0) + 1
            entry["max_version_index"] = max(int(entry.get("max_version_index", 1) or 1), version_index)

    all_names_sorted = sorted(set(all_names))
    non_selected_sorted = sorted(set(non_selected_names))
    group_items = list(groups.values())
    group_items.sort(
        key=lambda item: (
            str(item.get("material_type") or ""),
            str(item.get("finish") or ""),
            str(item.get("scene_tag") or ""),
        )
    )

    return {
        "total_scene_materials": len(all_names_sorted),
        "selected_materials": len(selected_ptrs),
        "non_selected_materials": len(non_selected_sorted),
        "all_material_names": all_names_sorted[:_MATERIAL_NAME_CONTEXT_LIMIT],
        "all_material_names_truncated": len(all_names_sorted) > _MATERIAL_NAME_CONTEXT_LIMIT,
        "non_selected_material_names": non_selected_sorted[:_MATERIAL_NAME_CONTEXT_LIMIT],
        "non_selected_material_names_truncated": len(non_selected_sorted) > _MATERIAL_NAME_CONTEXT_LIMIT,
        "material_version_groups": group_items[:_MATERIAL_GROUP_CONTEXT_LIMIT],
        "material_version_groups_truncated": len(group_items) > _MATERIAL_GROUP_CONTEXT_LIMIT,
    }


def material_shader_profile(mat: Optional[Material]) -> Dict[str, object]:
    profile: Dict[str, object] = {
        "uses_nodes": False,
        "metallic": 0.0,
        "roughness": 0.5,
        "transmission": 0.0,
        "ior": 1.45,
        "alpha": 1.0,
        "emission_strength": 0.0,
        "emission_luma": 0.0,
        "has_metallic_input": False,
        "has_roughness_input": False,
        "has_transmission_input": False,
        "has_normal_input": False,
        "has_emission_input": False,
    }
    if mat is None:
        return profile
    if not bool(getattr(mat, "use_nodes", False)):
        return profile
    profile["uses_nodes"] = True
    tree = getattr(mat, "node_tree", None)
    nodes = list(getattr(tree, "nodes", []) or [])
    if not nodes:
        return profile

    def _find_first_principled():
        for node in nodes:
            if getattr(node, "type", "") == "OUTPUT_MATERIAL" and bool(getattr(node, "is_active_output", False)):
                surface = getattr(node, "inputs", {}).get("Surface")
                if surface and bool(getattr(surface, "is_linked", False)):
                    links = list(getattr(surface, "links", []) or [])
                    if links:
                        src_node = getattr(links[0], "from_node", None)
                        if src_node is not None and getattr(src_node, "type", "") == "BSDF_PRINCIPLED":
                            return src_node
        for node in nodes:
            if getattr(node, "type", "") == "BSDF_PRINCIPLED":
                return node
        return None

    def _input_value(node, names: Sequence[str], default: float) -> float:
        inputs = getattr(node, "inputs", {})
        for name in names:
            socket = inputs.get(name)
            if socket is None:
                continue
            value = getattr(socket, "default_value", default)
            try:
                return float(value)
            except Exception:
                continue
        return default

    def _input_linked(node, names: Sequence[str]) -> bool:
        inputs = getattr(node, "inputs", {})
        for name in names:
            socket = inputs.get(name)
            if socket is not None and bool(getattr(socket, "is_linked", False)):
                return True
        return False

    def _input_color_luma(node, names: Sequence[str], default: float) -> float:
        inputs = getattr(node, "inputs", {})
        for name in names:
            socket = inputs.get(name)
            if socket is None:
                continue
            value = getattr(socket, "default_value", None)
            if isinstance(value, (list, tuple)) and len(value) >= 3:
                try:
                    r = float(value[0] or 0.0)
                    g = float(value[1] or 0.0)
                    b = float(value[2] or 0.0)
                    return max(0.0, (r + g + b) / 3.0)
                except Exception:
                    continue
        return default

    principled = _find_first_principled()
    if principled is None:
        return profile

    profile["metallic"] = _input_value(principled, ("Metallic",), 0.0)
    profile["roughness"] = _input_value(principled, ("Roughness",), 0.5)
    profile["transmission"] = _input_value(principled, ("Transmission Weight", "Transmission"), 0.0)
    profile["ior"] = _input_value(principled, ("IOR",), 1.45)
    profile["alpha"] = _input_value(principled, ("Alpha",), 1.0)
    profile["emission_strength"] = _input_value(principled, ("Emission Strength",), 0.0)
    profile["emission_luma"] = _input_color_luma(principled, ("Emission Color", "Emission"), 0.0)
    profile["has_metallic_input"] = _input_linked(principled, ("Metallic",))
    profile["has_roughness_input"] = _input_linked(principled, ("Roughness",))
    profile["has_transmission_input"] = _input_linked(principled, ("Transmission Weight", "Transmission"))
    profile["has_normal_input"] = _input_linked(principled, ("Normal",))
    profile["has_emission_input"] = _input_linked(principled, ("Emission Color", "Emission"))
    return profile


def material_texture_hints(mat: Optional[Material], *, limit: int = 8) -> List[str]:
    if mat is None or not bool(getattr(mat, "use_nodes", False)):
        return []
    tree = getattr(mat, "node_tree", None)
    nodes = list(getattr(tree, "nodes", []) or [])
    names: List[str] = []
    seen: set[str] = set()
    for node in nodes:
        if getattr(node, "type", "") != "TEX_IMAGE":
            continue
        image = getattr(node, "image", None)
        if image is None:
            continue
        image_name = (getattr(image, "name", "") or "").strip()
        image_path = (getattr(image, "filepath", "") or "").strip()
        hint = os.path.basename(image_path) if image_path else image_name
        hint = (hint or image_name or "").strip()
        if not hint:
            continue
        key = hint.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(hint)
        if len(names) >= limit:
            break
    return names

__all__ = [
    "material_shader_profile",
    "material_texture_hints",
    "build_material_scene_context",
]
