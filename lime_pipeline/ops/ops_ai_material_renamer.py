from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
import urllib.request
import urllib.error

import bpy
from bpy.types import Material, Operator, Scene

from ..prefs import LimePipelinePrefs
from ..props_ai_materials import LimeAIMatRow
from ..core.material_naming import (
    ALLOWED_FAMILIES,
    build_name,
    build_version,
    bump_version_until_unique,
    detect_issues,
    next_version_index,
    is_valid_name,
    normalize_family,
    normalize_finish,
    parse_name,
    strip_numeric_suffix,
)
from ..core.material_taxonomy import get_taxonomy_context


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
    principled = None
    try:
        nt = mat.node_tree
        if not nt:
            return {"ids": ids, "counts": counts, "principled": principled, "texture_basenames": [], "object_hints": [], "collection_hints": []}
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
    except Exception:
        pass
    texture_basenames = _get_texture_basenames(mat)
    object_hints, collection_hints = _get_object_and_collection_hints(mat)
    return {
        "ids": ids,
        "counts": counts,
        "principled": principled,
        "texture_basenames": texture_basenames,
        "object_hints": object_hints,
        "collection_hints": collection_hints,
    }


def _fingerprint_material(mat: Material) -> str:
    # Lightweight placeholder: could hash texture basenames + principled bins + node ids
    summary = _summarize_nodes(mat)
    ids = sorted(set(summary.get("ids", [])))
    key = f"nodes:{','.join(ids)[:64]}"
    return key


def _write_rows(scene: Scene, items: List[Dict[str, object]], incorrect_count: int = 0, total_count: int = 0) -> None:
    print(f"[AI Write Rows] Starting with {len(items)} items")
    state = scene.lime_ai_mat
    print(f"[AI Write Rows] State before clear: {len(state.rows)} rows")

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
        row.family = str(item.get("family") or "Plastic")
        row.finish = str(item.get("finish") or "Generic")
        row.version = str(item.get("version") or "V01")
        row.similar_group_id = str(item.get("similar_group_id") or "")
        row.status = str(item.get("notes") or "")
        row.read_only = bool(item.get("read_only") or False)
        # If not explicitly provided, infer from current material name validity
        _needs = item.get("needs_rename")
        row.needs_rename = bool(_needs) if _needs is not None else bool(detect_issues(row.material_name))

        if i < 3:  # Debug first 3 items
            print(f"[AI Write Rows] Added item {i}: {row.material_name} -> {row.proposed_name} (needs_rename: {row.needs_rename})")

    print(f"[AI Write Rows] Final state: {len(state.rows)} rows")
    _postprocess_statuses(scene)


def _postprocess_statuses(scene: Scene) -> None:
    """Compute status badges, sequence gaps, and actionable proposals.

    Status values:
    - VALID
    - NEEDS_RENAME
    - SEQUENCE_GAP
    - NAME_COLLISION
    - UNPARSEABLE

    Proposed name must be present only for NEEDS_RENAME or NAME_COLLISION.
    """
    try:
        state = scene.lime_ai_mat
    except Exception:
        return
    rows = list(state.rows)
    universe = set(_collect_existing_names())

    # First pass: parse current names and build grouping key (base)
    parsed_info = []
    group_to_versions: Dict[Tuple[str, str], List[int]] = {}
    for r in rows:
        parsed = parse_name(strip_numeric_suffix(r.material_name))
        if parsed is None:
            # Current name not parseable
            status = "NEEDS_RENAME" if r.needs_rename or r.proposed_name else "UNPARSEABLE"
        else:
            # Current name parseable
            status = "VALID" if not r.needs_rename else "NEEDS_RENAME"
            key = (parsed["familia"], parsed["acabado"])
            ver = int(parsed.get("version_index") or 0)
            group_to_versions.setdefault(key, []).append(ver)
        parsed_info.append((r, parsed, status))

    # Detect sequence gaps per group
    group_missing: Dict[Tuple[str, str], List[int]] = {}
    for key, versions in group_to_versions.items():
        if not versions:
            continue
        lo, hi = min(versions), max(versions)
        missing = [v for v in range(lo, hi + 1) if v not in versions]
        if missing:
            group_missing[key] = missing

    # Second pass: finalize statuses and proposals
    for r, parsed, baseline_status in parsed_info:
        status = baseline_status
        # Mark sequence gaps for VALID rows in groups with missing versions (informational)
        if parsed is not None:
            key = (parsed["familia"], parsed["acabado"])
            if status == "VALID" and key in group_missing:
                status = "SEQUENCE_GAP"
                missing_tokens = ", ".join(f"V{m:02d}" for m in group_missing[key][:6])
                r.status = f"SEQUENCE_GAP: Missing {missing_tokens}"
            else:
                r.status = status
        else:
            r.status = status

        # If proposed equals current, it's effectively non-actionable
        if r.proposed_name and r.proposed_name == r.material_name:
            r.proposed_name = ""
            if status == "NEEDS_RENAME":
                r.status = "VALID"

        # Collision check for actionable items with proposed name
        actionable = r.status in ("NEEDS_RENAME", "NAME_COLLISION") and not r.read_only and bool(r.proposed_name)
        if actionable:
            pn = r.proposed_name
            if pn in universe and pn != r.material_name:
                r.status = "NAME_COLLISION"

        # Ensure valid items do not carry proposals
        if status == "VALID":
            r.proposed_name = ""

        # Do not keep proposals for non-actionable states (VALID/SEQUENCE_GAP only)
        if r.status in ("VALID", "SEQUENCE_GAP"):
            r.proposed_name = ""


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


def _system_prompt() -> str:
    return (
        "You are a Blender materials librarian assisting an addon via OpenRouter.\n"
        "TARGET MODEL: google/gemini-2.5-flash-lite-preview-09-2025.\n\n"
        "Your ONLY job: output a final material name using the schema:\n"
        "MAT_{Family}_{Finish}_{V##}\n\n"
        "Rules (HARD):\n"
        "- Family ∈ [Plastic, Metal, Glass, Rubber, Paint, Wood, Fabric, Ceramic, Emissive, Stone, Concrete, Paper, Leather, Liquid].\n"
        "- Finish: CamelCase alphanumeric from the provided taxonomy; if none fits, use Generic.\n"
        "- Version: V01..V99. Ensure uniqueness by bumping V## only (no \"_1\", no \".001\").\n"
        "- If read_only=true → DO NOT propose a rename (proposed_name empty).\n\n"
        "Signals:\n"
        "- Use provided \"family_hint\" and \"finish_candidates\" first.\n"
        "- Principled heuristics (secondary): metallic≥0.5→Metal; transmission≥0.3 or glass tokens→Glass; emission_strength>0→Emissive; roughness≥0.6 and not metallic→Rubber; else Plastic.\n"
        "- Texture basenames and object/collection hints can refine finish (e.g., Herringbone, Hex, Brushed, Anodized, Rusty, Marble, Concrete, Velvet, Jean, Leather, PaperOld, Water).\n"
        "- Prefer specific tokens (Marble, Herringbone, Anodized) over generic ones (Tiles, Fabric).\n\n"
        "Output format: STRICT JSON schema you will receive (no extra fields).\n"
        "Short \"notes\" only (e.g., \"Heuristic: Metal\", \"From tokens: Marble\", \"Bumped V03\")."
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
                            "family": {"type": "string"},
                            "finish": {"type": "string"},
                            "version": {"type": "string"},
                            "read_only": {"type": "boolean"},
                            "notes": {"type": "string"},
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
                                "family": {"type": "string"},
                                "finish": {"type": "string"},
                                "version": {"type": "string"},
                                "read_only": {"type": "boolean"},
                                "similar_group_id": {"type": "string"},
                                "notes": {"type": "string"},
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

        payload = {
            "model": prefs.openrouter_model or "google/gemini-2.5-flash-lite-preview-09-2025",
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": json.dumps({
                    "active_scene": scene.name,
                    "policy": {"versioning_only": versioning_only},
                    "existing_names": _collect_existing_names(),
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
                    },
                })},
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
            base_name = strip_numeric_suffix(mat.name)
            parsed = parse_name(base_name)
            family = normalize_family(parsed["familia"] if parsed else "Plastic")
            finish = normalize_finish(parsed["acabado"] if parsed else "Generic")
            # If name is already valid, do not propose a rename
            if parsed is not None:
                item = {
                    "material_name": mat.name,
                    "proposed_name": "",
                    "family": family,
                    "finish": finish,
                    "version": parsed.get("version") or "V01",
                    "read_only": False,
                    "notes": "Already compliant",
                    "similar_group_id": _fingerprint_material(mat),
                    "needs_rename": False,
                }
            else:
                universe = _collect_existing_names()
                proposed = bump_version_until_unique(universe, "S1", family, finish, start_idx=1)
                version_block = proposed.split("_")[-1]
                item = {
                    "material_name": mat.name,
                    "proposed_name": proposed,
                    "family": family,
                    "finish": finish,
                    "version": version_block,
                    "read_only": False,
                    "notes": "Local baseline proposal",
                    "similar_group_id": _fingerprint_material(mat),
                    "needs_rename": True,
                }

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
        mats = list(sorted(bpy.data.materials, key=lambda m: m.name.lower()))

        # Detección local previa: marcar needs_rename y contar
        incorrect_count = 0
        total_count = len(mats)
        payload_materials = []
        print(f"[AI Scan] Total materials found: {total_count}")
        print(f"[AI Scan] Materials list: {[m.name for m in mats]}")

        for mat in mats:
            ro = _is_read_only(mat)
            issues = detect_issues(mat.name)
            needs_rename = bool(issues)
            if needs_rename:
                incorrect_count += 1
                print(f"[AI Scan] Material '{mat.name}' needs rename: {issues}")
            else:
                print(f"[AI Scan] Material '{mat.name}' is OK (issues: {issues})")
            summary = _summarize_nodes(mat)
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
                "needs_rename": needs_rename,
            })
        print(f"[AI Scan] Incorrect count: {incorrect_count}, Total: {total_count}")

        # Payload selectivo: solo materiales needs_rename=True
        payload_materials_filtered = [mat for mat in payload_materials if mat["needs_rename"]]

        payload = {
            "model": prefs.openrouter_model or "google/gemini-2.5-flash-lite-preview-09-2025",
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": json.dumps({
                    "active_scene": scene.name,
                    "policy": {"align_scene_tag": True, "respect_read_only": True, "versioning_only": True},
                    "existing_names": existing_names,
                    "materials": payload_materials_filtered,
                })},
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
                                if _is_read_only(bpy.data.materials.get(mat_data["material_name"])):
                                    item["read_only"] = True
                                    item["notes"] = (item.get("notes") or "") + " | Linked/Override"
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
                        "needs_rename": mat_data["needs_rename"]
                    })
                    continue
                parsed = parse_name(strip_numeric_suffix(mat_name))
                if mat_data["needs_rename"]:
                    family = normalize_family(parsed["familia"] if parsed else "Plastic")
                    finish = normalize_finish(parsed["acabado"] if parsed else "Generic")
                    # Build proposal without scene tag: use family/finish only
                    # For simplicity, re-use build_name with a neutral tag "S1" then strip it visually in UI
                    proposed = bump_version_until_unique(universe, "S1", family, finish, start_idx=1)
                    version_block = proposed.split("_")[-1]
                    items.append({
                        "material_name": mat_name,
                        "proposed_name": proposed,
                        "family": family,
                        "finish": finish,
                        "version": version_block,
                        "read_only": False,
                        "notes": "Local baseline proposal",
                        "similar_group_id": _fingerprint_material(mat),
                        "needs_rename": True,
                    })
                    if proposed not in universe:
                        universe.append(proposed)
                else:
                    # Correct item: do not propose rename and reflect parsed version
                    items.append({
                        "material_name": mat_name,
                        "proposed_name": "",
                        "family": normalize_family(parsed["familia"]) if parsed else "Plastic",
                        "finish": normalize_finish(parsed["acabado"]) if parsed else "Generic",
                        "version": parsed.get("version") if parsed else "V01",
                        "read_only": False,
                        "notes": "Already compliant",
                        "needs_rename": False,
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
                            "needs_rename": mat_data["needs_rename"]
                        })
                    else:
                        if mat_data["needs_rename"]:
                            # provide a conservative proposal
                            parsed = parse_name(strip_numeric_suffix(mat_name))
                            family = normalize_family(parsed["familia"] if parsed else "Plastic")
                            finish = normalize_finish(parsed["acabado"] if parsed else "Generic")
                            proposed = bump_version_until_unique(universe, "S1", family, finish, start_idx=1)
                            version_block = proposed.split("_")[-1]
                            items.append({
                                "material_name": mat_name,
                                "proposed_name": proposed,
                                "family": family,
                                "finish": finish,
                                "version": version_block,
                                "read_only": False,
                                "notes": "Local baseline proposal",
                                "similar_group_id": _fingerprint_material(mat),
                                "needs_rename": True,
                            })
                            if proposed not in universe:
                                universe.append(proposed)
                        else:
                            items.append({
                                "material_name": mat_name,
                                "read_only": False,
                                "notes": "Already compliant",
                                "needs_rename": False,
                            })

        _write_rows(scene, items, incorrect_count=incorrect_count, total_count=total_count)

        print(f"[AI Scan Complete] Final items count: {len(items)}")
        print(f"[AI Scan Complete] incorrect_count: {incorrect_count}, total_count: {total_count}")
        print(f"[AI Scan Complete] used_ai: {used_ai}")

        # Verify state after writing
        state = scene.lime_ai_mat
        print(f"[AI Scan Complete] State after write: {len(state.rows)} rows")

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
        # Refresh statuses before apply to avoid surprises
        _postprocess_statuses(scene)
        rows = list(state.rows)
        renamed = 0
        for row in sorted(rows, key=lambda r: r.material_name.lower()):
            status = (row.status or "").upper()
            # Apply only actionable items
            if not (status.startswith("NEEDS_RENAME") or status.startswith("NAME_COLLISION")):
                continue
            if row.read_only:
                continue
            mat: Optional[Material] = bpy.data.materials.get(row.material_name)
            if not mat:
                continue

            # Si el usuario editó proposed_name, usarlo como fuente de verdad
            proposed_name = row.proposed_name or mat.name
            if proposed_name != mat.name:
                # Intentar parsear el nombre propuesto
                parsed = parse_name(proposed_name)
                if parsed:
                    # Usar valores parseados
                    family = normalize_family(parsed["familia"] or "Plastic")
                    finish = normalize_finish(parsed["acabado"] or "Generic")
                    version_str = parsed["version"] or "V01"
                else:
                    # Fallback: normalizar por heurística
                    family = normalize_family("Plastic")  # Default
                    finish = normalize_finish("Generic")  # Default
                    version_str = "V01"
                    # Intentar extraer versión del final
                    parts = proposed_name.split("_")
                    if len(parts) >= 4 and parts[-1].startswith("V") and parts[-1][1:].isdigit():
                        version_str = parts[-1]
                        finish = normalize_finish("_".join(parts[2:-1]) or "Generic")

                # Calcular versión única
                try:
                    version_idx = int(version_str[1:]) if version_str.startswith('V') and version_str[1:].isdigit() else 1
                except Exception:
                    version_idx = 1

                target_name = build_name("S1", family, finish, build_version(version_idx))
                if target_name in universe and target_name != mat.name:
                    # Do not auto-bump on explicit NAME_COLLISION to avoid surprises
                    if status.startswith("NAME_COLLISION"):
                        row.status = "NAME_COLLISION"
                        continue
                    target_name = bump_version_until_unique(universe, "S1", family, finish, start_idx=version_idx)
            else:
                # Usar valores originales de la fila
                family = normalize_family(row.family or "Plastic")
                finish = normalize_finish(row.finish or "Generic")
                version_str = row.version or "V01"
                try:
                    version_idx = int(version_str[1:]) if version_str.startswith('V') and version_str[1:].isdigit() else 1
                except Exception:
                    version_idx = 1

                target_name = build_name("S1", family, finish, build_version(version_idx))
                if target_name in universe and target_name != mat.name:
                    target_name = bump_version_until_unique(universe, "S1", family, finish, start_idx=version_idx)

            if mat.name != target_name:
                mat.name = target_name
                renamed += 1
                universe.add(target_name)

            # reflect final
            row.proposed_name = ""
            row.family = family
            row.finish = finish
            row.version = mat.name.split("_")[-1]
            row.status = "VALID"

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


__all__ = [
    "LIME_TB_OT_ai_test_connection",
    "LIME_TB_OT_ai_rename_single",
    "LIME_TB_OT_ai_scan_materials",
    "LIME_TB_OT_ai_apply_materials",
    "LIME_TB_OT_ai_test_state",
    "LIME_TB_OT_ai_clear_materials",
]


