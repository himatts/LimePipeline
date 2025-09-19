"""Operators for the 3D Model Organizer panel."""

import bpy
import colorsys
from bpy.types import Operator
from bpy.props import BoolProperty


_LOCATION_EPSILON = 1e-4
_GOLDEN_RATIO_CONJUGATE = 0.61803398875
_PARENT_SATURATION = 1.0
_FIRST_CHILD_SATURATION = 0.75
_SATURATION_FALLOFF = 0.15
_MIN_SATURATION = 0.0
_GEOMETRY_TYPES = {
    'MESH',
    'CURVE',
    'SURFACE',
    'META',
    'FONT',
    'GPENCIL',
    'VOLUME',
    'LATTICE',
    'POINTCLOUD',
}


def _hsv_to_rgba(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (r, g, b, 1.0)


def _set_object_color(obj, rgba):
    try:
        obj.color = rgba
    except Exception:
        return False
    return True


def _is_geometry(obj):
    obj_type = getattr(obj, "type", None)
    return obj_type in _GEOMETRY_TYPES



def _nearest_geometry_parent(obj):
    parent = getattr(obj, "parent", None)
    while parent is not None and not _is_geometry(parent):
        parent = getattr(parent, "parent", None)
    return parent



def _root_geometry(obj):
    current = obj
    parent = _nearest_geometry_parent(current)
    while parent is not None:
        current = parent
        parent = _nearest_geometry_parent(current)
    return current



def _iter_geometry_descendants(obj):
    for child in getattr(obj, "children", []):
        if child is None:
            continue
        if _is_geometry(child):
            yield child
        yield from _iter_geometry_descendants(child)



def _saturation_for_depth(depth):
    if depth <= 0:
        return _PARENT_SATURATION
    saturation = _FIRST_CHILD_SATURATION - (depth - 1) * _SATURATION_FALLOFF
    if saturation < _MIN_SATURATION:
        return _MIN_SATURATION
    return saturation


_AUTO_SELECT_HANDLER_ACTIVE = False
_AUTO_SELECT_GUARD = False
_AUTO_SELECT_LAST_SELECTION = set()


def _iter_all_descendants(obj):
    for child in getattr(obj, "children", []):
        if child is None:
            continue
        yield child
        yield from _iter_all_descendants(child)


def _auto_select_hierarchy_handler(scene):
    global _AUTO_SELECT_GUARD, _AUTO_SELECT_LAST_SELECTION
    if _AUTO_SELECT_GUARD:
        return
    try:
        context = bpy.context
    except Exception:
        return
    if context is None:
        return
    wm = getattr(context, "window_manager", None)
    if wm is None:
        return
    state = getattr(wm, "lime_pipeline", None)
    if state is None or not getattr(state, "auto_select_hierarchy", False):
        return
    if getattr(context, "mode", "OBJECT") != 'OBJECT':
        return
    try:
        selected = list(getattr(context, "selected_objects", []) or [])
    except Exception:
        selected = []
    selection_ids = {obj.as_pointer() for obj in selected}
    if not selected:
        _AUTO_SELECT_LAST_SELECTION = selection_ids
        return
    if selection_ids == _AUTO_SELECT_LAST_SELECTION:
        return

    additions = []
    for obj in selected:
        for child in _iter_all_descendants(obj):
            if child is None:
                continue
            try:
                if not child.select_get():
                    additions.append(child)
            except Exception:
                continue

    if not additions:
        _AUTO_SELECT_LAST_SELECTION = selection_ids
        return

    _AUTO_SELECT_GUARD = True
    try:
        for child in additions:
            try:
                child.select_set(True)
            except Exception:
                pass
        try:
            selected_after = list(getattr(context, "selected_objects", []) or [])
        except Exception:
            selected_after = selected
        _AUTO_SELECT_LAST_SELECTION = {obj.as_pointer() for obj in selected_after}
    finally:
        _AUTO_SELECT_GUARD = False


def enable_auto_select_hierarchy():
    global _AUTO_SELECT_HANDLER_ACTIVE, _AUTO_SELECT_LAST_SELECTION
    if _AUTO_SELECT_HANDLER_ACTIVE:
        return True
    if _auto_select_hierarchy_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_auto_select_hierarchy_handler)
    _AUTO_SELECT_HANDLER_ACTIVE = True
    _AUTO_SELECT_LAST_SELECTION = set()
    return True


def disable_auto_select_hierarchy():
    global _AUTO_SELECT_HANDLER_ACTIVE, _AUTO_SELECT_LAST_SELECTION, _AUTO_SELECT_GUARD
    if _auto_select_hierarchy_handler in bpy.app.handlers.depsgraph_update_post:
        try:
            bpy.app.handlers.depsgraph_update_post.remove(_auto_select_hierarchy_handler)
        except ValueError:
            pass
    _AUTO_SELECT_HANDLER_ACTIVE = False
    _AUTO_SELECT_LAST_SELECTION = set()
    _AUTO_SELECT_GUARD = False
    return True



def objects_with_location_offset(scene):
    """Return scene objects whose location differs from zero within a tolerance."""
    offenders = []
    if scene is None:
        return offenders
    for obj in getattr(scene, 'objects', []) or []:
        if obj is None:
            continue
        if getattr(obj, 'type', None) == 'EMPTY':
            continue
        if getattr(obj, 'library', None) is not None:
            continue
        loc = getattr(obj, 'location', None)
        if loc is None:
            continue
        if any(abs(coord) > _LOCATION_EPSILON for coord in loc):
            offenders.append(obj)
    return offenders


class LIME_OT_group_selection_empty(Operator):
    """Create an empty centered on the selection bounds and preserve transforms."""

    bl_idname = "lime.group_selection_empty"
    bl_label = "Create Controller"
    bl_description = "Create an empty at the combined bounds center and parent selected objects to it."
    bl_options = {'REGISTER', 'UNDO'}

    debug: BoolProperty(
        name="Debug Logs",
        description="Print detailed bounds and transform info to the System Console",
        default=False,
    )

    def execute(self, context):
        from mathutils import Vector

        # Ignore existing empties in selection to compute true geometry bounds
        selection = [obj for obj in (context.selected_objects or []) if obj.type != 'EMPTY']
        if not selection:
            self.report({'WARNING'}, "Select at least one object to group.")
            return {'CANCELLED'}

        # Identify top-level parents to avoid breaking existing hierarchies
        selection_ids = {obj.as_pointer() for obj in selection}
        top_level_selection = []
        for obj in selection:
            parent = getattr(obj, "parent", None)
            parent_id = parent.as_pointer() if parent is not None else None
            if parent_id not in selection_ids:
                top_level_selection.append(obj)
        if not top_level_selection:
            top_level_selection = selection.copy()

        # Cache world transforms to restore after parenting top-level objects only
        original_matrices = {obj: obj.matrix_world.copy() for obj in top_level_selection}

        # Compute world-space AABB using evaluated geometry (includes modifiers)
        depsgraph = context.evaluated_depsgraph_get()
        min_x = min_y = min_z = float('inf')
        max_x = max_y = max_z = float('-inf')

        def _accum_point(p):
            nonlocal min_x, min_y, min_z, max_x, max_y, max_z
            if p.x < min_x:
                min_x = p.x
            if p.y < min_y:
                min_y = p.y
            if p.z < min_z:
                min_z = p.z
            if p.x > max_x:
                max_x = p.x
            if p.y > max_y:
                max_y = p.y
            if p.z > max_z:
                max_z = p.z

        if self.debug:
            print("[Lime][GroupSelectionEmpty] ---- Bounds collection start ----")

        for obj in selection:
            try:
                obj_eval = obj.evaluated_get(depsgraph)
                mesh = obj_eval.to_mesh()
            except Exception:
                mesh = None
                obj_eval = obj
            if mesh is not None and hasattr(mesh, "vertices") and len(mesh.vertices):
                mw = obj_eval.matrix_world
                if self.debug:
                    print(f"[Lime] Using evaluated mesh for '{obj.name}' (verts={len(mesh.vertices)})")
                for v in mesh.vertices:
                    _accum_point(mw @ v.co)
                # Free evaluated mesh to avoid leaks
                try:
                    obj_eval.to_mesh_clear()
                except Exception:
                    try:
                        bpy.data.meshes.remove(mesh)
                    except Exception:
                        pass
            else:
                # Fallback to object bound_box if no mesh (lights, cameras, etc.)
                bbox = getattr(obj, "bound_box", None)
                if bbox:
                    mw = obj.matrix_world
                    if self.debug:
                        print(f"[Lime] Using bound_box for '{obj.name}'")
                    for corner in bbox:
                        _accum_point(mw @ Vector(corner))
                else:
                    if self.debug:
                        print(f"[Lime] Fallback to origin for '{obj.name}'")
                    _accum_point(obj.matrix_world.translation.copy())

        if not (min_x < float('inf')):
            self.report({'WARNING'}, "Unable to compute a bounding box for the current selection.")
            return {'CANCELLED'}

        size_x = max(max_x - min_x, 1e-6)
        size_y = max(max_y - min_y, 1e-6)
        size_z = max(max_z - min_z, 1e-6)
        controller_size = sorted((size_x, size_y, size_z))[1] * 0.5  # Use half the middle axis length for controller size
        center = Vector(((min_x + max_x) * 0.5, (min_y + max_y) * 0.5, (min_z + max_z) * 0.5))

        if self.debug:
            print(f"[Lime] AABB min=({min_x:.6f}, {min_y:.6f}, {min_z:.6f}) max=({max_x:.6f}, {max_y:.6f}, {max_z:.6f})")
            print(f"[Lime] size=({size_x:.6f}, {size_y:.6f}, {size_z:.6f}) center=({center.x:.6f}, {center.y:.6f}, {center.z:.6f})")

        # Place helper objects next to the selection
        base_collection = None
        for obj in selection:
            collections = getattr(obj, "users_collection", None)
            if collections:
                base_collection = collections[0]
                break
        if base_collection is None:
            base_collection = context.collection or context.scene.collection

        cursor = context.scene.cursor
        cursor.location = center.copy()

        if self.debug:
            print(f"[Lime] Cursor moved to controller center at {tuple(cursor.location)}")

        # Create the grouping empty at cursor
        empty = bpy.data.objects.new("CONTROLLER", None)
        base_collection.objects.link(empty)
        empty.empty_display_type = 'PLAIN_AXES'
        empty.empty_display_size = controller_size
        empty.location = cursor.location
        empty.show_in_front = True
        empty.show_name = True

        # If any selected object has an external parent (not within the selection), parent the empty to it
        anchor_parent = None
        for obj in selection:
            candidate_parent = getattr(obj, 'parent', None)
            if candidate_parent and candidate_parent not in selection:
                anchor_parent = candidate_parent
                break
        if anchor_parent is not None:
            empty.parent = anchor_parent
            empty.matrix_parent_inverse = anchor_parent.matrix_world.inverted_safe()
            empty.matrix_world.translation = center
        else:
            empty.matrix_world.translation = center

        parent_inverse = empty.matrix_world.inverted_safe()
        for obj in top_level_selection:
            obj.parent = empty
            obj.matrix_parent_inverse = parent_inverse.copy()
            # Restore original world transform to avoid any drift
            obj.matrix_world = original_matrices[obj]
            if self.debug:
                new_loc = obj.matrix_world.translation
                old_loc = original_matrices[obj].translation
                dx, dy, dz = (new_loc - old_loc)
                print(f"[Lime] '{obj.name}' delta after parenting: ({dx:.6f}, {dy:.6f}, {dz:.6f})")

        # Apply transforms to deltas on the new controller
        for obj in list(context.selected_objects):
            obj.select_set(False)
        empty.select_set(True)
        context.view_layer.objects.active = empty
        bpy.ops.object.transforms_to_deltas(mode='ALL', reset_values=True)

        # Selection feedback
        for obj in selection:
            obj.select_set(True)
        empty.select_set(True)
        context.view_layer.objects.active = empty

        if self.debug:
            print("[Lime][GroupSelectionEmpty] ---- Done ----")
        self.report({'INFO'}, f"Created controller empty '{empty.name}' for the selection.")
        return {'FINISHED'}


class LIME_OT_move_controller(Operator):
    """Move a controller empty to the 3D cursor without moving its children."""

    bl_idname = "lime.move_controller"
    bl_label = "Move Controller"
    bl_description = "Move the selected controller empty to the 3D cursor while keeping children in place."
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        controller = context.active_object
        if controller is None or controller.type != 'EMPTY':
            self.report({'WARNING'}, "Select a controller empty to move.")
            return {'CANCELLED'}

        cursor_location = context.scene.cursor.location.copy()
        children = list(controller.children)
        child_world_matrices = {child: child.matrix_world.copy() for child in children}

        controller.matrix_world.translation = cursor_location

        for child in children:
            child.matrix_world = child_world_matrices[child]

        controller.select_set(True)
        context.view_layer.objects.active = controller
        self.report({'INFO'}, f"Moved controller '{controller.name}' to the 3D cursor.")
        return {'FINISHED'}


class LIME_OT_apply_scene_deltas(Operator):
    """Apply transforms to deltas for objects with non-zero location."""

    bl_idname = "lime.apply_scene_deltas"
    bl_label = "Apply Deltas"
    bl_description = "Move transforms into deltas for objects whose location is not zero."
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        offenders = objects_with_location_offset(scene)
        if not offenders:
            self.report({'INFO'}, "All scene objects already have zero location.")
            return {'CANCELLED'}

        prev_sel = list(context.selected_objects or [])
        prev_active = context.view_layer.objects.active

        try:
            if context.mode != 'OBJECT':
                context.view_layer.objects.active = offenders[0]
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

        try:
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in offenders:
                obj.select_set(True)
            context.view_layer.objects.active = offenders[0]
        except Exception:
            pass

        success = True
        try:
            bpy.ops.object.transforms_to_deltas(mode='ALL', reset_values=True)
        except Exception:
            success = False

        try:
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in prev_sel:
                if obj and obj.name in bpy.data.objects:
                    bpy.data.objects[obj.name].select_set(True)
            if prev_active and prev_active.name in bpy.data.objects:
                context.view_layer.objects.active = bpy.data.objects[prev_active.name]
        except Exception:
            pass

        if not success:
            self.report({'ERROR'}, "Failed to apply transforms to deltas.")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Applied transforms to deltas on {len(offenders)} object(s).")
        return {'FINISHED'}



class LIME_OT_colorize_parent_groups(Operator):
    """Assign viewport colors to parent-child hierarchies for quick inspection."""

    bl_idname = "lime.colorize_parent_groups"
    bl_label = "Color Parent Groups"
    bl_description = "Assign viewport colors to parents and their children to visualize hierarchies."
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selection = list(context.selected_objects or [])
        if not selection and context.active_object:
            selection = [context.active_object]
        if not selection:
            self.report({'WARNING'}, "Select at least one object to colorize.")
            return {'CANCELLED'}

        geometry_objects = {obj for obj in selection if _is_geometry(obj)}
        for obj in selection:
            if not _is_geometry(obj):
                geometry_objects.update(_iter_geometry_descendants(obj))

        geometry_objects = {obj for obj in geometry_objects if obj is not None and obj.name in bpy.data.objects}
        if not geometry_objects:
            self.report({'WARNING'}, "Select at least one geometry object to colorize.")
            return {'CANCELLED'}

        root_map = {}
        for obj in geometry_objects:
            root = _root_geometry(obj)
            if root is None:
                continue
            root_map[root.as_pointer()] = root

        roots = list(root_map.values())
        if not roots:
            self.report({'WARNING'}, "No geometry hierarchies found to colorize.")
            return {'CANCELLED'}

        roots.sort(key=lambda item: item.name.lower())

        colored_objects = 0
        for index, root in enumerate(roots):
            hue = (index * _GOLDEN_RATIO_CONJUGATE) % 1.0
            colored_objects += self._apply_group_colors(root, hue)

        if colored_objects == 0:
            self.report({'WARNING'}, "No geometry objects were colorized.")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Assigned colors to {len(roots)} hierarchy(ies) covering {colored_objects} object(s).")
        return {'FINISHED'}

    def _apply_group_colors(self, root, hue):
        stack = [(root, 0)]
        visited = set()
        colored = 0

        while stack:
            obj, depth = stack.pop()
            if obj is None:
                continue

            obj_id = obj.as_pointer()
            if obj_id in visited:
                continue
            visited.add(obj_id)

            if _is_geometry(obj):
                saturation = _saturation_for_depth(depth)
                color = _hsv_to_rgba(hue, saturation, 1.0)
                if _set_object_color(obj, color):
                    colored += 1

            for child in getattr(obj, "children", []):
                if child is None:
                    continue
                if getattr(child, "type", None) == 'EMPTY':
                    stack.append((child, depth))
                elif _is_geometry(child):
                    stack.append((child, depth + 1))

        return colored


__all__ = [
    "objects_with_location_offset",
    "LIME_OT_group_selection_empty",
    "LIME_OT_move_controller",
    "LIME_OT_apply_scene_deltas",
    "LIME_OT_colorize_parent_groups",
    "enable_auto_select_hierarchy",
    "disable_auto_select_hierarchy",
]
