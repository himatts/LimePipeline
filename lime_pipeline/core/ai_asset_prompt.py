"""Prompt/schema helpers for AI Asset Organizer."""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from .material_naming import ALLOWED_MATERIAL_TYPES


def schema_json_object() -> Dict[str, object]:
    return {"type": "json_object"}


def schema_assets() -> Dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ai_asset_namer",
            "strict": True,
            "schema": {
                "type": "object",
                "required": ["items"],
                "additionalProperties": False,
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["id", "name"],
                            "additionalProperties": False,
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "target_collection_hint": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    }


def build_prompt(
    context_text: str,
    scene_summary: str,
    objects: List[Dict[str, object]],
    materials: List[Dict[str, object]],
    collections: List[Dict[str, object]],
    *,
    collection_hierarchy: Optional[List[str]] = None,
    material_scene_context: Optional[Dict[str, object]] = None,
    object_group_hints: Optional[Dict[str, object]] = None,
) -> str:
    allowed_types = ", ".join(ALLOWED_MATERIAL_TYPES)
    context_block = (context_text or "").strip() or scene_summary
    context_line = f"Context: {context_block}\n" if context_block else ""

    payload: Dict[str, object] = {
        "scene_summary": scene_summary,
        "objects": objects,
        "materials": materials,
        "collections": collections,
    }
    if collection_hierarchy:
        payload["collection_hierarchy_paths"] = collection_hierarchy[:220]
    if material_scene_context:
        payload["material_scene_context"] = material_scene_context
    if object_group_hints:
        payload["object_group_hints"] = object_group_hints
    compact_json = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))

    return (
        "Return ONLY JSON per schema.\n"
        f"{context_line}"
        "Rules:\n"
        "- Objects: PascalCase segments separated by underscores (ASCII alphanumeric). "
        "No spaces/dots/dashes. Numeric identifiers must be a separate `_NN` block. "
        "No shot/scene prefixes.\n"
        "- Materials: MAT_{Tag?}_{MaterialType}_{Finish}_{V##}. Tag optional.\n"
        f"- MaterialType must be one of: {allowed_types}.\n"
        "- Collections: PascalCase segments separated by underscores (ASCII alphanumeric). "
        "No spaces/dots/dashes. Numeric identifiers must be a separate `_NN` block. "
        "Avoid shot prefixes.\n"
        "- For collection target suggestions, prefer human-friendly functional names (e.g., Background, Clothing, Accessories, Details, Lighting), not rigid academic taxonomy labels.\n"
        "- Treat target collections as suggestions to help users find items quickly in real production files.\n"
        "- Strong constraint: if an object is type LIGHT and already belongs to a LIGHTS collection path, keep it there.\n"
        "- Strong constraint: if an object is type CAMERA and already belongs to a CAM/CAMERA collection path, keep it there.\n"
        "- Do not suggest moving LIGHT/CAMERA objects to unrelated folders like props/annotations unless explicitly requested.\n"
        "- For object target collections, prioritize semantic clues in `name_tokens` and `semantic_tags` before generic buckets.\n"
        "- Avoid generic hints like Archive/Props unless there is no stronger semantic signal.\n"
        "- Use `object_group_hints` clusters to keep naming/grouping coherent across similar objects.\n"
        "- Material naming must consider all existing scene materials from material_scene_context (including non-selected).\n"
        "- Material naming must respect shader_profile cues in each material (metallic, roughness, transmission, emission).\n"
        "- Avoid Metal type when metallic is low and there is no explicit metal cue.\n"
        "- If finish/type is uncertain, prefer conservative generic names instead of over-specific labels.\n"
        "- Use specific finishes (e.g., Brushed, Chrome, Anodized, Frosted) only with clear evidence from source names, texture hints, or shader_profile.\n"
        "- Do not classify as Emissive when emission is effectively off (black emission or negligible emission energy).\n"
        "- Never propose a material name that already exists; if a group exists, propose the next available V##.\n"
        "- Optional for objects: include `target_collection_hint` with a full path when confident.\n"
        "- Use hierarchy/context hints (parent_id, children_count, shared_data_users, collection_hints, used_on).\n"
        "- Use hierarchy signals to infer semantics: parent_name, parent_type, root_name, hierarchy_depth, sibling_count, children_preview.\n"
        "- Treat EMPTY objects as meaningful semantic nodes using `empty_role_hint` (Controller, GroupRoot, Locator, Helper).\n"
        "- Infer hierarchical role from tree + naming: ROOT_CONTROLLER / CONTROLLER / GROUP_ROOT / COMPONENT.\n"
        "- Objects with role ROOT_CONTROLLER or CONTROLLER should prefer top-level/controller collections, not deep technical subcategories.\n"
        "- Never classify a root controller under Electronics/Fasteners unless there is explicit strong evidence in name + hierarchy.\n"
        "- Prefer grouping components under their controlling root_name when the hierarchy indicates a single system.\n"
        "- Keep parent/child families coherent: siblings should generally share collection intent unless explicit signal says otherwise.\n"
        "- For child objects with generic names (e.g., Mesh, Cube, Empty), inherit intent from parent/root semantics.\n"
        "- Names must be unique per category (object/material/collection).\n"
        "Items JSON:\n"
        f"{compact_json}\n"
    )


__all__ = ["schema_json_object", "schema_assets", "build_prompt"]
