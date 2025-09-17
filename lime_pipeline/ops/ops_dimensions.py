import math
from mathutils import Vector
import bpy
import bmesh
from bpy.props import FloatProperty

DIM_ENVELOPE_PROP = "lp_dimension_envelope"
DIM_LABEL_PROP = "lp_dimension_label"
EDGE_INDEX_FOR_AXIS = {
    'X': 0,
    'Y': 1,
    'Z': 8,
}

DIMENSION_COLLECTION_NAME = "Dimension Checker"
DIMENSION_HELPER_SUFFIX = "Dimension Checker"

DIM_MEASUREMENT_SCALE_PROP = "lp_dimension_measure_scale"

_OVERLAY_GUARD_STATE: bool | None = None
_OVERLAY_GUARD_SCALE: float | None = None

def _find_existing_envelope(scene: bpy.types.Scene) -> bpy.types.Object | None:
    for obj in scene.objects:
        try:
            if obj.get(DIM_ENVELOPE_PROP):
                return obj
        except Exception:
            continue
    return None

def _filtered_selection(context: bpy.types.Context, envelope: bpy.types.Object | None) -> list[bpy.types.Object]:
    selection: list[bpy.types.Object] = []
    try:
        selection.extend(context.selected_objects or [])
    except Exception:
        pass
    if context.mode != 'OBJECT':
        active = getattr(context, "active_object", None)
        if active and active not in selection:
            selection.append(active)
    filtered: list[bpy.types.Object] = []
    for obj in selection:
        if obj is None:
            continue
        if obj is envelope:
            continue
        try:
            if obj.get(DIM_ENVELOPE_PROP) or obj.get(DIM_LABEL_PROP):
                continue
        except Exception:
            continue
        filtered.append(obj)
    return filtered

def _accumulate_mesh_points(obj_eval: bpy.types.Object, min_corner: Vector, max_corner: Vector) -> bool:
    mesh = None
    try:
        mesh = obj_eval.to_mesh()
    except Exception:
        mesh = None
    if mesh is None:
        return False
    mw = obj_eval.matrix_world
    for vertex in mesh.vertices:
        world_co = mw @ vertex.co
        for i in range(3):
            if world_co[i] < min_corner[i]:
                min_corner[i] = world_co[i]
            if world_co[i] > max_corner[i]:
                max_corner[i] = world_co[i]
    try:
        obj_eval.to_mesh_clear()
    except Exception:
        try:
            bpy.data.meshes.remove(mesh)
        except Exception:
            pass
    return True

def _accumulate_bound_box(obj_eval: bpy.types.Object, min_corner: Vector, max_corner: Vector) -> bool:
    bbox = getattr(obj_eval, "bound_box", None)
    if not bbox:
        return False
    mw = obj_eval.matrix_world
    for corner in bbox:
        world_co = mw @ Vector(corner)
        for i in range(3):
            if world_co[i] < min_corner[i]:
                min_corner[i] = world_co[i]
            if world_co[i] > max_corner[i]:
                max_corner[i] = world_co[i]
    return True

def _compute_world_aabb(context: bpy.types.Context, objects: list[bpy.types.Object]) -> tuple[Vector, Vector] | None:
    if not objects:
        return None
    depsgraph = context.evaluated_depsgraph_get()
    min_corner = Vector((math.inf, math.inf, math.inf))
    max_corner = Vector((-math.inf, -math.inf, -math.inf))
    for obj in objects:
        if obj is None:
            continue
        try:
            obj_eval = obj.evaluated_get(depsgraph)
        except Exception:
            obj_eval = obj
        updated = _accumulate_mesh_points(obj_eval, min_corner, max_corner)
        updated = _accumulate_bound_box(obj_eval, min_corner, max_corner) or updated
        if not updated:
            world_loc = obj.matrix_world.translation.copy()
            for i in range(3):
                if world_loc[i] < min_corner[i]:
                    min_corner[i] = world_loc[i]
                if world_loc[i] > max_corner[i]:
                    max_corner[i] = world_loc[i]
    if math.isinf(min_corner.x) or math.isinf(min_corner.y) or math.isinf(min_corner.z):
        return None
    return min_corner, max_corner

def _ensure_dimension_collection(scene: bpy.types.Scene) -> bpy.types.Collection:
    collection = bpy.data.collections.get(DIMENSION_COLLECTION_NAME)
    if collection is None:
        collection = bpy.data.collections.new(DIMENSION_COLLECTION_NAME)
    scene_root = getattr(scene, "collection", None)
    if scene_root is not None:
        try:
            already_linked = any(child is collection for child in scene_root.children)
        except Exception:
            already_linked = True
        if not already_linked:
            try:
                scene_root.children.link(collection)
            except Exception:
                pass
    return collection

def _ensure_envelope_object(scene: bpy.types.Scene, selection: list[bpy.types.Object]) -> bpy.types.Object:
    target_collection = _ensure_dimension_collection(scene)
    envelope = _find_existing_envelope(scene)
    if envelope is not None:
        if envelope.data is None or envelope.type != 'MESH':
            mesh = bpy.data.meshes.new("LP_DimensionEnvelopeMesh")
            envelope.data = mesh
        if target_collection is not None:
            try:
                existing_collections = list(getattr(envelope, "users_collection", []) or [])
            except Exception:
                existing_collections = []
            if target_collection not in existing_collections:
                try:
                    target_collection.objects.link(envelope)
                except Exception:
                    pass
            for collection in existing_collections:
                if collection is target_collection:
                    continue
                try:
                    collection.objects.unlink(envelope)
                except Exception:
                    continue
        return envelope
    mesh = bpy.data.meshes.new("LP_DimensionEnvelopeMesh")
    envelope = bpy.data.objects.new(DIMENSION_HELPER_SUFFIX, mesh)
    envelope.hide_render = True
    envelope.show_in_front = True
    try:
        envelope.display_type = 'WIRE'
    except Exception:
        pass
    envelope[DIM_ENVELOPE_PROP] = True
    if target_collection is not None:
        try:
            target_collection.objects.link(envelope)
        except Exception:
            pass
    else:
        try:
            scene.collection.objects.link(envelope)
        except Exception:
            pass
    return envelope

def _update_envelope_geometry(envelope: bpy.types.Object, min_corner: Vector, max_corner: Vector) -> tuple[Vector, Vector]:
    mesh = envelope.data
    if mesh is None:
        mesh = bpy.data.meshes.new("LP_DimensionEnvelopeMesh")
        envelope.data = mesh
    mesh.clear_geometry()
    size = max_corner - min_corner
    center = (max_corner + min_corner) * 0.5
    verts = [
        Vector((min_corner.x, min_corner.y, min_corner.z)),
        Vector((max_corner.x, min_corner.y, min_corner.z)),
        Vector((max_corner.x, max_corner.y, min_corner.z)),
        Vector((min_corner.x, max_corner.y, min_corner.z)),
        Vector((min_corner.x, min_corner.y, max_corner.z)),
        Vector((max_corner.x, min_corner.y, max_corner.z)),
        Vector((max_corner.x, max_corner.y, max_corner.z)),
        Vector((min_corner.x, max_corner.y, max_corner.z)),
    ]
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    mesh.from_pydata([v - center for v in verts], edges, faces)
    mesh.update(calc_edges=True)
    envelope.location = center
    envelope.rotation_euler = (0.0, 0.0, 0.0)
    envelope.scale = (1.0, 1.0, 1.0)
    envelope.hide_render = True
    envelope.show_in_front = True
    try:
        envelope.display_type = 'WIRE'
    except Exception:
        pass
    envelope[DIM_ENVELOPE_PROP] = True
    return size, center

def _remove_existing_labels(envelope: bpy.types.Object) -> None:
    for child in list(getattr(envelope, 'children', []) or []):
        try:
            if child.get(DIM_LABEL_PROP):
                data = getattr(child, 'data', None)
                bpy.data.objects.remove(child, do_unlink=True)
                if data is not None and getattr(data, 'users', 0) == 0:
                    bpy.data.curves.remove(data, do_unlink=True)
        except Exception:
            continue

def _iter_view3d_overlays(context: bpy.types.Context | None):
    ctx = context or bpy.context
    wm = getattr(ctx, "window_manager", None) if ctx else None
    if wm is None:
        try:
            wm = bpy.context.window_manager
        except Exception:
            wm = None
    if wm is None:
        return
    for window in getattr(wm, "windows", []) or []:
        screen = getattr(window, "screen", None)
        if screen is None:
            continue
        for area in getattr(screen, "areas", []) or []:
            if getattr(area, "type", "") != "VIEW_3D":
                continue
            for space in getattr(area, "spaces", []) or []:
                if getattr(space, "type", "") != "VIEW_3D":
                    continue
                overlay = getattr(space, "overlay", None)
                if overlay is not None:
                    yield overlay


def _set_measure_overlay(context: bpy.types.Context | None, enable: bool, measurement_scale: float | None) -> None:
    for overlay in _iter_view3d_overlays(context):
        try:
            overlay.show_extra_edge_length = enable
        except Exception:
            pass
        try:
            overlay.show_text = enable
        except Exception:
            pass
        if enable and measurement_scale is not None:
            try:
                overlay.measurement_scale = measurement_scale
            except Exception:
                pass


def _install_overlay_guard(context: bpy.types.Context | None, enable: bool, measurement_scale: float | None) -> None:
    global _OVERLAY_GUARD_STATE, _OVERLAY_GUARD_SCALE
    handlers = bpy.app.handlers.depsgraph_update_post
    if enable:
        _OVERLAY_GUARD_SCALE = measurement_scale
        _OVERLAY_GUARD_STATE = None
        if _lp_overlay_guard not in handlers:
            handlers.append(_lp_overlay_guard)
        _set_measure_overlay(context, True, measurement_scale)
    else:
        _OVERLAY_GUARD_STATE = None
        _OVERLAY_GUARD_SCALE = None
        try:
            handlers.remove(_lp_overlay_guard)
        except ValueError:
            pass
        _set_measure_overlay(context, False, None)


def _lp_overlay_guard(scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph | None = None) -> None:
    global _OVERLAY_GUARD_STATE, _OVERLAY_GUARD_SCALE
    ctx = bpy.context
    if ctx is None:
        return
    view_layer = getattr(ctx, "view_layer", None)
    layer_objects = getattr(view_layer, "objects", None) if view_layer else None
    active = getattr(layer_objects, "active", None) if layer_objects else None
    has_envelope = bool(active and active.get(DIM_ENVELOPE_PROP))
    if has_envelope:
        scale = active.get(DIM_MEASUREMENT_SCALE_PROP, _OVERLAY_GUARD_SCALE if _OVERLAY_GUARD_SCALE is not None else 1.0)
    else:
        scale = None
    if has_envelope == _OVERLAY_GUARD_STATE and (not has_envelope or scale == _OVERLAY_GUARD_SCALE):
        return
    _OVERLAY_GUARD_STATE = has_envelope
    if has_envelope:
        _OVERLAY_GUARD_SCALE = scale
        _set_measure_overlay(ctx, True, scale)
    else:
        _OVERLAY_GUARD_SCALE = None
        _set_measure_overlay(ctx, False, None)


def disable_dimension_overlay_guard() -> None:
    _install_overlay_guard(None, False, None)


def _select_measurement_edges(context: bpy.types.Context, envelope: bpy.types.Object) -> None:
    mesh = envelope.data
    if not mesh or not isinstance(mesh, bpy.types.Mesh):
        return
    try:
        bm = bmesh.from_edit_mesh(mesh)
    except Exception:
        return
    try:
        bm.edges.ensure_lookup_table()
    except Exception:
        pass
    for edge in bm.edges:
        edge.select = False
    edge_indices = (
        EDGE_INDEX_FOR_AXIS.get('X'),
        EDGE_INDEX_FOR_AXIS.get('Y'),
        EDGE_INDEX_FOR_AXIS.get('Z'),
    )
    for edge_key in edge_indices:
        if edge_key is None:
            continue
        if 0 <= edge_key < len(bm.edges):
            bm.edges[edge_key].select = True
    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
    tool_settings = context.tool_settings
    try:
        prev_select_mode = tuple(tool_settings.mesh_select_mode)
    except Exception:
        prev_select_mode = None
    try:
        tool_settings.mesh_select_mode = (False, True, False)
    except Exception:
        pass
    if prev_select_mode is not None:
        try:
            tool_settings.mesh_select_mode = prev_select_mode
        except Exception:
            pass

class LIME_OT_dimension_envelope(bpy.types.Operator):
    """Create or update a dimension checker bounding box with viewport edge measurements."""

    bl_idname = "lime.dimension_envelope"
    bl_label = "Dimension Checker"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Generate a Dimension Checker helper and enable edge-length overlays for the selected objects."

    measurement_scale: FloatProperty(
        name="Measurement Overlay Scale",
        description="Scale factor for Blender's edge length overlay text.",
        default=1.6,
        min=0.5,
        max=3.0,
    )

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        envelope = _find_existing_envelope(scene)
        selection = _filtered_selection(context, envelope)
        if not selection:
            self.report({'WARNING'}, "Select at least one object to measure.")
            return {'CANCELLED'}
        try:
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass
        envelope = _ensure_envelope_object(scene, selection)
        bounds = _compute_world_aabb(context, selection)
        if not bounds:
            self.report({'WARNING'}, "Unable to compute dimensions for the current selection.")
            return {'CANCELLED'}
        min_corner, max_corner = bounds
        size, center = _update_envelope_geometry(envelope, min_corner, max_corner)
        _remove_existing_labels(envelope)
        display_label = selection[0].name if len(selection) == 1 else "Group"
        envelope.name = f"{display_label} {DIMENSION_HELPER_SUFFIX}"
        envelope[DIM_MEASUREMENT_SCALE_PROP] = self.measurement_scale
        _install_overlay_guard(context, True, self.measurement_scale)
        view_layer = context.view_layer
        for obj in view_layer.objects:
            try:
                obj.select_set(False)
            except Exception:
                pass
        try:
            envelope.select_set(True)
            view_layer.objects.active = envelope
        except Exception:
            pass
        try:
            bpy.ops.object.mode_set(mode='EDIT')
        except Exception:
            pass
        _select_measurement_edges(context, envelope)
        self.report({'INFO'}, "Dimension checker updated.")
        return {'FINISHED'}

__all__ = [
    "LIME_OT_dimension_envelope",
    "disable_dimension_overlay_guard",
]
