from __future__ import annotations

import bpy
from bpy.types import Operator


class LIME_OT_apply_object_alpha_mix(Operator):
    bl_idname = "lime.apply_object_alpha_mix"
    bl_label = "Enable Object Alpha Transparency"
    bl_description = (
        "For each selected object's materials, mix existing shader with Transparent BSDF "
        "using Object Info Alpha, and connect to Material Output."
    )
    bl_options = {"REGISTER", "UNDO"}

    def _find_active_output(self, nodes: bpy.types.Nodes) -> bpy.types.Node:
        for node in nodes:
            if getattr(node, "type", "") == "OUTPUT_MATERIAL" and getattr(node, "is_active_output", False):
                return node
        # Create if not found
        return nodes.new("ShaderNodeOutputMaterial")

    def _get_surface_link(self, nt: bpy.types.NodeTree, output_node: bpy.types.Node) -> bpy.types.NodeLink | None:
        try:
            surf = output_node.inputs.get("Surface")
        except Exception:
            surf = None
        if surf and surf.is_linked:
            return surf.links[0]
        # Fallback search
        for link in nt.links:
            if link.to_node is output_node and link.to_socket is surf:
                return link
        return None

    def _ensure_object_info(self, nodes: bpy.types.Nodes) -> bpy.types.Node:
        for n in nodes:
            if getattr(n, "type", "") == "OBJECT_INFO":
                return n
        return nodes.new("ShaderNodeObjectInfo")

    def _ensure_transparent(self, nodes: bpy.types.Nodes) -> bpy.types.Node:
        for n in nodes:
            if getattr(n, "type", "") == "BSDF_TRANSPARENT":
                return n
        return nodes.new("ShaderNodeBsdfTransparent")

    def _ensure_principled(self, nodes: bpy.types.Nodes) -> bpy.types.Node:
        for n in nodes:
            if getattr(n, "type", "") == "BSDF_PRINCIPLED":
                return n
        return nodes.new("ShaderNodeBsdfPrincipled")

    def _alpha_socket(self, obj_info: bpy.types.Node) -> bpy.types.NodeSocket | None:
        for sock in obj_info.outputs:
            try:
                if "alpha" in sock.name.lower():
                    return sock
            except Exception:
                pass
        return None

    def _is_idempotent_mix(self, mix: bpy.types.Node) -> bool:
        if getattr(mix, "type", "") != "MIX_SHADER":
            return False
        # Fac from Object Info Alpha
        fac_ok = False
        try:
            fac_in = mix.inputs[0]
            if fac_in.is_linked:
                fac_from = fac_in.links[0].from_node
                fac_sock = fac_in.links[0].from_socket
                fac_ok = getattr(fac_from, "type", "") == "OBJECT_INFO" and (
                    fac_sock and "alpha" in fac_sock.name.lower()
                )
        except Exception:
            fac_ok = False
        # Shader[0] from Transparent BSDF
        tr_ok = False
        try:
            sh0 = mix.inputs[1]
            if sh0.is_linked:
                tr_from = sh0.links[0].from_node
                tr_ok = getattr(tr_from, "type", "") == "BSDF_TRANSPARENT"
        except Exception:
            tr_ok = False
        return bool(fac_ok and tr_ok)

    def _position_nodes(self, output: bpy.types.Node, mix: bpy.types.Node, transparent: bpy.types.Node, obj_info: bpy.types.Node, shader1: bpy.types.Node | None) -> None:
        try:
            ox, oy = output.location.x, output.location.y
        except Exception:
            ox, oy = 0.0, 0.0
        try:
            mix.location = (ox - 220.0, oy)
        except Exception:
            pass
        try:
            transparent.location = (mix.location.x - 220.0, mix.location.y - 120.0)
        except Exception:
            pass
        try:
            obj_info.location = (mix.location.x - 220.0, mix.location.y + 120.0)
        except Exception:
            pass
        if shader1 is not None:
            try:
                shader1.location = (mix.location.x - 220.0, mix.location.y)
            except Exception:
                pass

    def _apply_to_material(self, mat: bpy.types.Material) -> bool:
        changed = False
        mat.use_nodes = True
        nt = mat.node_tree
        nodes = nt.nodes
        links = nt.links

        output = self._find_active_output(nodes)
        prev_link = self._get_surface_link(nt, output)
        prev_from_node = prev_link.from_node if prev_link else None
        prev_from_socket = prev_link.from_socket if prev_link else None

        # If already a Mix connected to Output and matches, skip entirely
        if prev_from_node and getattr(prev_from_node, "type", "") == "MIX_SHADER":
            if self._is_idempotent_mix(prev_from_node):
                return False

        # Create or reuse nodes
        objinfo = self._ensure_object_info(nodes)
        transparent = self._ensure_transparent(nodes)

        # Decide which mix to use
        if prev_from_node and getattr(prev_from_node, "type", "") == "MIX_SHADER":
            mix = prev_from_node
            # Ensure Fac and Shader[0] are correct
            # Fac -> Object Info Alpha
            alpha_sock = self._alpha_socket(objinfo)
            if alpha_sock is not None:
                if not mix.inputs[0].is_linked or getattr(mix.inputs[0].links[0].from_node, "type", "") != "OBJECT_INFO" or (
                    "alpha" not in mix.inputs[0].links[0].from_socket.name.lower()
                ):
                    while mix.inputs[0].is_linked:
                        links.remove(mix.inputs[0].links[0])
                    links.new(alpha_sock, mix.inputs[0])
                    changed = True
            # Shader[0] -> Transparent
            if not mix.inputs[1].is_linked or getattr(mix.inputs[1].links[0].from_node, "type", "") != "BSDF_TRANSPARENT":
                while mix.inputs[1].is_linked:
                    links.remove(mix.inputs[1].links[0])
                links.new(transparent.outputs.get("BSDF"), mix.inputs[1])
                changed = True
            # Nothing else to connect (Shader[1] should already be whatever previous shading is)
        else:
            mix = nodes.new("ShaderNodeMixShader")
            # Rewire previous shading into Shader[1]
            if prev_link:
                try:
                    links.remove(prev_link)
                except Exception:
                    pass
                if prev_from_socket is not None:
                    links.new(prev_from_socket, mix.inputs[2])
            else:
                # Create a default Principled for Shader[1] if nothing was connected
                principled = self._ensure_principled(nodes)
                try:
                    links.new(principled.outputs.get("BSDF"), mix.inputs[2])
                except Exception:
                    pass
            # Transparent -> Shader[0]
            try:
                links.new(transparent.outputs.get("BSDF"), mix.inputs[1])
            except Exception:
                pass
            # Object Info Alpha -> Fac
            alpha_sock = self._alpha_socket(objinfo)
            if alpha_sock is not None:
                try:
                    links.new(alpha_sock, mix.inputs[0])
                except Exception:
                    pass
            # Mix -> Output Surface
            try:
                links.new(mix.outputs.get("Shader"), output.inputs.get("Surface"))
            except Exception:
                pass
            changed = True

        # Eevee transparency settings
        try:
            mat.blend_method = 'BLEND'
        except Exception:
            pass
        try:
            mat.shadow_method = 'NONE'
        except Exception:
            pass

        # Layout for readability
        try:
            shader1_node = None
            try:
                if getattr(mix.inputs[2], "is_linked", False):
                    shader1_node = mix.inputs[2].links[0].from_node
            except Exception:
                shader1_node = None
            self._position_nodes(output, mix, transparent, objinfo, shader1_node)
        except Exception:
            pass

        return changed

    def execute(self, context):
        objs = list(getattr(context, "selected_objects", []) or [])
        if not objs:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}

        materials: set[bpy.types.Material] = set()
        for obj in objs:
            for slot in getattr(obj, "material_slots", []) or []:
                mat = getattr(slot, "material", None)
                if mat is not None:
                    materials.add(mat)

        if not materials:
            self.report({'WARNING'}, "No materials found on selection")
            return {'CANCELLED'}

        changed_count = 0
        for mat in materials:
            try:
                if self._apply_to_material(mat):
                    changed_count += 1
            except Exception as ex:
                # Continue to next material but report once at the end
                print(f"[LP] Error processing material '{getattr(mat, 'name', '?')}': {ex}")

        if changed_count == 0:
            self.report({'INFO'}, "Materials already configured")
        else:
            self.report({'INFO'}, f"Updated {changed_count} material(s)")
        return {'FINISHED'}


__all__ = [
    "LIME_OT_apply_object_alpha_mix",
]


