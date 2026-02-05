"""
Texture Fix/Adopt operator.

Copies external "loose" textures into the project shared folder:
<RAMV>/RSC/Textures

Rules:
- Never modify textures that are linked/library/protected roots.
- Copy (do not move) eligible files and relink Blender image paths.
- Deduplicate by file content hash (sha256) using an on-disk index.
- Write a JSON manifest: originals -> adopted paths and skipped reasons.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import base64
import tempfile
from pathlib import Path
import shutil
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import bpy
from bpy.types import Operator
from bpy.props import BoolProperty

from ..core.naming import find_project_root, normalize_project_name, parse_blend_details
from ..core.paths import get_ramv_dir
from ..core.texture_naming import canonicalize_texture_stem, sanitize_filename_stem, map_type_from_text
from ..core.texture_paths import classify_path, is_subpath
from .ai_http import (
    OPENROUTER_CHAT_URL,
    extract_message_content,
    http_post_json,
    openrouter_headers,
)


_SUPPORTED_IMAGE_SOURCES = {"FILE", "SEQUENCE", "MOVIE", "TILED"}
_SKIP_IMAGE_SOURCES = {"GENERATED", "VIEWER"}


@dataclass(frozen=True, slots=True)
class _Usage:
    material_name: str
    node_name: str
    node_label: str
    map_type: str
    material_is_linked: bool


def _bool_attr(obj: object, name: str) -> bool:
    try:
        return bool(getattr(obj, name))
    except Exception:
        return False


def _node_tree_key(tree: object) -> int:
    try:
        return int(tree.as_pointer())
    except Exception:
        return id(tree)


def _iter_image_texture_nodes(node_tree: Any) -> Iterable[Any]:
    visited: Set[int] = set()

    def _walk(tree: Any) -> Iterable[Any]:
        if tree is None:
            return
        key = _node_tree_key(tree)
        if key in visited:
            return
        visited.add(key)

        for node in list(getattr(tree, "nodes", []) or []):
            ntype = getattr(node, "type", "") or ""
            if ntype == "TEX_IMAGE":
                yield node
                continue
            if ntype == "GROUP":
                group_tree = getattr(node, "node_tree", None)
                if group_tree is not None:
                    yield from _walk(group_tree)

    yield from _walk(node_tree)


def _infer_map_type(material: Any, node: Any, image: Any) -> str:
    parts = [
        getattr(material, "name", "") or "",
        getattr(node, "name", "") or "",
        getattr(node, "label", "") or "",
        getattr(image, "name", "") or "",
        getattr(image, "filepath", "") or "",
    ]
    try:
        for output in list(getattr(node, "outputs", []) or []):
            parts.append(getattr(output, "name", "") or "")
            for link in list(getattr(output, "links", []) or []):
                parts.append(getattr(getattr(link, "to_socket", None), "name", "") or "")
                parts.append(getattr(getattr(link, "to_node", None), "type", "") or "")
                parts.append(getattr(getattr(link, "to_node", None), "name", "") or "")
    except Exception:
        pass
    return map_type_from_text(" ".join(parts))


def _collect_image_usages_from_materials(materials: Iterable[Any]) -> Dict[int, Tuple[Any, List[_Usage]]]:
    out: Dict[int, Tuple[Any, List[_Usage]]] = {}
    for mat in list(materials or []):
        node_tree = getattr(mat, "node_tree", None)
        if node_tree is None:
            continue
        if not _bool_attr(mat, "use_nodes"):
            continue

        mat_is_linked = getattr(mat, "library", None) is not None or _bool_attr(mat, "is_library_indirect")

        for node in _iter_image_texture_nodes(node_tree):
            image = getattr(node, "image", None)
            if image is None:
                continue
            try:
                image_key = int(image.as_pointer())
            except Exception:
                image_key = id(image)

            usage = _Usage(
                material_name=getattr(mat, "name", "") or "",
                node_name=getattr(node, "name", "") or "",
                node_label=getattr(node, "label", "") or "",
                map_type=_infer_map_type(mat, node, image),
                material_is_linked=mat_is_linked,
            )
            if image_key not in out:
                out[image_key] = (image, [usage])
            else:
                out[image_key][1].append(usage)
    return out


def _asset_library_roots_from_preferences(context) -> tuple[Path, ...]:
    roots: List[Path] = []
    try:
        libraries = list(getattr(context.preferences.filepaths, "asset_libraries", []) or [])
    except Exception:
        libraries = []
    for lib in libraries:
        raw = (getattr(lib, "path", "") or "").strip()
        if not raw:
            continue
        try:
            roots.append(Path(raw).resolve())
        except Exception:
            roots.append(Path(raw))

    unique: List[Path] = []
    seen: Set[str] = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return tuple(unique)


def _deduce_project_root(context) -> Optional[Path]:
    st = getattr(getattr(context, "window_manager", None), "lime_pipeline", None)
    raw = (getattr(st, "project_root", "") or "").strip() if st is not None else ""
    if raw:
        try:
            p = Path(raw)
            if p.exists():
                return p.resolve()
        except Exception:
            pass

    blend_path = (getattr(bpy.data, "filepath", "") or "").strip()
    if blend_path:
        try:
            root = find_project_root(blend_path)
            return root.resolve() if root is not None else None
        except Exception:
            return None
    return None


def _blend_dir() -> Path:
    blend_path = (getattr(bpy.data, "filepath", "") or "").strip()
    if blend_path:
        try:
            return Path(blend_path).resolve().parent
        except Exception:
            return Path(blend_path).parent
    try:
        return Path(bpy.path.abspath("//")).resolve()
    except Exception:
        return Path.cwd()


def _resolve_texture_root(project_root: Optional[Path]) -> Path:
    if project_root is not None:
        try:
            # Use lowercase to match existing project conventions and avoid ambiguity on case-sensitive shares.
            return get_ramv_dir(project_root) / "rsc" / "Textures"
        except Exception:
            pass
    return _blend_dir() / "rsc" / "Textures"


def _project_token_for_naming(context, *, project_root: Optional[Path]) -> str:
    # Prefer current blend filename details (most precise)
    try:
        blend_fp = (getattr(bpy.data, "filepath", "") or "").strip()
        if blend_fp:
            details = parse_blend_details(Path(blend_fp).name)
            if details and details.get("project_name"):
                return normalize_project_name(str(details["project_name"]))
    except Exception:
        pass

    # Fallback to selected project root folder name
    if project_root is not None:
        try:
            return normalize_project_name(project_root.name)
        except Exception:
            return str(project_root.name)
    return "Project"


def _resolve_abs_image_path(image: Any) -> tuple[Optional[Path], List[str]]:
    reasons: List[str] = []
    raw = (getattr(image, "filepath", "") or "").strip()
    if not raw:
        return None, ["Image has no filepath"]

    if "<UDIM>" in raw:
        reasons.append("UDIM token detected in filepath (skip in adopt)")
    try:
        resolved = bpy.path.abspath(raw)
    except Exception:
        resolved = raw
    resolved = (resolved or "").strip()
    if not resolved:
        return None, ["Image filepath could not be resolved"]
    try:
        return Path(resolved).resolve(), reasons
    except Exception:
        return Path(resolved), reasons


def _sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    total = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            h.update(chunk)
    return h.hexdigest(), total


def _safe_mkdir(path: Path) -> Optional[str]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return None
    except Exception as ex:
        return str(ex)


def _unique_destination(dest_root: Path, filename: str, full_hash: str) -> Path:
    """Return a destination path, reusing existing file if content matches."""
    dest_root = dest_root
    target = dest_root / filename
    if target.exists():
        try:
            existing_hash, _ = _sha256_file(target)
        except Exception:
            existing_hash = ""
        if existing_hash == full_hash:
            return target
        stem = target.stem
        ext = target.suffix
        for idx in range(2, 1000):
            candidate = dest_root / f"{stem}_{idx:02d}{ext}"
            if not candidate.exists():
                return candidate
    return target


def _relpath_for_blender(path: Path, *, project_root: Optional[Path]) -> tuple[str, List[str]]:
    """Prefer Blender-relative paths when blend is inside the project."""
    reasons: List[str] = []
    blend_fp = (getattr(bpy.data, "filepath", "") or "").strip()
    if not blend_fp:
        reasons.append("Blend file not saved; storing absolute path")
        return str(path), reasons

    blend_dir = _blend_dir()
    if project_root is not None and not is_subpath(blend_dir, project_root):
        reasons.append("Blend file is outside project root; storing absolute path")
        return str(path), reasons

    try:
        return bpy.path.relpath(str(path)), reasons
    except Exception:
        reasons.append("Failed computing Blender relative path; storing absolute path")
        return str(path), reasons


def _looks_like_map_type_only(stem: str, map_type: str) -> bool:
    s = sanitize_filename_stem(stem or "", max_len=48).lower()
    m = sanitize_filename_stem(map_type or "", max_len=24).lower()
    if not s:
        return False
    if m and s == m:
        return True
    # common map type tokens
    if s in {"alpha", "normal", "roughness", "metallic", "metalness", "basecolor", "albedo", "ao", "height", "emission"}:
        return True
    return False


class LIME_OT_texture_adopt(Operator):
    bl_idname = "lime.texture_adopt"
    bl_label = "Adopt Textures (Fix)"
    bl_description = (
        "Copy external textures into the project RSC/Textures folder and relink images. "
        "Skips linked/library/protected textures."
    )
    bl_options = {"REGISTER", "UNDO"}

    use_ai: BoolProperty(
        name="Use AI naming",
        description="Use OpenRouter to suggest a better texture name stem (falls back if unavailable)",
        default=False,
    )

    include_ai_preview: BoolProperty(
        name="AI include preview (low-res)",
        description="Send a tiny low-res preview of each texture to OpenRouter for better naming",
        default=False,
        options={"HIDDEN"},
    )

    def _ai_suggest_stem(
        self,
        *,
        prefs,
        original_filename: str,
        material_name: str,
        map_type: str,
        image_preview_data_url: str | None,
        want_image_summary: bool,
    ) -> tuple[str, str | None, str | None, str | None]:
        key = (getattr(prefs, "openrouter_api_key", "") or "").strip()
        if not key:
            return "", None, None, "OpenRouter API key not set"

        model = (getattr(prefs, "openrouter_model", "") or "").strip()
        if not model:
            model = "google/gemini-2.0-flash-lite-001"

        system_lines = [
            "You help a Blender pipeline simplify texture filenames.",
            "Goal: keep the original context but remove noise.",
            "Return ONLY a filename stem (no extension).",
            "Allowed characters: letters, digits, underscore.",
            "Prefer keeping existing project tokens and numeric suffixes (e.g. _01).",
            "Do NOT return only the map type (e.g. Alpha/Normal/Roughness/BaseColor). Focus on the visual/subject descriptor.",
            "Keep it short (max 48 characters). Do not invent long names.",
            "If the original is already good, return it unchanged.",
            "If the original contains the token 'Texture', keep it.",
            "",
            "Output must be a single JSON object with keys:",
            "- stem: string",
            "- explanation: string (short)",
        ]
        if want_image_summary:
            system_lines.append("- image_summary: string (only if an image is provided)")
        system_lines.append("Return ONLY JSON, no markdown.")
        system = "\n".join(system_lines)
        user = (
            f"Material: {material_name}\n"
            f"Map type: {map_type}\n"
            f"Original filename: {original_filename}\n"
            "Respond with JSON now."
        )
        content_parts: List[Dict[str, object]] = [{"type": "text", "text": user}]
        if image_preview_data_url:
            content_parts.append({"type": "image_url", "image_url": {"url": image_preview_data_url}})
        payload: Dict[str, object] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content_parts},
            ],
            "temperature": 0.2,
        }
        debug = bool(getattr(prefs, "openrouter_debug", False))
        if debug:
            try:
                print("[Texture Adopt] OpenRouter model:", model)
                print("[Texture Adopt] AI preview included:", bool(image_preview_data_url))
                print("[Texture Adopt] Original filename:", original_filename)
            except Exception:
                pass
        result = http_post_json(OPENROUTER_CHAT_URL, payload, headers=openrouter_headers(prefs), timeout=30)
        if not isinstance(result, dict):
            return "", None, "OpenRouter request failed"
        content = extract_message_content(result) or ""
        parsed = _parse_ai_json(content)
        stem = sanitize_filename_stem((parsed.get("stem") or "").strip()) if parsed else ""
        explanation = (parsed.get("explanation") or "").strip() if parsed else ""
        image_summary = (parsed.get("image_summary") or "").strip() if parsed else ""
        if not stem:
            return "", None, None, "OpenRouter returned an empty/invalid stem"
        if len(stem) > 48:
            stem = stem[:48]
        if debug:
            try:
                print("[Texture Adopt] AI stem:", stem)
                if explanation:
                    print("[Texture Adopt] AI explanation:", explanation)
                if want_image_summary and image_summary:
                    print("[Texture Adopt] AI image summary:", image_summary)
            except Exception:
                pass
        return stem, (explanation or None), (image_summary or None), None

    def execute(self, context):
        project_root = _deduce_project_root(context)
        protected_roots = _asset_library_roots_from_preferences(context)
        dest_root = _resolve_texture_root(project_root)
        prefs = context.preferences.addons[__package__.split(".")[0]].preferences
        project_token = _project_token_for_naming(context, project_root=project_root) or "Project"

        err = _safe_mkdir(dest_root)
        if err:
            self.report({"ERROR"}, f"Cannot create texture destination folder: {err}")
            return {"CANCELLED"}

        manifest_dir = dest_root / "_manifests"
        err = _safe_mkdir(manifest_dir)
        if err:
            self.report({"ERROR"}, f"Cannot create manifest folder: {err}")
            return {"CANCELLED"}

        usage_by_image = _collect_image_usages_from_materials(getattr(bpy.data, "materials", []) or [])
        if not usage_by_image:
            self.report({"INFO"}, "No image textures found in materials")
            return {"CANCELLED"}

        hash_to_dest: Dict[str, Path] = {}
        index_path = manifest_dir / "texture_sha256_index.json"
        sha256_index: Dict[str, str] = {}
        try:
            if index_path.exists():
                data = json.loads(index_path.read_text(encoding="utf-8"))
                sha256_index = dict((data.get("sha256_to_file") or {}) if isinstance(data, dict) else {})
        except Exception:
            sha256_index = {}

        ai_cache: Dict[str, str] = {}
        changes: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        relinked_images: Set[int] = set()

        stats = {
            "total_images": 0,
            "adopted": 0,
            "relinked_existing": 0,
            "skipped_protected": 0,
            "skipped_already_in_texture_root": 0,
            "skipped_packed": 0,
            "skipped_generated": 0,
            "skipped_unsupported": 0,
            "skipped_missing": 0,
            "skipped_unknown": 0,
            "copy_errors": 0,
            "relink_errors": 0,
        }

        for img_key, (image, usages) in usage_by_image.items():
            stats["total_images"] += 1
            reasons: List[str] = []

            source_kind = (getattr(image, "source", "") or "").upper()
            raw_filepath = (getattr(image, "filepath", "") or "").strip()
            is_packed = getattr(image, "packed_file", None) is not None
            is_linked_image = getattr(image, "library", None) is not None or _bool_attr(image, "is_library_indirect")

            mat_linked = sorted({u.material_name for u in usages if u.material_is_linked})
            if mat_linked:
                reasons.append("Used by linked material(s)")

            abs_path, path_reasons = _resolve_abs_image_path(image)
            reasons.extend(path_reasons)

            path_class = classify_path(abs_path, project_root=project_root, protected_roots=protected_roots)
            if path_class.kind == "PROTECTED_ROOT":
                reasons.append(path_class.reason)

            if source_kind and source_kind not in _SUPPORTED_IMAGE_SOURCES and source_kind not in _SKIP_IMAGE_SOURCES:
                stats["skipped_unsupported"] += 1
                skipped.append(
                    {
                        "image_name": getattr(image, "name", "") or "",
                        "raw_filepath": raw_filepath,
                        "abs_filepath": str(abs_path) if abs_path is not None else "",
                        "classification": "UNSUPPORTED",
                        "reasons": reasons + [f"Unsupported image source: {source_kind}"],
                    }
                )
                continue

            if source_kind in _SKIP_IMAGE_SOURCES:
                stats["skipped_generated"] += 1
                skipped.append(
                    {
                        "image_name": getattr(image, "name", "") or "",
                        "raw_filepath": raw_filepath,
                        "abs_filepath": str(abs_path) if abs_path is not None else "",
                        "classification": "GENERATED",
                        "reasons": reasons + [f"Image source is {source_kind}"],
                    }
                )
                continue

            if is_packed:
                stats["skipped_packed"] += 1
                skipped.append(
                    {
                        "image_name": getattr(image, "name", "") or "",
                        "raw_filepath": raw_filepath,
                        "abs_filepath": str(abs_path) if abs_path is not None else "",
                        "classification": "PACKED",
                        "reasons": reasons + ["Packed image (embedded in .blend)"],
                    }
                )
                continue

            if is_linked_image or mat_linked or path_class.kind == "PROTECTED_ROOT":
                stats["skipped_protected"] += 1
                skipped.append(
                    {
                        "image_name": getattr(image, "name", "") or "",
                        "raw_filepath": raw_filepath,
                        "abs_filepath": str(abs_path) if abs_path is not None else "",
                        "classification": "PROTECTED",
                        "reasons": reasons + ["Protected (linked/library/protected root)"],
                    }
                )
                continue

            if abs_path is None:
                stats["skipped_unknown"] += 1
                skipped.append(
                    {
                        "image_name": getattr(image, "name", "") or "",
                        "raw_filepath": raw_filepath,
                        "abs_filepath": "",
                        "classification": "UNKNOWN",
                        "reasons": reasons,
                    }
                )
                continue

            # If already centralized, do nothing.
            try:
                if is_subpath(abs_path, dest_root):
                    stats["skipped_already_in_texture_root"] += 1
                    skipped.append(
                        {
                            "image_name": getattr(image, "name", "") or "",
                            "raw_filepath": raw_filepath,
                            "abs_filepath": str(abs_path),
                            "classification": "IN_TEXTURE_ROOT",
                            "reasons": reasons + ["Already inside texture root"],
                        }
                    )
                    continue
            except Exception:
                pass

            if "<UDIM>" in raw_filepath:
                stats["skipped_unknown"] += 1
                skipped.append(
                    {
                        "image_name": getattr(image, "name", "") or "",
                        "raw_filepath": raw_filepath,
                        "abs_filepath": str(abs_path),
                        "classification": "UDIM_SKIP",
                        "reasons": reasons,
                    }
                )
                continue

            if not os.path.isfile(str(abs_path)):
                stats["skipped_missing"] += 1
                skipped.append(
                    {
                        "image_name": getattr(image, "name", "") or "",
                        "raw_filepath": raw_filepath,
                        "abs_filepath": str(abs_path),
                        "classification": "MISSING",
                        "reasons": reasons + ["Resolved file does not exist"],
                    }
                )
                continue

            # Adoptable: any non-protected existing file not already in texture root.
            try:
                digest, byte_count = _sha256_file(abs_path)
            except Exception as ex:
                stats["copy_errors"] += 1
                skipped.append(
                    {
                        "image_name": getattr(image, "name", "") or "",
                        "raw_filepath": raw_filepath,
                        "abs_filepath": str(abs_path),
                        "classification": "HASH_ERROR",
                        "reasons": reasons + [f"Failed hashing file: {ex}"],
                    }
                )
                continue

            short = digest[:8]
            existing = hash_to_dest.get(digest)
            if existing is None:
                indexed = (sha256_index.get(digest) or "").strip()
                if indexed:
                    candidate = dest_root / indexed
                    if candidate.exists():
                        existing = candidate

            first = usages[0] if usages else _Usage("", "", "", "Generic", False)
            ext = (abs_path.suffix or ".png").lower()
            original_filename = abs_path.name
            base_stem = sanitize_filename_stem(abs_path.stem) or "Texture"

            ai_error: str | None = None
            ai_used = False
            preview_used = False
            ai_explanation: str | None = None
            ai_image_summary: str | None = None
            preview_meta: Dict[str, object] | None = None
            if bool(self.use_ai):
                debug = bool(getattr(prefs, "openrouter_debug", False))
                cache_key = f"{original_filename}|{first.material_name}|{first.map_type}|{bool(self.include_ai_preview)}"
                if (not debug) and cache_key in ai_cache:
                    base_stem = ai_cache[cache_key]
                    ai_used = True
                else:
                    preview_url: str | None = None
                    if bool(self.include_ai_preview):
                        preview_url, preview_meta = _make_lowres_preview_data_url_with_meta(
                            image,
                            max_size=96,
                            max_bytes=120_000,
                        )
                        preview_used = bool(preview_url)
                    want_summary = bool(debug and preview_url)
                    suggested, explanation, image_summary, err_msg = self._ai_suggest_stem(
                        prefs=prefs,
                        original_filename=original_filename,
                        material_name=first.material_name,
                        map_type=first.map_type,
                        image_preview_data_url=preview_url,
                        want_image_summary=want_summary,
                    )
                    if suggested:
                        if _looks_like_map_type_only(suggested, first.map_type):
                            # AI returned only the map type; keep original descriptor.
                            ai_error = "AI suggested map-type-only stem; ignored"
                        else:
                            base_stem = suggested
                        if not debug:
                            ai_cache[cache_key] = base_stem
                        ai_used = True
                        ai_explanation = explanation
                        ai_image_summary = image_summary if want_summary else None
                    else:
                        ai_error = err_msg

            canonical_stem = canonicalize_texture_stem(project_token=project_token, stem=base_stem, map_type=first.map_type)
            filename = f"{canonical_stem}{ext}"

            if existing is not None:
                dest_path = existing
                action = "RELINK_EXISTING"
            else:
                dest_path = _unique_destination(dest_root, filename, digest)
                try:
                    shutil.copy2(str(abs_path), str(dest_path))
                except Exception as ex:
                    stats["copy_errors"] += 1
                    skipped.append(
                        {
                            "image_name": getattr(image, "name", "") or "",
                            "raw_filepath": raw_filepath,
                            "abs_filepath": str(abs_path),
                            "classification": "COPY_ERROR",
                            "reasons": reasons + [f"Failed copying file: {ex}"],
                        }
                    )
                    continue
                try:
                    if not dest_path.exists():
                        raise FileNotFoundError("Destination file not found after copy")
                    if dest_path.stat().st_size != int(byte_count):
                        raise OSError("Destination file size mismatch after copy")
                except Exception as ex:
                    stats["copy_errors"] += 1
                    skipped.append(
                        {
                            "image_name": getattr(image, "name", "") or "",
                            "raw_filepath": raw_filepath,
                            "abs_filepath": str(abs_path),
                            "classification": "COPY_VERIFY_FAILED",
                            "reasons": reasons + [f"Copy verification failed: {ex}"],
                        }
                    )
                    continue
                action = "COPIED"

            hash_to_dest[digest] = dest_path
            try:
                sha256_index[digest] = dest_path.name
            except Exception:
                pass

            # Relink image datablock once.
            if img_key in relinked_images:
                continue

            blender_path, rel_reasons = _relpath_for_blender(dest_path, project_root=project_root)
            try:
                image.filepath = blender_path
                try:
                    image.filepath_raw = blender_path  # type: ignore[attr-defined]
                except Exception:
                    pass
                image.name = dest_path.stem
                image.reload()
                relinked_images.add(img_key)
            except Exception as ex:
                stats["relink_errors"] += 1
                skipped.append(
                    {
                        "image_name": getattr(image, "name", "") or "",
                        "raw_filepath": raw_filepath,
                        "abs_filepath": str(abs_path),
                        "classification": "RELINK_ERROR",
                        "reasons": reasons + [f"Failed relinking image: {ex}"],
                    }
                )
                continue

            if action == "COPIED":
                stats["adopted"] += 1
            else:
                stats["relinked_existing"] += 1

            changes.append(
                {
                    "image_pointer": int(img_key),
                    "image_name_after": getattr(image, "name", "") or "",
                    "image_source": source_kind,
                    "original_raw_filepath": raw_filepath,
                    "original_abs_filepath": str(abs_path),
                    "content_sha256": digest,
                    "bytes": int(byte_count),
                    "project_token": project_token,
                    "canonical_stem": canonical_stem,
                    "ai_used": bool(ai_used),
                    "ai_preview_used": bool(preview_used),
                    "ai_preview_meta": preview_meta,
                    "ai_input": {
                        "original_filename": original_filename,
                        "material": first.material_name,
                        "map_type": first.map_type,
                    },
                    "ai_explanation": ai_explanation,
                    "ai_image_summary": ai_image_summary,
                    "ai_error": ai_error,
                    "action": action,
                    "dest_abs_filepath": str(dest_path),
                    "dest_blender_filepath": blender_path,
                    "relpath_notes": rel_reasons,
                    "used_by": [
                        {
                            "material": u.material_name,
                            "node": u.node_name,
                            "label": u.node_label,
                            "map_type": u.map_type,
                            "material_is_linked": u.material_is_linked,
                        }
                        for u in usages
                    ],
                }
            )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        manifest_path = manifest_dir / f"texture_adopt_{timestamp}.json"
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "blend_filepath": (getattr(bpy.data, "filepath", "") or "").strip(),
            "blend_dir": str(_blend_dir()),
            "project_root": str(project_root) if project_root is not None else None,
            "asset_library_roots": [str(p) for p in protected_roots],
            "texture_root": str(dest_root),
            "naming": {
                "pattern": "<Project>_<Descriptor>_<NN>.<ext> (descriptor from original filename, optionally AI-filtered)",
                "ai_enabled": bool(self.use_ai),
                "ai_include_preview": bool(self.include_ai_preview),
                "ai_debug_enabled": bool(getattr(prefs, "openrouter_debug", False)),
            },
            "stats": stats,
            "changes": changes,
            "skipped": skipped,
        }

        try:
            manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as ex:
            self.report({"ERROR"}, f"Failed writing texture adopt manifest: {ex}")
            return {"CANCELLED"}

        # Persist sha256 index for cross-run dedupe without hashes in filenames.
        try:
            index_payload = {
                "version": 1,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "sha256_to_file": sha256_index,
            }
            tmp = index_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(index_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(index_path)
        except Exception:
            pass

        self.report(
            {"INFO"},
            f"Texture adopt complete. Copied: {stats['adopted']}, Relinked existing: {stats['relinked_existing']}, "
            f"Skipped protected: {stats['skipped_protected']}, Already centralized: {stats['skipped_already_in_texture_root']}. "
            f"Manifest: {manifest_path}",
        )
        try:
            print("[Lime Pipeline] Texture adopt manifest written:", str(manifest_path))
        except Exception:
            pass
        return {"FINISHED"}


def _make_lowres_preview_data_url(image: Any, *, max_size: int, max_bytes: int) -> str | None:
    """Create a tiny PNG data URL from a Blender image datablock.

    Uses a copied datablock to avoid modifying the original.
    """
    try:
        if image is None:
            return None
        # Ensure we only attempt for file images that are loaded.
        if (getattr(image, "source", "") or "").upper() not in {"FILE", "TILED"}:
            return None
        tmp_img = image.copy()
    except Exception:
        return None

    tmp_path = None
    try:
        try:
            w = int(getattr(tmp_img, "size", [0, 0])[0] or 0)
            h = int(getattr(tmp_img, "size", [0, 0])[1] or 0)
        except Exception:
            w, h = 0, 0
        if w <= 0 or h <= 0:
            return None

        scale = max(w, h) / float(max_size)
        if scale < 1.0:
            scale = 1.0
        new_w = max(1, int(round(w / scale)))
        new_h = max(1, int(round(h / scale)))
        try:
            tmp_img.scale(new_w, new_h)
        except Exception:
            return None

        with tempfile.TemporaryDirectory(prefix="lime_tx_preview_") as td:
            tmp_path = Path(td) / "preview.png"
            try:
                tmp_img.filepath_raw = str(tmp_path)
            except Exception:
                pass
            try:
                tmp_img.file_format = "PNG"  # type: ignore[attr-defined]
            except Exception:
                pass
            tmp_img.save()
            data = tmp_path.read_bytes()
            if len(data) > int(max_bytes):
                return None
            b64 = base64.b64encode(data).decode("ascii")
            return f"data:image/png;base64,{b64}"
    except Exception:
        return None
    finally:
        try:
            bpy.data.images.remove(tmp_img)
        except Exception:
            pass


def _make_lowres_preview_data_url_with_meta(
    image: Any,
    *,
    max_size: int,
    max_bytes: int,
) -> tuple[str | None, Dict[str, object] | None]:
    """Wrapper that returns a data URL plus metadata (without embedding the image bytes in logs)."""
    try:
        url = _make_lowres_preview_data_url(image, max_size=max_size, max_bytes=max_bytes)
        if not url:
            return None, None
        # url is data:image/png;base64,...
        try:
            b64 = url.split(",", 1)[1]
            data = base64.b64decode(b64.encode("ascii"))
            sha1 = hashlib.sha1(data).hexdigest()
            return url, {"bytes": len(data), "sha1": sha1, "format": "png", "max_size": int(max_size)}
        except Exception:
            return url, {"format": "png", "max_size": int(max_size)}
    except Exception:
        return None, None


def _parse_ai_json(text: str) -> Dict[str, str] | None:
    """Parse a one-line JSON object from an LLM response (best-effort)."""
    raw = (text or "").strip()
    if not raw:
        return None
    # Strip common code fences
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
    # Try direct JSON
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            stem = obj.get("stem")
            explanation = obj.get("explanation")
            image_summary = obj.get("image_summary")
            out: Dict[str, str] = {}
            if isinstance(stem, str):
                out["stem"] = stem
            if isinstance(explanation, str):
                out["explanation"] = explanation
            if isinstance(image_summary, str):
                out["image_summary"] = image_summary
            return out if out else None
    except Exception:
        pass
    # Fallback: try to locate a JSON object substring
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            obj = json.loads(raw[start : end + 1])
            if isinstance(obj, dict):
                stem = obj.get("stem")
                explanation = obj.get("explanation")
                image_summary = obj.get("image_summary")
                out2: Dict[str, str] = {}
                if isinstance(stem, str):
                    out2["stem"] = stem
                if isinstance(explanation, str):
                    out2["explanation"] = explanation
                if isinstance(image_summary, str):
                    out2["image_summary"] = image_summary
                return out2 if out2 else None
    except Exception:
        return None
    return None


__all__ = [
    "LIME_OT_texture_adopt",
]
