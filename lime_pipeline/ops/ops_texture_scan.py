"""
Texture Scan/Report operator.

First deliverable for safer texture workflows:
- Detect images used by materials (Image Texture nodes, including nested groups).
- Classify them conservatively into:
  - Protected (linked/library/asset-library roots) -> never touch
  - External user paths (outside project root) -> candidates to adopt
  - In-project / packed / generated / missing -> report only
- Write a JSON report with proposed adoption destinations (no modifications).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import bpy
from bpy.types import Operator

from ..core.naming import find_project_root
from ..core.paths import get_ramv_dir
from ..core.texture_naming import canonicalize_texture_stem, sanitize_filename_stem, map_type_from_text
from ..core.naming import normalize_project_name, parse_blend_details
from ..core.texture_paths import classify_path


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
    """Yield image texture nodes from a node tree, recursing into groups."""
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
    """Return image pointer -> (image, usages)."""
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

            map_type = _infer_map_type(mat, node, image)
            usage = _Usage(
                material_name=getattr(mat, "name", "") or "",
                node_name=getattr(node, "name", "") or "",
                node_label=getattr(node, "label", "") or "",
                map_type=map_type,
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
    # De-duplicate while preserving order
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
    """Project-level shared texture folder: <RAMV>/RSC/Textures."""
    if project_root is not None:
        try:
            # Use lowercase to match existing project conventions and avoid ambiguity on case-sensitive shares.
            return get_ramv_dir(project_root) / "rsc" / "Textures"
        except Exception:
            pass
    return _blend_dir() / "rsc" / "Textures"


def _project_token_for_naming(*, project_root: Optional[Path]) -> str:
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

def _resolve_abs_image_path(image: Any) -> tuple[Optional[Path], List[str]]:
    reasons: List[str] = []
    raw = (getattr(image, "filepath", "") or "").strip()
    if not raw:
        return None, ["Image has no filepath"]

    if "<UDIM>" in raw:
        # Can't resolve deterministically without scanning tiles; treat as special.
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


def _exists_for_scan(abs_path: Optional[Path], *, raw_filepath: str) -> bool:
    if abs_path is None:
        return False
    if "<UDIM>" in (raw_filepath or ""):
        probe = str(abs_path).replace("<UDIM>", "1001")
        return os.path.isfile(probe)
    return os.path.isfile(str(abs_path))


def _propose_unique_destination(dest_dir: Path, filename: str) -> Path:
    dest_dir = dest_dir
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


def _relpath_for_blender(path: Path) -> str:
    if (getattr(bpy.data, "filepath", "") or "").strip():
        try:
            return bpy.path.relpath(str(path))
        except Exception:
            pass
    return str(path)


class LIME_OT_texture_scan_report(Operator):
    bl_idname = "lime.texture_scan_report"
    bl_label = "Scan Textures (Report)"
    bl_description = (
        "Scan material image textures, classify protected vs external paths, and write a JSON report. "
        "Does not modify files or relink images."
    )
    bl_options = {"REGISTER"}

    def execute(self, context):
        project_root = _deduce_project_root(context)
        protected_roots = _asset_library_roots_from_preferences(context)
        dest_root = _resolve_texture_root(project_root)
        project_token = _project_token_for_naming(project_root=project_root) or "Project"

        usage_by_image = _collect_image_usages_from_materials(getattr(bpy.data, "materials", []) or [])

        items: List[Dict[str, Any]] = []
        summary = {
            "total_images": 0,
            "protected": 0,
            "adoptable": 0,
            "external_adoptable": 0,
            "in_project_adoptable": 0,
            "in_project": 0,
            "missing": 0,
            "packed": 0,
            "generated": 0,
            "unsupported": 0,
            "unknown": 0,
            "already_in_texture_root": 0,
        }

        for _img_key, (image, usages) in usage_by_image.items():
            summary["total_images"] += 1
            reasons: List[str] = []

            source_kind = (getattr(image, "source", "") or "").upper()
            is_packed = getattr(image, "packed_file", None) is not None
            is_linked_image = getattr(image, "library", None) is not None or _bool_attr(image, "is_library_indirect")

            if is_packed:
                reasons.append("Packed image (embedded in .blend)")
            if source_kind in _SKIP_IMAGE_SOURCES:
                reasons.append(f"Image source is {source_kind}")

            raw_filepath = (getattr(image, "filepath", "") or "").strip()
            abs_path, path_reasons = _resolve_abs_image_path(image)
            reasons.extend(path_reasons)
            exists = _exists_for_scan(abs_path, raw_filepath=raw_filepath)

            if is_linked_image:
                reasons.append("Image datablock is linked from a Blender library")

            linked_materials = sorted({u.material_name for u in usages if u.material_is_linked})
            if linked_materials:
                reasons.append(f"Used by linked material(s): {', '.join(linked_materials[:5])}")
                if len(linked_materials) > 5:
                    reasons.append(f"...and {len(linked_materials) - 5} more linked material(s)")

            path_class = classify_path(
                abs_path,
                project_root=project_root,
                protected_roots=protected_roots,
            )
            if path_class.kind == "PROTECTED_ROOT":
                reasons.append(path_class.reason)

            classification = "UNKNOWN"
            proposal: Dict[str, Any] | None = None

            if source_kind and source_kind not in _SUPPORTED_IMAGE_SOURCES and source_kind not in _SKIP_IMAGE_SOURCES:
                classification = "UNSUPPORTED"
                reasons.append(f"Unsupported image source: {source_kind}")
                summary["unsupported"] += 1
            elif source_kind in _SKIP_IMAGE_SOURCES:
                classification = "GENERATED"
                summary["generated"] += 1
            elif is_packed:
                classification = "PACKED"
                summary["packed"] += 1
            elif is_linked_image or linked_materials or path_class.kind == "PROTECTED_ROOT":
                classification = "PROTECTED"
                summary["protected"] += 1
            elif abs_path is None:
                classification = "UNKNOWN"
                summary["unknown"] += 1
            elif not exists and "<UDIM>" not in raw_filepath:
                classification = "MISSING"
                reasons.append("Resolved file does not exist")
                summary["missing"] += 1
            else:
                # Adopt rule (centralize): any existing file texture not already under the texture root
                # is considered adoptable, regardless of being in-project or external. Protected cases
                # were handled above.
                is_already_in_texture_root = False
                try:
                    is_already_in_texture_root = abs_path is not None and abs_path.is_file() and abs_path.is_relative_to(dest_root)  # type: ignore[attr-defined]
                except Exception:
                    try:
                        is_already_in_texture_root = abs_path is not None and abs_path.is_file() and bool(abs_path.resolve().relative_to(dest_root.resolve()))
                    except Exception:
                        is_already_in_texture_root = False

                if is_already_in_texture_root:
                    classification = "IN_TEXTURE_ROOT"
                    summary["already_in_texture_root"] += 1
                else:
                    if path_class.kind == "EXTERNAL":
                        classification = "EXTERNAL_ADOPTABLE"
                        summary["external_adoptable"] += 1
                        summary["adoptable"] += 1
                    elif path_class.kind == "IN_PROJECT":
                        classification = "IN_PROJECT_ADOPTABLE"
                        summary["in_project_adoptable"] += 1
                        summary["adoptable"] += 1
                    else:
                        classification = "ADOPTABLE"
                        summary["adoptable"] += 1

                    first = usages[0] if usages else _Usage("", "", "", "Generic", False)
                    ext = (abs_path.suffix if abs_path is not None else "") or ".png"
                    ext = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
                    stem = sanitize_filename_stem(abs_path.stem if abs_path is not None else "") or "Texture"
                    canonical_stem = canonicalize_texture_stem(project_token=project_token, stem=stem, map_type=first.map_type)
                    proposed_name = f"{canonical_stem}{ext}"
                    dest_path = _propose_unique_destination(dest_root, proposed_name)
                    proposal = {
                        "action": "ADOPT",
                        "dest_dir": str(dest_root),
                        "dest_path": str(dest_path),
                        "dest_blender_path": _relpath_for_blender(dest_path),
                        "new_image_name": dest_path.stem,
                    }

            used_by = [
                {
                    "material": u.material_name,
                    "node": u.node_name,
                    "label": u.node_label,
                    "map_type": u.map_type,
                    "material_is_linked": u.material_is_linked,
                }
                for u in usages
            ]

            items.append(
                {
                    "image_name": getattr(image, "name", "") or "",
                    "image_source": source_kind,
                    "raw_filepath": raw_filepath,
                    "abs_filepath": str(abs_path) if abs_path is not None else "",
                    "exists": bool(exists),
                    "is_packed": bool(is_packed),
                    "is_linked_image": bool(is_linked_image),
                    "classification": classification,
                    "reasons": reasons,
                    "used_by": used_by,
                    "proposal": proposal,
                }
            )

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "blend_filepath": (getattr(bpy.data, "filepath", "") or "").strip(),
            "blend_dir": str(_blend_dir()),
            "project_root": str(project_root) if project_root is not None else None,
            "asset_library_roots": [str(p) for p in protected_roots],
            "proposed_texture_root": str(dest_root),
            "summary": summary,
            "items": items,
        }

        report_dir = dest_root / "_manifests"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_path = report_dir / f"texture_scan_{timestamp}.json"
        try:
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as ex:
            self.report({"ERROR"}, f"Failed writing texture scan report: {ex}")
            return {"CANCELLED"}

        adoptable = summary.get("external_adoptable", 0)
        adoptable_total = summary.get("adoptable", 0)
        protected = summary.get("protected", 0)
        missing = summary.get("missing", 0)
        self.report(
            {"INFO"},
            f"Texture scan complete. Adoptable: {adoptable_total} (external: {adoptable}), Protected: {protected}, Missing: {missing}. "
            f"Report: {report_path}",
        )
        try:
            print("[Lime Pipeline] Texture scan report written:", str(report_path))
        except Exception:
            pass
        return {"FINISHED"}


__all__ = [
    "LIME_OT_texture_scan_report",
]
