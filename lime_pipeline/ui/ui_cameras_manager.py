import bpy
from bpy.types import Panel, UIList, PropertyGroup
from bpy.props import (
    StringProperty,
    CollectionProperty,
    IntProperty,
)
from pathlib import Path

from ..core import validate_scene
from ..scene.scene_utils import ensure_camera_margin_backgrounds


CAT = "Lime Pipeline"


_CAM_LIST_HANDLER = None


class LIME_PT_render_cameras(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Cameras"
    bl_idname = "LIME_PT_render_cameras"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 6

    def draw(self, ctx):
        layout = self.layout
        scene = ctx.scene

        row = layout.row(align=True)
        row.template_list("LIME_UL_render_cameras", "", scene, "lime_render_cameras", scene, "lime_render_cameras_index", rows=6)

        col = row.column(align=True)
        col.operator("lime.add_camera_rig", text='', icon='ADD')
        del_op = col.operator("lime.delete_camera_rig_and_sync", text='', icon='REMOVE')
        try:
            idx = getattr(scene, 'lime_render_cameras_index', -1)
            items = getattr(scene, 'lime_render_cameras', None)
            if items is not None and 0 <= idx < len(items):
                del_op.camera_name = items[idx].name
        except Exception:
            pass
        col.separator()
        col.operator("lime.duplicate_active_camera", text='', icon='DUPLICATE')
        col.operator("lime.sync_camera_list", text='', icon='FILE_REFRESH')

        # -- Márgenes / Backgrounds section for selected camera --
        cam = getattr(scene, 'camera', None)
        if cam is not None and getattr(cam, 'type', None) == 'CAMERA':
            cam_data = getattr(cam, 'data', None)
            if cam_data is not None:
                layout.separator()
                layout.label(text="Márgenes / Backgrounds:")

                # Toggle for show_background_images with status message
                row = layout.row(align=True)
                row.prop(cam_data, 'show_background_images', text="Mostrar fondos")
                if not getattr(cam_data, 'show_background_images', True):
                    row.label(text="", icon='INFO')
                    activate_op = row.operator("lime.retry_camera_margin_backgrounds", text="Activar fondos", icon='CHECKBOX_HLT')
                    if activate_op is not None:
                        activate_op.set_visible = True

                # Sliders for each margin image if visible or show toggle is off
                if getattr(cam_data, 'show_background_images', True) or True:  # Always show sliders for config
                    # Target aliases in fixed order
                    margin_aliases = ["Box Horizontal", "Box", "Box Vertical"]
                    for alias in margin_aliases:
                        # Find matching background entry by checking if any entry's image name/filepath matches our target
                        entry = None
                        try:
                            for bg_entry in list(getattr(cam_data, 'background_images', []) or []):
                                try:
                                    img = getattr(bg_entry, 'image', None)
                                    fp = getattr(img, 'filepath', '') if img else ''
                                    name = getattr(img, 'name', '') if img else ''
                                    base = (Path(fp).name if fp else (name or '')).lower()
                                    target_base = alias.lower().replace(' ', '_') + '_margins.png'
                                    if target_base in base:
                                        entry = bg_entry
                                        break
                                except Exception:
                                    pass
                        except Exception:
                            pass

                        if entry is not None:
                            # Show slider with current alpha
                            row = layout.row(align=True)
                            alpha_slider = row.prop(entry, 'alpha', text=alias, slider=True)
                            row.scale_x = 0.7

                            # Visual indicator when alpha is 0
                            current_alpha = getattr(entry, 'alpha', 0.5)
                            if current_alpha == 0:
                                # Add a small visual indicator for zero opacity
                                indicator = row.row(align=True)
                                indicator.scale_x = 0.3
                                indicator.label(text="", icon='HIDE_OFF')
                                # Add quick reset button
                                reset_btn = indicator.row(align=True)
                                reset_btn.scale_x = 0.7
                                reset_op = reset_btn.operator("lime.reset_margin_alpha", text="0.5", icon='LOOP_BACK')
                                if reset_op is not None:
                                    reset_op.alias = alias
                                    reset_op.target_alpha = 0.5
                        else:
                            # Show missing entry with retry button
                            row = layout.row(align=True)
                            row.label(text=f"{alias}:", icon='ERROR')
                            retry_op = row.operator("lime.retry_camera_margin_backgrounds", text="Reintentar", icon='FILE_REFRESH')
                            if retry_op is not None:
                                retry_op.alias = alias


class LimeRenderCamItem(PropertyGroup):
    name: StringProperty(name="Camera")


class LIME_UL_render_cameras(UIList):
    bl_idname = "LIME_UL_render_cameras"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        scene = context.scene
        is_active = False
        try:
            is_active = (getattr(scene, 'camera', None) is not None and scene.camera and scene.camera.name == item.name)
        except Exception:
            pass
        split = layout.split(factor=0.85, align=True)
        split.label(text=item.name, icon='CHECKMARK' if is_active else 'OUTLINER_DATA_CAMERA')
        controls = split.row(align=True)
        controls.alignment = 'RIGHT'
        controls.scale_x = 0.9
        btn2 = controls.operator('lime.pose_camera_rig', text='', icon='POSE_HLT')
        btn2.camera_name = item.name


def register_camera_list_props():
    bpy.utils.register_class(LimeRenderCamItem)
    bpy.utils.register_class(LIME_UL_render_cameras)

    bpy.types.Scene.lime_render_cameras = CollectionProperty(type=LimeRenderCamItem)

    def _on_active_cam_index(self, context):
        try:
            idx = getattr(self, 'lime_render_cameras_index', -1)
            items = getattr(self, 'lime_render_cameras', None)
            if items is None or not (0 <= idx < len(items)):
                return
            name = items[idx].name
            cam = bpy.data.objects.get(name)
            if cam is not None and getattr(cam, 'type', None) == 'CAMERA':
                context.scene.camera = cam
                arm = None
                cur = getattr(cam, 'parent', None)
                while cur is not None:
                    try:
                        if getattr(cur, 'type', None) == 'ARMATURE':
                            arm = cur
                        cur = getattr(cur, 'parent', None)
                    except Exception:
                        break
                if arm is not None:
                    try:
                        for ob in context.selected_objects or []:
                            try:
                                ob.select_set(False)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    try:
                        arm.select_set(True)
                    except Exception:
                        pass
                    try:
                        cam.select_set(True)
                    except Exception:
                        pass
                    try:
                        context.view_layer.objects.active = arm
                    except Exception:
                        pass
        except Exception:
            pass

    bpy.types.Scene.lime_render_cameras_index = IntProperty(
        name="Active Camera Index",
        default=-1,
        options={'HIDDEN'},
        update=_on_active_cam_index,
    )

    bpy.types.Scene.lime_render_cameras_token = StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    from ..data.templates import C_CAM
    def _cams_in_scene(scene, prefer_active_shot: bool = True):
        try:
            if prefer_active_shot:
                shot = validate_scene.active_shot_context(bpy.context)
                if shot:
                    cam_coll = validate_scene.get_shot_child_by_basename(shot, C_CAM)
                    if cam_coll:
                        return [o for o in cam_coll.objects if getattr(o, 'type', None) == 'CAMERA']
        except Exception:
            pass
        try:
            return [o for o in scene.objects if getattr(o, 'type', None) == 'CAMERA']
        except Exception:
            return []

    def _compute_cam_token(scene=None) -> str:
        try:
            sc = scene or bpy.context.scene
            names = sorted([o.name for o in _cams_in_scene(sc)])
            return f"{getattr(sc, 'name', '')}:{len(names)}|" + "|".join(names)
        except Exception:
            return ""

    def _fill_cam_items(scene):
        try:
            items = getattr(scene, 'lime_render_cameras', None)
            if items is None:
                return
            items.clear()
            cams = _cams_in_scene(scene, prefer_active_shot=True)
            cams.sort(key=lambda o: o.name)
            seen_names = set()
            for cam in cams:
                name = getattr(cam, 'name', '') or ''
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                it = items.add()
                it.name = name
            try:
                active_name = getattr(scene.camera, 'name', '') if getattr(scene, 'camera', None) else ''
                if active_name:
                    for i, it in enumerate(items):
                        if it.name == active_name:
                            scene.lime_render_cameras_index = i
                            break
            except Exception:
                pass
        except Exception:
            pass

    def _cam_depsgraph_update_post(_deps):
        scene = bpy.context.scene
        if scene is None:
            return
        try:
            cur = _compute_cam_token(scene)
            prev = getattr(scene, 'lime_render_cameras_token', '') or ''
            if cur != prev:
                _fill_cam_items(scene)
                scene.lime_render_cameras_token = cur
                # Always do recheck to ensure consistency, but with improved logic
                def _recheck():
                    try:
                        sc = bpy.context.scene
                        if sc is None:
                            return None
                        now = _compute_cam_token(sc)
                        prev2 = getattr(sc, 'lime_render_cameras_token', '') or ''
                        if now != prev2:
                            _fill_cam_items(sc)
                            sc.lime_render_cameras_token = now
                        # Also check again after a short delay to catch any remaining changes
                        def _delayed_recheck():
                            try:
                                s = bpy.context.scene
                                if s is None:
                                    return None
                                current = _compute_cam_token(s)
                                prev3 = getattr(s, 'lime_render_cameras_token', '') or ''
                                if current != prev3:
                                    _fill_cam_items(s)
                                    s.lime_render_cameras_token = current
                            except Exception:
                                pass
                            return None
                        import bpy as _bpy3
                        _bpy3.app.timers.register(_delayed_recheck, first_interval=0.2)
                    except Exception:
                        pass
                    return None
                import bpy as _bpy2
                _bpy2.app.timers.register(_recheck, first_interval=0.1)
        except Exception:
            pass

    global _CAM_LIST_HANDLER
    if _CAM_LIST_HANDLER is None:
        _CAM_LIST_HANDLER = _cam_depsgraph_update_post
        if _CAM_LIST_HANDLER not in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.append(_CAM_LIST_HANDLER)
    try:
        scene = bpy.context.scene
        if scene is not None:
            cur = _compute_cam_token(scene)
            if cur != (getattr(scene, 'lime_render_cameras_token', '') or ''):
                _fill_cam_items(scene)
                scene.lime_render_cameras_token = cur
    except Exception:
        pass


def unregister_camera_list_props():
    for attr in (
        'lime_render_cameras',
        'lime_render_cameras_index',
        'lime_render_cameras_token',
    ):
        try:
            delattr(bpy.types.Scene, attr)
        except Exception:
            pass
    global _CAM_LIST_HANDLER
    if _CAM_LIST_HANDLER is not None:
        try:
            bpy.app.handlers.depsgraph_update_post.remove(_CAM_LIST_HANDLER)
        except Exception:
            pass
        _CAM_LIST_HANDLER = None
    for cls in (
        LIME_UL_render_cameras,
        LimeRenderCamItem,
    ):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass


__all__ = [
    "LIME_PT_render_cameras",
    "LIME_UL_render_cameras",
    "LimeRenderCamItem",
    "register_camera_list_props",
    "unregister_camera_list_props",
]
