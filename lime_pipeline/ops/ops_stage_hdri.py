"""
Stage HDRI Operators

Provides quick actions to switch the active scene world between packaged HDRI
variants (contrast and light). Worlds are created on demand, re-used on
subsequent executions, and configured with mapping controls so the Stage panel
can expose rotation/offset tweaking while keeping the original world untouched.
"""

from __future__ import annotations

from pathlib import Path
import bpy
from bpy.props import EnumProperty
from bpy.types import Operator, World


HDRI_VARIANTS = {
    "CONTRAST": {
        "filename": "HDRI_Contrast.exr",
        "world_name": "LIME_HDRI_Contrast",
        "label": "Contrast HDRI",
    },
    "LIGHT": {
        "filename": "HDRI_Light.exr",
        "world_name": "LIME_HDRI_Light",
        "label": "Light HDRI",
    },
}


class LIME_OT_stage_set_hdri(Operator):
    bl_idname = "lime.stage_set_hdri"
    bl_label = "Set Stage HDRI"
    bl_description = "Assign a Lime Pipeline HDRI world to the current scene"
    bl_options = {"REGISTER", "UNDO"}

    variant: EnumProperty(
        name="HDRI Variant",
        description="Select which Lime HDRI world to assign",
        items=(
            ("CONTRAST", "Contrast", "Switch to the high-contrast HDRI"),
            ("LIGHT", "Light", "Switch to the bright HDRI"),
        ),
    )

    def execute(self, context):
        variant_cfg = HDRI_VARIANTS.get(self.variant)
        if variant_cfg is None:
            self.report({'ERROR'}, f"Unknown HDRI variant: {self.variant}")
            return {'CANCELLED'}

        hdri_path = self._resolve_hdri_path(variant_cfg["filename"])
        if not hdri_path.exists():
            self.report({'ERROR'}, f"HDRI not found: {hdri_path}")
            return {'CANCELLED'}

        image = self._load_environment_image(hdri_path)
        if image is None:
            self.report({'ERROR'}, "Failed to load HDRI image.")
            return {'CANCELLED'}

        world = self._ensure_world(variant_cfg["world_name"], image, variant_cfg["label"])
        scene = getattr(context, "scene", None)
        if scene is None:
            self.report({'ERROR'}, "No active scene to assign the HDRI.")
            return {'CANCELLED'}

        scene.world = world
        self.report({'INFO'}, f"Assigned {variant_cfg['label']} world.")
        return {'FINISHED'}

    def _resolve_hdri_path(self, filename: str) -> Path:
        base_dir = Path(__file__).resolve().parents[1]
        return base_dir / "data" / "libraries" / filename

    def _load_environment_image(self, path: Path):
        try:
            return bpy.data.images.load(path.as_posix(), check_existing=True)
        except RuntimeError:
            return None

    def _ensure_world(self, name: str, image, label: str) -> World:
        world = bpy.data.worlds.get(name)
        if world is None:
            world = bpy.data.worlds.new(name=name)
        world.use_nodes = True
        node_tree = world.node_tree
        if node_tree is None:
            raise RuntimeError("World node tree is unavailable.")

        nodes = node_tree.nodes
        needs_reset = any(
            nodes.get(node_name) is None
            for node_name in ("Mapping", "Texture Coordinate", "Background", "LIME_STAGE_HDRI", "World Output")
        )
        if needs_reset:
            self._setup_nodes(node_tree)

        self._assign_image(node_tree, image, label)
        return world

    def _setup_nodes(self, node_tree) -> None:
        nodes = node_tree.nodes
        links = node_tree.links
        nodes.clear()

        output = nodes.new("ShaderNodeOutputWorld")
        output.name = "World Output"
        output.location = (200, 0)

        background = nodes.new("ShaderNodeBackground")
        background.name = "Background"
        background.location = (40, 0)

        env = nodes.new("ShaderNodeTexEnvironment")
        env.name = "LIME_STAGE_HDRI"
        env.location = (-300, 0)

        mapping = nodes.new("ShaderNodeMapping")
        mapping.name = "Mapping"
        mapping.location = (-520, 0)
        mapping.inputs[3].default_value = (1.0, 1.0, 1.0)

        tex_coord = nodes.new("ShaderNodeTexCoord")
        tex_coord.name = "Texture Coordinate"
        tex_coord.location = (-760, 0)

        # Link chain: Texture Coordinate -> Mapping -> Environment -> Background -> Output
        vector_out = tex_coord.outputs.get("Generated") or tex_coord.outputs.get("Object")
        mapping_vector_in = mapping.inputs.get("Vector")
        mapping_vector_out = mapping.outputs.get("Vector")
        env_vector_in = env.inputs.get("Vector")
        env_color_out = env.outputs.get("Color")
        background_color_in = background.inputs.get("Color")
        background_output = background.outputs.get("Background")
        output_surface_in = output.inputs.get("Surface")

        if vector_out is not None and mapping_vector_in is not None:
            links.new(vector_out, mapping_vector_in)
        if mapping_vector_out is not None and env_vector_in is not None:
            links.new(mapping_vector_out, env_vector_in)
        if env_color_out is not None and background_color_in is not None:
            links.new(env_color_out, background_color_in)
        if background_output is not None and output_surface_in is not None:
            links.new(background_output, output_surface_in)

        # Default strength for both HDRIs
        if background.inputs.get("Strength") is not None:
            background.inputs["Strength"].default_value = 1.0

    def _assign_image(self, node_tree, image, label: str) -> None:
        env = node_tree.nodes.get("LIME_STAGE_HDRI")
        if env is None:
            raise RuntimeError("Environment node missing after setup.")
        env.image = image
        env.label = label

        # Keep strength normalized when switching variants
        background = node_tree.nodes.get("Background")
        if background and background.inputs.get("Strength") is not None:
            background.inputs["Strength"].default_value = 1.0


__all__ = [
    "LIME_OT_stage_set_hdri",
    "HDRI_VARIANTS",
]
