"""Shared helpers for AI Textures Organizer workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import bpy

from ..core.naming import normalize_project_name, parse_blend_details
from ..core.texture_naming import (
    canonicalize_texture_stem,
    map_type_from_socket_links,
    sanitize_filename_stem,
)
from ..core.texture_paths import classify_path, is_subpath
from ..core.texture_workspace import (
    deduce_texture_project_workspace,
    extra_protected_texture_roots,
    resolve_texture_root,
    unique_paths,
)
from .ai_http import (
    OPENROUTER_CHAT_URL,
    extract_message_content,
    has_openrouter_api_key,
    http_post_json,
    openrouter_headers,
)


SUPPORTED_IMAGE_SOURCES = {"FILE", "SEQUENCE", "MOVIE", "TILED"}
SKIP_IMAGE_SOURCES = {"GENERATED", "VIEWER"}
ALLOWED_MAP_TYPES = {
    "Generic",
    "BaseColor",
    "Normal",
    "Roughness",
    "Metallic",
    "AO",
    "Alpha",
    "Height",
    "Emission",
}


@dataclass(frozen=True, slots=True)
class TextureUsage:
    material_name: str
    node_name: str
    node_label: str
    map_type: str
    material_is_linked: bool
    socket_targets: Tuple[str, ...]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def bool_attr(obj: object, name: str) -> bool:
    try:
        return bool(getattr(obj, name))
    except Exception:
        return False


def node_tree_key(tree: object) -> int:
    try:
        return int(tree.as_pointer())
    except Exception:
        return id(tree)


def iter_image_texture_nodes(node_tree: Any) -> Iterable[Any]:
    visited: Set[int] = set()

    def walk(tree: Any) -> Iterable[Any]:
        if tree is None:
            return
        key = node_tree_key(tree)
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
                    yield from walk(group_tree)

    yield from walk(node_tree)


def node_target_socket_names(node: Any) -> Tuple[str, ...]:
    names: List[str] = []
    seen: Set[str] = set()
    try:
        for output in list(getattr(node, "outputs", []) or []):
            for link in list(getattr(output, "links", []) or []):
                socket_name = (getattr(getattr(link, "to_socket", None), "name", "") or "").strip()
                if not socket_name:
                    continue
                key = socket_name.lower()
                if key in seen:
                    continue
                seen.add(key)
                names.append(socket_name)
    except Exception:
        pass
    return tuple(names)


def infer_map_type(material: Any, node: Any, image: Any) -> str:
    parts = [
        getattr(material, "name", "") or "",
        getattr(node, "name", "") or "",
        getattr(node, "label", "") or "",
        getattr(image, "name", "") or "",
        getattr(image, "filepath", "") or "",
    ]
    socket_names: List[str] = []
    try:
        for output in list(getattr(node, "outputs", []) or []):
            parts.append(getattr(output, "name", "") or "")
            for link in list(getattr(output, "links", []) or []):
                socket_name = getattr(getattr(link, "to_socket", None), "name", "") or ""
                parts.append(socket_name)
                if socket_name:
                    socket_names.append(socket_name)
                parts.append(getattr(getattr(link, "to_node", None), "type", "") or "")
                parts.append(getattr(getattr(link, "to_node", None), "name", "") or "")
    except Exception:
        pass
    return map_type_from_socket_links(socket_names, fallback_text=" ".join(parts))


def collect_image_usages_from_materials(materials: Iterable[Any]) -> Dict[int, Tuple[Any, List[TextureUsage]]]:
    out: Dict[int, Tuple[Any, List[TextureUsage]]] = {}
    for mat in list(materials or []):
        node_tree = getattr(mat, "node_tree", None)
        if node_tree is None or not bool_attr(mat, "use_nodes"):
            continue
        mat_is_linked = getattr(mat, "library", None) is not None or bool_attr(mat, "is_library_indirect")
        for node in iter_image_texture_nodes(node_tree):
            image = getattr(node, "image", None)
            if image is None:
                continue
            try:
                image_key = int(image.as_pointer())
            except Exception:
                image_key = id(image)
            usage = TextureUsage(
                material_name=getattr(mat, "name", "") or "",
                node_name=getattr(node, "name", "") or "",
                node_label=getattr(node, "label", "") or "",
                map_type=infer_map_type(mat, node, image),
                material_is_linked=mat_is_linked,
                socket_targets=node_target_socket_names(node),
            )
            if image_key not in out:
                out[image_key] = (image, [usage])
            else:
                out[image_key][1].append(usage)
    return out


def collect_materials_from_selected_objects(context) -> List[Any]:
    mats: List[Any] = []
    seen: Set[int] = set()
    for obj in list(getattr(context, "selected_objects", []) or []):
        for slot in list(getattr(obj, "material_slots", []) or []):
            mat = getattr(slot, "material", None)
            if mat is None:
                continue
            ptr = int(mat.as_pointer())
            if ptr in seen:
                continue
            seen.add(ptr)
            mats.append(mat)
    return mats


def asset_library_roots_from_preferences(context) -> tuple[Path, ...]:
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
    return unique_paths(roots)


def state_local_mode(context) -> bool:
    st = getattr(getattr(context, "window_manager", None), "lime_pipeline", None)
    return bool(getattr(st, "use_local_project", False)) if st is not None else False


def deduce_project_root(context) -> tuple[Optional[Path], bool]:
    st = getattr(getattr(context, "window_manager", None), "lime_pipeline", None)
    raw_root = (getattr(st, "project_root", "") or "").strip() if st is not None else ""
    blend_path = (getattr(bpy.data, "filepath", "") or "").strip()
    root, local_mode = deduce_texture_project_workspace(
        state_project_root=raw_root,
        use_local_project=state_local_mode(context),
        blend_path=blend_path,
    )
    return root, local_mode


def blend_dir() -> Path:
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


def resolve_texture_root_for_context(project_root: Optional[Path], *, local_mode: bool) -> Path:
    return resolve_texture_root(project_root, local_mode=local_mode, blend_dir=blend_dir())


def protected_roots_for_context(context) -> tuple[Path, ...]:
    return unique_paths((*asset_library_roots_from_preferences(context), *extra_protected_texture_roots()))


def project_token_for_naming(*, project_root: Optional[Path]) -> str:
    try:
        blend_fp = (getattr(bpy.data, "filepath", "") or "").strip()
        if blend_fp:
            details = parse_blend_details(Path(blend_fp).name)
            if details and details.get("project_name"):
                return normalize_project_name(str(details["project_name"]))
    except Exception:
        pass
    if project_root is not None:
        try:
            return normalize_project_name(project_root.name)
        except Exception:
            return str(project_root.name)
    return "Project"


def resolve_abs_image_path(image: Any) -> tuple[Optional[Path], List[str]]:
    reasons: List[str] = []
    raw = (getattr(image, "filepath", "") or "").strip()
    if not raw:
        return None, ["Image has no filepath"]
    if "<UDIM>" in raw:
        reasons.append("UDIM token detected in filepath")
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


def exists_for_scan(abs_path: Optional[Path], *, raw_filepath: str) -> bool:
    if abs_path is None:
        return False
    if "<UDIM>" in (raw_filepath or ""):
        probe = str(abs_path).replace("<UDIM>", "1001")
        return os.path.isfile(probe)
    return os.path.isfile(str(abs_path))


def safe_mkdir(path: Path) -> Optional[str]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return None
    except Exception as ex:
        return str(ex)


def sha256_file(path: Path) -> tuple[str, int]:
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


def unique_destination(dest_root: Path, filename: str, full_hash: str) -> Path:
    target = dest_root / filename
    if target.exists():
        try:
            existing_hash, _ = sha256_file(target)
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


def propose_unique_destination(dest_dir: Path, filename: str) -> Path:
    base = Path(filename).stem
    ext = Path(filename).suffix
    candidate = dest_dir / (base + ext)
    if not candidate.exists():
        return candidate
    for idx in range(2, 1000):
        candidate = dest_dir / f"{base}_{idx:02d}{ext}"
        if not candidate.exists():
            return candidate
    return dest_dir / f"{base}_{datetime.now(timezone.utc).strftime('%H%M%S')}{ext}"


def relpath_for_blender(path: Path, *, project_root: Optional[Path]) -> tuple[str, List[str]]:
    reasons: List[str] = []
    blend_fp = (getattr(bpy.data, "filepath", "") or "").strip()
    if not blend_fp:
        reasons.append("Blend file not saved; storing absolute path")
        return str(path), reasons

    bdir = blend_dir()
    if project_root is not None and not is_subpath(bdir, project_root):
        reasons.append("Blend file is outside project root; storing absolute path")
        return str(path), reasons

    try:
        return bpy.path.relpath(str(path)), reasons
    except Exception:
        reasons.append("Failed computing Blender relative path; storing absolute path")
        return str(path), reasons


def usage_socket_targets(usages: List[TextureUsage]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for usage in list(usages or []):
        for socket_name in list(getattr(usage, "socket_targets", ()) or ()):
            value = str(socket_name or "").strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(value)
    return out


def normalize_ai_map_type(value: str) -> str:
    raw = sanitize_filename_stem(value or "", max_len=24).lower()
    if not raw:
        return ""
    aliases = {
        "basecolor": "BaseColor",
        "albedo": "BaseColor",
        "diffuse": "BaseColor",
        "color": "BaseColor",
        "normal": "Normal",
        "roughness": "Roughness",
        "gloss": "Roughness",
        "metallic": "Metallic",
        "metalness": "Metallic",
        "ao": "AO",
        "alpha": "Alpha",
        "opacity": "Alpha",
        "mask": "Alpha",
        "height": "Height",
        "displacement": "Height",
        "emission": "Emission",
        "emit": "Emission",
        "generic": "Generic",
    }
    normalized = aliases.get(raw, "")
    if normalized in ALLOWED_MAP_TYPES:
        return normalized
    return ""


def looks_like_map_type_only(stem: str, map_type: str) -> bool:
    s = sanitize_filename_stem(stem or "", max_len=48).lower()
    m = sanitize_filename_stem(map_type or "", max_len=24).lower()
    if not s:
        return False
    if m and s == m:
        return True
    if s in {"alpha", "normal", "roughness", "metallic", "metalness", "basecolor", "albedo", "ao", "height", "emission"}:
        return True
    return False


def parse_ai_json(text: str) -> Dict[str, str] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            out: Dict[str, str] = {}
            for key in ("stem", "map_type", "explanation", "image_summary"):
                val = obj.get(key)
                if isinstance(val, str):
                    out[key] = val
            return out if out else None
    except Exception:
        pass
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            obj2 = json.loads(raw[start : end + 1])
            if isinstance(obj2, dict):
                out2: Dict[str, str] = {}
                for key in ("stem", "map_type", "explanation", "image_summary"):
                    val = obj2.get(key)
                    if isinstance(val, str):
                        out2[key] = val
                return out2 if out2 else None
    except Exception:
        return None
    return None


def make_lowres_preview_data_url(image: Any, *, max_size: int, max_bytes: int) -> str | None:
    try:
        if image is None:
            return None
        if (getattr(image, "source", "") or "").upper() not in {"FILE", "TILED"}:
            return None
        tmp_img = image.copy()
    except Exception:
        return None

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


def make_lowres_preview_data_url_with_meta(
    image: Any,
    *,
    max_size: int,
    max_bytes: int,
) -> tuple[str | None, Dict[str, object] | None]:
    url = make_lowres_preview_data_url(image, max_size=max_size, max_bytes=max_bytes)
    if not url:
        return None, None
    try:
        b64 = url.split(",", 1)[1]
        data = base64.b64decode(b64.encode("ascii"))
        sha1 = hashlib.sha1(data).hexdigest()
        return url, {"bytes": len(data), "sha1": sha1, "format": "png", "max_size": int(max_size)}
    except Exception:
        return url, {"format": "png", "max_size": int(max_size)}


def ai_suggest_texture_name(
    *,
    context,
    original_filename: str,
    material_name: str,
    map_type: str,
    socket_targets: Sequence[str],
    manual_hint: str = "",
    prior_suggestion: str = "",
    include_preview: bool = False,
    image: Any = None,
) -> tuple[str, str | None, str | None, str | None, Dict[str, object] | None, str | None]:
    if not has_openrouter_api_key():
        return "", None, None, None, None, "OpenRouter API key not found in .env"

    prefs = context.preferences.addons[__package__.split(".")[0]].preferences
    model = (getattr(prefs, "openrouter_model", "") or "").strip() or "google/gemini-3-flash-preview"

    preview_url: str | None = None
    preview_meta: Dict[str, object] | None = None
    if include_preview and image is not None:
        preview_url, preview_meta = make_lowres_preview_data_url_with_meta(
            image,
            max_size=96,
            max_bytes=120_000,
        )

    system_lines = [
        "You help a Blender pipeline simplify texture filenames.",
        "Return ONLY JSON.",
        "JSON keys: stem, map_type, explanation.",
        "stem must be filename-safe using letters, digits, underscore only.",
        "Keep context from original filename and avoid generic map-only names.",
        "If a manual hint is provided, prioritize that intent while keeping it concise.",
        "map_type must be one of Generic, BaseColor, Normal, Roughness, Metallic, AO, Alpha, Height, Emission.",
    ]
    user_lines = [
        f"Original filename: {original_filename}",
        f"Material: {material_name}",
        f"Current map type: {map_type}",
        f"Socket targets: {', '.join(list(socket_targets)[:10]) if socket_targets else 'None'}",
        f"Manual hint: {manual_hint or 'None'}",
        f"Prior suggestion: {prior_suggestion or 'None'}",
    ]
    content_parts: List[Dict[str, object]] = [{"type": "text", "text": "\n".join(user_lines)}]
    if preview_url:
        content_parts.append({"type": "image_url", "image_url": {"url": preview_url}})

    payload: Dict[str, object] = {
        "model": model,
        "messages": [
            {"role": "system", "content": "\n".join(system_lines)},
            {"role": "user", "content": content_parts},
        ],
        "temperature": 0.2,
    }
    result = http_post_json(OPENROUTER_CHAT_URL, payload, headers=openrouter_headers(prefs), timeout=30)
    if not isinstance(result, dict):
        return "", None, None, None, preview_meta, "OpenRouter request failed"

    content = extract_message_content(result) or ""
    parsed = parse_ai_json(content)
    stem = sanitize_filename_stem((parsed.get("stem") or "").strip()) if parsed else ""
    ai_map_type = normalize_ai_map_type((parsed.get("map_type") or "").strip()) if parsed else ""
    explanation = (parsed.get("explanation") or "").strip() if parsed else ""
    image_summary = (parsed.get("image_summary") or "").strip() if parsed else ""
    if not stem:
        return "", None, None, None, preview_meta, "OpenRouter returned an empty/invalid stem"
    if len(stem) > 48:
        stem = stem[:48]
    if looks_like_map_type_only(stem, map_type):
        return "", None, None, None, preview_meta, "AI suggested map-type-only stem"
    return stem, (ai_map_type or None), (explanation or None), (image_summary or None), preview_meta, None


def read_sha256_index(index_path: Path) -> Dict[str, str]:
    try:
        if index_path.exists():
            data = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return dict((data.get("sha256_to_file") or {}) if isinstance(data.get("sha256_to_file"), dict) else {})
    except Exception:
        pass
    return {}


def write_sha256_index(index_path: Path, sha256_to_file: Dict[str, str]) -> None:
    payload = {
        "version": 1,
        "updated_at": utc_now_iso(),
        "sha256_to_file": sha256_to_file,
    }
    tmp = index_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(index_path)


def infer_scan_classification(
    *,
    image: Any,
    usages: List[TextureUsage],
    abs_path: Optional[Path],
    raw_filepath: str,
    exists: bool,
    project_root: Optional[Path],
    protected_roots: tuple[Path, ...],
    dest_root: Path,
) -> tuple[str, List[str]]:
    reasons: List[str] = []
    source_kind = (getattr(image, "source", "") or "").upper()
    is_packed = getattr(image, "packed_file", None) is not None
    is_linked_image = getattr(image, "library", None) is not None or bool_attr(image, "is_library_indirect")

    if is_packed:
        reasons.append("Packed image (embedded in .blend)")
    if source_kind in SKIP_IMAGE_SOURCES:
        reasons.append(f"Image source is {source_kind}")
    if is_linked_image:
        reasons.append("Image datablock is linked from a Blender library")

    linked_materials = sorted({u.material_name for u in usages if u.material_is_linked})
    if linked_materials:
        reasons.append("Used by linked material(s)")

    path_class = classify_path(abs_path, project_root=project_root, protected_roots=protected_roots)
    if path_class.kind == "PROTECTED_ROOT":
        reasons.append(path_class.reason)

    if source_kind and source_kind not in SUPPORTED_IMAGE_SOURCES and source_kind not in SKIP_IMAGE_SOURCES:
        return "UNSUPPORTED", reasons + [f"Unsupported image source: {source_kind}"]
    if source_kind in SKIP_IMAGE_SOURCES:
        return "GENERATED", reasons
    if is_packed:
        return "PACKED", reasons
    if is_linked_image or linked_materials or path_class.kind == "PROTECTED_ROOT":
        return "PROTECTED", reasons + ["Protected (linked/library/protected root)"]
    if abs_path is None:
        return "UNKNOWN", reasons
    if not exists and "<UDIM>" not in raw_filepath:
        return "MISSING", reasons + ["Resolved file does not exist"]

    try:
        if abs_path is not None and abs_path.is_file() and is_subpath(abs_path, dest_root):
            return "IN_TEXTURE_ROOT", reasons + ["Already inside texture root"]
    except Exception:
        pass

    if "<UDIM>" in raw_filepath:
        return "UDIM_SKIP", reasons

    if path_class.kind == "EXTERNAL":
        return "EXTERNAL_ADOPTABLE", reasons
    if path_class.kind == "IN_PROJECT":
        return "IN_PROJECT_ADOPTABLE", reasons
    return "ADOPTABLE", reasons


def canonical_filename_for_item(
    *,
    project_token: str,
    source_stem: str,
    map_type: str,
    ext: str,
) -> str:
    stem = sanitize_filename_stem(source_stem) or "Texture"
    clean_ext = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
    canonical = canonicalize_texture_stem(project_token=project_token, stem=stem, map_type=map_type)
    return f"{canonical}{clean_ext}"


def copy_texture_file(source: Path, dest: Path) -> None:
    shutil.copy2(str(source), str(dest))

