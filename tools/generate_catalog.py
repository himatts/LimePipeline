import argparse
import ast
import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional, Dict, Tuple


LIME_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
PKG_ROOT = os.path.join(LIME_ROOT, "lime_pipeline")
DOCS_ROOT = os.path.join(LIME_ROOT, "docs")


BLENDER_BASES = {"Panel", "Operator", "PropertyGroup", "UIList"}


@dataclass
class ClassInfo:
    name: str
    bases: List[str]
    bl_idname: Optional[str] = None
    bl_label: Optional[str] = None
    bl_space_type: Optional[str] = None
    bl_region_type: Optional[str] = None
    bl_category: Optional[str] = None
    doc: Optional[str] = None


@dataclass
class ModuleInfo:
    path: str
    package: str
    rel_path: str
    doc: str
    classes: List[ClassInfo]
    internal_deps: List[str]


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def iter_python_files(base: str) -> List[str]:
    results: List[str] = []
    for root, _dirs, files in os.walk(base):
        for name in files:
            if name.endswith(".py") and not name.startswith("__pycache__"):
                results.append(os.path.join(root, name))
    return sorted(results)


def detect_package(rel_path: str) -> str:
    parts = rel_path.replace("\\", "/").split("/")
    if len(parts) >= 2:
        return parts[1]
    return "misc"


def extract_internal_deps(tree: ast.AST) -> List[str]:
    deps: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("lime_pipeline"):
                    deps.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("lime_pipeline"):
                deps.append(node.module)
    return sorted(set(deps))


def get_base_names(bases: List[ast.expr]) -> List[str]:
    names: List[str] = []
    for b in bases:
        if isinstance(b, ast.Attribute):
            # e.g., bpy.types.Panel
            names.append(b.attr)
        elif isinstance(b, ast.Name):
            names.append(b.id)
        elif isinstance(b, ast.Subscript):
            # generics not expected, but be safe
            if isinstance(b.value, ast.Name):
                names.append(b.value.id)
    return names


def get_assign_str(class_body: List[ast.stmt], target_name: str) -> Optional[str]:
    for stmt in class_body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == target_name:
                    if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                        return stmt.value.value
    return None


def summarize(text: Optional[str], max_lines: int = 3) -> str:
    if not text:
        return ""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    return " ".join(lines[:max_lines])


def parse_module(path: str) -> ModuleInfo:
    rel = os.path.relpath(path, LIME_ROOT)
    src = read_text(path)
    tree = ast.parse(src)
    mod_doc = ast.get_docstring(tree) or ""

    classes: List[ClassInfo] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = get_base_names(node.bases)
            if any(base in BLENDER_BASES for base in bases):
                ci = ClassInfo(
                    name=node.name,
                    bases=bases,
                    bl_idname=get_assign_str(node.body, "bl_idname"),
                    bl_label=get_assign_str(node.body, "bl_label"),
                    bl_space_type=get_assign_str(node.body, "bl_space_type"),
                    bl_region_type=get_assign_str(node.body, "bl_region_type"),
                    bl_category=get_assign_str(node.body, "bl_category"),
                    doc=ast.get_docstring(node) or None,
                )
                classes.append(ci)

    deps = extract_internal_deps(tree)
    package = detect_package(rel)
    return ModuleInfo(path=path, package=package, rel_path=rel.replace("\\", "/"), doc=mod_doc, classes=classes, internal_deps=deps)


def render_catalog_index(by_package: Dict[str, List[ModuleInfo]]) -> str:
    lines: List[str] = []
    lines.append("# Catálogo por archivo — Índice\n")
    lines.append("Este índice se generó automáticamente a partir del código.\n\n")
    for pkg in ("ui", "ops", "core", "scene"):
        if pkg in by_package:
            lines.append(f"- [{pkg.upper()}](" + pkg + ".md)\n")
    return "".join(lines)


def render_package_page(package: str, modules: List[ModuleInfo]) -> str:
    lines: List[str] = []
    lines.append(f"# {package.upper()} — Catálogo por archivo\n\n")
    for mi in modules:
        anchor = mi.rel_path.replace("/", "-")
        lines.append(f"## {mi.rel_path}\n\n")
        # Mostrar docstring COMPLETO sin truncar
        full_doc = mi.doc.strip() if mi.doc else ""
        if full_doc:
            lines.append(f"{full_doc}\n\n")
        else:
            lines.append("(sin docstring de módulo)\n\n")
        
        if mi.classes:
            lines.append("Clases Blender detectadas:\n\n")
            for c in mi.classes:
                cls_line = f"- {c.name} ({', '.join(c.bases)})"
                meta: List[str] = []
                for key in ("bl_idname", "bl_label", "bl_space_type", "bl_region_type", "bl_category"):
                    val = getattr(c, key)
                    if val:
                        meta.append(f"{key}={val}")
                if meta:
                    cls_line += ": " + ", ".join(meta)
                lines.append(cls_line + "\n")
            lines.append("\n")
        if mi.internal_deps:
            lines.append("Dependencias internas: " + ", ".join(mi.internal_deps) + "\n\n")
    return "".join(lines)


def write_checkpoint(package: str, processed: List[ModuleInfo], checkpoint_file: str, next_hint: Optional[str]) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: List[str] = []
    lines.append(f"# Checkpoint de documentación — {ts}\n")
    lines.append("## Bloque procesado\n")
    lines.append(f"- Paquete: {package}/\n")
    lines.append(f"- Archivos: {len(processed)}\n\n")

    # Tally
    num_panels = sum(1 for m in processed for c in m.classes if "Panel" in c.bases)
    num_ops = sum(1 for m in processed for c in m.classes if "Operator" in c.bases)
    num_props = sum(1 for m in processed for c in m.classes if "PropertyGroup" in c.bases)

    lines.append("## Resumen de lo documentado\n")
    lines.append(f"- Paneles detectados: {num_panels}  | Operators: {num_ops}  | PropertyGroups: {num_props}\n\n")

    lines.append("## Cobertura por archivo (extracto)\n")
    for m in processed[:10]:
        brief = summarize(m.doc, 1) or m.rel_path
        dep = (", dep: " + m.internal_deps[0]) if m.internal_deps else ""
        lines.append(f"- {m.rel_path} — {brief}{dep}\n")
    lines.append("\n")

    lines.append("## Recomendación de continuación\n")
    if next_hint:
        lines.append(f"- Siguiente bloque sugerido: {next_hint}\n")
    else:
        lines.append("- Siguiente bloque sugerido: ops/ (límite 10 archivos)\n")

    write_text(checkpoint_file, "".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate per-file catalog for Lime Pipeline")
    parser.add_argument("--path", type=str, default=PKG_ROOT, help="Path to file or directory to process")
    parser.add_argument("--package", type=str, default=None, help="Filter by top-level package (ui|ops|core|scene)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of files to process (0 = sin límite)")
    parser.add_argument("--checkpoint-file", type=str, default=os.path.join(DOCS_ROOT, "para-IA", "last_checkpoint.md"))
    parser.add_argument("--resume-from", type=str, default=None, help="Resume from relative path")
    parser.add_argument("--json-out", type=str, default=os.path.join(LIME_ROOT, "tools", "catalog.json"))
    parser.add_argument("--full", action="store_true", help="Generate complete catalog for all packages (ignora límites)")
    args = parser.parse_args()

    # Si --full, procesamos TODO sin límites
    if args.full:
        args.limit = 0
        args.package = None

    # Collect files
    paths: List[str] = []
    if os.path.isdir(args.path):
        paths = [p for p in iter_python_files(args.path) if p.endswith(".py")]
    elif os.path.isfile(args.path) and args.path.endswith(".py"):
        paths = [args.path]

    # Normalize and filter
    modules: List[ModuleInfo] = []
    resume_hit = args.resume_from is None
    for p in paths:
        rel = os.path.relpath(p, LIME_ROOT).replace("\\", "/")
        pkg = detect_package(rel)
        if args.package and pkg != args.package:
            continue
        if not resume_hit:
            if rel == args.resume_from:
                resume_hit = True
            else:
                continue
        modules.append(parse_module(p))
        if args.limit and len(modules) >= args.limit:
            break

    # Group by package
    by_pkg: Dict[str, List[ModuleInfo]] = {}
    for m in modules:
        by_pkg.setdefault(m.package, []).append(m)

    # Write per-package pages
    for pkg, mods in by_pkg.items():
        pkg_md = render_package_page(pkg, mods)
        write_text(os.path.join(DOCS_ROOT, "catalogo", f"{pkg}.md"), pkg_md)

    # Update index (incluye TODOS los paquetes posibles, no solo los procesados)
    all_packages = {}
    for pkg in ("ui", "ops", "core", "scene"):
        pkg_file = os.path.join(DOCS_ROOT, "catalogo", f"{pkg}.md")
        if os.path.exists(pkg_file):
            # Leer el archivo para confirmar que tiene contenido
            content = read_text(pkg_file)
            if len(content) > 50:  # Más que solo headers
                all_packages[pkg] = [ModuleInfo("", pkg, "", "", [], [])]
    
    index_md = render_catalog_index(all_packages)
    write_text(os.path.join(DOCS_ROOT, "catalogo", "index.md"), index_md)

    # Write json summary
    summary = {m.rel_path: {
        "package": m.package,
        "doc": summarize(m.doc, 3),
        "classes": [asdict(c) for c in m.classes],
        "internal_deps": m.internal_deps,
    } for m in modules}
    write_text(args.json_out, json.dumps(summary, indent=2, ensure_ascii=False))

    # Checkpoint
    next_hint = None
    if args.package == "ui":
        next_hint = "ops/"
    elif args.package == "ops":
        next_hint = "core/"
    elif args.package == "core":
        next_hint = "scene/"
    
    write_checkpoint(args.package or "complete", modules, args.checkpoint_file, next_hint)


if __name__ == "__main__":
    main()


