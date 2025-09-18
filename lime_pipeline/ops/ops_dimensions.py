import math
from typing import NamedTuple

from mathutils import Matrix, Vector
import bpy
# NOTE: bmesh import removed; Edit Mode overlay no longer used.
import blf
import gpu
from bpy.props import BoolProperty, EnumProperty
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader

DIM_ENVELOPE_PROP = "lp_dimension_envelope"

DIM_LABEL_PROP = "lp_dimension_label"

DIMENSION_COLLECTION_NAME = "Dimension Checker"

DIMENSION_HELPER_SUFFIX = "Dimension Checker"

DIM_SIZE_PROP = "lp_dimension_size"

DIM_ORIENTATION_PROP = "lp_dimension_orientation_mode"

OVERLAY_FONT_SIZE_PX = 12

OVERLAY_PADDING_PX = 6

OVERLAY_TEXT_COLOR = (1.0, 1.0, 1.0, 1.0)

OVERLAY_BG_COLOR = (0.0, 0.0, 0.0, 0.45)

OVERLAY_SCREEN_OFFSET = Vector((10.0, 10.0))

OVERLAY_DEBUG = False

OVERLAY_DRAW_REGION = 'WINDOW'

OVERLAY_DRAW_TYPE = 'POST_PIXEL'

ORIENTATION_MODE_ITEMS = [

    ('WORLD', "World", "Align to the global axes."),
    ('ROOT', "Root", "Align to the highest ancestor rotation."),
    ('LCA', "Lowest Common Ancestor", "Align to the closest shared parent rotation."),
    ('PCA3D', "PCA 3D", "Align to the principal components of the geometry."),
    ('PCA_ZUP', "PCA Z-Up", "Align PCA in XY while preserving global Z up."),

]

ORIENTATION_MODE_LABELS = {identifier: label for identifier, label, _ in ORIENTATION_MODE_ITEMS}

DEFAULT_ORIENTATION_MODE = 'LCA'

ORIENTATION_MODE_KEYS = set(ORIENTATION_MODE_LABELS.keys())

PCA_POINT_SAMPLE_LIMIT = 40000

PCA_EPSILON = 1e-6

_OVERLAY_DRAW_HANDLE = None

def _overlay_debug_print(*args) -> None:

    if OVERLAY_DEBUG:
        try:
            print("[Lime][DimensionOverlay]", *args)
        except Exception:
            pass

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

class OrientationPick(NamedTuple):
    matrix: Matrix
    effective_mode: str
    points: list[Vector] | None
    message: str | None

def _object_ancestry(obj: bpy.types.Object | None) -> list[bpy.types.Object]:
    ancestry: list[bpy.types.Object] = []
    current = obj
    while current is not None:
        ancestry.append(current)
        parent = getattr(current, "parent", None)
        if parent in ancestry:
            break
        current = parent
    return ancestry

def _shared_root_object(objects: list[bpy.types.Object]) -> bpy.types.Object | None:
    shared: bpy.types.Object | None = None
    for obj in objects:
        if obj is None:
            continue
        ancestry = _object_ancestry(obj)
        if not ancestry:
            continue
        candidate = ancestry[-1]
        if shared is None:
            shared = candidate
        elif candidate is not shared:
            return None
    return shared

def _find_lowest_common_ancestor(objects: list[bpy.types.Object]) -> bpy.types.Object | None:
    if not objects:
        return None
    ancestor_lists = [_object_ancestry(obj) for obj in objects if obj is not None]
    if not ancestor_lists:
        return None
    reference = ancestor_lists[0]
    for candidate in reference:
        if all(candidate in ancestry for ancestry in ancestor_lists[1:]):
            return candidate
    return None

def _rotation_matrix_from_object(obj: bpy.types.Object | None) -> Matrix | None:
    if obj is None:
        return None
    try:
        _, rotation, _ = obj.matrix_world.decompose()
    except Exception:
        return None
    if rotation is None:
        return None
    try:
        rotation = rotation.normalized()
    except Exception:
        pass
    try:
        matrix = rotation.to_matrix().to_4x4()
    except Exception:
        matrix = Matrix.Identity(4)
    matrix.translation = Vector((0.0, 0.0, 0.0))
    return matrix

def _collect_world_points(
    context: bpy.types.Context,
    objects: list[bpy.types.Object],
    *,
    sample_limit: int | None = None,
) -> list[Vector]:
    if not objects:
        return []
    points: list[Vector] = []
    try:
        depsgraph = context.evaluated_depsgraph_get()
    except Exception:
        depsgraph = None
    selected_handles: set[int] = set()
    for obj in objects:
        if obj is None:
            continue
        try:
            selected_handles.add(obj.as_pointer())
        except Exception:
            pass
        original = getattr(obj, "original", None)
        if original is not None:
            try:
                selected_handles.add(original.as_pointer())
            except Exception:
                pass
        obj_eval = obj
        if depsgraph is not None:
            try:
                obj_eval = obj.evaluated_get(depsgraph)
            except Exception:
                obj_eval = obj
        mesh = None
        updated = False
        try:
            mesh = obj_eval.to_mesh()
        except Exception:
            mesh = None
        if mesh is not None and getattr(mesh, "vertices", None):
            mw = obj_eval.matrix_world
            for vertex in mesh.vertices:
                try:
                    points.append(mw @ vertex.co)
                except Exception:
                    continue
            updated = True
        bbox_source = obj_eval if getattr(obj_eval, "bound_box", None) else obj
        bbox = getattr(bbox_source, "bound_box", None)
        if bbox:
            mw = getattr(obj_eval, "matrix_world", obj.matrix_world)
            for corner in bbox:
                try:
                    points.append(mw @ Vector(corner))
                except Exception:
                    continue
            updated = True
        if not updated:
            mw = obj.matrix_world
            try:
                points.append(mw.translation.copy())
            except Exception:
                pass
        if mesh is not None:
            try:
                obj_eval.to_mesh_clear()
            except Exception:
                try:
                    bpy.data.meshes.remove(mesh)
                except Exception:
                    pass
    if depsgraph is not None:
        try:
            for instance in depsgraph.object_instances:
                inst_obj = getattr(instance, "object", None)
                if inst_obj is None:
                    continue
                include = False
                try:
                    if inst_obj.as_pointer() in selected_handles:
                        include = True
                except Exception:
                    pass
                if not include:
                    original = getattr(inst_obj, "original", None)
                    if original is not None:
                        try:
                            if original.as_pointer() in selected_handles:
                                include = True
                        except Exception:
                            pass
                if not include:
                    parent = getattr(instance, "parent", None)
                    if parent is not None:
                        try:
                            if parent.as_pointer() in selected_handles:
                                include = True
                        except Exception:
                            pass
                if not include or not getattr(instance, "is_instance", False):
                    continue
                bbox = getattr(inst_obj, "bound_box", None)
                if not bbox:
                    continue
                matrix_world = getattr(instance, "matrix_world", None)
                if matrix_world is None:
                    continue
                for corner in bbox:
                    try:
                        points.append(matrix_world @ Vector(corner))
                    except Exception:
                        continue
        except Exception:
            pass
    if sample_limit and sample_limit > 0 and len(points) > sample_limit:
        step = max(1, len(points) // sample_limit)
        points = points[::step]
        if len(points) > sample_limit:
            points = points[:sample_limit]
    return points

def _jacobi_eigen_decomposition(matrix_values: list[list[float]]) -> tuple[list[float], list[Vector]]:
    a = [[float(matrix_values[r][c]) for c in range(3)] for r in range(3)]
    v = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]
    for _ in range(32):
        candidates = (
            (0, 1, abs(a[0][1])),
            (0, 2, abs(a[0][2])),
            (1, 2, abs(a[1][2])),
        )
        p, q, max_val = max(candidates, key=lambda item: item[2])
        if max_val <= 1e-9:
            break
        apq = a[p][q]
        if abs(apq) <= 1e-20:
            continue
        app = a[p][p]
        aqq = a[q][q]
        tau = (aqq - app) / (2.0 * apq)
        t = math.copysign(1.0 / (abs(tau) + math.sqrt(1.0 + tau * tau)), tau)
        c = 1.0 / math.sqrt(1.0 + t * t)
        s = t * c
        for r in range(3):
            if r == p or r == q:
                continue
            arp = a[r][p]
            arq = a[r][q]
            a[r][p] = c * arp - s * arq
            a[p][r] = a[r][p]
            a[r][q] = s * arp + c * arq
            a[q][r] = a[r][q]
        app_new = c * c * app - 2.0 * s * c * apq + s * s * aqq
        aqq_new = s * s * app + 2.0 * s * c * apq + c * c * aqq
        a[p][p] = app_new
        a[q][q] = aqq_new
        a[p][q] = 0.0
        a[q][p] = 0.0
        for r in range(3):
            vip = v[r][p]
            viq = v[r][q]
            v[r][p] = c * vip - s * viq
            v[r][q] = s * vip + c * viq
    eigenvalues = [a[0][0], a[1][1], a[2][2]]
    eigenvectors = [Vector((v[0][i], v[1][i], v[2][i])) for i in range(3)]
    return eigenvalues, eigenvectors

def _axes_to_matrix(x_axis: Vector, y_axis: Vector, z_axis: Vector) -> Matrix:
    mat3 = Matrix((
        (x_axis.x, y_axis.x, z_axis.x),
        (x_axis.y, y_axis.y, z_axis.y),
        (x_axis.z, y_axis.z, z_axis.z),
    ))
    mat4 = mat3.to_4x4()
    mat4.translation = Vector((0.0, 0.0, 0.0))
    return mat4

def _axes_from_pca3d(points: list[Vector]) -> Matrix | None:
    if len(points) < 3:
        return None
    centroid = Vector((0.0, 0.0, 0.0))
    for p in points:
        centroid += p
    centroid /= len(points)
    cov_xx = cov_xy = cov_xz = cov_yy = cov_yz = cov_zz = 0.0
    for p in points:
        d = p - centroid
        cov_xx += d.x * d.x
        cov_xy += d.x * d.y
        cov_xz += d.x * d.z
        cov_yy += d.y * d.y
        cov_yz += d.y * d.z
        cov_zz += d.z * d.z
    if len(points) > 1:
        scale = 1.0 / float(len(points) - 1)
        cov_xx *= scale
        cov_xy *= scale
        cov_xz *= scale
        cov_yy *= scale
        cov_yz *= scale
        cov_zz *= scale
    cov_matrix = [
        [cov_xx, cov_xy, cov_xz],
        [cov_xy, cov_yy, cov_yz],
        [cov_xz, cov_yz, cov_zz],
    ]
    eigenvalues, eigenvectors = _jacobi_eigen_decomposition(cov_matrix)
    axis_data = sorted(zip(eigenvalues, eigenvectors), key=lambda item: item[0], reverse=True)
    axes: list[Vector] = []
    for _, axis in axis_data:
        length = axis.length
        if length <= PCA_EPSILON:
            return None
        axes.append(axis / length)
    if len(axes) < 3:
        return None
    if axes[0].cross(axes[1]).dot(axes[2]) < 0.0:
        axes[2] = -axes[2]
    return _axes_to_matrix(axes[0], axes[1], axes[2])

def _axes_from_pca_xy(points: list[Vector]) -> Matrix | None:
    if not points:
        return None
    centroid = Vector((0.0, 0.0, 0.0))
    for p in points:
        centroid += p
    centroid /= len(points)
    cov_xx = cov_xy = cov_yy = 0.0
    for p in points:
        dx = p.x - centroid.x
        dy = p.y - centroid.y
        cov_xx += dx * dx
        cov_xy += dx * dy
        cov_yy += dy * dy
    if len(points) > 1:
        scale = 1.0 / float(len(points) - 1)
        cov_xx *= scale
        cov_xy *= scale
        cov_yy *= scale
    diff = cov_xx - cov_yy
    discriminant = math.sqrt(max(0.0, diff * diff + 4.0 * cov_xy * cov_xy))
    lambda1 = 0.5 * (cov_xx + cov_yy + discriminant)
    if abs(cov_xy) > PCA_EPSILON:
        vec = Vector((lambda1 - cov_yy, cov_xy))
    else:
        vec = Vector((1.0, 0.0)) if cov_xx >= cov_yy else Vector((0.0, 1.0))
    if vec.length <= PCA_EPSILON:
        vec = Vector((1.0, 0.0))
    x_axis = Vector((vec.x, vec.y, 0.0)).normalized()
    if x_axis.length <= PCA_EPSILON:
        x_axis = Vector((1.0, 0.0, 0.0))
    if x_axis.dot(Vector((1.0, 0.0, 0.0))) < 0.0:
        x_axis = -x_axis
    z_axis = Vector((0.0, 0.0, 1.0))
    y_axis = z_axis.cross(x_axis)
    if y_axis.length <= PCA_EPSILON:
        y_axis = Vector((0.0, 1.0, 0.0))
        x_axis = y_axis.cross(z_axis)
    x_axis.normalize()
    y_axis.normalize()
    z_axis.normalize()
    if x_axis.cross(y_axis).dot(z_axis) < 0.0:
        y_axis = -y_axis
    return _axes_to_matrix(x_axis, y_axis, z_axis)

def _compute_pca_matrix(
    points: list[Vector],
    *,
    lock_z_up: bool,
    fallback_to_z_up: bool = True,
) -> Matrix | None:
    if not points:
        return None
    if lock_z_up:
        return _axes_from_pca_xy(points)
    matrix = _axes_from_pca3d(points)
    if matrix is None and fallback_to_z_up:
        matrix = _axes_from_pca_xy(points)
    return matrix

def _pick_reference_rotation(
    context: bpy.types.Context,
    objects: list[bpy.types.Object],
    mode: str,
    *,
    lock_z_up: bool = False,
) -> OrientationPick:
    identity = Matrix.Identity(4)
    if not objects:
        return OrientationPick(identity, 'WORLD', None, None)
    desired_mode = (mode or DEFAULT_ORIENTATION_MODE).upper()
    if desired_mode not in ORIENTATION_MODE_KEYS:
        desired_mode = DEFAULT_ORIENTATION_MODE
    points_cache: list[Vector] | None = None
    def ensure_points() -> list[Vector]:
        nonlocal points_cache
        if points_cache is None:
            points_cache = _collect_world_points(
                context,
                objects,
                sample_limit=PCA_POINT_SAMPLE_LIMIT,
            )
        return points_cache
    if desired_mode == 'WORLD':
        return OrientationPick(identity, 'WORLD', None, None)
    if desired_mode == 'ROOT':
        rotation = _rotation_matrix_from_object(_shared_root_object(objects))
        if rotation is not None:
            return OrientationPick(rotation, 'ROOT', None, None)
        points = ensure_points()
        matrix = _compute_pca_matrix(points, lock_z_up=True, fallback_to_z_up=False)
        message = "Mixed roots detected; using PCA Z-Up instead."
        return OrientationPick(matrix or identity, 'PCA_ZUP' if matrix else 'WORLD', points or None, message)
    if desired_mode == 'LCA':
        rotation = _rotation_matrix_from_object(_find_lowest_common_ancestor(objects))
        if rotation is not None:
            return OrientationPick(rotation, 'LCA', None, None)
        points = ensure_points()
        matrix = _compute_pca_matrix(points, lock_z_up=True, fallback_to_z_up=False)
        message = "No common ancestor; using PCA Z-Up instead."
        return OrientationPick(matrix or identity, 'PCA_ZUP' if matrix else 'WORLD', points or None, message)
    if desired_mode == 'PCA3D':
        points = ensure_points()
        matrix = _compute_pca_matrix(points, lock_z_up=lock_z_up, fallback_to_z_up=not lock_z_up)
        if matrix is not None:
            effective = 'PCA_ZUP' if lock_z_up else 'PCA3D'
            return OrientationPick(matrix, effective, points or None, None)
        message = "PCA 3D failed; using World axes."
        return OrientationPick(identity, 'WORLD', points or None, message)
    if desired_mode == 'PCA_ZUP':
        points = ensure_points()
        matrix = _compute_pca_matrix(points, lock_z_up=True, fallback_to_z_up=False)
        if matrix is not None:
            return OrientationPick(matrix, 'PCA_ZUP', points or None, None)
        return OrientationPick(identity, 'WORLD', points or None, "PCA Z-Up failed; using World axes.")
    return OrientationPick(identity, 'WORLD', None, None)

def _compute_oriented_aabb(
    context: bpy.types.Context,
    objects: list[bpy.types.Object],
    orientation_matrix: Matrix,
    *,
    points_override: list[Vector] | None = None,
) -> tuple[Vector, Vector] | None:
    if not objects:
        return None
    try:
        rotation = orientation_matrix.to_3x3()
    except Exception:
        rotation = Matrix.Identity(3)
    try:
        world_to_ref = rotation.inverted()
    except Exception:
        world_to_ref = Matrix.Identity(3)
    min_corner = Vector((float('inf'), float('inf'), float('inf')))
    max_corner = Vector((float('-inf'), float('-inf'), float('-inf')))
    has_points = False
    def accumulate(world_co: Vector) -> None:
        nonlocal has_points, min_corner, max_corner
        if world_co is None:
            return
        try:
            oriented = world_to_ref @ world_co
        except Exception:
            oriented = Vector((float(world_co[0]), float(world_co[1]), float(world_co[2])))
        for idx in range(3):
            value = oriented[idx]
            if value < min_corner[idx]:
                min_corner[idx] = value
            if value > max_corner[idx]:
                max_corner[idx] = value
        has_points = True
    if points_override:
        for point in points_override:
            accumulate(point)
    else:
        points = _collect_world_points(
            context,
            objects,
            sample_limit=PCA_POINT_SAMPLE_LIMIT,
        )
        for point in points:
            accumulate(point)
    if not has_points:
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

def _update_envelope_geometry(
    envelope: bpy.types.Object,
    size: Vector,
    center_o: Vector,
    orientation_matrix: Matrix,
) -> tuple[Vector, Vector]:
    mesh = envelope.data
    if mesh is None:
        mesh = bpy.data.meshes.new("LP_DimensionEnvelopeMesh")
        envelope.data = mesh
    mesh.clear_geometry()
    size_abs = Vector((abs(float(size.x)), abs(float(size.y)), abs(float(size.z))))
    half = size_abs * 0.5
    verts = [
        Vector((-half.x, -half.y, -half.z)),
        Vector((half.x, -half.y, -half.z)),
        Vector((half.x, half.y, -half.z)),
        Vector((-half.x, half.y, -half.z)),
        Vector((-half.x, -half.y, half.z)),
        Vector((half.x, -half.y, half.z)),
        Vector((half.x, half.y, half.z)),
        Vector((-half.x, half.y, half.z)),
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
    mesh.from_pydata(verts, edges, faces)
    mesh.update(calc_edges=True)
    try:
        rotation3 = orientation_matrix.to_3x3()
    except Exception:
        rotation3 = Matrix.Identity(3)
    center_world = rotation3 @ center_o
    envelope.location = center_world
    envelope.rotation_mode = 'QUATERNION'
    try:
        envelope.rotation_quaternion = orientation_matrix.to_quaternion()
    except Exception:
        envelope.rotation_quaternion = rotation3.to_quaternion()
    envelope.scale = (1.0, 1.0, 1.0)
    envelope.hide_render = True
    envelope.show_in_front = True
    try:
        envelope.display_type = 'WIRE'
    except Exception:
        pass
    envelope[DIM_ENVELOPE_PROP] = True
    envelope[DIM_SIZE_PROP] = (size_abs.x, size_abs.y, size_abs.z)
    return size_abs, center_world

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

def _ensure_overlay_draw_handler() -> None:

    global _OVERLAY_DRAW_HANDLE
    if _OVERLAY_DRAW_HANDLE is None:
        try:
            _OVERLAY_DRAW_HANDLE = bpy.types.SpaceView3D.draw_handler_add(_draw_dimension_overlay, (), OVERLAY_DRAW_REGION, OVERLAY_DRAW_TYPE)
            _overlay_debug_print("Draw handler installed")
        except Exception as exc:
            _overlay_debug_print(f"Failed to install draw handler: {exc}")
            _OVERLAY_DRAW_HANDLE = None

def _remove_overlay_draw_handler() -> None:

    global _OVERLAY_DRAW_HANDLE
    if _OVERLAY_DRAW_HANDLE is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_OVERLAY_DRAW_HANDLE, OVERLAY_DRAW_REGION)
            _overlay_debug_print("Draw handler removed")
        except Exception as exc:
            _overlay_debug_print(f"Failed to remove draw handler: {exc}")
        _OVERLAY_DRAW_HANDLE = None

def disable_dimension_overlay_guard() -> None:

    _overlay_debug_print('Disabling overlay draw handler from unregister')
    _remove_overlay_draw_handler()

def _format_dimension_lines(axis: str, length: float, scene: bpy.types.Scene | None) -> list[tuple[str, str]]:

    scene_obj = scene or getattr(bpy.context, "scene", None)
    if scene_obj is not None:
        try:
            scale_length = float(scene_obj.unit_settings.scale_length) or 1.0
        except Exception:
            scale_length = 1.0
    else:
        scale_length = 1.0
    length_m = float(length) * scale_length
    mm_value = length_m * 1000.0
    cm_value = length_m * 100.0
    inch_value = length_m / 0.0254 if length_m else 0.0
    return [
        ("Axis", f"{axis}"),
        (f"{mm_value:.1f}", "mm"),
        (f"{cm_value:.2f}", "cm"),
        (f"{inch_value:.2f}", "in"),
    ]

def _dimension_axis_data(envelope: bpy.types.Object) -> list[tuple[str, float, Vector]]:

    size_data = envelope.get(DIM_SIZE_PROP)
    if size_data:
        try:
            size_vec = Vector((float(size_data[0]), float(size_data[1]), float(size_data[2])))
        except Exception:
            size_vec = Vector(envelope.dimensions) if hasattr(envelope, "dimensions") else None
    else:
        size_vec = Vector(envelope.dimensions) if hasattr(envelope, "dimensions") else None
    if size_vec is None:
        return []
    size_vec = Vector((abs(float(size_vec.x)), abs(float(size_vec.y)), abs(float(size_vec.z))))
    half = size_vec * 0.5
    local_vertices = {
        0: Vector((-half.x, -half.y, -half.z)),
        1: Vector((half.x, -half.y, -half.z)),
        2: Vector((half.x, half.y, -half.z)),
        3: Vector((-half.x, half.y, -half.z)),
        4: Vector((-half.x, -half.y, half.z)),
        5: Vector((half.x, -half.y, half.z)),
        6: Vector((half.x, half.y, half.z)),
        7: Vector((-half.x, half.y, half.z)),
    }
    axis_edges = {
        "X": (4, 5),
        "Y": (1, 2),
        "Z": (0, 4),
    }
    axis_lengths = {
        "X": float(size_vec.x),
        "Y": float(size_vec.y),
        "Z": float(size_vec.z),
    }
    axis_info: list[tuple[str, float, Vector]] = []
    matrix = envelope.matrix_world
    offset = max(size_vec.x, size_vec.y, size_vec.z) * 0.02
    for axis, (v1_idx, v2_idx) in axis_edges.items():
        length = axis_lengths.get(axis, 0.0)
        if length <= 1e-6:
            continue
        v1 = local_vertices[v1_idx]
        v2 = local_vertices[v2_idx]
        midpoint_local = (v1 + v2) * 0.5
        direction = midpoint_local.normalized() if midpoint_local.length > 1e-6 else Vector((0.0, 0.0, 0.0))
        midpoint_local = midpoint_local + direction * offset
        midpoint_world = matrix @ midpoint_local
        axis_info.append((axis, length, midpoint_world))
    return axis_info

def _draw_dimension_overlay() -> None:

    ctx = bpy.context
    if ctx is None:
        return
    region = getattr(ctx, "region", None)
    rv3d = getattr(ctx, "region_data", None)
    if region is None or rv3d is None:
        _overlay_debug_print('Draw skipped: missing region or rv3d')
        return
    view_layer = getattr(ctx, "view_layer", None)
    layer_objects = getattr(view_layer, "objects", None) if view_layer else None
    active = getattr(layer_objects, "active", None) if layer_objects else None
    if active is None or not active.get(DIM_ENVELOPE_PROP):
        _overlay_debug_print('Draw skipped: active is not envelope')
        return
    axis_data = _dimension_axis_data(active)
    if not axis_data:
        _overlay_debug_print('Draw skipped: no axis data')
        return
    scene = getattr(ctx, "scene", None)
    font_id = 0
    try:
        blf.size(font_id, OVERLAY_FONT_SIZE_PX, 72)
    except TypeError:
        blf.size(font_id, OVERLAY_FONT_SIZE_PX)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    try:
        for axis, length, world_point in axis_data:
            screen_point = view3d_utils.location_3d_to_region_2d(region, rv3d, world_point)
            if screen_point is None:
                _overlay_debug_print(f"Axis {axis} off-screen")
                continue
            screen_point = Vector((float(screen_point.x), float(screen_point.y)))
            anchor_point = screen_point + OVERLAY_SCREEN_OFFSET
            rows = _format_dimension_lines(axis, length, scene)
            if not rows:
                continue
            left_width = 0.0
            right_width = 0.0
            row_heights: list[float] = []
            left_row_widths: list[float] = []
            for left_text, right_text in rows:
                left_dims = blf.dimensions(font_id, left_text)
                right_dims = blf.dimensions(font_id, right_text)
                if isinstance(left_dims, (tuple, list)) and len(left_dims) >= 2:
                    left_w = float(left_dims[0])
                    left_h = float(left_dims[1])
                else:
                    left_w = float(left_dims) if left_dims is not None else 0.0
                    left_h = float(OVERLAY_FONT_SIZE_PX)
                if isinstance(right_dims, (tuple, list)) and len(right_dims) >= 2:
                    right_w = float(right_dims[0])
                    right_h = float(right_dims[1])
                else:
                    right_w = float(right_dims) if right_dims is not None else 0.0
                    right_h = float(OVERLAY_FONT_SIZE_PX)
                left_width = max(left_width, left_w)
                right_width = max(right_width, right_w)
                row_heights.append(max(left_h, right_h))
                left_row_widths.append(left_w)
            column_spacing = max(4.0, OVERLAY_FONT_SIZE_PX * 0.4)
            content_width = left_width + column_spacing + right_width
            line_spacing = max(2.0, OVERLAY_FONT_SIZE_PX * 0.2)
            total_height = sum(row_heights) + line_spacing * max(0, len(rows) - 1)
            pad = float(OVERLAY_PADDING_PX)
            origin_x = anchor_point.x - (content_width * 0.5)
            origin_y = anchor_point.y
            left = origin_x - pad
            right = origin_x + content_width + pad
            bottom = origin_y - pad
            top = origin_y + total_height + pad
            bg_vertices = [
                (left, bottom),
                (right, bottom),
                (right, top),
                (left, top),
            ]
            batch = batch_for_shader(shader, 'TRI_FAN', {'pos': bg_vertices})
            shader.bind()
            shader.uniform_float('color', OVERLAY_BG_COLOR)
            batch.draw(shader)
            blf.color(font_id, *OVERLAY_TEXT_COLOR)
            cursor_y = origin_y + total_height
            for idx, (left_w, row_height, (left_text, right_text)) in enumerate(zip(left_row_widths, row_heights, rows)):
                cursor_y -= row_height
                left_x = origin_x + left_width - left_w
                right_x = origin_x + left_width + column_spacing
                blf.position(font_id, left_x, cursor_y, 0)
                blf.draw(font_id, left_text)
                blf.position(font_id, right_x, cursor_y, 0)
                blf.draw(font_id, right_text)
                if idx < len(rows) - 1:
                    cursor_y -= line_spacing
            _overlay_debug_print('Drawing label rows', rows, 'at', (origin_x, origin_y))
    finally:
        gpu.state.blend_set('NONE')

class LIME_OT_dimension_envelope(bpy.types.Operator):

    """Create or update a dimension checker bounding box with custom viewport labels."""
    bl_idname = "lime.dimension_envelope"
    bl_label = "Dimension Checker"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Generate a Dimension Checker helper and enable custom labels in the viewport."
    orientation_mode: EnumProperty(
        name="Orientation Mode",
        description="Reference frame used for the Dimension Checker bounding box.",
        items=ORIENTATION_MODE_ITEMS,
        default=DEFAULT_ORIENTATION_MODE,
    )

    lock_z_up: BoolProperty(
        name="Lock Z-Up",
        description="Keep the global Z axis upright when PCA orientation is used.",
        default=False,
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
        use_lock_z = bool(self.lock_z_up and self.orientation_mode == 'PCA3D')
        orientation = _pick_reference_rotation(
            context,
            selection,
            self.orientation_mode,
            lock_z_up=use_lock_z,
        )
        bounds = _compute_oriented_aabb(
            context,
            selection,
            orientation.matrix,
            points_override=orientation.points,
        )
        if not bounds:
            self.report({'WARNING'}, "Unable to compute dimensions for the current selection.")
            return {'CANCELLED'}
        min_corner, max_corner = bounds
        size = max_corner - min_corner
        center_o = (max_corner + min_corner) * 0.5
        _update_envelope_geometry(envelope, size, center_o, orientation.matrix)
        envelope[DIM_ORIENTATION_PROP] = orientation.effective_mode
        _remove_existing_labels(envelope)
        display_label = selection[0].name if len(selection) == 1 else "Group"
        envelope.name = f"{display_label} {DIMENSION_HELPER_SUFFIX}"
        _ensure_overlay_draw_handler()
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
        if orientation.message:
            self.report({'INFO'}, orientation.message)
        mode_label = ORIENTATION_MODE_LABELS.get(orientation.effective_mode, orientation.effective_mode)
        self.report({'INFO'}, f"Dimension checker updated ({mode_label}).")
        return {'FINISHED'}

__all__ = [

    "LIME_OT_dimension_envelope",
    "disable_dimension_overlay_guard",

]