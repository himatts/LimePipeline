"""
Auto Camera Background Operators

This module provides comprehensive functionality for creating and managing automatic
camera background planes that follow the active camera based on timeline markers.
The system creates background planes that automatically fill the camera frame and
update their position, rotation, and scale in real-time.

The auto camera background system supports:
- Automatic background plane creation and placement in SHOT collections
- Real-time tracking of camera movements based on timeline markers
- Configurable distance and padding parameters for frame filling
- Support for both perspective and orthographic cameras
- Live update handlers for smooth animation playback
- Baking of background animations to keyframes for static shots
- Comprehensive cleanup and state management utilities

Key Features:
- Marker-based camera tracking with automatic plane positioning
- Configurable distance and padding for frame coverage control
- Support for multiple background planes per scene
- SHOT-based organization and collection management
- Live update system with performance optimizations
- Bake-to-keyframes functionality for static animation
- Diagnostic and cleanup utilities for troubleshooting
- Comprehensive error handling and user feedback
"""
from __future__ import annotations
import bpy
from bpy.types import Operator
from bpy.props import EnumProperty, BoolProperty, IntProperty
from bpy.app.handlers import persistent
from mathutils import Vector
import bmesh
import uuid
import re

from ..core import validate_scene
from ..data import C_BG
from ..scene.scene_utils import make_collection
# Constants
PROP_DIST = "lpbg_distance"
PROP_PAD = "lpbg_padding"
DEFAULT_DIST = 10.0
DEFAULT_PAD = 2.0
PROP_MANUAL_SCALE = "lpbg_manual_scale"
PROP_UID = "lpbg_uid"

_BG_COLL_RE = re.compile(r"^SH\d{2,3}_90_BG(\.\d{3})?$")
# Handler management
_BG_HANDLER = None
_HANDLER_LISTS = (
    bpy.app.handlers.depsgraph_update_post,
    bpy.app.handlers.frame_change_post,
)

def _resolve_target_plane(
    context,
    *,
    shot: bpy.types.Collection | None = None,
    require_shot_match: bool = False,
) -> bpy.types.Object | None:
    """Resolve which BG plane to operate on."""
    scene = getattr(context, "scene", None)
    try:
        selected = [obj for obj in getattr(context, "selected_objects", []) if obj.get("LP_AUTO_BG")]
    except Exception:
        selected = []

    def _matches_shot(obj: bpy.types.Object) -> bool:
        if shot is None or scene is None:
            return True
        return _resolve_plane_shot(scene, obj) == shot

    if selected:
        if not require_shot_match:
            if len(selected) == 1:
                return selected[0]
            return None
        filtered = [obj for obj in selected if _matches_shot(obj)]
        if len(filtered) == 1:
            return filtered[0]
        if len(filtered) > 1:
            return None
        if not require_shot_match and len(selected) == 1:
            return selected[0]

    if scene is None:
        return None

    planes = list(_iter_scene_bg_planes(scene))
    if shot is not None:
        planes = [plane for plane in planes if _matches_shot(plane)]
        if len(planes) == 1:
            return planes[0]
        if len(planes) > 1:
            return None  # requerir selección explícita cuando hay múltiples en el shot
        # Si no hay planos en el shot activo, no buscar en otros shots
        return None

    # Sin shot específico, usar lógica anterior
    if len(planes) == 1:
        return planes[0]
    if len(planes) > 1:
        return None

    return None
def _ensure_plane_properties(plane: bpy.types.Object) -> None:
    """Ensure Auto BG custom properties and UI metadata exist on the plane."""
    if PROP_DIST not in plane:
        plane[PROP_DIST] = DEFAULT_DIST
    ui_dist = plane.id_properties_ui(PROP_DIST)
    ui_dist.update(
        default=float(DEFAULT_DIST),
        min=0.01,
        max=1000.0,
        soft_min=0.1,
        soft_max=500.0,
        description="Distance from the active camera along its local -Z axis (meters).",
    )

    if PROP_PAD not in plane:
        plane[PROP_PAD] = DEFAULT_PAD
    ui_pad = plane.id_properties_ui(PROP_PAD)
    ui_pad.update(
        default=float(DEFAULT_PAD),
        min=1.0,
        max=10.0,
        soft_min=1.0,
        soft_max=10.0,
        description="Multiplier that enlarges the plane slightly so it overfills the frame.",
    )

    if PROP_MANUAL_SCALE not in plane:
        plane[PROP_MANUAL_SCALE] = False
    ui_manual = plane.id_properties_ui(PROP_MANUAL_SCALE)
    ui_manual.update(
        default=False,
        description="When enabled, auto-scaling is skipped so you can adjust the object scale manually.",
    )
    _ensure_plane_uid(plane)

def _ensure_plane_uid(plane: bpy.types.Object) -> str:
    """Ensure the plane has a unique identifier property."""
    uid = plane.get(PROP_UID)
    if uid:
        for obj in bpy.data.objects:
            if obj is not plane and obj.get(PROP_UID) == uid:
                uid = None
                break
    if not uid:
        uid = str(uuid.uuid4())
        plane[PROP_UID] = uid
    return uid


def _create_plane_object(name: str = "LP_BG_Plane", size: float = 1.0) -> bpy.types.Object:
    """Create a mesh plane object without relying on VIEW_3D context."""
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bm = bmesh.new()
    half = size * 0.5
    verts = [
        bm.verts.new((-half, -half, 0.0)),
        bm.verts.new((half, -half, 0.0)),
        bm.verts.new((half, half, 0.0)),
        bm.verts.new((-half, half, 0.0)),
    ]
    bm.faces.new(verts)
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    plane = bpy.data.objects.new(name, mesh)
    plane.rotation_mode = 'QUATERNION'
    return plane


def _shot_index_width(index: int) -> int:
    return 3 if index >= 100 else 2


def _format_shot_child_name(shot_idx: int, base: str) -> str:
    if shot_idx <= 0:
        return base
    width = _shot_index_width(shot_idx)
    return f"SH{shot_idx:0{width}d}_{base}"


def _is_shot_bg_collection(coll: bpy.types.Collection) -> bool:
    name = getattr(coll, "name", "") or ""
    core = name.split('.', 1)[0]
    return bool(_BG_COLL_RE.match(core))


def _iter_collection_tree(root: bpy.types.Collection):
    stack = [root]
    seen: set[int] = set()
    while stack:
        coll = stack.pop()
        ident = coll.as_pointer() if hasattr(coll, "as_pointer") else id(coll)
        if ident in seen:
            continue
        seen.add(ident)
        yield coll
        try:
            stack.extend(list(coll.children))
        except Exception:
            pass


def _collect_shot_cameras(shot: bpy.types.Collection) -> tuple[bpy.types.Object, ...]:
    cameras: list[bpy.types.Object] = []
    if shot is None:
        return tuple()
    for coll in _iter_collection_tree(shot):
        try:
            for obj in coll.objects:
                if getattr(obj, "type", None) == 'CAMERA':
                    cameras.append(obj)
        except Exception:
            pass
    return tuple(cameras)


def _ensure_shot_bg_collection(shot: bpy.types.Collection) -> bpy.types.Collection | None:
    if shot is None:
        return None
    shot_idx = validate_scene.parse_shot_index(getattr(shot, "name", "") or "") or 0
    coll = validate_scene.get_shot_child_by_basename(shot, C_BG)
    if coll is None:
        name = _format_shot_child_name(shot_idx, C_BG)
        coll = make_collection(shot, name)
    return coll


def _resolve_plane_shot(scene: bpy.types.Scene, plane: bpy.types.Object) -> bpy.types.Collection | None:
    if plane is None:
        return None
    try:
        collections = list(getattr(plane, "users_collection", []) or [])
    except Exception:
        collections = []
    for coll in collections:
        shot = validate_scene.find_shot_root_for_collection(coll, scene)
        if shot is not None:
            return shot
    return None


def _ensure_plane_in_shot_bg(context, plane: bpy.types.Object, shot: bpy.types.Collection | None = None) -> bpy.types.Collection:
    scene = getattr(context, "scene", None)
    shot = shot or _resolve_plane_shot(scene, plane) or validate_scene.active_shot_context(context)
    if shot is None:
        raise RuntimeError("No active SHOT to place Auto BG plane.")
    bg_coll = _ensure_shot_bg_collection(shot)
    if bg_coll is None:
        raise RuntimeError("Unable to locate or create SHxx_90_BG collection for the shot.")

    # Unlink de TODAS las colecciones distintas a la BG objetivo
    try:
        for coll in tuple(getattr(plane, "users_collection", []) or []):
            if coll is not bg_coll:
                try:
                    coll.objects.unlink(plane)
                except Exception:
                    pass
    except Exception:
        pass

    # Link garantizado a la BG objetivo
    try:
        if plane.name not in bg_coll.objects:
            bg_coll.objects.link(plane)
    except Exception:
        pass

    return shot


def _iter_scene_bg_planes(scene: bpy.types.Scene):
    if scene is None:
        return tuple()
    try:
        return tuple(obj for obj in scene.objects if obj.get("LP_AUTO_BG"))
    except Exception:
        return tuple()


def ensure_auto_bg_live_updates(
    *,
    scene: bpy.types.Scene | None = None,
    force_update: bool = True,
) -> bool:
    """Garantizar que los planos Auto BG tengan handler y actualización tras cargar un archivo.

    Args:
        scene: Escena específica a comprobar. Si es ``None`` se recorren todas las escenas disponibles.
        force_update: Si es ``True`` se fuerza una actualización inmediata tras reinstalar el handler.

    Returns:
        bool: ``True`` si se encontraron planos Auto BG en alguna escena y se realizaron acciones.
    """

    scenes: list[bpy.types.Scene | None] = []
    if scene is not None:
        scenes.append(scene)
    else:
        try:
            scenes.extend(list(bpy.data.scenes))
        except Exception:
            pass
        if not scenes:
            try:
                ctx_scene = getattr(bpy.context, "scene", None)
            except Exception:
                ctx_scene = None
            if ctx_scene is not None:
                scenes.append(ctx_scene)

    has_planes = False
    for scn in scenes:
        if scn is None:
            continue
        planes = list(_iter_scene_bg_planes(scn))
        if not planes:
            continue
        has_planes = True
        for plane in planes:
            try:
                _ensure_plane_properties(plane)
            except Exception:
                pass

    if not has_planes:
        return False

    _install_handler()

    if force_update:
        for scn in scenes:
            if scn is None:
                continue
            try:
                _auto_bg_update_handler(scn)
            except Exception:
                pass

    return True

def _iter_camera_markers(
    scene: bpy.types.Scene,
    frame_limit: int | None = None,
    allowed_cameras: set[bpy.types.Object] | None = None,
):
    """Iterate over timeline markers that have camera references."""
    markers = sorted(scene.timeline_markers, key=lambda marker: marker.frame)
    allowed = allowed_cameras if isinstance(allowed_cameras, set) else (set(allowed_cameras) if allowed_cameras is not None else None)
    for marker in markers:
        camera = getattr(marker, "camera", None)
        if not camera:
            continue
        if allowed is not None and camera not in allowed:
            continue
        if frame_limit is not None and marker.frame > frame_limit:
            break
        yield marker
def _get_active_camera_at_frame(
    scene: bpy.types.Scene,
    frame: int,
    allowed_cameras: set[bpy.types.Object] | None = None,
) -> bpy.types.Object | None:
    """Get the active camera at the given frame based on markers."""
    allowed = allowed_cameras if isinstance(allowed_cameras, set) else (set(allowed_cameras) if allowed_cameras is not None else None)
    active_marker = None
    for marker in scene.timeline_markers:
        camera = getattr(marker, "camera", None)
        if not camera:
            continue
        if allowed is not None and camera not in allowed:
            continue
        if marker.frame <= frame and (active_marker is None or marker.frame > active_marker.frame):
            active_marker = marker
    if active_marker:
        return active_marker.camera
    return None
def _calculate_plane_size(camera: bpy.types.Object, distance: float, padding: float, scene: bpy.types.Scene = None) -> tuple[float, float]:
    """Calculate required plane width and height to fill camera frame."""
    camera_data = camera.data
    if camera_data.type == 'ORTHO':
        # Orthographic camera
        ortho_scale = camera_data.ortho_scale
        if scene is None:
            scene = bpy.context.scene
        aspect_ratio = scene.render.resolution_x / scene.render.resolution_y
        # ortho_scale is half the vertical size, so multiply by 2 for full height
        height = ortho_scale * 2.0 * padding
        width = height * aspect_ratio
        return width, height
    else:
        # Perspective camera
        # Get camera angles in radians
        angle_x = camera_data.angle_x
        angle_y = camera_data.angle_y
        # Calculate plane size at given distance with safety check
        import math
        half_angle_x = angle_x / 2.0
        half_angle_y = angle_y / 2.0
        if half_angle_x > 0.001 and half_angle_y > 0.001:
            width = 2.0 * distance * math.tan(half_angle_x) * padding
            height = 2.0 * distance * math.tan(half_angle_y) * padding
        else:
            # Fallback for very small angles
            width = distance * padding
            height = distance * padding
        return width, height
# DEBUG COMPLETAMENTE DESACTIVADO - No generar ningún mensaje en consola
# def _debug_print(message: str) -> None:
#     """Print debug message if debug mode is enabled."""
#     # Esta función ha sido completamente desactivada para eliminar ruido en consola
#     pass
def _update_plane(
    scene: bpy.types.Scene,
    plane: bpy.types.Object,
    distance: float,
    padding: float,
    *,
    shot: bpy.types.Collection | None = None,
    allowed_cameras: set[bpy.types.Object] | None = None,
) -> None:
    """Update plane position, rotation, and scale for current frame."""
    frame_current = getattr(scene, 'frame_current', 0)
    _ensure_plane_properties(plane)
    shot_ctx = shot or _resolve_plane_shot(scene, plane)
    if shot_ctx is None:
        return
    allowed = allowed_cameras if isinstance(allowed_cameras, set) else (set(allowed_cameras) if allowed_cameras is not None else None)
    if allowed is None:
        allowed = set(_collect_shot_cameras(shot_ctx))
    if not allowed:
        return
    camera = _get_active_camera_at_frame(scene, frame_current, allowed_cameras=allowed)
    if not camera:
        return
    cam_matrix = camera.matrix_world.copy()
    try:
        plane.location = cam_matrix @ Vector((0.0, 0.0, -distance))
    except Exception:
        return
    try:
        plane.rotation_mode = 'QUATERNION'
        plane.rotation_quaternion = cam_matrix.to_quaternion()
    except Exception:
        pass
    if bool(plane.get(PROP_MANUAL_SCALE)):
        return
    try:
        cam_world_loc = cam_matrix.to_translation()
        effective_distance = (plane.location - cam_world_loc).length
        distance_for_size = effective_distance if effective_distance > 1e-6 else distance
        width, height = _calculate_plane_size(camera, distance_for_size, padding, scene)
        plane.scale = (width / 2.0, height / 2.0, 1.0)
    except Exception:
        pass
# Global variables
_last_processed_frames: dict[int, int] = {}

def _clear_frame_history() -> None:
    """Clear the frame processing history."""
    _last_processed_frames.clear()

@persistent
def _auto_bg_update_handler(scene: bpy.types.Scene | None = None, depsgraph=None) -> None:
    """Update all active BG planes when the scene or depsgraph changes."""
    try:
        handler_registered = any(_BG_HANDLER in handler_list for handler_list in _HANDLER_LISTS)
        if not handler_registered:
            return

        if scene is None and depsgraph is not None:
            scene = getattr(depsgraph, "scene", None) or getattr(depsgraph, "scene_eval", None)
        if scene is None:
            scene = bpy.context.scene
        if scene is None:
            return

        bg_planes = list(_iter_scene_bg_planes(scene))
        if not bg_planes:
            return

        frame_current = getattr(scene, "frame_current", None)
        scene_key = scene.as_pointer() if hasattr(scene, "as_pointer") else id(scene)
        is_frame_change_event = depsgraph is None
        if is_frame_change_event and frame_current is not None:
            last_frame = _last_processed_frames.get(scene_key)
            if last_frame == frame_current:
                return
            _last_processed_frames[scene_key] = frame_current

        camera_cache: dict[int, tuple[bpy.types.Object, ...]] = {}
        allowed_cache: dict[int, set[bpy.types.Object]] = {}

        for plane in bg_planes:
            try:
                dist = float(plane.get(PROP_DIST, DEFAULT_DIST))
                pad = float(plane.get(PROP_PAD, DEFAULT_PAD))
                shot = _resolve_plane_shot(scene, plane)
                if shot is None:
                    continue
                shot_key = shot.as_pointer() if hasattr(shot, "as_pointer") else id(shot)
                cameras = camera_cache.get(shot_key)
                if cameras is None:
                    cameras = _collect_shot_cameras(shot)
                    camera_cache[shot_key] = cameras
                if not cameras:
                    continue
                allowed = allowed_cache.get(shot_key)
                if allowed is None:
                    allowed = set(cameras)
                    allowed_cache[shot_key] = allowed
                _update_plane(scene, plane, dist, pad, shot=shot, allowed_cameras=allowed)
            except Exception:
                pass
    except Exception:
        pass

def _ensure_bg_plane(context) -> tuple[bpy.types.Object | None, bpy.types.Collection | None]:
    """Create or find existing BG plane and ensure it is placed inside the shot BG collection."""
    scene = getattr(context, 'scene', None)
    active_shot = validate_scene.active_shot_context(context)

    plane = None
    shot = None
    if active_shot is not None:
        plane = _resolve_target_plane(context, shot=active_shot, require_shot_match=True)
        if plane is not None:
            shot = active_shot

    if plane is None:
        plane = _resolve_target_plane(context)
        if plane is not None and scene is not None:
            shot = _resolve_plane_shot(scene, plane)
            if active_shot is not None and shot != active_shot:
                plane = None
                shot = None

    if plane is not None:
        _ensure_plane_properties(plane)
        try:
            shot = _ensure_plane_in_shot_bg(context, plane, shot=shot or active_shot)
        except RuntimeError:
            if scene is not None and shot is None:
                shot = _resolve_plane_shot(scene, plane)
        return plane, shot

    shot = active_shot
    if shot is None:
        raise RuntimeError('Activate a SHOT collection before creating an Auto BG plane.')

    plane = _create_plane_object()
    plane['LP_AUTO_BG'] = True
    _ensure_plane_properties(plane)

    # Ensure plane is in scene
    scene = getattr(context, 'scene', None)
    if scene and plane.name not in scene.objects:
        scene.collection.objects.link(plane)

    _ensure_plane_in_shot_bg(context, plane, shot=shot)

    # Ensure plane is visible
    try:
        plane.hide_set(False)
        plane.hide_viewport = False
        plane.hide_render = False
    except Exception:
        pass

    try:
        plane.select_set(True)
    except Exception:
        pass
    try:
        view_layer = getattr(context, 'view_layer', None)
        if view_layer is not None:
            view_layer.objects.active = plane
    except Exception:
        pass
    return plane, shot
def _remove_handler_if_any() -> None:
    """Remove BG handler if registered."""
    global _BG_HANDLER
    if not _BG_HANDLER:
        return
    removed = False
    for handler_list in _HANDLER_LISTS:
        if _BG_HANDLER in handler_list:
            handler_list.remove(_BG_HANDLER)
            removed = True
    if removed:
        _BG_HANDLER = None


def _install_handler() -> None:
    """Install BG handler if not already present."""
    global _BG_HANDLER
    if _BG_HANDLER is None:
        _BG_HANDLER = _auto_bg_update_handler
    installed = False
    for handler_list in _HANDLER_LISTS:
        if _BG_HANDLER not in handler_list:
            handler_list.append(_BG_HANDLER)
            installed = True
    if installed:
        _clear_frame_history()  # Clear history when installing handler

class LIME_OT_auto_camera_background(Operator):
    """Create or update Auto Camera Background plane that follows active camera based on markers."""
    bl_idname = "lime.auto_camera_background"
    bl_label = "Auto Camera Background"
    bl_description = "Create background plane that automatically follows active camera based on markers"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        scene = getattr(context, "scene", None)
        if not scene:
            return False
        shot = validate_scene.active_shot_context(context)
        if shot is None:
            return False
        cameras = _collect_shot_cameras(shot)
        if not cameras:
            return False
        allowed = set(cameras)
        return any(marker.camera and marker.camera in allowed for marker in scene.timeline_markers)
    def execute(self, context):
        scene = context.scene
        try:
            plane, shot = _ensure_bg_plane(context)
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        if not plane:
            self.report({'ERROR'}, "Failed to create background plane")
            return {'CANCELLED'}
        if shot is None:
            shot = _resolve_plane_shot(scene, plane)
        allowed = set(_collect_shot_cameras(shot)) if shot else set()
        if shot and not allowed:
            self.report({'ERROR'}, f"No cameras found in shot '{shot.name}'.")
            return {'CANCELLED'}
        dist = float(plane.get(PROP_DIST, DEFAULT_DIST))
        pad = float(plane.get(PROP_PAD, DEFAULT_PAD))
        _update_plane(scene, plane, dist, pad, shot=shot, allowed_cameras=allowed or None)
        _install_handler()
        self.report({'INFO'}, f"Auto Camera Background active for '{plane.name}'")
        return {'FINISHED'}
class LIME_OT_auto_camera_background_refresh(Operator):
    """Refresh Auto Camera Background plane position and scale for current frame."""
    bl_idname = "lime.auto_camera_background_refresh"
    bl_label = "Refresh BG"
    bl_description = "Recalculate background plane position and scale for current frame"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        return _resolve_target_plane(context) is not None
    def execute(self, context):
        scene = context.scene
        plane = _resolve_target_plane(context)
        if not plane:
            self.report({'ERROR'}, "No Auto Camera Background plane found")
            return {'CANCELLED'}
        shot = _resolve_plane_shot(scene, plane)
        if shot is None:
            try:
                shot = _ensure_plane_in_shot_bg(context, plane)
            except RuntimeError as exc:
                self.report({'ERROR'}, str(exc))
                return {'CANCELLED'}
        allowed = set(_collect_shot_cameras(shot)) if shot else set()
        if shot and not allowed:
            self.report({'ERROR'}, f"No cameras found in shot '{shot.name}'.")
            return {'CANCELLED'}
        dist = float(plane.get(PROP_DIST, DEFAULT_DIST))
        pad = float(plane.get(PROP_PAD, DEFAULT_PAD))
        _update_plane(scene, plane, dist, pad, shot=shot, allowed_cameras=allowed or None)
        self.report({'INFO'}, f"Refreshed background plane '{plane.name}'")
        return {'FINISHED'}
class LIME_OT_auto_camera_background_toggle_live(Operator):
    """Toggle live updates for Auto Camera Background planes."""
    bl_idname = "lime.auto_camera_background_toggle_live"
    bl_label = "Toggle Live BG"
    bl_description = "Enable or disable live background plane updates"
    bl_options = {'REGISTER', 'UNDO'}
    enable: BoolProperty(
        name="Enable Live Updates",
        default=True,
        description="Enable or disable live handler"
    )
    @classmethod
    def poll(cls, context):
        scene = getattr(context, "scene", None)
        if not scene:
            return False
        plane = _resolve_target_plane(context)
        if plane is not None:
            return True
        shot = validate_scene.active_shot_context(context)
        if shot is None:
            return False
        cameras = _collect_shot_cameras(shot)
        if not cameras:
            return False
        allowed = set(cameras)
        return any(marker.camera and marker.camera in allowed for marker in scene.timeline_markers)
    def execute(self, context):
        plane = getattr(context, "active_object", None)

        if self.enable:
            if not plane:
                plane = _resolve_target_plane(context)
            if not plane:
                self.report({'ERROR'}, "Select a background plane to enable live updates.")
                return {'CANCELLED'}
            if plane.type != 'MESH':
                self.report({'ERROR'}, "Active object must be a mesh plane.")
                return {'CANCELLED'}
            try:
                shot = _ensure_plane_in_shot_bg(context, plane)
            except RuntimeError as exc:
                self.report({'ERROR'}, str(exc))
                return {'CANCELLED'}
            _ensure_plane_properties(plane)
            plane["LP_AUTO_BG"] = True
            allowed = set(_collect_shot_cameras(shot))
            if not allowed:
                self.report({'ERROR'}, f"No cameras found in shot '{shot.name}'.")
                return {'CANCELLED'}
            scene = context.scene
            dist = float(plane.get(PROP_DIST, DEFAULT_DIST))
            pad = float(plane.get(PROP_PAD, DEFAULT_PAD))
            _update_plane(scene, plane, dist, pad, shot=shot, allowed_cameras=allowed)
            _install_handler()
            self.report({'INFO'}, "'{}' is now following camera markers".format(plane.name))
        else:
            plane = _resolve_target_plane(context)
            if not plane:
                self.report({'ERROR'}, "Select an Auto BG plane to disable live updates.")
                return {'CANCELLED'}

            plane.pop("LP_AUTO_BG", None)
            if not any(obj.get("LP_AUTO_BG") for obj in bpy.data.objects):
                _remove_handler_if_any()

            self.report({'INFO'}, "'{}' released from auto camera background".format(plane.name))

        return {'FINISHED'}
class LIME_OT_auto_camera_background_bake(Operator):
    """Bake the Auto BG plane transforms to keyframes and optionally disable live updates."""
    bl_idname = "lime.auto_camera_background_bake"
    bl_label = "Bake BG to Keyframes"
    bl_description = "Keyframe the BG plane over markers or full frame range; optionally disable live handler"
    bl_options = {'REGISTER', 'UNDO'}
    mode: EnumProperty(
        name="Bake Mode",
        items=[
            ('PER_MARKER', "Per Marker", "Keyframe at each camera marker frame"),
            ('EACH_FRAME', "Each Frame", "Keyframe every frame (or step) in scene range"),
        ],
        default='PER_MARKER'
    )
    step: IntProperty(
        name="Step",
        description="Frame step for EACH_FRAME mode",
        default=1, min=1, max=20
    )
    clear_existing: BoolProperty(
        name="Clear Existing Keys",
        default=True,
        description="Remove existing fcurves/keys for loc/rot/scale before baking"
    )
    live_off_after: BoolProperty(
        name="Live OFF After Bake",
        default=True,
        description="Disable the live handler after baking"
    )
    @classmethod
    def poll(cls, context):
        scene = getattr(context, "scene", None)
        if not scene:
            return False
        plane = _resolve_target_plane(context)
        if plane is None:
            return False
        shot = _resolve_plane_shot(scene, plane) or validate_scene.active_shot_context(context)
        if shot is None:
            return False
        return bool(_collect_shot_cameras(shot))
    def execute(self, context):
        scene = context.scene
        plane = _resolve_target_plane(context)
        if not plane:
            self.report({'ERROR'}, "Select a single Auto BG plane to bake.")
            return {'CANCELLED'}
        shot = _resolve_plane_shot(scene, plane) or validate_scene.active_shot_context(context)
        if shot is None:
            self.report({'ERROR'}, "Auto BG plane is not linked to a SHOT.")
            return {'CANCELLED'}
        allowed = set(_collect_shot_cameras(shot))
        if not allowed:
            self.report({'ERROR'}, f"No cameras found in shot '{shot.name}'.")
            return {'CANCELLED'}
        frames = []
        if self.mode == 'PER_MARKER':
            frames = sorted({marker.frame for marker in _iter_camera_markers(scene, allowed_cameras=allowed)})
            if not frames:
                self.report({'ERROR'}, f"No camera markers found for shot '{shot.name}'.")
                return {'CANCELLED'}
        else:  # EACH_FRAME
            frames = list(range(scene.frame_start, scene.frame_end + 1, self.step))
        if self.clear_existing and plane.animation_data:
            ad = plane.animation_data
            if ad.action:
                ad.action.fcurves.clear()
        dist = float(plane.get(PROP_DIST, DEFAULT_DIST))
        pad = float(plane.get(PROP_PAD, DEFAULT_PAD))
        current = scene.frame_current
        try:
            for frame in frames:
                scene.frame_set(frame)
                _update_plane(scene, plane, dist, pad, shot=shot, allowed_cameras=allowed)
                plane.keyframe_insert(data_path="location", frame=frame)
                plane.keyframe_insert(data_path="rotation_quaternion", frame=frame)
                plane.keyframe_insert(data_path="scale", frame=frame)
        finally:
            scene.frame_set(current)
        _update_plane(scene, plane, dist, pad, shot=shot, allowed_cameras=allowed)
        if self.live_off_after:
            plane.pop("LP_AUTO_BG", None)
            if not any(obj.get("LP_AUTO_BG") for obj in bpy.data.objects):
                _remove_handler_if_any()
        self.report({'INFO'}, f"Baked {len(frames)} keys ({self.mode}).")
        return {'FINISHED'}
def _diagnostic_info(context) -> str:
    """Return diagnostic information about BG planes in the scene."""
    scene = getattr(context, 'scene', None)
    if not scene:
        return "No scene context available"

    bg_objects = [obj for obj in scene.objects if obj.get("LP_AUTO_BG")]
    info_lines = []

    info_lines.append(f"Found {len(bg_objects)} BG planes in scene:")
    for obj in bg_objects:
        collections = [c.name for c in getattr(obj, "users_collection", [])]
        info_lines.append(f"  - {obj.name}: visible={obj.visible_get()}, collections={collections}")

    # Check for orphaned objects in bpy.data
    orphaned = [obj for obj in bpy.data.objects if obj.get("LP_AUTO_BG") and obj.name not in scene.objects]
    if orphaned:
        info_lines.append(f"Found {len(orphaned)} orphaned BG planes in bpy.data:")
        for obj in orphaned:
            info_lines.append(f"  - {obj.name} (not in scene)")

    return "\n".join(info_lines)


class LIME_OT_auto_camera_background_cleanup(Operator):
    """Clean up any inconsistent Auto Camera Background state."""
    bl_idname = "lime.auto_camera_background_cleanup"
    bl_label = "Cleanup BG State"
    bl_description = "Remove orphaned BG planes and reset handler state"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        scene = context.scene

        # Remove orphaned BG planes
        orphaned = [obj for obj in bpy.data.objects if obj.get("LP_AUTO_BG") and obj.name not in scene.objects]
        for obj in orphaned:
            bpy.data.objects.remove(obj)
            self.report({'INFO'}, f"Removed orphaned BG plane: {obj.name}")

        # Reset handler state
        _remove_handler_if_any()
        _clear_frame_history()

        self.report({'INFO'}, f"Cleanup completed. Removed {len(orphaned)} orphaned planes.")
        return {'FINISHED'}


__all__ = [
    "LIME_OT_auto_camera_background",
    "LIME_OT_auto_camera_background_refresh",
    "LIME_OT_auto_camera_background_toggle_live",
    "LIME_OT_auto_camera_background_bake",
    "LIME_OT_auto_camera_background_cleanup",
    "ensure_auto_bg_live_updates",
    "_diagnostic_info",
]
 