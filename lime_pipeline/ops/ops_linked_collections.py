"""
Linked Collections Operators

This module provides functionality for managing linked collections from external .blend files.
It converts objects to local while preserving hierarchy and keeping mesh data externally linked.

Key Features:
- Convert linked objects (MESH and EMPTY) to local while keeping mesh data linked
- Realize selected linked collection instances into local collection hierarchies
- Configure material slots to link='OBJECT' level
- Duplicate external materials to local (cached per source material)
- Prioritize selected objects; fallback to active collection (recursive)
- Handle linked data and library overrides
- Comprehensive error handling and reporting
"""

import bpy
from bpy.types import Operator


SUPPORTED_TYPES = {"MESH", "EMPTY"}
LARGE_OPERATION_CONFIRM_THRESHOLD = 50


def _is_linked_or_override(id_block):
    """Return True when an ID is external (linked or library override)."""
    if id_block is None:
        return False

    if getattr(id_block, "library", None) is not None:
        return True

    return getattr(id_block, "override_library", None) is not None


def _is_supported_external_object(obj):
    """Return True when object type is supported and external."""
    if obj is None or getattr(obj, "type", None) not in SUPPORTED_TYPES:
        return False

    if _is_linked_or_override(obj):
        return True

    if obj.type == "MESH":
        return _is_linked_or_override(getattr(obj, "data", None))

    if obj.type == "EMPTY" and getattr(obj, "instance_type", None) == "COLLECTION":
        return _is_linked_or_override(getattr(obj, "instance_collection", None))

    return False


def _get_active_collection(context):
    """Return active collection in current view layer, or None."""
    try:
        active_layer_coll = context.view_layer.active_layer_collection
        if active_layer_coll:
            return active_layer_coll.collection
    except Exception:
        pass
    return None


def _iter_collection_objects(collection):
    """Iterate direct and nested objects from a collection when available."""
    if collection is None:
        return ()

    all_objects = getattr(collection, "all_objects", None)
    if all_objects is not None:
        return all_objects

    return getattr(collection, "objects", ())


def _collect_external_objects_from_collection(collection, objects_out, seen_ids):
    """Append supported external objects from collection (including nested)."""
    for obj in _iter_collection_objects(collection):
        if not _is_supported_external_object(obj):
            continue

        obj_id = id(obj)
        if obj_id in seen_ids:
            continue
        seen_ids.add(obj_id)
        objects_out.append(obj)


def _collect_external_objects_from_selection(selected_objects):
    """Collect supported external objects from selected objects."""
    objects_out = []
    seen_ids = set()

    for obj in selected_objects:
        if not _is_supported_external_object(obj):
            continue

        obj_id = id(obj)
        if obj_id in seen_ids:
            continue
        seen_ids.add(obj_id)
        objects_out.append(obj)

    return objects_out


def _collect_context_targets(context):
    """Return objects to process and source scope used for discovery."""
    selected_objects = list(getattr(context, "selected_objects", []) or [])
    selection_targets = _collect_external_objects_from_selection(selected_objects)
    if selection_targets:
        return selection_targets, "selection"

    active_collection = _get_active_collection(context)
    active_collection_targets = []
    _collect_external_objects_from_collection(active_collection, active_collection_targets, set())
    if active_collection_targets:
        return active_collection_targets, "active collection"

    return [], "none"


def _count_external_materials(objects):
    """Estimate unique external materials that may be duplicated to local."""
    materials = set()
    for obj in objects:
        if getattr(obj, "type", None) != "MESH":
            continue
        for slot in getattr(obj, "material_slots", ()) or ():
            mat = getattr(slot, "material", None)
            if _is_linked_or_override(mat):
                materials.add(mat)
    return len(materials)


def get_localize_linked_summary(context):
    """Return UI-friendly diagnostics for Linked Data localization."""
    selected_objects = list(getattr(context, "selected_objects", []) or [])
    selection_targets = _collect_external_objects_from_selection(selected_objects)

    active_collection = _get_active_collection(context)
    active_collection_targets = []
    _collect_external_objects_from_collection(active_collection, active_collection_targets, set())

    targets, scope = _collect_context_targets(context)
    available = bool(targets)

    mesh_targets = [obj for obj in targets if getattr(obj, "type", None) == "MESH"]
    empty_targets = [obj for obj in targets if getattr(obj, "type", None) == "EMPTY"]
    instance_targets = [obj for obj in targets if _is_external_collection_instance_object(obj)]
    mesh_data_linked_targets = [
        obj for obj in mesh_targets if _is_linked_or_override(getattr(obj, "data", None))
    ]
    linked_object_targets = [obj for obj in targets if getattr(obj, "library", None) is not None]
    override_object_targets = [
        obj for obj in targets
        if getattr(obj, "library", None) is None and getattr(obj, "override_library", None) is not None
    ]
    estimated_external_materials = _count_external_materials(targets)

    unavailable_reason = ""
    if not available:
        unavailable_reason = "No linked/override MESH or EMPTY found in selection or active collection"

    return {
        "available": available,
        "scope": scope,
        "selection_candidates": len(selection_targets),
        "active_collection_candidates": len(active_collection_targets),
        "targets": len(targets),
        "mesh_targets": len(mesh_targets),
        "empty_targets": len(empty_targets),
        "instance_targets": len(instance_targets),
        "mesh_data_linked_targets": len(mesh_data_linked_targets),
        "linked_object_targets": len(linked_object_targets),
        "override_object_targets": len(override_object_targets),
        "estimated_external_materials": estimated_external_materials,
        "unavailable_reason": unavailable_reason,
    }


def _is_external_collection_instance_object(obj):
    """Return True for EMPTY objects instancing a linked/override collection."""
    if obj is None or getattr(obj, "type", None) != "EMPTY":
        return False
    if getattr(obj, "instance_type", None) != "COLLECTION":
        return False
    return _is_linked_or_override(getattr(obj, "instance_collection", None))


def _process_mesh_material_slots(obj, material_duplicate_cache):
    """Set material slots to OBJECT and duplicate external materials to local."""
    reassigned = 0
    duplicated = 0

    material_slots = getattr(obj, "material_slots", None)
    if material_slots is None:
        return reassigned, duplicated

    for slot in material_slots:
        mat = getattr(slot, "material", None)
        if mat is None:
            continue

        try:
            slot.link = 'OBJECT'
            if _is_linked_or_override(mat):
                if mat in material_duplicate_cache:
                    slot.material = material_duplicate_cache[mat]
                    reassigned += 1
                else:
                    new_mat = mat.copy()
                    material_duplicate_cache[mat] = new_mat
                    slot.material = new_mat
                    duplicated += 1
            else:
                slot.material = mat
                reassigned += 1
        except Exception:
            # Keep the loop resilient per slot/object.
            continue

    return reassigned, duplicated


def _realize_collection_instance_hierarchy(context, instance_obj, material_duplicate_cache):
    """
    Realize a collection instance into a local collection/object hierarchy.

    Returns:
        tuple(list[Object], int):
            - created objects
            - created collections count
    """
    source_root = getattr(instance_obj, "instance_collection", None)
    if source_root is None:
        return [], 0

    parent_collections = list(getattr(instance_obj, "users_collection", []) or [])
    destination_parent = parent_collections[0] if parent_collections else context.scene.collection

    object_map = {}
    created_collections = 0

    def clone_collection_recursive(source_collection, destination_parent):
        nonlocal created_collections
        new_collection = bpy.data.collections.new(source_collection.name)
        destination_parent.children.link(new_collection)
        created_collections += 1

        for source_obj in source_collection.objects:
            new_obj = source_obj.copy()
            source_data = getattr(source_obj, "data", None)
            if source_data is not None:
                try:
                    # Keep mesh data linked; other data types can be copied when possible.
                    if getattr(source_obj, "type", None) == "MESH":
                        new_obj.data = source_data
                    elif hasattr(source_data, "copy"):
                        new_obj.data = source_data.copy()
                except Exception:
                    pass
            new_collection.objects.link(new_obj)
            object_map[source_obj] = new_obj

        for source_child in source_collection.children:
            clone_collection_recursive(source_child, new_collection)

        return new_collection

    clone_collection_recursive(source_root, destination_parent)

    # Rebuild parent relationships inside each cloned hierarchy.
    for source_obj, new_obj in object_map.items():
        source_parent = getattr(source_obj, "parent", None)
        if source_parent in object_map:
            try:
                new_obj.parent = object_map[source_parent]
                new_obj.matrix_parent_inverse = source_obj.matrix_parent_inverse.copy()
            except Exception:
                pass

    # Apply collection-instance transform so the realized hierarchy keeps visual placement.
    instance_matrix = instance_obj.matrix_world.copy()
    for source_obj, new_obj in object_map.items():
        try:
            new_obj.matrix_world = instance_matrix @ source_obj.matrix_world
        except Exception:
            pass

    created_objects = list(object_map.values())

    # Preserve current material behavior on realized meshes too.
    for new_obj in created_objects:
        if getattr(new_obj, "type", None) != "MESH":
            continue
        _process_mesh_material_slots(new_obj, material_duplicate_cache)

    # Remove the original instance object to avoid duplicate visuals/confusion.
    try:
        bpy.data.objects.remove(instance_obj, do_unlink=True)
    except Exception:
        pass

    return created_objects, created_collections


class LIME_OT_localize_linked_collection(Operator):
    bl_idname = "lime.localize_linked_collection"
    bl_label = "Localize Linked Data"
    bl_description = "Convert linked objects/collection instances to local while preserving hierarchy, keeping mesh data linked, configuring material slots to OBJECT level, and duplicating external materials to local"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """Check if there are linked objects to process."""
        objects_to_process, _scope = _collect_context_targets(context)
        return bool(objects_to_process)

    def invoke(self, context, event):
        """Ask confirmation for large operations before applying destructive changes."""
        objects_to_process, _scope = _collect_context_targets(context)
        if len(objects_to_process) >= LARGE_OPERATION_CONFIRM_THRESHOLD:
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, context):
        """Process linked data: keep hierarchy, localize objects, keep mesh data linked, configure material slots."""
        objects_to_process, processing_scope = _collect_context_targets(context)

        if not objects_to_process:
            self.report(
                {'WARNING'},
                "No linked/override MESH or EMPTY objects found in selection or active collection",
            )
            return {'CANCELLED'}

        object_was_external = {}
        mesh_backup = {}
        instance_objects_processed = 0
        collections_realized = 0
        objects_realized = 0

        for obj in objects_to_process:
            object_was_external[obj] = _is_linked_or_override(obj)
            if getattr(obj, "type", None) == "MESH":
                mesh_data = getattr(obj, "data", None)
                if _is_linked_or_override(mesh_data):
                    mesh_backup[obj] = mesh_data

        # Save current selection and active object
        previous_selection = list(context.selected_objects)
        previous_active = context.active_object

        # Cache for duplicated materials: original_external_material -> duplicated_local_material
        material_duplicate_cache = {}

        # Realize linked collection instances first to preserve collection hierarchy and manipulability.
        realized_objects = []
        remaining_objects = []
        for obj in objects_to_process:
            if _is_external_collection_instance_object(obj):
                new_objects, created_collections = _realize_collection_instance_hierarchy(
                    context,
                    obj,
                    material_duplicate_cache,
                )
                if new_objects:
                    instance_objects_processed += 1
                    collections_realized += created_collections
                    objects_realized += len(new_objects)
                    realized_objects.extend(new_objects)
                continue

            remaining_objects.append(obj)

        for obj in realized_objects:
            object_was_external[obj] = False

        objects_to_process = remaining_objects + realized_objects
        objects_to_make_local = [obj for obj in remaining_objects if _is_linked_or_override(obj)]

        if objects_to_make_local:
            # Select only the objects we want to localize.
            try:
                bpy.ops.object.select_all(action='DESELECT')
                for obj in objects_to_make_local:
                    obj.select_set(True)
                context.view_layer.objects.active = objects_to_make_local[0]
            except Exception:
                pass

            # Make objects local; mesh data is restored/kept linked afterwards.
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

        # Process each object
        localized_count = 0
        meshes_kept_linked = 0
        materials_reassigned = 0
        materials_duplicated = 0

        for obj in objects_to_process:
            try:
                # Verify object external reference was cleared by localization.
                if object_was_external.get(obj, False) and not _is_linked_or_override(obj):
                    localized_count += 1

                # For MESH objects: restore linked mesh and configure material slots
                if obj.type == 'MESH':
                    if obj in mesh_backup:
                        original_mesh = mesh_backup[obj]
                        if _is_linked_or_override(original_mesh):
                            try:
                                obj.data = original_mesh
                            except Exception:
                                pass

                    if _is_linked_or_override(getattr(obj, "data", None)):
                        meshes_kept_linked += 1

                    reassigned, duplicated = _process_mesh_material_slots(obj, material_duplicate_cache)
                    materials_reassigned += reassigned
                    materials_duplicated += duplicated

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
        if processing_scope != "none":
            summary_parts.append(f"scope: {processing_scope}")
        if localized_count > 0:
            summary_parts.append(f"{localized_count} object(s) localized")
        if meshes_kept_linked > 0:
            summary_parts.append(f"{meshes_kept_linked} mesh(es) kept linked")
        if materials_reassigned > 0:
            summary_parts.append(f"{materials_reassigned} material slot(s) configured (OBJECT level)")
        if materials_duplicated > 0:
            summary_parts.append(f"{materials_duplicated} external material(s) duplicated to local")
        if instance_objects_processed > 0:
            summary_parts.append(
                f"{instance_objects_processed} collection instance(s) realized "
                f"({collections_realized} collection(s), {objects_realized} object(s))"
            )

        if summary_parts:
            summary = ", ".join(summary_parts)
            self.report({'INFO'}, summary)
        else:
            self.report({'WARNING'}, "No changes made")

        return {'FINISHED'}


__all__ = [
    "LIME_OT_localize_linked_collection",
    "get_localize_linked_summary",
]
