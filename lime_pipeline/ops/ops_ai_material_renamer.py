"""
AI Material Renamer Operators

This module provides operators for AI-powered material renaming and management in Blender.
It integrates with external AI services to analyze material properties and suggest
appropriate names based on material taxonomy and naming conventions.

The operators handle various aspects of the AI material renaming workflow:
- Testing AI service connections
- Scanning materials for analysis
- Generating renaming proposals
- Applying approved name changes
- Managing material selection states

Key Features:
- Integrates with external AI services for material analysis
- Supports batch material processing with progress tracking
- Maintains material naming consistency with Lime Pipeline conventions
- Provides selection management for large material sets
- Includes connection testing and error handling for AI services
- Supports taxonomy-based material type detection and validation
"""

from __future__ import annotations

import json
import colorsys
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
import urllib.request
import urllib.error

import bpy
from bpy.types import Material, Operator, Scene

from ..prefs import LimePipelinePrefs
from ..props_ai_materials import LimeAIMatRow
from ..core.material_naming import (
    ALLOWED_MATERIAL_TYPES,
    PREFIX,
    build_name,
    build_version,
    bump_version_until_unique,
    detect_issues,
    normalize_material_type,
    normalize_finish,
    parse_name,
    parse_version,
    strip_numeric_suffix,
)
from ..core.material_taxonomy import get_taxonomy_context, get_allowed_material_types
from ..core.material_reconciliation import reconcile_proposal, apply_batch_normalization
from ..core.material_quality import evaluate_material_name


def _get_active_scene(context) -> Scene:
    scene: Scene = context.window.scene if context.window else context.scene
    return scene


def _is_read_only(mat: Material) -> bool:
    return bool(mat.library or mat.override_library)


def _collect_existing_names() -> List[str]:
    return [m.name for m in bpy.data.materials]


def _get_texture_basenames(mat: Material) -> List[str]:
    basenames = []
    try:
        nt = mat.node_tree
        if not nt:
            return basenames
        for n in nt.nodes:
            if n.bl_idname == 'ShaderNodeTexImage' and n.image:
                img_name = getattr(n.image, 'name', '')
                if img_name:
                    basename = img_name.rsplit('.', 1)[0]  # Remove extension
                    if basename not in basenames:
                        basenames.append(basename)
    except Exception:
        pass
    return basenames


_BACKGROUND_KEYWORDS = (
    "background",
    "backdrop",
    "backplate",
    "sky",
    "skybox",
    "skydome",
    "horizon",
    "environment",
    "env",
    "envmap",
    "fondo",
)


def _has_background_hint(text: str) -> bool:
    lower = text.lower()
    for keyword in _BACKGROUND_KEYWORDS:
        if keyword in lower:
            return True
    if lower.startswith("bg") and (len(lower) == 2 or not lower[2].isalpha()):
        return True
    for sep in ("_", "-", " "):
        if f"{sep}bg" in lower or f"bg{sep}" in lower:
            return True
    return False


def _is_background_material(mat: Material, object_hints: List[str], collection_hints: List[str]) -> bool:
    try:
        if _has_background_hint(mat.name):
            return True
        for hint in object_hints:
            if _has_background_hint(hint):
                return True
        for hint in collection_hints:
            if _has_background_hint(hint):
                return True
    except Exception:
        pass
    return False


def _rgb_to_color_name(r: float, g: float, b: float) -> str:
    r = max(0.0, min(1.0, float(r)))
    g = max(0.0, min(1.0, float(g)))
    b = max(0.0, min(1.0, float(b)))

    brightness = max(r, g, b)
    min_channel = min(r, g, b)
    saturation = brightness - min_channel

    if brightness < 0.1:
        return "Black"
    if saturation < 0.08:
        if brightness > 0.85:
            return "White"
        if brightness > 0.6:
            return "LightGray"
        if brightness > 0.3:
            return "Gray"
        return "DarkGray"

    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    hue = (h * 360.0) % 360.0
    prefix = ""
    if v > 0.75:
        prefix = "Light"
    elif v < 0.35:
        prefix = "Dark"

    if 0 <= hue < 20 or hue >= 340:
        base = "Red"
    elif 20 <= hue < 45:
        base = "Orange"
    elif 45 <= hue < 70:
        base = "Yellow"
    elif 70 <= hue < 150:
        base = "Green"
    elif 150 <= hue < 200:
        base = "Teal"
    elif 200 <= hue < 255:
        base = "Blue"
    elif 255 <= hue < 290:
        base = "Purple"
    elif 290 <= hue < 330:
        base = "Magenta"
    else:
        base = "Red"

    if prefix and base not in ("Teal", "Magenta"):
        return f"{prefix}{base}"
    return base


def _extract_color_from_input(node, socket_name: str) -> Optional[Tuple[float, float, float]]:
    try:
        if socket_name not in node.inputs:
            return None
        socket = node.inputs[socket_name]
        if socket.is_linked:
            return None
        color = socket.default_value
        if not color or len(color) < 3:
            return None
        return (float(color[0]), float(color[1]), float(color[2]))
    except Exception:
        return None


def _extract_background_color(mat: Material) -> Optional[str]:
    try:
        nt = mat.node_tree
        if not nt:
            return None

        candidate_colors: List[Tuple[float, float, float]] = []

        for node in nt.nodes:
            bl_idname = getattr(node, "bl_idname", "")

            if bl_idname == "ShaderNodeValToRGB":
                elements = getattr(node.color_ramp, "elements", None)
                if elements and len(elements) >= 1:
                    color = elements[0].color
                    candidate_colors.append((float(color[0]), float(color[1]), float(color[2])))
            elif bl_idname == "ShaderNodeBackground":
                color = _extract_color_from_input(node, "Color")
                if color:
                    candidate_colors.append(color)
            elif bl_idname == "ShaderNodeEmission":
                color = _extract_color_from_input(node, "Color")
                if color:
                    candidate_colors.append(color)
            elif bl_idname == "ShaderNodeBsdfPrincipled":
                base_color = _extract_color_from_input(node, "Base Color")
                if base_color:
                    candidate_colors.append(base_color)
                emission_color = _extract_color_from_input(node, "Emission Color")
                if emission_color:
                    candidate_colors.append(emission_color)

        if not candidate_colors:
            return None

        # Prefer brightest colors (backgrounds are usually luminous)
        candidate_colors.sort(key=lambda c: max(c), reverse=True)
        color = candidate_colors[0]
        return _rgb_to_color_name(*color)
    except Exception:
        return None


def _build_background_material_name(
    mat: Material,
    color_name: str,
    universe: List[str],
    start_idx: int = 1,
) -> str:
    finish = normalize_finish(color_name or "Generic")
    return bump_version_until_unique(universe, "Background", finish, start_idx=max(1, int(start_idx or 1)))


def _get_object_and_collection_hints(mat: Material) -> Tuple[List[str], List[str]]:
    object_hints = []
    collection_hints = []
    try:
        for obj in bpy.data.objects:
            for slot in obj.material_slots:
                if slot.material == mat:
                    if obj.name not in object_hints:
                        object_hints.append(obj.name)
                    for col in obj.users_collection:
                        if col.name not in collection_hints:
                            collection_hints.append(col.name)
                    break  # Only need one per object
    except Exception:
        pass
    return object_hints[:3], collection_hints[:3]  # Limit to 3 each


def _summarize_nodes(mat: Material) -> Dict[str, object]:
    ids: List[str] = []
    counts: Dict[str, int] = {}
    principled: Optional[Dict[str, object]] = None
    texture_basenames: List[str] = []
    object_hints, collection_hints = _get_object_and_collection_hints(mat)
    is_background = _is_background_material(mat, object_hints, collection_hints)
    background_color: Optional[str] = None

    try:
        nt = mat.node_tree
        if not nt:
            return {
                "ids": ids,
                "counts": counts,
                "principled": principled,
                "texture_basenames": texture_basenames,
                "object_hints": object_hints,
                "collection_hints": collection_hints,
                "is_background": is_background,
                "background_color": background_color,
            }

        texture_basenames = _get_texture_basenames(mat)

        for n in nt.nodes:
            bl_idname = getattr(n, 'bl_idname', '')
            if bl_idname:
                ids.append(bl_idname)
                counts[bl_idname] = counts.get(bl_idname, 0) + 1
            if bl_idname == 'ShaderNodeBsdfPrincipled':
                principled = {
                    "metallic": float(n.inputs["Metallic"].default_value) if "Metallic" in n.inputs else 0.0,
                    "roughness": float(n.inputs["Roughness"].default_value) if "Roughness" in n.inputs else 0.5,
                    "specular": float(n.inputs["Specular"].default_value) if "Specular" in n.inputs else 0.5,
                    "ior": float(n.inputs["IOR"].default_value) if "IOR" in n.inputs else 1.45,
                    "alpha": float(n.inputs["Alpha"].default_value) if "Alpha" in n.inputs else 1.0,
                    "emission_strength": float(n.inputs["Emission Strength"].default_value) if "Emission Strength" in n.inputs else 0.0,
                    "normal_connected": bool(n.inputs.get("Normal") and n.inputs["Normal"].is_linked),
                    "clearcoat": float(n.inputs["Clearcoat"].default_value) if "Clearcoat" in n.inputs else 0.0,
                    "transmission": float(n.inputs["Transmission"].default_value) if "Transmission" in n.inputs else 0.0,
                }
                base_color = _extract_color_from_input(n, "Base Color")
                if base_color:
                    principled["base_color"] = base_color
                emission_color = _extract_color_from_input(n, "Emission Color")
                if emission_color:
                    principled["emission_color"] = emission_color

        if is_background:
            background_color = _extract_background_color(mat)
    except Exception:
        pass

    return {
        "ids": ids,
        "counts": counts,
        "principled": principled,
        "texture_basenames": texture_basenames,
        "object_hints": object_hints,
        "collection_hints": collection_hints,
        "is_background": is_background,
        "background_color": background_color,
    }


def _fingerprint_material(mat: Material) -> str:
    # Lightweight placeholder: could hash texture basenames + principled bins + node ids
    summary = _summarize_nodes(mat)
    ids = sorted(set(summary.get("ids", [])))
    key = f"nodes:{','.join(ids)[:64]}"
    return key


def _build_review_proposal_entry(
    mat: Material,
    parsed: Optional[Dict[str, object]],
    universe: List[str],
    *,
    quality_label: str,
    quality_score: float,
    quality_issues: str,
    taxonomy_match: str,
) -> Dict[str, object]:
    material_name = mat.name
    material_type = normalize_material_type(parsed["material_type"] if parsed else "Plastic")
    finish = normalize_finish(parsed["finish"] if parsed else "Generic")
    current_idx = (parsed.get("version_index") if parsed else None) or 1
    
    # Check if current name is valid and unique - preserve it if so
    current_name_clean = strip_numeric_suffix(material_name)
    current_is_valid = parse_name(current_name_clean) is not None
    current_is_unique = current_name_clean not in universe or current_name_clean == material_name
    
    if current_is_valid and current_is_unique:
        # Material name is already valid and unique - preserve it
        proposed = current_name_clean
        version_block = parsed.get("version") if parsed else "V01"
        notes = "Review proposal - keeping current valid name"
    else:
        # Need to find a unique version - try current version first, then bump if needed
        proposed = bump_version_until_unique(universe, material_type, finish, start_idx=current_idx)
        parts = proposed.split("_")
        version_block = parts[-1] if len(parts) > 2 else "V01"
        notes = "Review proposal - adjusted version for uniqueness"
    
    return {
        "material_name": material_name,
        "proposed_name": proposed,
        "material_type": material_type,
        "finish": finish,
        "version_token": version_block,
        "read_only": False,
        "notes": notes,
        "similar_group_id": _fingerprint_material(mat),
        "needs_rename": False,
        "review_requested": True,
        "selected_for_apply": False,
        "quality_label": quality_label,
        "quality_score": quality_score,
        "quality_issues": quality_issues,
        "taxonomy_match": taxonomy_match,
    }


_SELECTION_REFRESH_GUARD = 0
_SELECTION_REFRESH_SUSPENDED = False


@contextmanager
def _suspend_selection_refresh() -> Iterable[None]:
    """Temporarily disable automatic preview recalculation while mutating rows."""
    global _SELECTION_REFRESH_SUSPENDED
    previous = _SELECTION_REFRESH_SUSPENDED
    _SELECTION_REFRESH_SUSPENDED = True
    try:
        yield
    finally:
        _SELECTION_REFRESH_SUSPENDED = previous


def refresh_selection_preview(scene: Optional[Scene] = None) -> None:
    """Recalculate statuses and sequential previews when selection changes."""
    global _SELECTION_REFRESH_GUARD

    if _SELECTION_REFRESH_SUSPENDED:
        return

    if scene is None:
        try:
            scene = bpy.context.scene
        except Exception:
            scene = None
    if scene is None:
        return

    if _SELECTION_REFRESH_GUARD > 0:
        return

    try:
        _SELECTION_REFRESH_GUARD += 1
        # Get force_reanalysis state from scene
        state = getattr(scene, 'lime_ai_mat', None)
        force_reanalysis = getattr(state, 'force_reanalysis', False) if state else False
        _postprocess_statuses(scene, force_reanalysis)
    finally:
        _SELECTION_REFRESH_GUARD -= 1


def _write_rows(scene: Scene, items: List[Dict[str, object]], incorrect_count: int = 0, total_count: int = 0) -> None:
    print(f"[AI Write Rows] Starting with {len(items)} items")
    state = scene.lime_ai_mat
    print(f"[AI Write Rows] State before clear: {len(state.rows)} rows")

    with _suspend_selection_refresh():
        state.rows.clear()
        # scene_tag_used no longer used
        state.incorrect_count = incorrect_count
        state.total_count = total_count

        print(f"[AI Write Rows] After clear: {len(state.rows)} rows")
        print(f"[AI Write Rows] incorrect_count: {incorrect_count}, total_count: {total_count}")

        for i, item in enumerate(items):
            row = state.rows.add()
            row.material_name = str(item.get("material_name") or "")
            row.proposed_name = str(item.get("proposed_name") or "")
            row.original_proposal = str(item.get("proposed_name") or "")  # Save original AI proposal
            row.material_type = str(item.get("material_type") or "Plastic")
            row.finish = str(item.get("finish") or "Generic")
            row.version_token = str(item.get("version_token") or "V01")
            row.similar_group_id = str(item.get("similar_group_id") or "")
            row.status = str(item.get("status") or item.get("notes") or "")
            row.read_only = bool(item.get("read_only") or False)
            row.confidence = float(item.get("confidence", 0.7) or 0.0)
            row.is_indexed = bool(item.get("is_indexed", False))
            row.quality_score = float(item.get("quality_score", 0.0) or 0.0)
            row.quality_label = str(item.get("quality_label") or "invalid")
            row.quality_issues = str(item.get("quality_issues") or "")
            row.review_requested = bool(item.get("review_requested", False))
            row.taxonomy_match = str(item.get("taxonomy_match") or "")
            row.is_normalized = bool(item.get("is_normalized", False))
            row.reconciliation_action = str(item.get("reconciliation_action", "ACCEPT"))
            # If not explicitly provided, infer from current material name validity
            _needs = item.get("needs_rename")
            row.needs_rename = bool(_needs) if _needs is not None else bool(detect_issues(row.material_name))

            # Check if we're in force reanalysis mode
            state = scene.lime_ai_mat
            force_reanalysis = getattr(state, "force_reanalysis", False)

            default_selected = item.get("selected_for_apply")
            if default_selected is None:
                # In force reanalysis mode, select materials that need rename OR correctly named materials for re-analysis
                if force_reanalysis:
                    # In force reanalysis, select all non-read-only materials by default
                    # User can then deselect if they don't want to change a particular material
                    default_selected = not row.read_only
                else:
                    default_selected = (not row.read_only) and (row.needs_rename or row.review_requested)
            row.selected_for_apply = bool(default_selected and not row.read_only)

            if i < 3:  # Debug first 3 items
                print(f"[AI Write Rows] Added item {i}: {row.material_name} -> {row.proposed_name} (confidence: {row.confidence}, needs_rename: {row.needs_rename})")

    print(f"[AI Write Rows] Final state: {len(state.rows)} rows")
    refresh_selection_preview(scene)


@dataclass
class _ResequenceCandidate:
    row: LimeAIMatRow
    material_type: str
    finish: str
    version_width: int
    version_index_hint: int
    order_key: Tuple[str, str, int, str, int]
    source_token: str


def _version_width(token: str) -> int:
    if not token or not token.startswith("V"):
        return 2
    digits = token[1:]
    return max(2, len(digits)) if digits.isdigit() else 2


def _derive_row_target(row: LimeAIMatRow) -> Tuple[str, str, str, int]:
    """Return normalized material type, finish, raw version token and index hint for a row."""
    if row.proposed_name:
        parsed = parse_name(row.proposed_name)
        if parsed:
            token = row.proposed_name.split("_")[-1]
            if not (token.startswith("V") and token[1:].isdigit()):
                token = parsed["version"]
            version_idx = parsed.get("version_index") or parse_version(token) or 1
            return (
                normalize_material_type(parsed["material_type"]),
                normalize_finish(parsed["finish"]),
                token,
                version_idx,
            )

    current_candidate = strip_numeric_suffix(row.material_name or "")
    if current_candidate:
        parsed = parse_name(current_candidate)
        if parsed:
            token = current_candidate.split("_")[-1]
            if not (token.startswith("V") and token[1:].isdigit()):
                token = parsed["version"]
            version_idx = parsed.get("version_index") or parse_version(token) or 1
            return (
                normalize_material_type(parsed["material_type"]),
                normalize_finish(parsed["finish"]),
                token,
                version_idx,
            )

    material_type = normalize_material_type(getattr(row, "material_type", "") or "Plastic")
    finish = normalize_finish(getattr(row, "finish", "") or "Generic")
    token = getattr(row, "version_token", "") or "V01"
    version_idx = parse_version(token) or 1
    if not (token.startswith("V") and token[1:].isdigit()):
        token = f"V{version_idx:02d}"
    return material_type, finish, token, version_idx


def _resequence_selected_rows(rows: Iterable[LimeAIMatRow], existing_names: List[str]) -> None:
    """Assign sequential version tokens to selected actionable rows without collisions."""
    candidates: List[_ResequenceCandidate] = []
    selected_current_names: set[str] = set()

    for idx, row in enumerate(rows):
        status = (row.status or "").upper()
        if row.read_only or not row.selected_for_apply:
            continue
        if not (status.startswith("NEEDS_RENAME") or status.startswith("NAME_COLLISION")):
            continue
        material_type, finish, token, version_idx = _derive_row_target(row)
        order_key = (
            material_type,
            finish,
            int(version_idx or 0),
            (row.material_name or "").lower(),
            idx,
        )
        candidates.append(
            _ResequenceCandidate(
                row=row,
                material_type=material_type,
                finish=finish,
                version_width=_version_width(token),
                version_index_hint=int(version_idx or 0),
                order_key=order_key,
                source_token=token,
            )
        )
        selected_current_names.add(row.material_name)

    if not candidates:
        return

    existing_name_set = set(existing_names or [])
    group_used_versions: Dict[Tuple[str, str], set[int]] = {}
    group_width_map: Dict[Tuple[str, str], int] = {}

    for name in existing_names or []:
        if not name:
            continue
        base_name = strip_numeric_suffix(name)
        parsed = parse_name(base_name)
        if not parsed:
            continue
        key = (parsed["material_type"], parsed["finish"])
        token_raw = base_name.split("_")[-1]
        group_width_map[key] = max(group_width_map.get(key, 2), _version_width(token_raw))
        if name in selected_current_names:
            continue
        version_idx = parsed.get("version_index")
        if isinstance(version_idx, int):
            group_used_versions.setdefault(key, set()).add(version_idx)

    group_map: Dict[Tuple[str, str], List[_ResequenceCandidate]] = {}
    for candidate in candidates:
        key = (candidate.material_type, candidate.finish)
        group_width_map[key] = max(group_width_map.get(key, 2), candidate.version_width)
        group_map.setdefault(key, []).append(candidate)

    assigned_names: set[str] = set()

    for key, group_candidates in group_map.items():
        group_candidates.sort(key=lambda c: c.order_key)
        used_versions = set(group_used_versions.get(key, set()))
        width = group_width_map.get(key, 2)
        current_version = 1
        while current_version in used_versions:
            current_version += 1

        for candidate in group_candidates:
            while True:
                if current_version in used_versions:
                    current_version += 1
                    continue
                token = f"V{current_version:0{width}d}"
                name = f"{PREFIX}_{candidate.material_type}_{candidate.finish}_{token}"
                if name in assigned_names:
                    current_version += 1
                    continue
                if name in existing_name_set and name not in selected_current_names:
                    current_version += 1
                    continue
                break

            candidate.row.proposed_name = name
            candidate.row.material_type = candidate.material_type
            candidate.row.finish = candidate.finish
            candidate.row.version_token = token

            assigned_names.add(name)
            used_versions.add(current_version)
            existing_name_set.add(name)
            current_version += 1

def _postprocess_statuses(scene: Scene, force_reanalysis: bool = False) -> None:
    """Compute status badges, sequence gaps and resequenced proposals."""
    try:
        state = scene.lime_ai_mat
    except Exception:
        return

    rows = list(state.rows)
    if not rows:
        return

    existing_names = list(_collect_existing_names())
    existing_name_set = set(existing_names)

    parsed_info: List[Tuple[LimeAIMatRow, Optional[Dict[str, object]], str]] = []
    group_to_versions: Dict[Tuple[str, str], List[int]] = {}

    for row in rows:
        current_name = strip_numeric_suffix(row.material_name or "")
        parsed = parse_name(current_name)
        if parsed is None:
            status = "NEEDS_RENAME" if row.needs_rename or row.proposed_name else "UNPARSEABLE"
        else:
            key = (parsed["material_type"], parsed["finish"])
            version_idx = parsed.get("version_index")
            if isinstance(version_idx, int):
                group_to_versions.setdefault(key, []).append(version_idx)
            # Keep normalized metadata in sync with actual name
            row.material_type = parsed["material_type"]
            row.finish = parsed["finish"]
            row.version_token = parsed["version"]

            if row.needs_rename:
                status = "NEEDS_RENAME"
            elif row.review_requested:
                status = "REVIEW"
            else:
                quality_label = (row.quality_label or "").strip().lower()
                if quality_label:
                    status = f"VALID:{quality_label}"
                else:
                    status = "VALID"

        parsed_info.append((row, parsed, status))

    group_missing: Dict[Tuple[str, str], List[int]] = {}
    for key, versions in group_to_versions.items():
        if not versions:
            continue
        normalized_versions = sorted(v for v in versions if isinstance(v, int))
        if not normalized_versions:
            continue
        lo, hi = normalized_versions[0], normalized_versions[-1]
        missing = [v for v in range(lo, hi + 1) if v not in normalized_versions]
        if missing:
            group_missing[key] = missing

    for row, parsed, baseline_status in parsed_info:
        status = baseline_status
        if parsed is not None and status == "VALID":
            key = (parsed["material_type"], parsed["finish"])
            if key in group_missing:
                missing_tokens = ", ".join(f"V{m:02d}" for m in group_missing[key][:6])
                row.status = f"SEQUENCE_GAP: Missing {missing_tokens}"
            else:
                row.status = status
        else:
            row.status = status

        # Check if we're in force reanalysis mode
        state = scene.lime_ai_mat
        force_reanalysis = getattr(state, 'force_reanalysis', False)

        # Always keep proposed_name visible - users should see what was determined
        # even if material is already correct (VALID status)
        # The UI will show it as non-editable if the material doesn't need changes

        if row.read_only or (
            row.status not in ("NEEDS_RENAME", "NAME_COLLISION") and not row.review_requested
        ):
            # In force reanalysis mode, keep materials selected even if they were valid
            # This allows users to apply changes to well-named materials if they want
            if not force_reanalysis:
                row.selected_for_apply = False

    _resequence_selected_rows(rows, existing_names)

    assigned_targets: set[str] = set()

    for row in rows:
        status = (row.status or "").upper()
        if status in ("NEEDS_RENAME", "NAME_COLLISION") and not row.read_only:
            target = row.proposed_name or ""
            if target:
                parsed_target = parse_name(target)
                if parsed_target:
                    row.material_type = parsed_target["material_type"]
                    row.finish = parsed_target["finish"]
                    row.version_token = parsed_target["version"]
                if target in existing_name_set and target != row.material_name:
                    row.status = "NAME_COLLISION"
                elif target in assigned_targets:
                    row.status = "NAME_COLLISION"
                else:
                    row.status = "NEEDS_RENAME"
                    assigned_targets.add(target)
        else:
            # For correctly indexed materials, ensure the field shows the real name
            if status.startswith("VALID"):
                proposal_clean = (row.proposed_name or "").strip()
                if not proposal_clean or proposal_clean.upper().startswith("MAT_PLASTIC_GENERIC"):
                    row.proposed_name = row.material_name


def _is_row_visible(row: LimeAIMatRow, view_filter: str) -> bool:
    status = (row.status or "").upper()
    if view_filter == 'ALL':
        return True
    if view_filter == 'CORRECT':
        return status.startswith('VALID')
    return (
        status.startswith('NEEDS_RENAME')
        or status.startswith('NAME_COLLISION')
        or status.startswith('UNPARSEABLE')
        or status.startswith('SEQUENCE_GAP')
    )


# -----------------------------------------------------------------------------
# OpenRouter helpers
# -----------------------------------------------------------------------------

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def _openrouter_headers(prefs: LimePipelinePrefs) -> Dict[str, str]:
    key = (getattr(prefs, 'openrouter_api_key', '') or '').strip()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if key:
        headers["Authorization"] = f"Bearer {key}"
    else:
        print("[AI] Warning: OpenRouter API key empty after strip().")
    if getattr(prefs, 'http_referer', None):
        headers["HTTP-Referer"] = prefs.http_referer
    else:
        headers["HTTP-Referer"] = "https://limepipeline.local"  # safe default per OpenRouter attribution
    if getattr(prefs, 'x_title', None):
        headers["X-Title"] = prefs.x_title
    else:
        headers["X-Title"] = "Lime Pipeline"
    # Debug (no secrets):
    try:
        print(f"[AI] Headers prepared. Authorization present: {'Authorization' in headers}")
    except Exception:
        pass
    return headers


def _http_get_json(url: str, headers: Dict[str, str], timeout: int = 20) -> Optional[Dict[str, object]]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        try:
            err = e.read().decode("utf-8", errors="replace")
        except Exception:
            err = str(e)
        print(f"[AI] GET failed {e.code}: {err}")
        return None
    except Exception as e:
        print(f"[AI] GET exception: {e}")
        return None


def _http_post_json(url: str, payload: Dict[str, object], headers: Dict[str, str], timeout: int = 60) -> Optional[Dict[str, object]]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        try:
            err = e.read().decode("utf-8", errors="replace")
        except Exception:
            err = str(e)
        print(f"[AI] POST failed {e.code}: {err}")
        return None
    except Exception as e:
        print(f"[AI] POST exception: {e}")
        return None


def _truncate_context(context: str, max_chars: int = 500) -> str:
    """Truncate scene context to max length, preserving key material keywords."""
    if not context or len(context) <= max_chars:
        return context
    truncated = context[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.8:
        return truncated[:last_space]
    return truncated


def _build_user_message_with_context(
    base_payload: Dict[str, object],
    scene_context: str,
) -> Dict[str, object]:
    """
    Inject scene context into the user message with high priority.
    
    The scene_context is prominently placed to influence material classification.
    """
    if not scene_context:
        return base_payload
    
    context_text = _truncate_context(scene_context, max_chars=500)
    payload = dict(base_payload)
    
    # Add context as a prominent field, not just a hint
    payload["scene_context"] = context_text
    payload["_scene_context"] = context_text  # Keep both for compatibility
    
    # Add context-aware instructions
    payload["context_instructions"] = {
        "priority": "HIGH",
        "description": "Use this scene context to make intelligent material type inferences",
        "mapping_rules": {
            "textiles": ["toalla", "tela", "textil", "ropa", "towel", "fabric", "cloth"],
            "organic": ["piel", "diente", "ojo", "cabello", "skin", "tooth", "eye", "hair"],
            "plastic": ["plástico", "silicona", "goma", "plastic", "silicone", "rubber"],
            "metal": ["metal", "acero", "aluminio", "steel", "aluminum", "brushed"],
            "natural": ["madera", "piedra", "mármol", "wood", "stone", "marble"]
        }
    }
    
    return payload


def _system_prompt() -> str:
    # Use taxonomy-driven allowed types to avoid divergence from core
    allowed_types = get_allowed_material_types()
    allowed = ", ".join(allowed_types)
    return (
        "You are a Blender materials librarian assisting an addon via OpenRouter.\n"
        "TARGET MODEL: google/gemini-2.5-flash-lite-preview-09-2025.\n\n"
        "Your ONLY job: output a final material name using the schema:\n"
        "MAT_{MaterialType}_{MaterialFinish}_{Version}\n\n"
        "Deliberate internally (do not reveal chain-of-thought). Return only JSON with a short 'notes'.\n\n"
        "Hard rules:\n"
        f"- MaterialType must be one of [{allowed}].\n"
        "- Version token is V01..V99 at the end. Ensure uniqueness by bumping V## only (never add '_1' or '.001').\n"
        "- MaterialFinish must be CamelCase alphanumeric; if none fits, use Generic.\n"
        "- If read_only=true -> do not propose a rename (leave proposed_name empty).\n\n"
        "Scoring & Indexation (NEW):\n"
        "- confidence: A number 0.0–1.0 indicating your certainty in the proposal.\n"
        "  * > 0.8: High confidence (proposes even if slight deviation from known taxonomy)\n"
        "  * 0.5–0.8: Medium confidence (recommends review)\n"
        "  * < 0.5: Low confidence (prefer falling back to taxonomy base)\n"
        "- is_indexed: boolean. True if MaterialType and MaterialFinish match the allowed taxonomy exactly.\n"
        "  If your proposal uses experimental types (e.g., 'Tissue' for eyeball, 'Organic' for hair),\n"
        "  mark is_indexed=false ONLY if these are not in the allowed list, with reconciliation_note explaining.\n"
        "- reconciliation_note: Short explanation (1–2 sentences) of why you chose this type/finish,\n"
        "  especially if is_indexed=false (e.g., 'Eyeball is specialized tissue; recommend Tissue type').\n\n"
        "Deliberative rubric (internal):\n"
        "1) Understand: Does the current name precisely describe the real-world material? Identify domain: architectural (Concrete/Brick/Tile/Marble/Granite/Slate/Herringbone/Hex), product/industrial (ABS/PC/Steel/Aluminum/Anodized/Brushed/Galvanized), natural (Wood/Leather/Paper/Cardboard/Stone), textiles (Velvet/Denim/Knitting/Embroidery), coatings/paint (Paint/Varnish/Polished/Rough/Matte/Gloss), liquids (Water/Oil), optics (Glass/Frosted/Tint), decals/signage (Decal/Sticker/Label), FX/emissive (Emissive/Neon), and organic/anatomical (Skin/Iris/Sclera/Cornea/Pupil/Hair/Beard/Eyelash/Eyebrow/Nail/Tooth/Gum/Tongue).\n"
        "2) **CONTEXT ANALYSIS**: If scene_context is provided, analyze it FIRST to understand the overall material domain. Look for keywords that indicate the primary material types in the scene (e.g., 'toalla' suggests textiles, 'piel' suggests organic materials). Use this context to guide material type selection, especially for ambiguous names like 'Crease' or 'Stitch'.\n"
        "3) **BACKGROUND MATERIALS**: If object/collection names or material name contain background cues (bg, background, sky, skybox, skydome, environment, backdrop, backplate), set MaterialType='Background'. Derive MaterialFinish from the dominant color: inspect Background/Principled/Emission nodes or color ramps; use descriptive CamelCase color names (e.g., Blue, LightBlue, DarkGray).\n"
        "4) Decide: If the name is expressive and compliant, do not rename. Otherwise, transform to the schema preserving as much descriptive semantics as possible in Finish (e.g., for 'HairMatAniso' → 'MAT_Organic_Hair_V01' with 'Aniso' as sub-element if needed; for 'Eyeball' → 'MAT_Tissue_Eyeball_V01'). Select the closest MaterialType from the allowed list, but prioritize preserving key terms in Finish for clarity and replicability (e.g., Hair, Eyeball, Skin, Tooth).\n"
        "5) Validate: Ensure the final name strictly matches the schema and does not conflict with existing names; only bump V## for uniqueness.\n\n"
        "Signals (use in order):\n"
        "- **PRIORITY 1**: Scene context analysis - if scene_context contains material domain keywords, use them to guide type selection\n"
        "- **PRIORITY 2**: Use 'material_type_hint' and 'finish_candidates' from context. Respect policy flags (versioning_only, preserve_semantics, force_reanalysis).\n"
        "- **PRIORITY 3**: Background detection - if payload marks is_background=true or hints include background keywords, force MaterialType='Background' and use color-derived finish (see rubric step 3).\n"
        "- **PRIORITY 4**: Principled heuristics: metallic>=0.5→Metal; transmission>=0.3→Glass/Liquid (favor Glass for solids, Liquid for fluids); emission_strength>0→Emissive (unless Background applies); roughness>=0.6 & metallic<0.5→Rubber; else Plastic.\n"
        "- **PRIORITY 5**: Tokens by domain (non-exhaustive): Architecture (Concrete/Brick/Tile/Marble/Granite/Slate/Herringbone/Hex), Product (ABS/PC/Steel/Aluminum/Anodized/Brushed/Galvanized), Natural (Wood/Leather/Paper/Cardboard/Stone), Textiles (Denim/Velvet/Knitting/Embroidery), Coatings (Paint/Varnish/Polished/Rough/Matte/Gloss), Liquids (Water/Oil), Optics (Glass/Frosted/Tint), Decals (Decal/Sticker/Label), FX (Emissive/Neon), Organics (Skin/Iris/Tooth/Hair/etc.).\n"
        "- Prefer specific tokens over generic ones (e.g., Herringbone over Tiles; ToothEnamel over Tooth).\n"
        "- **FORCE REANALYSIS**: If force_reanalysis=True, reconsider ALL materials including those already correctly named. For materials with current_name_quality=high, carefully evaluate if the current name is already excellent and should be preserved. Only suggest changes if there's a significantly better alternative based on material properties, scene context, or naming consistency.\n\n"
        "Scene Context (if provided):\n"
        "- Additional context may be provided about the scene environment (e.g., 'kitchen interior with quartz and brushed metal').\n"
        "- **CRITICAL**: Use this context to make intelligent material type inferences, especially for ambiguous material names.\n"
        "- **Context Mapping Rules**:\n"
        "  * 'toalla', 'tela', 'textil', 'ropa' → Fabric type with appropriate finish\n"
        "  * 'piel', 'diente', 'ojo', 'cabello' → Organic/Tissue type with anatomical finish\n"
        "  * 'plástico', 'silicona', 'goma' → Plastic/Rubber type with appropriate finish\n"
        "  * 'cielo', 'sky', 'bg', 'environment', 'skybox' → Background type with color-derived finish\n"
        "  * 'metal', 'acero', 'aluminio' → Metal type with finish (Brushed, Polished, etc.)\n"
        "  * 'madera', 'piedra', 'mármol' → Wood/Stone type with appropriate finish\n"
        "- **Priority**: Context clues should override generic heuristics when material names are ambiguous.\n"
        "- **Examples**: 'Crease' in context of 'toalla' → MAT_Fabric_Crease_V01, not MAT_Emissive_Crease_V01\n"
        "- E.g., if context says 'quartz kitchen', lean toward Stone types and finishes like Polished/Rough.\n\n"
        "Output: STRICT JSON per provided schema (no extra fields).\n"
        "Notes examples: 'Preserved semantics: Hair', 'From tokens: Eyeball', 'Heuristic: Glass', 'Bumped V03'.\n"
        "Confidence examples: 'High (0.9): standard Plastic', 'Med (0.65): Eyeball debatable', 'Low (0.4): ambiguous material'.\n"
        "Examples for organic: 'HairMatAniso' → 'MAT_Organic_Hair_V01' (preserve 'Hair' in Finish, confidence 0.8); 'Eyeball' → 'MAT_Tissue_Eyeball_V01' (use 'Eyeball' as Finish, confidence 0.85).\n\n"
        "**CONTEXT-DRIVEN EXAMPLES**:\n"
        "- Scene context: 'toalla de baño' + material 'Crease' → 'MAT_Fabric_Crease_V01' (confidence 0.9)\n"
        "- Scene context: 'piel humana' + material 'Stitch' → 'MAT_Organic_Stitch_V01' (confidence 0.8)\n"
        "- Scene context: 'objeto de plástico' + material 'Crease' → 'MAT_Plastic_Crease_V01' (confidence 0.7)\n"
        "- Scene context: 'materiales de humano' + material 'Crease' → 'MAT_Organic_Crease_V01' (confidence 0.8)"
    )


def _schema_single() -> Dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ai_material_namer_single",
            "strict": True,
            "schema": {
                "type": "object",
                "required": ["item"],
                "additionalProperties": False,
                "properties": {
                    "item": {
                        "type": "object",
                        "required": ["material_name", "read_only"],
                        "additionalProperties": False,
                        "properties": {
                            "material_name": {"type": "string"},
                            "proposed_name": {"type": "string"},
                            "material_type": {"type": "string"},
                            "finish": {"type": "string"},
                            "version_token": {"type": "string"},
                            "read_only": {"type": "boolean"},
                            "notes": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "is_indexed": {"type": "boolean"},
                            "reconciliation_note": {"type": "string"},
                        },
                    }
                },
            },
        },
    }


def _schema_bulk() -> Dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ai_material_namer_bulk",
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
                            "required": ["material_name", "read_only"],
                            "additionalProperties": False,
                            "properties": {
                                "material_name": {"type": "string"},
                                "proposed_name": {"type": "string"},
                                "material_type": {"type": "string"},
                                "finish": {"type": "string"},
                                "version_token": {"type": "string"},
                                "read_only": {"type": "boolean"},
                                "similar_group_id": {"type": "string"},
                                "notes": {"type": "string"},
                                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                                "is_indexed": {"type": "boolean"},
                                "reconciliation_note": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    }


def _schema_json_object() -> Dict[str, object]:
    # Fallback for providers that don't support json_schema structured outputs
    return {"type": "json_object"}


def _extract_message_content(result: Dict[str, object]) -> Optional[str]:
    try:
        choices = result.get("choices") or []
        if not choices:
            return None
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text") or part.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts) if parts else None
        return None
    except Exception:
        return None


def _parse_json_from_text(text: str) -> Optional[Dict[str, object]]:
    if not text:
        return None
    s = text.strip()
    # Strip fences if present
    if s.startswith("```"):
        # remove first line and last fence
        try:
            s = s.split("\n", 1)[1]
            if s.endswith("```"):
                s = s[: -3]
        except Exception:
            pass
    # Try direct parse
    try:
        return json.loads(s)
    except Exception:
        # Best-effort: find the first '{' and last '}'
        try:
            i = s.find('{')
            j = s.rfind('}')
            if i != -1 and j != -1 and j > i:
                return json.loads(s[i:j+1])
        except Exception:
            return None
    return None


class LIME_TB_OT_ai_test_connection(Operator):
    bl_idname = "lime_tb.ai_test_connection"
    bl_label = "AI: Test Connection"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs: LimePipelinePrefs = bpy.context.preferences.addons[__package__.split('.')[0]].preferences  # type: ignore
        if not prefs.openrouter_api_key:
            self.report({'ERROR'}, "OpenRouter API key not set in Preferences")
            return {'CANCELLED'}
        headers = _openrouter_headers(prefs)
        data = _http_get_json(OPENROUTER_MODELS_URL, headers=headers, timeout=15)
        if not data or not isinstance(data, dict):
            self.report({'ERROR'}, "OpenRouter: request failed")
            return {'CANCELLED'}
        models = [m.get('id') for m in data.get('data', []) if isinstance(m, dict)] if 'data' in data else []
        slug = prefs.openrouter_model or "google/gemini-2.5-flash-lite-preview-09-2025"
        if slug in models:
            self.report({'INFO'}, f"OpenRouter OK. Model available: {slug}")
            # Minimal chat echo test (json_object) to validate POST path
            payload = {
                "model": slug,
                "messages": [
                    {"role": "system", "content": "You are a test endpoint validator."},
                    {"role": "user", "content": json.dumps({"ping": True})},
                ],
                "temperature": 0,
                "response_format": _schema_json_object(),
            }
            r = _http_post_json(OPENROUTER_CHAT_URL, payload, headers=headers, timeout=20)
            ok = bool(_extract_message_content(r or {}))
            self.report({'INFO'}, f"Chat endpoint: {'OK' if ok else 'UNKNOWN'}")
            return {'FINISHED'}
        # If listing succeeded but slug not found, still confirm connectivity
        self.report({'WARNING'}, f"OpenRouter reachable. Model not found in provider list: {slug}")
        return {'FINISHED'}


class LIME_TB_OT_ai_rename_single(Operator):
    bl_idname = "lime_tb.ai_rename_single"
    bl_label = "AI: Propose Single"
    bl_options = {'REGISTER', 'UNDO'}

    material_name: bpy.props.StringProperty(name="Material", default="")

    def execute(self, context):
        scene = _get_active_scene(context)
        mat: Optional[Material] = bpy.data.materials.get(self.material_name) if self.material_name else context.object.active_material if getattr(context, 'object', None) else None
        if not mat:
            self.report({'ERROR'}, "No material selected or found")
            return {'CANCELLED'}

        if _is_read_only(mat):
            _write_rows(scene, [{
                "material_name": mat.name,
                "read_only": True,
                "notes": "Linked/Override"
            }])
            return {'FINISHED'}

        # Try OpenRouter first
        prefs: LimePipelinePrefs = bpy.context.preferences.addons[__package__.split('.')[0]].preferences  # type: ignore
        summary = _summarize_nodes(mat)

        # Determine versioning policy based on material name validity
        base_name = strip_numeric_suffix(mat.name)
        parsed = parse_name(base_name)
        is_currently_valid = parsed is not None
        versioning_only = is_currently_valid  # If already valid, only bump version; if invalid, allow full reclasification

        # Get taxonomy context
        taxonomy_context = get_taxonomy_context(
            mat.name,
            summary.get("texture_basenames", []),
            summary.get("object_hints", []),
            summary.get("collection_hints", []),
            summary.get("principled", {})
        )
        quality_result = evaluate_material_name(
            mat.name,
            texture_basenames=summary.get("texture_basenames", []),
            object_hints=summary.get("object_hints", []),
            collection_hints=summary.get("collection_hints", []),
            principled=summary.get("principled", {}),
            taxonomy_context=taxonomy_context,
        )
        quality_label = quality_result.label
        quality_score = quality_result.score
        quality_issues = "; ".join(quality_result.issues)

        # Read scene context and policies for injection
        scene_context = getattr(scene.lime_ai_mat, "scene_context", "") or ""
        allow_non_indexed = getattr(scene.lime_ai_mat, "allow_non_indexed", False)

        user_message_dict = {
            "active_scene": scene.name,
            "policy": {
                "versioning_only": versioning_only,
                "preserve_semantics": True,
                "organic_material_types": ["Organic", "Tissue", "Tooth"],
                "allow_non_indexed": allow_non_indexed,
            },
            "existing_names": _collect_existing_names(),
            "current_quality": {
                "label": quality_label,
                "score": quality_score,
                "issues": quality_result.issues,
                "taxonomy_match": quality_result.taxonomy_match,
            },
            "taxonomy_context": taxonomy_context,
            "material": {
                "material_name": mat.name,
                "linked": bool(mat.library),
                "overridden": bool(mat.override_library),
                "used_in_scenes": [scene.name],
                "current_tag_guess": None,
                "has_numeric_suffix": bool(strip_numeric_suffix(mat.name) != mat.name),
                "nodes_summary": {k: v for k, v in summary.items() if k in ("ids", "counts")},
                "principled": summary.get("principled"),
                "pbr_detected": {},
                "texture_basenames": summary.get("texture_basenames", []),
                "object_hints": summary.get("object_hints", []),
                "collection_hints": summary.get("collection_hints", []),
                "similar_group_id": _fingerprint_material(mat),
                "material_type_hint": taxonomy_context.get("material_type_hint"),
                "finish_candidates": taxonomy_context.get("finish_candidates"),
                "allowed_material_types": taxonomy_context.get("allowed_material_types"),
            },
        }
        
        # Inject scene context if provided
        if scene_context:
            user_message_dict["_scene_context"] = _truncate_context(scene_context, max_chars=500)

        payload = {
            "model": prefs.openrouter_model or "google/gemini-2.5-flash-lite-preview-09-2025",
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": json.dumps(user_message_dict)},
            ],
            "temperature": 0,
            "response_format": _schema_single(),
        }
        result = None
        used_ai = False
        if (getattr(prefs, 'openrouter_api_key', '') or '').strip():
            result = _http_post_json(OPENROUTER_CHAT_URL, payload, headers=_openrouter_headers(prefs), timeout=60)

        item = None
        try:
            if result and isinstance(result, dict):
                choices = result.get("choices") or []
                if choices:
                    content = choices[0].get("message", {}).get("content")
                    parsed_content = json.loads(content) if isinstance(content, str) else content
                    if isinstance(parsed_content, dict):
                        item = parsed_content.get("item")
                        used_ai = item is not None
        except Exception:
            item = None

        # Fallback attempt: request json_object and parse message text
        if not item and (getattr(prefs, 'openrouter_api_key', '') or '').strip():
            payload_fallback = dict(payload)
            payload_fallback["response_format"] = _schema_json_object()
            result2 = _http_post_json(OPENROUTER_CHAT_URL, payload_fallback, headers=_openrouter_headers(prefs), timeout=60)
            text = _extract_message_content(result2 or {}) if result2 else None
            parsed_text = _parse_json_from_text(text or "") if text else None
            if isinstance(parsed_text, dict):
                item = parsed_text.get("item")
                used_ai = item is not None

        if not item:
            # Fallback local baseline
            summary = _summarize_nodes(mat)
            is_background = bool(summary.get("is_background", False))
            background_color = summary.get("background_color")
            background_finish = normalize_finish(background_color) if background_color else "Generic"

            base_name = strip_numeric_suffix(mat.name)
            parsed = parse_name(base_name)
            material_type = normalize_material_type(parsed["material_type"] if parsed else "Plastic")
            finish = normalize_finish(parsed["finish"] if parsed else "Generic")

            if is_background:
                target_finish = background_finish
                target_type = "Background"
            else:
                target_type = material_type
                target_finish = finish

            background_requires_rename = False
            if is_background:
                current_is_background = parsed and parsed["material_type"] == "Background"
                current_finish_norm = normalize_finish(parsed["finish"]) if parsed else ""
                if (not current_is_background) or (current_finish_norm != background_finish):
                    background_requires_rename = True

            material_type = target_type
            finish = target_finish

            # Check if we're in force reanalysis mode
            force_reanalysis = getattr(scene.lime_ai_mat, 'force_reanalysis', False)

            # If name is already valid, handle based on force_reanalysis mode
            if parsed is not None and not background_requires_rename:
                if force_reanalysis:
                    # In force reanalysis mode, keep current name as proposal for review
                    # Only suggest improvements if the current name could be enhanced
                    current_name = mat.name
                    base_name = strip_numeric_suffix(current_name)

                    # For materials that are already well-named, keep current name
                    # The IA should have evaluated this, but as fallback, preserve good names
                    item = {
                        "material_name": current_name,
                        "proposed_name": current_name,  # Keep current excellent name
                        "material_type": material_type,
                        "finish": finish,
                        "version_token": parsed.get("version") or "V01",
                        "read_only": False,
                        "notes": "Well-named material - preserved",
                        "similar_group_id": _fingerprint_material(mat),
                        "needs_rename": False,
                        "confidence": 0.95,  # Very high confidence for already good names
                        "is_indexed": True,
                        "quality_label": quality_label,
                        "quality_score": quality_score,
                        "quality_issues": quality_issues,
                        "taxonomy_match": quality_result.taxonomy_match,
                        "review_requested": quality_label == "fair",
                    }
                else:
                    # Normal mode: do not propose a rename
                    item = {
                        "material_name": mat.name,
                        "proposed_name": "",
                        "material_type": material_type,
                        "finish": finish,
                        "version_token": parsed.get("version") or "V01",
                        "read_only": False,
                        "notes": "Already compliant",
                        "similar_group_id": _fingerprint_material(mat),
                        "needs_rename": False,
                        "selected_for_apply": False,
                        "quality_label": quality_label,
                        "quality_score": quality_score,
                        "quality_issues": quality_issues,
                        "taxonomy_match": quality_result.taxonomy_match,
                        "review_requested": quality_label == "fair",
                        "is_background": is_background,
                        "background_color": background_color,
                    }
            else:
                universe = _collect_existing_names()
                # Try to preserve current version if valid, otherwise start from 1
                parsed_current = parse_name(strip_numeric_suffix(mat.name))
                current_version_idx = parsed_current.get("version_index") if parsed_current else None
                start_idx = max(1, current_version_idx) if current_version_idx else 1
                if is_background:
                    proposed = _build_background_material_name(mat, background_color or "Generic", universe, start_idx=start_idx)
                    notes = "Background material - local proposal"
                    finish = background_finish
                    material_type = "Background"
                else:
                    proposed = bump_version_until_unique(universe, material_type, finish, start_idx=start_idx)
                    notes = "Local baseline proposal"
                parts = proposed.split("_")
                version_block = parts[-1] if len(parts) > 2 else "V01"
                item = {
                    "material_name": mat.name,
                    "proposed_name": proposed,
                    "material_type": material_type,
                    "finish": finish,
                    "version_token": version_block,
                    "read_only": False,
                    "notes": notes,
                    "similar_group_id": _fingerprint_material(mat),
                    "needs_rename": True,
                    "selected_for_apply": True,
                    "quality_label": quality_label,
                    "quality_score": quality_score,
                    "quality_issues": quality_issues,
                    "taxonomy_match": quality_result.taxonomy_match,
                    "is_background": is_background,
                    "background_color": background_color,
                }

        # Apply reconciliation logic to the item
        if item:
            if "confidence" not in item:
                item["confidence"] = 0.7  # default from AI
            
            reconciliation_result = reconcile_proposal(
                proposed_name=item.get("proposed_name", ""),
                proposed_type=item.get("material_type", "Plastic"),
                proposed_finish=item.get("finish", "Generic"),
                confidence_from_ai=float(item.get("confidence", 0.7)),
                allow_non_indexed=allow_non_indexed,
                taxonomy_context={
                    "allowed_material_types": taxonomy_context.get("allowed_material_types", []),
                },
            )
            
            # Update item with reconciliation results
            item["is_indexed"] = reconciliation_result["is_indexed"]
            item["taxonomy_match"] = f"{reconciliation_result['taxonomy_type']}/{reconciliation_result['taxonomy_finish']}"
            item["reconciliation_note"] = reconciliation_result["reason"]
            
            if reconciliation_result["action"] == "normalize" and reconciliation_result["suggested_normalized"]:
                item["proposed_name"] = reconciliation_result["suggested_normalized"]
            if "quality_label" not in item or not item.get("quality_label"):
                item["quality_label"] = quality_label
            if "quality_score" not in item:
                item["quality_score"] = quality_score
            if "quality_issues" not in item:
                item["quality_issues"] = quality_issues
            if "taxonomy_match" not in item or not item.get("taxonomy_match"):
                item["taxonomy_match"] = quality_result.taxonomy_match
            if "review_requested" not in item:
                item["review_requested"] = quality_label == "fair"

        _write_rows(scene, [item])
        note = item.get("notes") or ("AI" if used_ai else "Local")
        self.report({'INFO'}, f"Single proposal ready ({note})")
        return {'FINISHED'}


class LIME_TB_OT_ai_scan_materials(Operator):
    bl_idname = "lime_tb.ai_scan_materials"
    bl_label = "AI: Scan Materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = _get_active_scene(context)
        prefs: LimePipelinePrefs = bpy.context.preferences.addons[__package__.split('.')[0]].preferences  # type: ignore
        existing_names = _collect_existing_names()
        universe = existing_names[:]
        mats = list(sorted(bpy.data.materials, key=lambda m: m.name.lower()))
        allowed_material_types: List[str] = []

        # Detección local previa: marcar needs_rename y contar
        incorrect_count = 0
        total_count = len(mats)
        payload_materials = []
        print(f"[AI Scan] Total materials found: {total_count}")
        print(f"[AI Scan] Materials list: {[m.name for m in mats]}")

        for mat in mats:
            ro = _is_read_only(mat)
            issues = detect_issues(mat.name)
            summary = _summarize_nodes(mat)
            taxonomy_context = get_taxonomy_context(
                mat.name,
                summary.get("texture_basenames", []),
                summary.get("object_hints", []),
                summary.get("collection_hints", []),
                summary.get("principled", {})
            )
            quality_result = evaluate_material_name(
                mat.name,
                texture_basenames=summary.get("texture_basenames", []),
                object_hints=summary.get("object_hints", []),
                collection_hints=summary.get("collection_hints", []),
                principled=summary.get("principled", {}),
                taxonomy_context=taxonomy_context,
            )
            quality_label = quality_result.label
            quality_score = quality_result.score
            quality_issues = "; ".join(quality_result.issues)

            is_background = bool(summary.get("is_background", False))
            background_color = summary.get("background_color")
            background_finish = normalize_finish(background_color) if background_color else "Generic"

            needs_rename = bool(issues) or quality_label in ("poor", "invalid")
            needs_review = not needs_rename and quality_label == "fair"
            background_requires_rename = False

            if is_background:
                parsed_current = parse_name(strip_numeric_suffix(mat.name))
                current_is_background = parsed_current and parsed_current["material_type"] == "Background"
                current_finish_norm = normalize_finish(parsed_current["finish"]) if parsed_current else ""
                if (not current_is_background) or (current_finish_norm != background_finish):
                    background_requires_rename = True
                    needs_rename = True
                    needs_review = False

            if needs_rename:
                incorrect_count += 1
                if background_requires_rename:
                    print(
                        f"[AI Scan] Material '{mat.name}' marked for background rename (target finish: {background_finish})"
                    )
                else:
                    print(
                        f"[AI Scan] Material '{mat.name}' marked for rename (issues: {issues}, quality={quality_label})"
                    )
            elif needs_review:
                print(f"[AI Scan] Material '{mat.name}' flagged for review (quality={quality_label})")
            else:
                print(f"[AI Scan] Material '{mat.name}' preserved (quality={quality_label})")

            if not allowed_material_types:
                allowed_material_types = list(taxonomy_context.get("allowed_material_types") or [])
            payload_materials.append({
                "material_name": mat.name,
                "linked": bool(mat.library),
                "overridden": bool(mat.override_library),
                "used_in_scenes": [scene.name],
                "current_tag_guess": None,
                "has_numeric_suffix": bool(strip_numeric_suffix(mat.name) != mat.name),
                "nodes_summary": {k: v for k, v in summary.items() if k in ("ids", "counts")},
                "principled": summary.get("principled"),
                "pbr_detected": {},
                "texture_basenames": summary.get("texture_basenames", []),
                "object_hints": summary.get("object_hints", []),
                "collection_hints": summary.get("collection_hints", []),
                "similar_group_id": _fingerprint_material(mat),
                "material_type_hint": taxonomy_context.get("material_type_hint"),
                "finish_candidates": taxonomy_context.get("finish_candidates"),
                "allowed_material_types": taxonomy_context.get("allowed_material_types"),
                "taxonomy_context": taxonomy_context,
                "needs_rename": needs_rename,
                "needs_review": needs_review,
                "quality_label": quality_label,
                "quality_score": quality_score,
                "quality_issues": quality_issues,
                "taxonomy_match": quality_result.taxonomy_match,
                "read_only": ro,
                "is_background": is_background,
                "background_color": background_color,
                "background_finish": background_finish,
                "background_requires_rename": background_requires_rename,
            })
        print(f"[AI Scan] Incorrect count: {incorrect_count}, Total: {total_count}")

        # Read scene context and policies for injection
        scene_context = getattr(scene.lime_ai_mat, "scene_context", "") or ""
        allow_non_indexed = getattr(scene.lime_ai_mat, "allow_non_indexed", False)
        force_reanalysis = getattr(scene.lime_ai_mat, "force_reanalysis", False)

        # If force_reanalysis is True, include correctly named materials for re-analysis
        if force_reanalysis:
            # Include all materials for re-analysis
            payload_materials_filtered = payload_materials.copy()
            print(f"[AI Scan] Force reanalysis enabled: including {len(payload_materials)} total materials")
            # In force reanalysis mode, count all materials as "need attention"
            incorrect_count_for_report = total_count

            # Add force_reanalysis flag to each material for better AI guidance
            for mat_data in payload_materials_filtered:
                mat_data["force_reanalysis"] = True
                mat_data["current_name_quality"] = "high" if not mat_data["needs_rename"] else "low"
        else:
            # Payload selectivo: solo materiales needs_rename=True
            payload_materials_filtered = [mat for mat in payload_materials if mat["needs_rename"]]
            print(f"[AI Scan] Normal mode: filtering to {len(payload_materials_filtered)} materials needing rename")
            incorrect_count_for_report = incorrect_count

        user_message_dict = {
            "active_scene": scene.name,
            "policy": {
                "align_material_type_hint": True,
                "respect_read_only": True,
                "versioning_only": False,
                "preserve_semantics": True,
                "organic_material_types": ["Organic", "Tissue", "Tooth"],
                "allow_non_indexed": allow_non_indexed,
                "force_reanalysis": force_reanalysis,
            },
            "existing_names": existing_names,
            "allowed_material_types": allowed_material_types,
            "materials": payload_materials_filtered,
        }
        
        # Inject scene context if provided
        if scene_context:
            user_message_dict["_scene_context"] = _truncate_context(scene_context, max_chars=500)

        payload = {
            "model": prefs.openrouter_model or "google/gemini-2.5-flash-lite-preview-09-2025",
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": json.dumps(user_message_dict)},
            ],
            "temperature": 0,
            "response_format": _schema_bulk(),
        }

        result = None
        used_ai = False
        if (getattr(prefs, 'openrouter_api_key', '') or '').strip():
            result = _http_post_json(OPENROUTER_CHAT_URL, payload, headers=_openrouter_headers(prefs), timeout=120)

        items: List[Dict[str, object]] = []
        try:
            if result and isinstance(result, dict):
                choices = result.get("choices") or []
                if choices:
                    content = choices[0].get("message", {}).get("content")
                    parsed_content = json.loads(content) if isinstance(content, str) else content
                    if isinstance(parsed_content, dict):
                        items = list(parsed_content.get("items") or [])
                        used_ai = len(items) > 0
                        # Mapear respuestas de AI a materiales correspondientes (solo incorrectos)
                        for i, item in enumerate(items):
                            if i < len(payload_materials_filtered):
                                mat_data = payload_materials_filtered[i]
                                item["needs_rename"] = mat_data["needs_rename"]
                                item["needs_review"] = mat_data.get("needs_review", False)
                                item["review_requested"] = mat_data.get("needs_review", False)
                                item["quality_label"] = mat_data.get("quality_label")
                                item["quality_score"] = mat_data.get("quality_score")
                                item["quality_issues"] = mat_data.get("quality_issues")
                                item["is_background"] = mat_data.get("is_background", False)
                                item["background_color"] = mat_data.get("background_color")
                                item["background_finish"] = mat_data.get("background_finish")
                                if "taxonomy_match" not in item or not item.get("taxonomy_match"):
                                    item["taxonomy_match"] = mat_data.get("taxonomy_match")
                                if _is_read_only(bpy.data.materials.get(mat_data["material_name"])):
                                    item["read_only"] = True
                                    item["notes"] = (item.get("notes") or "") + " | Linked/Override"
                        
                        # Apply reconciliation logic to each item
                        for item in items:
                            if "confidence" not in item:
                                item["confidence"] = 0.7  # default from AI
                            
                            reconciliation_result = reconcile_proposal(
                                proposed_name=item.get("proposed_name", ""),
                                proposed_type=item.get("material_type", "Plastic"),
                                proposed_finish=item.get("finish", "Generic"),
                                confidence_from_ai=float(item.get("confidence", 0.7)),
                                allow_non_indexed=allow_non_indexed,
                                taxonomy_context={
                                    "allowed_material_types": allowed_material_types,
                                },
                            )
                            
                            # Update item with reconciliation results
                            item["is_indexed"] = reconciliation_result["is_indexed"]
                            item["taxonomy_match"] = f"{reconciliation_result['taxonomy_type']}/{reconciliation_result['taxonomy_finish']}"
                            item["reconciliation_note"] = reconciliation_result["reason"]
                            
                            if reconciliation_result["action"] == "normalize" and reconciliation_result["suggested_normalized"]:
                                item["proposed_name"] = reconciliation_result["suggested_normalized"]
        except Exception:
            items = []

        # Fallback attempt: json_object + parse text
        if not items and (getattr(prefs, 'openrouter_api_key', '') or '').strip():
            payload_fallback = dict(payload)
            payload_fallback["response_format"] = _schema_json_object()
            result2 = _http_post_json(OPENROUTER_CHAT_URL, payload_fallback, headers=_openrouter_headers(prefs), timeout=120)
            text = _extract_message_content(result2 or {}) if result2 else None
            parsed_text = _parse_json_from_text(text or "") if text else None
            if isinstance(parsed_text, dict):
                items = list(parsed_text.get("items") or [])
                used_ai = len(items) > 0
                for idx, mat in enumerate(mats):
                    if idx < len(items) and _is_read_only(mat):
                        items[idx]["read_only"] = True
                        items[idx]["notes"] = (items[idx].get("notes") or "") + " | Linked/Override"

        if not items:
            # Fallback local baseline: incluir todos los materiales
            universe = existing_names[:]
            for mat_data in payload_materials:
                mat_name = mat_data["material_name"]
                mat = bpy.data.materials.get(mat_name)
                if _is_read_only(mat):
                    items.append({
                        "material_name": mat_name,
                        "read_only": True,
                        "notes": "Linked/Override",
                        "needs_rename": mat_data["needs_rename"],
                        "quality_label": mat_data.get("quality_label"),
                        "quality_score": mat_data.get("quality_score"),
                        "quality_issues": mat_data.get("quality_issues"),
                        "taxonomy_match": mat_data.get("taxonomy_match"),
                        "review_requested": mat_data.get("needs_review", False),
                        "is_background": mat_data.get("is_background", False),
                        "background_color": mat_data.get("background_color"),
                    })
                    continue
                parsed = parse_name(strip_numeric_suffix(mat_name))
                review_requested = mat_data.get("needs_review", False)
                quality_label = mat_data.get("quality_label") or ""
                quality_score = float(mat_data.get("quality_score") or 0.0)
                quality_issues = mat_data.get("quality_issues") or ""
                taxonomy_match = mat_data.get("taxonomy_match") or ""
                is_background = bool(mat_data.get("is_background", False))
                background_color = mat_data.get("background_color")
                background_finish = mat_data.get("background_finish") or (
                    normalize_finish(background_color) if background_color else "Generic"
                )

                if mat_data["needs_rename"]:
                    if is_background:
                        material_type = "Background"
                        finish = normalize_finish(background_finish)
                        current_version_idx = parsed.get("version_index") if parsed else None
                        start_idx = max(1, current_version_idx) if current_version_idx else 1
                        proposed = _build_background_material_name(mat, background_color or "Generic", universe, start_idx=start_idx)
                        notes = "Background material - local proposal"
                    else:
                        material_type = normalize_material_type(parsed["material_type"] if parsed else "Plastic")
                        finish = normalize_finish(parsed["finish"] if parsed else "Generic")
                        current_version_idx = parsed.get("version_index") if parsed else None
                        start_idx = max(1, current_version_idx) if current_version_idx else 1
                        proposed = bump_version_until_unique(universe, material_type, finish, start_idx=start_idx)
                        notes = "Local baseline proposal"
                    parts = proposed.split("_")
                    version_block = parts[-1] if len(parts) > 2 else "V01"
                    items.append({
                        "material_name": mat_name,
                        "proposed_name": proposed,
                        "material_type": material_type,
                        "finish": finish,
                        "version_token": version_block,
                        "read_only": False,
                        "notes": notes,
                        "similar_group_id": _fingerprint_material(mat),
                        "needs_rename": True,
                        "quality_label": quality_label,
                        "quality_score": quality_score,
                        "quality_issues": quality_issues,
                        "taxonomy_match": taxonomy_match,
                        "review_requested": review_requested,
                        "is_background": is_background,
                        "background_color": background_color,
                    })
                    if proposed not in universe:
                        universe.append(proposed)
                elif review_requested:
                    review_item = _build_review_proposal_entry(
                        mat,
                        parsed,
                        universe,
                        quality_label=quality_label,
                        quality_score=quality_score,
                        quality_issues=quality_issues,
                        taxonomy_match=taxonomy_match,
                    )
                    items.append(review_item)
                    if review_item["proposed_name"] not in universe:
                        universe.append(review_item["proposed_name"])
                else:
                    # Correct item: do not propose rename and reflect parsed version
                    # But if force_reanalysis is enabled, suggest improvements based on context
                    if force_reanalysis:
                        # Generate contextual proposal for correctly named materials
                        current_parsed = parse_name(strip_numeric_suffix(mat_name))
                        if current_parsed:
                            # Use current values but potentially suggest better finish based on context
                            material_type = current_parsed["material_type"]
                            finish = current_parsed["finish"]

                            # For now, keep current name as proposal (could be enhanced with context analysis)
                            items.append({
                                "material_name": mat_name,
                                "proposed_name": mat_name,  # Keep current name as proposal
                                "material_type": material_type,
                                "finish": finish,
                                "version_token": current_parsed.get("version") or "V01",
                                "read_only": False,
                                "notes": "Correctly named - re-analysis available",
                                "needs_rename": False,
                                "confidence": 0.8,  # High confidence for existing correct names
                                "is_indexed": True,
                                "quality_label": quality_label,
                                "quality_score": quality_score,
                                "quality_issues": quality_issues,
                                "taxonomy_match": taxonomy_match,
                                "review_requested": review_requested,
                            })
                        else:
                            # Fallback for unparseable but somehow considered correct
                            items.append({
                                "material_name": mat_name,
                                "proposed_name": "",
                                "material_type": "Plastic",
                                "finish": "Generic",
                                "version_token": "V01",
                                "read_only": False,
                                "notes": "Already compliant",
                                "needs_rename": False,
                                "quality_label": quality_label,
                                "quality_score": quality_score,
                                "quality_issues": quality_issues,
                                "taxonomy_match": taxonomy_match,
                                "review_requested": review_requested,
                            })
                    else:
                        items.append({
                            "material_name": mat_name,
                            "proposed_name": "",
                            "material_type": normalize_material_type(parsed["material_type"]) if parsed else "Plastic",
                            "finish": normalize_finish(parsed["finish"]) if parsed else "Generic",
                            "version_token": parsed.get("version") if parsed else "V01",
                            "read_only": False,
                            "notes": "Already compliant",
                            "needs_rename": False,
                            "quality_label": quality_label,
                            "quality_score": quality_score,
                            "quality_issues": quality_issues,
                            "taxonomy_match": taxonomy_match,
                            "review_requested": review_requested,
                        })

        # Asegurar que todos los materiales estén en items (correctos sin propuesta)
        if len(items) < len(payload_materials):
            mat_dict = {item["material_name"]: item for item in items}
            for mat_data in payload_materials:
                mat_name = mat_data["material_name"]
                if mat_name not in mat_dict:
                    mat = bpy.data.materials.get(mat_name)
                    if _is_read_only(mat):
                        items.append({
                            "material_name": mat_name,
                            "read_only": True,
                            "notes": "Linked/Override",
                            "needs_rename": mat_data["needs_rename"],
                            "quality_label": mat_data.get("quality_label"),
                            "quality_score": mat_data.get("quality_score"),
                            "quality_issues": mat_data.get("quality_issues"),
                            "taxonomy_match": mat_data.get("taxonomy_match"),
                            "review_requested": mat_data.get("needs_review", False),
                        })
                    else:
                        if mat_data["needs_rename"]:
                            parsed = parse_name(strip_numeric_suffix(mat_name))
                            is_background = bool(mat_data.get("is_background", False))
                            background_color = mat_data.get("background_color")
                            background_finish = mat_data.get("background_finish") or (
                                normalize_finish(background_color) if background_color else "Generic"
                            )

                            if is_background:
                                material_type = "Background"
                                finish = normalize_finish(background_finish)
                                current_version_idx = parsed.get("version_index") if parsed else None
                                start_idx = max(1, current_version_idx) if current_version_idx else 1
                                proposed = _build_background_material_name(mat, background_color or "Generic", universe, start_idx=start_idx)
                                notes = "Background material - local proposal"
                            else:
                                material_type = normalize_material_type(parsed["material_type"] if parsed else "Plastic")
                                finish = normalize_finish(parsed["finish"] if parsed else "Generic")
                                current_version_idx = parsed.get("version_index") if parsed else None
                                start_idx = max(1, current_version_idx) if current_version_idx else 1
                                proposed = bump_version_until_unique(universe, material_type, finish, start_idx=start_idx)
                                notes = "Local baseline proposal"

                            parts = proposed.split("_")
                            version_block = parts[-1] if len(parts) > 2 else "V01"
                            items.append({
                                "material_name": mat_name,
                                "proposed_name": proposed,
                                "material_type": material_type,
                                "finish": finish,
                                "version_token": version_block,
                                "read_only": False,
                                "notes": notes,
                                "similar_group_id": _fingerprint_material(mat),
                                "needs_rename": True,
                                "quality_label": mat_data.get("quality_label"),
                                "quality_score": mat_data.get("quality_score"),
                                "quality_issues": mat_data.get("quality_issues"),
                                "taxonomy_match": mat_data.get("taxonomy_match"),
                                "review_requested": mat_data.get("needs_review", False),
                                "is_background": is_background,
                                "background_color": background_color,
                            })
                            if proposed not in universe:
                                universe.append(proposed)
                        elif mat_data.get("needs_review", False):
                            review_item = _build_review_proposal_entry(
                                mat,
                                parse_name(strip_numeric_suffix(mat_name)),
                                universe,
                                quality_label=mat_data.get("quality_label") or "",
                                quality_score=float(mat_data.get("quality_score") or 0.0),
                                quality_issues=mat_data.get("quality_issues") or "",
                                taxonomy_match=mat_data.get("taxonomy_match") or "",
                            )
                            items.append(review_item)
                            if review_item["proposed_name"] not in universe:
                                universe.append(review_item["proposed_name"])
                        else:
                            # Correct item in force reanalysis mode
                            if force_reanalysis:
                                # Generate contextual proposal for correctly named materials
                                current_parsed = parse_name(strip_numeric_suffix(mat_name))
                                if current_parsed:
                                    material_type = current_parsed["material_type"]
                                    finish = current_parsed["finish"]
                                    items.append({
                                        "material_name": mat_name,
                                        "proposed_name": mat_name,  # Keep current name as proposal
                                        "material_type": material_type,
                                        "finish": finish,
                                        "version_token": current_parsed.get("version") or "V01",
                                        "read_only": False,
                                        "notes": "Correctly named - re-analysis available",
                                        "needs_rename": False,
                                        "confidence": 0.8,
                                        "is_indexed": True,
                                        "quality_label": mat_data.get("quality_label"),
                                        "quality_score": mat_data.get("quality_score"),
                                        "quality_issues": mat_data.get("quality_issues"),
                                        "taxonomy_match": mat_data.get("taxonomy_match"),
                                        "review_requested": mat_data.get("needs_review", False),
                                    })
                                else:
                                    items.append({
                                        "material_name": mat_name,
                                        "proposed_name": "",
                                        "material_type": "Plastic",
                                        "finish": "Generic",
                                        "version_token": "V01",
                                        "read_only": False,
                                        "notes": "Already compliant",
                                        "needs_rename": False,
                                        "quality_label": mat_data.get("quality_label"),
                                        "quality_score": mat_data.get("quality_score"),
                                        "quality_issues": mat_data.get("quality_issues"),
                                        "taxonomy_match": mat_data.get("taxonomy_match"),
                                        "review_requested": mat_data.get("needs_review", False),
                                    })
                            else:
                                items.append({
                                    "material_name": mat_name,
                                    "read_only": False,
                                    "notes": "Already compliant",
                                    "needs_rename": False,
                                    "quality_label": mat_data.get("quality_label"),
                                    "quality_score": mat_data.get("quality_score"),
                                    "quality_issues": mat_data.get("quality_issues"),
                                    "taxonomy_match": mat_data.get("taxonomy_match"),
                                    "review_requested": mat_data.get("needs_review", False),
                                })

        _write_rows(scene, items, incorrect_count=incorrect_count_for_report, total_count=total_count)

        print(f"[AI Scan Complete] Final items count: {len(items)}")
        print(f"[AI Scan Complete] incorrect_count: {incorrect_count}, total_count: {total_count}")
        print(f"[AI Scan Complete] used_ai: {used_ai}")

        # Verify state after writing
        state = scene.lime_ai_mat
        print(f"[AI Scan Complete] State after write: {len(state.rows)} rows")

        if force_reanalysis:
            self.report({'INFO'}, f"AI re-analysis ready: {len(items)} items ({'AI' if used_ai else 'Local'}), {incorrect_count_for_report} materiales para reconsiderar de {total_count}")
        else:
            self.report({'INFO'}, f"AI scan ready: {len(items)} items ({'AI' if used_ai else 'Local'}), {incorrect_count} incorrectos de {total_count}")
        return {'FINISHED'}


class LIME_TB_OT_ai_apply_materials(Operator):
    bl_idname = "lime_tb.ai_apply_materials"
    bl_label = "AI: Apply Proposals"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = _get_active_scene(context)
        state = scene.lime_ai_mat
        rows = list(state.rows)
        if not rows:
            self.report({'INFO'}, "No AI proposals to apply")
            return {'CANCELLED'}

        universe = set(_collect_existing_names())
        # Refresh statuses before apply to align preview with selection
        refresh_selection_preview(scene)
        rows = list(state.rows)
        
        # Apply batch normalization for experimental materials
        allow_non_indexed = getattr(scene.lime_ai_mat, "allow_non_indexed", False)
        if not allow_non_indexed:
            # Normalize experimental materials to closest taxonomy match
            normalization_results = apply_batch_normalization(
                rows,
                policy={"allow_experimental": False, "confidence_threshold": 0.5}
            )
            for row, new_name in normalization_results:
                if new_name and new_name != row.material_name:
                    row.proposed_name = new_name
                    # Update taxonomy fields
                    parts = new_name.split("_")
                    if len(parts) >= 4 and parts[0] == "MAT":
                        row.material_type = parts[1]
                        row.finish = "_".join(parts[2:-1]) if len(parts) > 3 else parts[2]
                        row.version_token = parts[-1]
                        row.is_indexed = True
                        row.taxonomy_match = f"{parts[1]}/{parts[2]}"
                        row.reconciliation_note = "Normalized to closest taxonomy match"
        
        renamed = 0

        # Check if we're in force reanalysis mode
        force_reanalysis = getattr(state, 'force_reanalysis', False)

        with _suspend_selection_refresh():
            for row in sorted(rows, key=lambda r: r.material_name.lower()):
                # Simplified logic: If checkbox is checked and not read_only, apply it
                if row.read_only or not row.selected_for_apply:
                    continue
                
                # Must have a proposed_name and it must be different from current
                if not row.proposed_name or row.proposed_name == row.material_name:
                    continue
                
                mat: Optional[Material] = bpy.data.materials.get(row.material_name)
                if not mat:
                    continue

                # Use proposed_name if available, otherwise derive from current values
                if row.proposed_name and row.proposed_name.strip():
                    target_name = row.proposed_name
                    # Try to parse for metadata, but don't reject if it doesn't follow pattern
                    parsed_target = parse_name(target_name)
                    if parsed_target:
                        material_type = parsed_target["material_type"]
                        finish = parsed_target["finish"]
                        version_token = parsed_target["version"]
                        version_idx = parsed_target.get("version_index") or parse_version(version_token) or 1
                    else:
                        # User manually edited - respect it even if format is non-standard
                        # Extract what we can for metadata, but use the name as-is
                        material_type = row.material_type or "Plastic"
                        finish = row.finish or "Generic"
                        version_token = row.version_token or "V01"
                        version_idx = parse_version(version_token) or 1
                else:
                    # No proposal, derive target from current values
                    material_type, finish, version_token, version_idx = _derive_row_target(row)
                    target_name = f"{PREFIX}_{material_type}_{finish}_{version_token}"

                # Handle name collisions
                if target_name in universe and target_name != mat.name:
                    if row.proposed_name and row.proposed_name.strip():
                        # For proposed names, try to bump version
                        bumped = bump_version_until_unique(universe, material_type, finish, start_idx=version_idx)
                        target_name = bumped
                        version_token = target_name.split('_')[-1]
                        version_idx = parse_version(version_token) or version_idx
                    else:
                        # For derived names, this shouldn't happen but handle it
                        bumped = bump_version_until_unique(universe, material_type, finish, start_idx=version_idx)
                        target_name = bumped
                        version_token = target_name.split('_')[-1]
                        version_idx = parse_version(version_token) or version_idx

                if mat.name != target_name:
                    mat.name = target_name
                    renamed += 1
                universe.add(target_name)

                row.proposed_name = ''
                row.material_type = material_type
                row.finish = finish
                row.version_token = version_token
                row.status = 'VALID'
                row.selected_for_apply = False
                row.review_requested = False

        refresh_selection_preview(scene)
        # Scene tag no longer used

        self.report({'INFO'}, f"Renamed {renamed} materials")
        return {'FINISHED'}


# Removed LIME_TB_OT_ai_toggle_show_correct as requested


# Removed LIME_TB_OT_ai_refresh_order and LIME_TB_OT_ai_toggle_unlock_correct as requested


class LIME_TB_OT_ai_test_state(Operator):
    bl_idname = "lime_tb.ai_test_state"
    bl_label = "AI: Test State"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = _get_active_scene(context)
        state = scene.lime_ai_mat

        print(f"[AI Test State] scene: {scene}")
        print(f"[AI Test State] state: {state}")
        print(f"[AI Test State] state type: {type(state)}")
        print(f"[AI Test State] hasattr state.rows: {hasattr(state, 'rows')}")
        if hasattr(state, 'rows'):
            print(f"[AI Test State] len(state.rows): {len(state.rows)}")
        print(f"[AI Test State] state.incorrect_count: {state.incorrect_count}")
        print(f"[AI Test State] state.total_count: {state.total_count}")

        # List first few rows
        for i in range(min(3, len(state.rows))):
            row = state.rows[i]
            print(f"[AI Test State] Row {i}: {row.material_name} -> {row.proposed_name}")

        self.report({'INFO'}, f"State has {len(state.rows)} rows, {state.incorrect_count}/{state.total_count} incorrect")
        return {'FINISHED'}


class LIME_TB_OT_ai_clear_materials(Operator):
    bl_idname = "lime_tb.ai_clear_materials"
    bl_label = "AI: Clear Proposals"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = _get_active_scene(context)
        state = scene.lime_ai_mat
        state.rows.clear()
        state.active_index = 0
        # scene_tag_used no longer used
        state.incorrect_count = 0
        state.total_count = 0
        self.report({'INFO'}, "AI proposals cleared")
        return {'FINISHED'}


class LIME_TB_OT_ai_select_all(Operator):
    bl_idname = "lime_tb.ai_select_all"
    bl_label = "AI: Select All"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = _get_active_scene(context)
        state = scene.lime_ai_mat
        if not state.rows:
            self.report({'INFO'}, "No AI proposals to select")
            return {'CANCELLED'}

        refresh_selection_preview(scene)
        view = getattr(state, 'view_filter', 'NEEDS')
        selected = 0
        with _suspend_selection_refresh():
            for row in state.rows:
                if not _is_row_visible(row, view):
                    continue
                if row.read_only:
                    row.selected_for_apply = False
                    continue

                row.selected_for_apply = True
                selected += 1

        refresh_selection_preview(scene)
        self.report({'INFO'}, f"Selected {selected} items")
        return {'FINISHED'}


class LIME_TB_OT_ai_select_none(Operator):
    bl_idname = "lime_tb.ai_select_none"
    bl_label = "AI: Select None"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = _get_active_scene(context)
        state = scene.lime_ai_mat
        if not state.rows:
            self.report({'INFO'}, "No AI proposals to deselect")
            return {'CANCELLED'}

        refresh_selection_preview(scene)
        view = getattr(state, 'view_filter', 'NEEDS')
        deselected = 0
        with _suspend_selection_refresh():
            for row in state.rows:
                if not _is_row_visible(row, view):
                    continue
                if row.selected_for_apply:
                    deselected += 1
                row.selected_for_apply = False

        refresh_selection_preview(scene)
        self.report({'INFO'}, f"Deselected {deselected} items")
        return {'FINISHED'}


class LIME_TB_OT_ai_normalize_to_closest(Operator):
    bl_idname = "lime_tb.ai_normalize_to_closest"
    bl_label = "AI: Normalize to Closest"
    bl_options = {'REGISTER', 'UNDO'}

    material_name: bpy.props.StringProperty(name="Material", default="")

    def execute(self, context):
        scene = _get_active_scene(context)
        state = scene.lime_ai_mat
        
        # Find the row for this material
        target_row = None
        for row in state.rows:
            if row.material_name == self.material_name:
                target_row = row
                break
        
        if not target_row:
            self.report({'ERROR'}, f"Material {self.material_name} not found in proposals")
            return {'CANCELLED'}
        
        # If not yet normalized, apply normalization
        if not target_row.is_normalized:
            # Save original proposal if not already saved
            if not target_row.original_proposal:
                target_row.original_proposal = target_row.proposed_name
            
            reconciliation_result = reconcile_proposal(
                proposed_name=target_row.original_proposal or "",
                proposed_type=target_row.material_type or "Plastic",
                proposed_finish=target_row.finish or "Generic",
                confidence_from_ai=float(getattr(target_row, "confidence", 0.7)),
                allow_non_indexed=False,  # Force normalization
                taxonomy_context={
                    "allowed_material_types": get_allowed_material_types(),
                },
            )
            
            if reconciliation_result["suggested_normalized"]:
                target_row.proposed_name = reconciliation_result["suggested_normalized"]
                target_row.material_type = reconciliation_result["taxonomy_type"]
                target_row.finish = reconciliation_result["taxonomy_finish"]
                target_row.is_indexed = True
                target_row.is_normalized = True
                target_row.taxonomy_match = f"{reconciliation_result['taxonomy_type']}/{reconciliation_result['taxonomy_finish']}"
                target_row.reconciliation_note = "Normalized to taxonomy match"
                
                self.report({'INFO'}, f"Normalized {self.material_name} to {reconciliation_result['suggested_normalized']}")
            else:
                self.report({'WARNING'}, f"Could not normalize {self.material_name}")
        else:
            self.report({'INFO'}, f"{self.material_name} is already normalized")
        
        return {'FINISHED'}


class LIME_TB_OT_ai_keep_proposal(Operator):
    bl_idname = "lime_tb.ai_keep_proposal"
    bl_label = "AI: Keep Proposal or Undo Normalize"
    bl_options = {'REGISTER', 'UNDO'}

    material_name: bpy.props.StringProperty(name="Material", default="")

    def execute(self, context):
        scene = _get_active_scene(context)
        state = scene.lime_ai_mat
        
        # Find the row for this material
        target_row = None
        for row in state.rows:
            if row.material_name == self.material_name:
                target_row = row
                break
        
        if not target_row:
            self.report({'ERROR'}, f"Material {self.material_name} not found in proposals")
            return {'CANCELLED'}
        
        # Toggle: if normalized, revert to original; if not normalized, keep as-is
        if target_row.is_normalized and target_row.original_proposal:
            # Undo normalization - revert to original AI proposal
            target_row.proposed_name = target_row.original_proposal
            target_row.is_normalized = False
            target_row.is_indexed = False
            target_row.taxonomy_match = ""
            target_row.reconciliation_note = "Kept original AI proposal (undid normalization)"
            self.report({'INFO'}, f"Reverted {self.material_name} to AI proposal")
        else:
            # Already at original proposal - just confirm we're keeping it
            target_row.reconciliation_note = "Kept as experimental proposal"
            self.report({'INFO'}, f"Keeping {self.material_name} as proposed")
        
        return {'FINISHED'}


class LIME_TB_OT_ai_toggle_review(Operator):
    bl_idname = "lime_tb.ai_toggle_review"
    bl_label = "AI: Toggle Manual Review"
    bl_options = {'REGISTER', 'UNDO'}

    material_name: bpy.props.StringProperty(name="Material", default="")

    def execute(self, context):
        scene = _get_active_scene(context)
        state = scene.lime_ai_mat

        target_row = None
        for row in state.rows:
            if row.material_name == self.material_name:
                target_row = row
                break

        if target_row is None:
            self.report({'WARNING'}, f"Material {self.material_name} not found")
            return {'CANCELLED'}

        target_row.review_requested = not target_row.review_requested
        if target_row.review_requested:
            if not target_row.read_only:
                target_row.selected_for_apply = True
        elif not target_row.needs_rename:
            target_row.selected_for_apply = False

        refresh_selection_preview(scene)
        state_msg = "queued for review" if target_row.review_requested else "review cleared"
        self.report({'INFO'}, f"{self.material_name}: {state_msg}")
        return {'FINISHED'}


class LIME_TB_OT_open_ai_material_manager(Operator):
    """Abre el AI Material Manager en una ventana flotante."""
    bl_idname = "lime_tb.open_ai_material_manager"
    bl_label = "Open AI Material Manager"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Abre el gestor completo de materiales IA en una ventana flotante"

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=1080)

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        state = getattr(scene, 'lime_ai_mat', None)

        # Header con controles principales
        header = layout.box()
        header.label(text="AI Material Manager", icon='MATERIAL')

        # Controles de contexto - más compactos
        if state:
            context_box = header.box()
            context_box.label(text="Scene Context", icon='INFO')

            # Contexto de escena - más compacto
            context_col = context_box.column(align=True)
            context_col.scale_y = 0.9
            context_col.prop(state, "scene_context", text="",
                           placeholder="Describe the scene context (e.g., kitchen, marble, brushed metal)")

            # Toggle para permitir no indexados - más compacto
            context_row = context_box.row(align=True)
            context_row.scale_y = 0.9
            context_row.prop(state, "allow_non_indexed", text="Allow flexible names", toggle=True)

            # Toggle para forzar re-análisis - más compacto
            reanalysis_row = context_box.row(align=True)
            reanalysis_row.scale_y = 0.9
            reanalysis_row.prop(state, "force_reanalysis", text="Re-scan approved names", toggle=True)

        # Botones principales - distribución profesional
        controls = layout.box()
        controls.label(text="Actions", icon='TOOL_SETTINGS')

        btn_row = controls.row(align=True)

        # Scan button - tamaño estándar
        scan_col = btn_row.column(align=True)
        scan_col.scale_x = 2.0
        scan_col.operator("lime_tb.ai_scan_materials", text="Scan Materials", icon='VIEWZOOM')

        # Count linked materials and show warning
        linked_count = 0
        if state and state.rows:
            linked_count = sum(1 for it in state.rows if getattr(it, 'read_only', False))
        
        if linked_count > 0:
            linked_box = layout.box()
            linked_box.alert = True
            linked_row = linked_box.row(align=True)
            linked_row.label(text=f"{linked_count} linked material(s) detected", icon="LIBRARY_DATA_DIRECT")
            linked_row = linked_box.row(align=True)
            linked_row.label(text="Convert to local in 'Project Organization' panel first", icon="INFO")
            linked_box.separator()

        # Contador de seleccionados
        actionable_selected = 0
        if state and state.rows:
            force_reanalysis = getattr(state, 'force_reanalysis', False)
            for it in state.rows:
                s = (getattr(it, 'status', '') or '').upper()
                read_only = getattr(it, 'read_only', False)
                selected = getattr(it, 'selected_for_apply', False)

                if not read_only and selected:
                    if force_reanalysis:
                        # In force reanalysis mode, count all selected materials
                        # But only if they have actual proposals to apply
                        if it.proposed_name and it.proposed_name != it.material_name:
                            actionable_selected += 1
                    elif (s.startswith('NEEDS_RENAME') or s.startswith('NAME_COLLISION')):
                        # In normal mode, only count actionable materials
                        actionable_selected += 1

        # Apply button - tamaño estándar
        apply_col = btn_row.column(align=True)
        apply_col.scale_x = 1.8
        apply_col.enabled = actionable_selected > 0
        apply_col.operator("lime_tb.ai_apply_materials", text="Apply Renames", icon='CHECKMARK')

        # Clear button - tamaño estándar
        clear_col = btn_row.column(align=True)
        clear_col.scale_x = 1.2
        clear_col.operator("lime_tb.ai_clear_materials", text="Clear", icon='TRASH')

        # Filtros y selección - distribución profesional
        if state:
            filter_box = layout.box()
            filter_box.label(text="Filters & Selection", icon='FILTER')

            # Filtros de vista - tamaño estándar
            filter_row = filter_box.row(align=True)
            filter_row.scale_y = 1.0
            filter_row.prop(state, "view_filter", expand=True)

            # Selección masiva - tamaño estándar
            sel_row = filter_box.row(align=True)
            sel_row.scale_y = 1.0
            sel_row.enabled = bool(state.rows)

            # Select All button - tamaño estándar
            sel_all_col = sel_row.column(align=True)
            sel_all_col.scale_x = 1.5
            sel_all_col.operator("lime_tb.ai_select_all", text="Select All", icon='CHECKBOX_HLT')

            # Select None button - tamaño estándar
            sel_none_col = sel_row.column(align=True)
            sel_none_col.scale_x = 1.5
            sel_none_col.operator("lime_tb.ai_select_none", text="Select None", icon='CHECKBOX_DEHLT')

        # Lista de materiales expandida
        if state and state.rows:
            list_box = layout.box()
            list_box.label(text=f"Materials ({len(state.rows)})", icon='MATERIAL')

            # Usar más filas para la lista
            list_box.template_list("LIME_TB_UL_ai_mat_rows", "",
                                 state, "rows", state, "active_index",
                                 rows=12)  # Más filas que el panel compacto
        else:
            layout.label(text="No materials to display", icon='INFO')

    def execute(self, context):
        # Este método no se ejecuta directamente, solo cuando se usa invoke_props_dialog
        self.report({'INFO'}, "AI Material Manager dialog opened")
        return {'FINISHED'}


__all__ = [
    "LIME_TB_OT_ai_test_connection",
    "LIME_TB_OT_ai_rename_single",
    "LIME_TB_OT_ai_scan_materials",
    "LIME_TB_OT_ai_apply_materials",
    "LIME_TB_OT_ai_test_state",
    "LIME_TB_OT_ai_clear_materials",
    "LIME_TB_OT_ai_select_all",
    "LIME_TB_OT_ai_select_none",
    "LIME_TB_OT_ai_normalize_to_closest",
    "LIME_TB_OT_ai_keep_proposal",
    "LIME_TB_OT_ai_toggle_review",
    "LIME_TB_OT_open_ai_material_manager",
]
