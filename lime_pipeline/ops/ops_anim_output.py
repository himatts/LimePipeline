"""
Animation Render Output Operators

Provides operators to configure Blender's render output path for animation
frames following Lime Pipeline conventions. The operators resolve the active
SHOT, scene number, revision letter, and project root to build folder structures
like:

    Animation/Rev X/SC010_SH03/[test/]{basename}_####

They create missing directories when possible and set the render filepath so
F11 renders write frames into standardized locations. Errors are reported with
actionable guidance when context is incomplete (no SHOT active, missing Rev,
etc.).
"""

from __future__ import annotations

from pathlib import Path

import bpy
from bpy.types import Operator

from ..core.naming import hydrate_state_from_filepath, resolve_project_name
from ..core.paths import paths_for_type
from ..core.validate_scene import active_shot_context, parse_shot_index


def _container_type_for_state(state) -> str:
    """Return container project type for animation outputs."""
    try:
        ptype = (getattr(state, "project_type", "") or "").strip().upper()
    except Exception:
        ptype = ""
    if ptype in {"ANIM", "REND"}:
        return ptype
    return "ANIM"


def _ensure_state(context) -> tuple[object, bpy.types.Scene]:
    scene = context.scene
    wm = context.window_manager
    state = getattr(wm, "lime_pipeline", None)
    if state is None:
        raise RuntimeError(
            "Estado Lime Pipeline no disponible. Abre 'Project Organization' para inicializarlo."
        )
    try:
        hydrate_state_from_filepath(state)
    except Exception:
        pass
    return state, scene


def _resolve_core_context(context) -> tuple[Path, str, int, int, str]:
    """Resolve root path, container type, scene number, shot index, and revision."""
    state, _scene = _ensure_state(context)

    root_str = (getattr(state, "project_root", "") or "").strip()
    if not root_str:
        raise RuntimeError("Project Root no detectado. Revisa 'Project Organization'.")
    root = Path(root_str)
    if not root.exists():
        raise RuntimeError(f"Project Root inválido o inaccesible: {root}")

    try:
        sc_number = int(getattr(state, "sc_number", 0) or 0)
    except Exception:
        sc_number = 0
    if sc_number <= 0:
        raise RuntimeError(
            "No se pudo resolver el número de escena (SC###). Normaliza el nombre del archivo o define SC en Project Organization."
        )

    rev = (getattr(state, "rev_letter", "") or "").strip().upper()
    if not rev:
        raise RuntimeError("Revisión no configurada. Define la Rev en Project Organization.")

    shot = active_shot_context(context)
    if shot is None:
        raise RuntimeError("No hay SHOT activo. Activa un SHOT en el Outliner.")
    shot_idx = parse_shot_index(getattr(shot, "name", ""))
    if shot_idx is None or shot_idx <= 0:
        raise RuntimeError(
            "No se pudo leer el índice del SHOT activo. Usa colecciones 'SHOT 01', 'SHOT 02', etc."
        )

    container_ptype = _container_type_for_state(state)
    return root, container_ptype, sc_number, shot_idx, rev


class _LimeSetAnimOutput(Operator):
    """Shared logic for animation output buttons."""

    bl_options = {"REGISTER"}
    output_label = "Animation Output"
    use_test_variant = False

    def execute(self, context):
        try:
            root, container_ptype, sc_number, shot_idx, rev = _resolve_core_context(context)
        except RuntimeError as ex:
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}
        except Exception as ex:  # Safety net
            self.report({"ERROR"}, f"Error preparando contexto: {ex}")
            return {"CANCELLED"}

        try:
            _ramv, folder_type, _scenes, _target, _backups = paths_for_type(
                root, container_ptype, rev, sc_number
            )
        except Exception as ex:
            self.report({"ERROR"}, f"No se pudo resolver carpeta RAMV: {ex}")
            return {"CANCELLED"}

        shot_token = f"SC{sc_number:03d}_SH{shot_idx:02d}"
        target_dir = folder_type / shot_token
        if self.use_test_variant:
            target_dir = target_dir / "test"
            basename = f"{shot_token}_test_"
            mode_label = "Test"
        else:
            basename = f"{shot_token}_"
            mode_label = "Final"

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception as ex:
            self.report({"ERROR"}, f"No se pudo crear la carpeta destino:\n{target_dir}\n{ex}")
            return {"CANCELLED"}

        output_path = target_dir / basename
        try:
            context.scene.render.filepath = str(output_path)
        except Exception as ex:
            self.report({"ERROR"}, f"Blender rechazó la ruta de salida: {ex}")
            return {"CANCELLED"}

        container_label = "Animation" if container_ptype == "ANIM" else "Renders"
        self.report(
            {"INFO"},
            f"{mode_label} output listo en {container_label}: {output_path}",
        )
        return {"FINISHED"}


class LIME_OT_set_anim_output_test(_LimeSetAnimOutput):
    bl_idname = "lime.set_anim_output_test"
    bl_label = "Set Anim Output: Test"
    bl_description = "Configura la salida de animación para pruebas rápidas (carpeta test/)"
    output_label = "Animation Output (Test)"
    use_test_variant = True


class LIME_OT_set_anim_output_final(_LimeSetAnimOutput):
    bl_idname = "lime.set_anim_output_final"
    bl_label = "Set Anim Output: Final"
    bl_description = "Configura la salida de animación final siguiendo la convención RAMV"
    output_label = "Animation Output (Final)"
    use_test_variant = False


class _LimeSetAnimOutputLocal(Operator):
    """Shared logic for local desktop animation output buttons."""

    bl_options = {"REGISTER"}
    output_label = "Animation Output (Local)"
    use_test_variant = False

    def execute(self, context):
        try:
            state, _scene = _ensure_state(context)
        except RuntimeError as ex:
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}
        except Exception as ex:
            self.report({"ERROR"}, f"Error preparando contexto: {ex}")
            return {"CANCELLED"}

        try:
            sc_number = int(getattr(state, "sc_number", 0) or 0)
        except Exception:
            sc_number = 0
        if sc_number <= 0:
            self.report({"ERROR"}, "No se pudo resolver el número de escena (SC###). Revisa Project Organization.")
            return {"CANCELLED"}

        shot = active_shot_context(context)
        if shot is None:
            self.report({"ERROR"}, "No hay SHOT activo. Activa un SHOT en el Outliner.")
            return {"CANCELLED"}
        shot_idx = parse_shot_index(getattr(shot, "name", ""))
        if shot_idx is None or shot_idx <= 0:
            self.report({"ERROR"}, "No se pudo leer el índice del SHOT activo. Usa colecciones 'SHOT 01', 'SHOT 02', etc.")
            return {"CANCELLED"}

        # Get project name
        project_name = resolve_project_name(state)
        if not project_name:
            self.report({"ERROR"}, "No se pudo obtener el nombre del proyecto. Revisa Project Organization.")
            return {"CANCELLED"}

        # Get desktop path
        try:
            desktop = Path.home() / "Desktop"
            if not desktop.exists():
                # Fallback for Windows OneDrive desktop
                desktop = Path.home() / "OneDrive" / "Desktop"
                if not desktop.exists():
                    raise RuntimeError(f"Escritorio no encontrado en: {desktop}")
        except Exception as ex:
            self.report({"ERROR"}, f"No se pudo acceder al escritorio: {ex}")
            return {"CANCELLED"}

        # Create project folder on desktop
        project_dir = desktop / project_name
        shot_token = f"SC{sc_number:03d}_SH{shot_idx:02d}"
        target_dir = project_dir / shot_token

        if self.use_test_variant:
            target_dir = target_dir / "test"
            basename = f"{shot_token}_test_"
            mode_label = "Test (Local)"
        else:
            basename = f"{shot_token}_"
            mode_label = "Final (Local)"

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception as ex:
            self.report({"ERROR"}, f"No se pudo crear la carpeta destino:\n{target_dir}\n{ex}")
            return {"CANCELLED"}

        output_path = target_dir / basename
        try:
            context.scene.render.filepath = str(output_path)
        except Exception as ex:
            self.report({"ERROR"}, f"Blender rechazó la ruta de salida: {ex}")
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            f"{mode_label} output listo en escritorio: {output_path}",
        )
        return {"FINISHED"}


class LIME_OT_set_anim_output_test_local(_LimeSetAnimOutputLocal):
    bl_idname = "lime.set_anim_output_test_local"
    bl_label = "Set Anim Output: Test (Local)"
    bl_description = "Configura la salida de animación para pruebas rápidas en el escritorio local"
    output_label = "Animation Output (Test Local)"
    use_test_variant = True


class LIME_OT_set_anim_output_final_local(_LimeSetAnimOutputLocal):
    bl_idname = "lime.set_anim_output_final_local"
    bl_label = "Set Anim Output: Final (Local)"
    bl_description = "Configura la salida de animación final en el escritorio local"
    output_label = "Animation Output (Final Local)"
    use_test_variant = False


__all__ = [
    "LIME_OT_set_anim_output_test",
    "LIME_OT_set_anim_output_final",
    "LIME_OT_set_anim_output_test_local",
    "LIME_OT_set_anim_output_final_local",
]

