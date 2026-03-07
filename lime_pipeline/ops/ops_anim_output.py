"""
Animation Render Output Operators

Provides operators to configure Blender's render output path for animation
frames following Lime Pipeline conventions.
"""

from __future__ import annotations

from pathlib import Path

import bpy
from bpy.types import Operator

from ..core.anim_output_paths import (
    build_local_anim_output_path,
    build_pipeline_anim_output_path,
)
from ..core.naming import hydrate_state_from_filepath, resolve_project_name, RE_PROJECT_DIR
from ..core.validate_scene import active_shot_context, parse_shot_index


def _container_type_for_state(state) -> str:
    """Return the container project type for animation outputs."""
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
            "Lime Pipeline state is not available. Open Project Organization first."
        )
    try:
        hydrate_state_from_filepath(state)
    except Exception:
        pass
    return state, scene


def _resolve_core_context(context) -> tuple[object, Path, str, int, int, str]:
    """Resolve Lime state, root path, container type, scene number, shot index, and revision."""
    state, _scene = _ensure_state(context)

    root_str = (getattr(state, "project_root", "") or "").strip()
    if not root_str:
        raise RuntimeError("Project Root was not detected. Check Project Organization.")
    root = Path(root_str)
    if not root.exists():
        raise RuntimeError(f"Project Root is invalid or inaccessible: {root}")

    try:
        sc_number = int(getattr(state, "sc_number", 0) or 0)
    except Exception:
        sc_number = 0
    if sc_number <= 0:
        raise RuntimeError(
            "Scene number (SC###) could not be resolved. Normalize the blend filename or set SC in Project Organization."
        )

    rev = (getattr(state, "rev_letter", "") or "").strip().upper()
    if not rev:
        raise RuntimeError("Revision is not configured. Set Rev in Project Organization.")

    shot = active_shot_context(context)
    if shot is None:
        raise RuntimeError("No active SHOT was found. Activate a SHOT collection in the Outliner.")
    shot_idx = parse_shot_index(getattr(shot, "name", ""))
    if shot_idx is None or shot_idx <= 0:
        raise RuntimeError(
            "Could not read the active SHOT index. Use collection names like 'SHOT 01' or 'SHOT 02'."
        )

    container_ptype = _container_type_for_state(state)
    return state, root, container_ptype, sc_number, shot_idx, rev


def _resolve_local_output_base_dir(context) -> Path:
    """Resolve the configured local output base directory."""
    try:
        prefs = context.preferences.addons[__package__.split(".")[0]].preferences
        base_dir = (getattr(prefs, "local_projects_root", "") or "").strip()
    except Exception:
        base_dir = ""

    if base_dir:
        return Path(base_dir)

    desktop = Path.home() / "Desktop"
    if desktop.exists():
        return desktop

    return Path.home() / "OneDrive" / "Desktop"


class _LimeSetAnimOutput(Operator):
    """Shared logic for animation output buttons."""

    bl_options = {"REGISTER"}
    output_label = "Animation Output"
    use_test_variant = False

    def execute(self, context):
        try:
            state, root, container_ptype, sc_number, shot_idx, rev = _resolve_core_context(context)
        except RuntimeError as ex:
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}
        except Exception as ex:
            self.report({"ERROR"}, f"Error preparing the render context: {ex}")
            return {"CANCELLED"}

        local_mode = bool(getattr(state, "use_local_project", False))
        try:
            if local_mode:
                project_name = resolve_project_name(state)
                if not project_name:
                    self.report({"ERROR"}, "Project name could not be resolved. Check Project Organization.")
                    return {"CANCELLED"}
                output_path = build_local_anim_output_path(
                    _resolve_local_output_base_dir(context),
                    project_name,
                    sc_number,
                    shot_idx,
                    use_test_variant=self.use_test_variant,
                )
                container_label = "Local"
            else:
                output_path = build_pipeline_anim_output_path(
                    root,
                    container_ptype,
                    rev,
                    sc_number,
                    shot_idx,
                    use_test_variant=self.use_test_variant,
                    local_mode=False,
                )
                container_label = "Animation" if container_ptype == "ANIM" else "Renders"
        except Exception as ex:
            self.report({"ERROR"}, f"Could not resolve the animation output path: {ex}")
            return {"CANCELLED"}

        target_dir = output_path.parent
        mode_label = "Test" if self.use_test_variant else "Final"

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception as ex:
            self.report({"ERROR"}, f"Could not create the target folder:\n{target_dir}\n{ex}")
            return {"CANCELLED"}

        try:
            context.scene.render.filepath = str(output_path)
        except Exception as ex:
            self.report({"ERROR"}, f"Blender rejected the output path: {ex}")
            return {"CANCELLED"}

        self.report({"INFO"}, f"{mode_label} animation output set to {container_label}: {output_path}")
        return {"FINISHED"}


class LIME_OT_set_anim_output_test(_LimeSetAnimOutput):
    bl_idname = "lime.set_anim_output_test"
    bl_label = "Set Anim Output: Test"
    bl_description = "Set the animation output path for quick tests"
    output_label = "Animation Output (Test)"
    use_test_variant = True


class LIME_OT_set_anim_output_final(_LimeSetAnimOutput):
    bl_idname = "lime.set_anim_output_final"
    bl_label = "Set Anim Output: Final"
    bl_description = "Set the final animation output path following Lime conventions"
    output_label = "Animation Output (Final)"
    use_test_variant = False


class _LimeSetAnimOutputLocal(Operator):
    """Shared logic for local animation output buttons."""

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
            self.report({"ERROR"}, f"Error preparing the render context: {ex}")
            return {"CANCELLED"}

        try:
            sc_number = int(getattr(state, "sc_number", 0) or 0)
        except Exception:
            sc_number = 0
        if sc_number <= 0:
            self.report({"ERROR"}, "Scene number (SC###) could not be resolved. Check Project Organization.")
            return {"CANCELLED"}

        shot = active_shot_context(context)
        if shot is None:
            self.report({"ERROR"}, "No active SHOT was found. Activate a SHOT collection in the Outliner.")
            return {"CANCELLED"}
        shot_idx = parse_shot_index(getattr(shot, "name", ""))
        if shot_idx is None or shot_idx <= 0:
            self.report({"ERROR"}, "Could not read the active SHOT index. Use 'SHOT 01', 'SHOT 02', etc.")
            return {"CANCELLED"}

        if not getattr(state, "use_local_project", False):
            try:
                root_name = Path(getattr(state, "project_root", "") or "").name
                if root_name and not RE_PROJECT_DIR.match(root_name) and not getattr(state, "use_custom_name", False):
                    self.report(
                        {"WARNING"},
                        "Project Root does not look like a project folder; the local project name may be inaccurate.",
                    )
            except Exception:
                pass

        project_name = resolve_project_name(state)
        if not project_name:
            self.report({"ERROR"}, "Project name could not be resolved. Check Project Organization.")
            return {"CANCELLED"}

        try:
            output_path = build_local_anim_output_path(
                _resolve_local_output_base_dir(context),
                project_name,
                sc_number,
                shot_idx,
                use_test_variant=self.use_test_variant,
            )
        except Exception as ex:
            self.report({"ERROR"}, f"Could not resolve the local output path: {ex}")
            return {"CANCELLED"}

        target_dir = output_path.parent
        mode_label = "Test (Local)" if self.use_test_variant else "Final (Local)"

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception as ex:
            self.report({"ERROR"}, f"Could not create the target folder:\n{target_dir}\n{ex}")
            return {"CANCELLED"}

        try:
            context.scene.render.filepath = str(output_path)
        except Exception as ex:
            self.report({"ERROR"}, f"Blender rejected the output path: {ex}")
            return {"CANCELLED"}

        self.report({"INFO"}, f"{mode_label} animation output set to local: {output_path}")
        return {"FINISHED"}


class LIME_OT_set_anim_output_test_local(_LimeSetAnimOutputLocal):
    bl_idname = "lime.set_anim_output_test_local"
    bl_label = "Set Anim Output: Test (Local)"
    bl_description = "Set the local animation output path for quick tests"
    output_label = "Animation Output (Test Local)"
    use_test_variant = True


class LIME_OT_set_anim_output_final_local(_LimeSetAnimOutputLocal):
    bl_idname = "lime.set_anim_output_final_local"
    bl_label = "Set Anim Output: Final (Local)"
    bl_description = "Set the final local animation output path"
    output_label = "Animation Output (Final Local)"
    use_test_variant = False


__all__ = [
    "LIME_OT_set_anim_output_test",
    "LIME_OT_set_anim_output_final",
    "LIME_OT_set_anim_output_test_local",
    "LIME_OT_set_anim_output_final_local",
]
