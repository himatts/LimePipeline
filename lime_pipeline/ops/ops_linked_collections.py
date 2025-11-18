"""
Linked Collections Operators

This module provides functionality for managing linked collections from external .blend files.
It allows converting linked objects to local while preserving linked mesh data and configuring material slot links.

Key Features:
- Convert linked objects (MESH and EMPTY) to local for editing
- Preserve linked mesh data (read-only, updates from source)
- Configure material slots to link='OBJECT' level
- Optional material duplication flag
- Process active collection or manual selection
- Comprehensive error handling and reporting
"""

import bpy
from bpy.types import Operator
from bpy.props import BoolProperty


class LIME_OT_localize_linked_collection(Operator):
    bl_idname = "lime.localize_linked_collection"
    bl_label = "Convert Linked Collection to Local (Keep Mesh Linked)"
    bl_description = "Convert linked objects to local while keeping mesh data linked, configuring material slots to OBJECT level, and duplicating linked materials to local"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """Check if there are linked objects to process."""
        # Check active collection
        active_coll = None
        try:
            active_layer_coll = context.view_layer.active_layer_collection
            if active_layer_coll:
                active_coll = active_layer_coll.collection
        except Exception:
            pass

        # Check if there are linked MESH or EMPTY objects in active collection
        if active_coll:
            for obj in active_coll.objects:
                if obj.type in {'MESH', 'EMPTY'} and getattr(obj, 'library', None) is not None:
                    return True

        # Check selected objects as fallback
        for obj in context.selected_objects:
            if obj.type in {'MESH', 'EMPTY'} and getattr(obj, 'library', None) is not None:
                return True

        return False

    def execute(self, context):
        """Process linked objects: localize objects, keep meshes linked, configure material slots."""
        scene = context.scene

        # Collect objects to process
        objects_to_process = []

        # First, try active collection
        active_coll = None
        try:
            active_layer_coll = context.view_layer.active_layer_collection
            if active_layer_coll:
                active_coll = active_layer_coll.collection
        except Exception:
            pass

        if active_coll:
            # Process all MESH and EMPTY objects in active collection
            for obj in active_coll.objects:
                if obj.type in {'MESH', 'EMPTY'} and getattr(obj, 'library', None) is not None:
                    objects_to_process.append(obj)

        # If no objects found in active collection, try selected objects
        if not objects_to_process:
            for obj in context.selected_objects:
                if obj.type in {'MESH', 'EMPTY'} and getattr(obj, 'library', None) is not None:
                    # Avoid duplicates if object is already in the list
                    if obj not in objects_to_process:
                        objects_to_process.append(obj)

        if not objects_to_process:
            self.report({'WARNING'}, "No linked MESH or EMPTY objects found in active collection or selection")
            return {'CANCELLED'}

        # Store original mesh and material references before making objects local
        # Key: object, Value: (original linked mesh data, list of original materials per slot)
        mesh_backup = {}
        materials_backup = {}
        
        for obj in objects_to_process:
            if obj.type == 'MESH':
                mesh_data = getattr(obj, 'data', None)
                if mesh_data is not None and getattr(mesh_data, 'library', None) is not None:
                    mesh_backup[obj] = mesh_data
                
                # Store original materials from mesh data slots
                if mesh_data is not None:
                    materials_list = []
                    for slot in getattr(obj, 'material_slots', []) or []:
                        mat = getattr(slot, 'material', None)
                        materials_list.append(mat)
                    materials_backup[obj] = materials_list

        # Save current selection and active object
        previous_selection = list(context.selected_objects)
        previous_active = context.active_object

        # Select only the objects we want to process
        try:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in objects_to_process:
                obj.select_set(True)
            context.view_layer.objects.active = objects_to_process[0] if objects_to_process else None
        except Exception:
            pass

        # Make objects local (this will also make mesh data local, but we'll restore it for MESH objects)
        try:
            bpy.ops.object.make_local(type='SELECT_OBJECT')
        except Exception as ex:
            self.report({'ERROR'}, f"Failed to make objects local: {str(ex)}")
            # Restore selection
            try:
                bpy.ops.object.select_all(action='DESELECT')
                for obj in previous_selection:
                    obj.select_set(True)
                context.view_layer.objects.active = previous_active
            except Exception:
                pass
            return {'CANCELLED'}

        # Cache for duplicated materials: original_linked_material -> duplicated_local_material
        # This ensures we create only one duplicate per original material, shared across objects
        material_duplicate_cache = {}

        # Process each object
        localized_count = 0
        meshes_kept_linked = 0
        materials_reassigned = 0
        materials_duplicated = 0

        for obj in objects_to_process:
            try:
                # Verify object is now local
                if getattr(obj, 'library', None) is None:
                    localized_count += 1

                # For MESH objects: restore linked mesh and configure material slots
                if obj.type == 'MESH':
                    # Restore the linked mesh if we backed it up
                    if obj in mesh_backup:
                        original_mesh = mesh_backup[obj]
                        # Check if the original mesh still exists and is linked
                        if original_mesh and getattr(original_mesh, 'library', None) is not None:
                            try:
                                obj.data = original_mesh
                                meshes_kept_linked += 1
                            except Exception:
                                # If restoration fails, try to find the linked mesh by name
                                mesh_name = original_mesh.name
                                for mesh in bpy.data.meshes:
                                    if mesh.name == mesh_name and getattr(mesh, 'library', None) is not None:
                                        try:
                                            obj.data = mesh
                                            meshes_kept_linked += 1
                                            break
                                        except Exception:
                                            pass

                    # Process material slots: configure link='OBJECT' and reassign materials
                    if obj in materials_backup:
                        original_materials = materials_backup[obj]
                        material_slots = getattr(obj, 'material_slots', None)
                        
                        if material_slots is not None:
                            for slot_idx, slot in enumerate(material_slots):
                                original_mat = None
                                if slot_idx < len(original_materials):
                                    original_mat = original_materials[slot_idx]
                                
                                if original_mat is None:
                                    continue
                                
                                try:
                                    # Set slot link to OBJECT level
                                    slot.link = 'OBJECT'
                                    
                                    # If material is linked, duplicate it to local (or reuse cached duplicate)
                                    if getattr(original_mat, 'library', None) is not None:
                                        # Check if we already have a duplicate of this material
                                        if original_mat in material_duplicate_cache:
                                            # Reuse the cached duplicate
                                            new_mat = material_duplicate_cache[original_mat]
                                            slot.material = new_mat
                                            materials_reassigned += 1
                                        else:
                                            # Create new duplicate and cache it
                                            try:
                                                new_mat = original_mat.copy()
                                                material_duplicate_cache[original_mat] = new_mat
                                                slot.material = new_mat
                                                materials_duplicated += 1
                                            except Exception as ex:
                                                self.report({'WARNING'}, f"Failed to duplicate material '{original_mat.name}': {str(ex)}")
                                                # Fall back to original material
                                                slot.material = original_mat
                                                materials_reassigned += 1
                                    else:
                                        # Material is already local, just reassign it
                                        slot.material = original_mat
                                        materials_reassigned += 1
                                        
                                except Exception as ex:
                                    self.report({'WARNING'}, f"Failed to configure material slot {slot_idx} for '{obj.name}': {str(ex)}")

                # For EMPTY objects: just verify they're local (no mesh or materials to process)
                elif obj.type == 'EMPTY':
                    # EMPTY objects don't have mesh data or materials, so just verify they're local
                    pass

            except Exception as ex:
                self.report({'WARNING'}, f"Failed to process object '{obj.name}': {str(ex)}")
                continue

        # Restore previous selection
        try:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in previous_selection:
                obj.select_set(True)
            context.view_layer.objects.active = previous_active
        except Exception:
            pass

        # Report results
        summary_parts = []
        if localized_count > 0:
            summary_parts.append(f"{localized_count} object(s) localized")
        if meshes_kept_linked > 0:
            summary_parts.append(f"{meshes_kept_linked} mesh(es) kept linked")
        if materials_reassigned > 0:
            summary_parts.append(f"{materials_reassigned} material slot(s) configured (OBJECT level)")
        if materials_duplicated > 0:
            summary_parts.append(f"{materials_duplicated} material(s) duplicated to local")

        if summary_parts:
            summary = ", ".join(summary_parts)
            self.report({'INFO'}, summary)
        else:
            self.report({'WARNING'}, "No changes made")

        return {'FINISHED'}


__all__ = [
    "LIME_OT_localize_linked_collection",
]
