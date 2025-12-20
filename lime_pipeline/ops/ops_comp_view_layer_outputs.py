"""Compositor utilities for per-View Layer outputs."""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata

import bpy
from bpy.types import Operator

from ..core.naming import hydrate_state_from_filepath
from ..core.naming import parse_blend_details
from ..core.paths import RAMV_DIR_1
from ..core.paths import paths_for_type
from ..core.validate_scene import active_shot_context, parse_shot_index


_NODE_PREFIX = "LP_VL_"


def _normalize_layer_name(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return "LAYER"
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", normalized).strip("_")
    return cleaned.upper() if cleaned else "LAYER"


def _ensure_state(context) -> tuple[object, bpy.types.Scene]:
    scene = context.scene
    wm = context.window_manager
    state = getattr(wm, "lime_pipeline", None)
    if state is None:
        raise RuntimeError("Estado Lime Pipeline no disponible. Abre 'Project Organization' para inicializarlo.")
    try:
        hydrate_state_from_filepath(state)
    except Exception:
        pass
    return state, scene


def _infer_project_root_and_mode() -> tuple[Path, str] | None:
    """Infer project root and layout mode from current .blend path.

    Returns (root, mode) where mode is "RAMV" or "LOCAL".
    """
    try:
        blend_path = Path(getattr(bpy.data, "filepath", "") or "")
    except Exception:
        return None
    if not blend_path or not blend_path.exists():
        return None
    current = blend_path.parent
    for parent in (current,) + tuple(current.parents):
        if parent.name == RAMV_DIR_1:
            return parent.parent, "RAMV"
    for parent in (current,) + tuple(current.parents):
        if parent.name.lower() in {"animation", "renders", "proposal views", "storyboard", "3d base model", "tmp"}:
            return parent.parent, "LOCAL"
    return None


def _resolve_core_context(context) -> tuple[object, bpy.types.Scene, Path, int, int, str, bool]:
    state, scene = _ensure_state(context)

    try:
        print("[LP][VL] Debug: use_local_project =", bool(getattr(state, "use_local_project", False)))
        print("[LP][VL] Debug: state.project_root =", getattr(state, "project_root", None))
        print("[LP][VL] Debug: state.sc_number =", getattr(state, "sc_number", None))
        print("[LP][VL] Debug: state.rev_letter =", getattr(state, "rev_letter", None))
        print("[LP][VL] Debug: bpy.data.filepath =", getattr(bpy.data, "filepath", ""))
    except Exception:
        pass

    inferred_mode = None
    root_str = (getattr(state, "project_root", "") or "").strip()
    if not root_str:
        inferred = _infer_project_root_and_mode()
        inferred_mode = inferred[1] if inferred else None
        try:
            print("[LP][VL] Debug: inferred root/mode =", inferred)
        except Exception:
            pass
        if inferred is not None:
            state.project_root = str(inferred[0])
            root_str = str(inferred[0])
    local_mode = bool(getattr(state, "use_local_project", False)) or inferred_mode == "LOCAL"

    if not root_str:
        try:
            print("[LP][VL] Debug: project_root still empty after inference")
        except Exception:
            pass
        raise RuntimeError("Project Root no detectado. Revisa 'Project Organization'.")
    root = Path(root_str)
    if not root.exists():
        try:
            print("[LP][VL] Debug: project_root not found on disk =", root)
        except Exception:
            pass
        raise RuntimeError(f"Project Root invalido o inaccesible: {root}")

    try:
        sc_number = int(getattr(state, "sc_number", 0) or 0)
    except Exception:
        sc_number = 0
    if sc_number <= 0:
        info = parse_blend_details(getattr(bpy.data, "filepath", "") or "")
        try:
            print("[LP][VL] Debug: parse_blend_details for SC =", info)
        except Exception:
            pass
        if info and info.get("sc"):
            sc_number = int(info["sc"])
        if sc_number <= 0:
            raise RuntimeError(
                "No se pudo resolver el numero de escena (SC###). Normaliza el nombre del archivo o define SC en Project Organization."
            )

    rev = (getattr(state, "rev_letter", "") or "").strip().upper()
    if not rev:
        info = parse_blend_details(getattr(bpy.data, "filepath", "") or "")
        try:
            print("[LP][VL] Debug: parse_blend_details for Rev =", info)
        except Exception:
            pass
        if info and info.get("rev"):
            rev = info["rev"]
        if not rev:
            raise RuntimeError("Revision no configurada. Define la Rev en Project Organization.")

    shot = active_shot_context(context)
    if shot is None:
        raise RuntimeError("No hay SHOT activo. Activa un SHOT en el Outliner.")
    shot_idx = parse_shot_index(getattr(shot, "name", ""))
    if shot_idx is None or shot_idx <= 0:
        raise RuntimeError("No se pudo leer el indice del SHOT activo. Usa colecciones 'SHOT 01', 'SHOT 02', etc.")

    return state, scene, root, sc_number, shot_idx, rev, local_mode


def _apply_output_format(node: bpy.types.Node, fmt_key: str) -> None:
    fmt = getattr(node, "format", None)
    if fmt is None:
        return
    key = (fmt_key or "EXR").upper()
    if key == "PNG":
        fmt.file_format = "PNG"
        fmt.color_mode = "RGBA"
        fmt.color_depth = "16"
        return
    fmt.file_format = "OPEN_EXR"
    fmt.color_mode = "RGBA"
    fmt.color_depth = "16"
    try:
        fmt.exr_codec = "DWAA"
    except Exception:
        pass


def _ensure_node(nodes: bpy.types.Nodes, node_id: str, name: str) -> bpy.types.Node:
    existing = nodes.get(name)
    if existing and getattr(existing, "bl_idname", "") == node_id:
        return existing
    if existing:
        try:
            nodes.remove(existing)
        except Exception:
            pass
    node = nodes.new(node_id)
    node.name = name
    return node


class LIME_OT_setup_view_layer_outputs(Operator):
    """Create or refresh compositor outputs for each View Layer (excluding Complete)."""

    bl_idname = "lime.setup_view_layer_outputs"
    bl_label = "Setup View Layer Outputs"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, ctx):
        scene = getattr(ctx, "scene", None)
        view_layer = getattr(ctx, "view_layer", None)
        if scene is None or view_layer is None:
            return False
        shot = active_shot_context(ctx)
        return shot is not None

    def execute(self, context):
        try:
            state, scene, root, sc_number, shot_idx, rev, local_mode = _resolve_core_context(context)
        except RuntimeError as ex:
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}
        except Exception as ex:
            self.report({"ERROR"}, f"Error preparando contexto: {ex}")
            return {"CANCELLED"}

        try:
            _ramv, folder_type, _scenes, target_dir, _backups = paths_for_type(
                root,
                "ANIM",
                rev,
                sc_number,
                local=local_mode,
            )
        except Exception as ex:
            self.report({"ERROR"}, f"No se pudo resolver carpeta RAMV: {ex}")
            return {"CANCELLED"}

        shot_token = f"SC{sc_number:03d}_SH{shot_idx:02d}"

        view_layers = [
            vl for vl in scene.view_layers
            if (getattr(vl, "name", "") or "").strip().lower() != "complete"
        ]
        if not view_layers:
            self.report({"ERROR"}, "No hay View Layers exportables (Complete excluido).")
            return {"CANCELLED"}

        try:
            scene.use_nodes = True
        except Exception:
            pass
        node_tree = getattr(scene, "node_tree", None)
        if node_tree is None:
            self.report({"ERROR"}, "Compositor no disponible en esta escena.")
            return {"CANCELLED"}

        nodes = node_tree.nodes
        links = node_tree.links

        fmt_key = (getattr(state, "view_layer_output_format", "") or "EXR").upper()

        used_names = {}
        def _unique_name(base: str) -> str:
            count = used_names.get(base, 0)
            used_names[base] = count + 1
            return base if count == 0 else f"{base}_{count + 1}"

        keep_nodes: set[str] = set()
        base_x = 0
        base_y = 0
        step_y = -240
        out_x = 340

        for idx, layer in enumerate(view_layers):
            raw_name = getattr(layer, "name", "") or ""
            normalized = _unique_name(_normalize_layer_name(raw_name))

            render_name = f"{_NODE_PREFIX}RL_{normalized}"
            output_name = f"{_NODE_PREFIX}OUT_{normalized}"
            keep_nodes.update({render_name, output_name})

            render_node = _ensure_node(nodes, "CompositorNodeRLayers", render_name)
            output_node = _ensure_node(nodes, "CompositorNodeOutputFile", output_name)

            try:
                render_node.layer = raw_name
            except Exception:
                pass
            render_node.label = raw_name
            output_node.label = normalized

            layer_dir = target_dir / shot_token / normalized
            try:
                layer_dir.mkdir(parents=True, exist_ok=True)
            except Exception as ex:
                self.report({"ERROR"}, f"No se pudo crear carpeta destino:\n{layer_dir}\n{ex}")
                return {"CANCELLED"}

            try:
                output_node.base_path = str(layer_dir)
            except Exception:
                pass

            try:
                slots = getattr(output_node, "file_slots", None)
                if slots and len(slots) > 0:
                    slot = slots[0]
                elif slots:
                    slot = slots.new("Image")
                else:
                    slot = None
                if slot is not None:
                    slot.path = f"{shot_token}_{normalized}_"
            except Exception:
                pass

            _apply_output_format(output_node, fmt_key)

            out_socket = output_node.inputs.get("Image") if output_node.inputs else None
            if out_socket is None and output_node.inputs:
                out_socket = output_node.inputs[0]
            if out_socket is not None:
                for link in list(out_socket.links):
                    try:
                        links.remove(link)
                    except Exception:
                        pass
                image_out = render_node.outputs.get("Image") if render_node.outputs else None
                if image_out is None and render_node.outputs:
                    image_out = render_node.outputs[0]
                if image_out is not None:
                    try:
                        links.new(image_out, out_socket)
                    except Exception:
                        pass

            try:
                render_node.location = (base_x, base_y + idx * step_y)
                output_node.location = (base_x + out_x, base_y + idx * step_y)
            except Exception:
                pass

        for node in list(nodes):
            if node.name.startswith(_NODE_PREFIX) and node.name not in keep_nodes:
                try:
                    nodes.remove(node)
                except Exception:
                    pass

        self.report({"INFO"}, "View Layer outputs configurados")
        return {"FINISHED"}


__all__ = [
    "LIME_OT_setup_view_layer_outputs",
]
