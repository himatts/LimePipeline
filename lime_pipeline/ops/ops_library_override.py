"""
Library Override Operators

This module provides functionality for creating library overrides on linked objects
in Blender scenes. It automates the process of converting linked objects to library
overrides while preserving their linked status and enabling local modifications.

The override system handles recursive object hierarchies, ensuring that all child
objects of linked parents are properly processed for consistent override behavior.

Key Features:
- Automated library override creation for linked objects
- Recursive processing of object hierarchies and children
- Content and selection-based override modes
- Batch processing of multiple selected objects
- Validation of object linked status before override creation
- Integration with Blender's library override system
"""

from __future__ import annotations

import bpy
from bpy.types import Operator


class LIME_OT_make_library_override(Operator):
    bl_idname = "lime.make_library_override"
    bl_label = "Make Library Override"
    bl_description = (
        "For each selected linked object, create a Library Override "
        "using Content & Selected mode."
    )
    bl_options = {"REGISTER", "UNDO"}

    def _get_all_linked_objects(self, objs):
        """Recursively get all linked objects including children"""
        linked = []
        for obj in objs:
            if getattr(obj, "library", None) is not None:
                linked.append(obj)
                # Also add all children that might be linked
                for child in obj.children:
                    if child not in linked:
                        linked.extend(self._get_all_linked_objects([child]))
        return linked

    def execute(self, context):
        objs = list(getattr(context, "selected_objects", []) or [])
        if not objs:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}

        # Debug: print info about selected objects
        print(f"[LP] Selected objects: {len(objs)}")
        for obj in objs:
            lib = getattr(obj, "library", None)
            lib_name = lib.name if lib else "None"
            print(f"  {obj.name}: library={lib_name}, type={obj.type}")

        # Get all linked objects recursively
        linked_objs = self._get_all_linked_objects(objs)
        if not linked_objs:
            self.report({'WARNING'}, "No linked objects found in selection")
            return {'CANCELLED'}

        print(f"[LP] Linked objects (including children): {len(linked_objs)}")
        for obj in linked_objs:
            lib = getattr(obj, "library", None)
            lib_name = lib.name if lib else "None"
            print(f"  Linked: {obj.name} (library: {lib_name})")

        # Group by library to avoid multiple overrides per library
        libraries = {}
        for obj in linked_objs:
            lib = getattr(obj, "library", None)
            if lib:
                if lib not in libraries:
                    libraries[lib] = []
                libraries[lib].append(obj)

        overridden = 0
        for lib, lib_objs in libraries.items():
            try:
                # Ensure we're in Object mode
                if context.mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')

                # Select all objects from this library
                bpy.ops.object.select_all(action='DESELECT')
                for obj in lib_objs:
                    obj.select_set(True)

                # Set the first object as active
                if lib_objs:
                    context.view_layer.objects.active = lib_objs[0]

                print(f"[LP] Making override for library {lib.name} with {len(lib_objs)} objects")
                # Make override with Selected & Content
                result = bpy.ops.object.make_override_library()
                print(f"[LP] Override result for library {lib.name}: {result}")
                overridden += len(lib_objs)

            except Exception as ex:
                print(f"[LP] Error overriding library {lib.name}: {ex}")
                self.report({'WARNING'}, f"Failed to override library {lib.name}: {ex}")

        if overridden == 0:
            self.report({'ERROR'}, "Failed to create any overrides")
        else:
            self.report({'INFO'}, f"Created overrides for {overridden} object(s)")
        return {'FINISHED'}


__all__ = [
    "LIME_OT_make_library_override",
]
