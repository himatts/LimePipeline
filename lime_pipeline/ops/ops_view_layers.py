"""Operators to configure standard view layers for Lime Pipeline shots."""

from __future__ import annotations

import bpy
from bpy.types import Operator

from ..core import validate_scene
from ..core.naming import resolve_project_name
from ..scene.scene_utils import (
    ensure_stage_collections,
    configure_stage_view_layer,
)


def _reset_render_passes(view_layer: bpy.types.ViewLayer | None) -> None:
    if view_layer is None:
        return

    rna = getattr(view_layer, "bl_rna", None)
    props = getattr(rna, "properties", []) if rna else []
    for prop in props:
        ident = getattr(prop, "identifier", "")
        if not ident.startswith("use_pass_"):
            continue
        try:
            setattr(view_layer, ident, ident == "use_pass_combined")
        except Exception:
            pass


def _ensure_outliner_columns() -> None:
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return
    for window in getattr(wm, "windows", []) or []:
        screen = getattr(window, "screen", None)
        if screen is None:
            continue
        for area in getattr(screen, "areas", []) or []:
            if getattr(area, "type", "") != 'OUTLINER':
                continue
            for space in getattr(area, "spaces", []) or []:
                if getattr(space, "type", "") != 'OUTLINER':
                    continue
                try:
                    space.show_restrict_column_indirect_only = True
                except Exception:
                    pass
                try:
                    space.show_restrict_column_holdout = True
                except Exception:
                    pass


class LIME_OT_create_view_layers(Operator):
    """Create standard stage view layers (Complete/BG/Main)."""

    bl_idname = "lime.create_view_layers"
    bl_label = "Create View Layers"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        scene = getattr(ctx, "scene", None)
        view_layer = getattr(ctx, "view_layer", None)
        if scene is None or view_layer is None:
            return False
        shot = validate_scene.active_shot_context(ctx)
        return shot is not None

    def execute(self, context):
        scene = getattr(context, "scene", None)
        view_layer = getattr(context, "view_layer", None)
        if scene is None or view_layer is None:
            self.report({'ERROR'}, "Scene/View Layer unavailable")
            return {'CANCELLED'}

        shot_active = validate_scene.active_shot_context(context)
        if shot_active is None:
            self.report({'ERROR'}, "Activate a collection inside a SHOT to continue")
            return {'CANCELLED'}

        wm_state = getattr(context.window_manager, "lime_pipeline", None)
        if wm_state is None:
            self.report({'ERROR'}, "Lime Pipeline state unavailable")
            return {'CANCELLED'}

        try:
            project_name = resolve_project_name(wm_state)
        except Exception:
            self.report({'ERROR'}, "Unable to resolve project name")
            return {'CANCELLED'}

        shots = validate_scene.list_shot_roots(scene)
        if not shots:
            self.report({'ERROR'}, "No SHOT collections found")
            return {'CANCELLED'}

        stage_infos: list[tuple[bpy.types.Collection, dict[str, bpy.types.Collection | None]]] = []
        missing_bg: list[str] = []
        for shot_coll, _idx in shots:
            stage = ensure_stage_collections(shot_coll, project_name)
            if not stage.get("bg"):
                missing_bg.append(getattr(shot_coll, "name", "Unknown"))
            stage_infos.append((shot_coll, stage))

        if missing_bg:
            joined = ", ".join(sorted(missing_bg))
            self.report({'ERROR'}, f"Background collection missing for SHOT(s): {joined}")
            return {'CANCELLED'}

        complete_layer = scene.view_layers.get("Complete")
        if complete_layer is None:
            target_layer = view_layer
            if target_layer is None:
                self.report({'ERROR'}, "Active View Layer unavailable to rename")
                return {'CANCELLED'}
            try:
                target_layer.name = "Complete"
            except Exception:
                self.report({'ERROR'}, "Failed to rename active View Layer to 'Complete'")
                return {'CANCELLED'}
            complete_layer = target_layer

        # Ensure BG layer
        bg_layer = scene.view_layers.get("BG")
        if bg_layer is None:
            try:
                bg_layer = scene.view_layers.new(name="BG")
            except Exception as exc:
                self.report({'ERROR'}, f"Failed to create BG View Layer: {exc}")
                return {'CANCELLED'}

        # Ensure Main layer
        main_layer = scene.view_layers.get("Main")
        if main_layer is None:
            try:
                main_layer = scene.view_layers.new(name="Main")
            except Exception as exc:
                self.report({'ERROR'}, f"Failed to create Main View Layer: {exc}")
                return {'CANCELLED'}

        # Configure render usage
        try:
            complete_layer.use = False
        except Exception:
            pass
        for layer in (bg_layer, main_layer):
            try:
                layer.use = True
            except Exception:
                pass

        # Reset passes to Combined only
        for layer in (complete_layer, bg_layer, main_layer):
            _reset_render_passes(layer)

        # Apply collection flags per layer
        for shot_coll, stage in stage_infos:
            configure_stage_view_layer(
                complete_layer,
                shot_root=shot_coll,
                main_collection=stage.get("main"),
                props_collection=stage.get("props"),
                bg_collection=stage.get("bg"),
                mode="COMPLETE",
            )
            configure_stage_view_layer(
                bg_layer,
                shot_root=shot_coll,
                main_collection=stage.get("main"),
                props_collection=stage.get("props"),
                bg_collection=stage.get("bg"),
                mode="BG",
            )
            configure_stage_view_layer(
                main_layer,
                shot_root=shot_coll,
                main_collection=stage.get("main"),
                props_collection=stage.get("props"),
                bg_collection=stage.get("bg"),
                mode="MAIN",
            )

        _ensure_outliner_columns()

        self.report({'INFO'}, "Stage view layers configured")
        return {'FINISHED'}


__all__ = [
    "LIME_OT_create_view_layers",
]


