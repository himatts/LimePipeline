import bpy
from bpy.types import Panel, UIList, PropertyGroup, Operator
from bpy.props import (
    StringProperty,
    CollectionProperty,
    IntProperty,
)
from pathlib import Path

from ..core.paths import paths_for_type
from ..core.naming import hydrate_state_from_filepath
from ..core import validate_scene


CAT = "Lime Pipeline"


_CAM_LIST_HANDLER = None


class LIME_PT_render_configs(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Render Configs"
    bl_idname = "LIME_PT_render_configs"
    bl_order = 2

    def draw(self, ctx):
        layout = self.layout
        # Presets row (placeholders 1–5)
        row = layout.row(align=True)
        for i in range(1, 6):
            op = row.operator("lime.apply_preset_placeholder", text=str(i), icon='PRESET')
            op.preset_index = i
            op.tooltip = f"Preset {i}"


class LIME_PT_render_settings(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Settings"
    bl_parent_id = "LIME_PT_render_configs"

    def draw(self, ctx):
        layout = self.layout
        scene = ctx.scene

        # Resolution
        box = layout.box()
        box.label(text="Resolution")
        row = box.row(align=True)
        row.prop(scene.render, "resolution_x", text="X")
        row.prop(scene.render, "resolution_y", text="Y")

        # Cycles
        box = layout.box()
        box.label(text="Cycles")
        cy = getattr(scene, 'cycles', None)
        if cy is None:
            col = box.column()
            col.enabled = False
            col.label(text="Cycles not available", icon='INFO')
        else:
            col = box.column(align=True)
            col.label(text="Viewport")
            # One row: Noise Threshold, Samples, Denoise (checkbox without label)
            row = col.row(align=True)
            try:
                row.prop(cy, "preview_adaptive_threshold", text="Noise Threshold")
            except Exception:
                pass
            try:
                row.prop(cy, "preview_samples", text="Samples")
            except Exception:
                pass
            # Denoise toggle (prefer Cycles viewport prop; fallback to View Layer Cycles)
            added = False
            try:
                row.prop(cy, "use_preview_denoising", text="")
                added = True
            except Exception:
                pass
            if not added:
                try:
                    row.prop(ctx.view_layer.cycles, "use_denoising", text="")
                    added = True
                except Exception:
                    pass
            if not added:
                try:
                    row.prop(cy, "use_denoising", text="")
                except Exception:
                    pass

            col.separator()
            col.label(text="Render")
            # One row: Noise Threshold, Samples, Denoise (checkbox without label)
            row = col.row(align=True)
            try:
                row.prop(cy, "adaptive_threshold", text="Noise Threshold")
            except Exception:
                pass
            try:
                row.prop(cy, "samples", text="Samples")
            except Exception:
                pass
            added = False
            try:
                row.prop(ctx.view_layer.cycles, "use_denoising", text="")
                added = True
            except Exception:
                pass
            if not added:
                try:
                    row.prop(cy, "use_denoising", text="")
                except Exception:
                    pass

        # Color Management
        box = layout.box()
        box.label(text="Color Management")
        vs = scene.view_settings
        row = box.row(align=True)
        # Two dropdowns in one row; no labels (tooltips suffice)
        row.prop(vs, "view_transform", text="")
        row.prop(vs, "look", text="")


class LIME_PT_render_cameras(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Cameras"
    bl_order = 3

    def draw(self, ctx):
        layout = self.layout
        scene = ctx.scene

        # Controls: single row so buttons are tightly grouped
        row = layout.row(align=True)
        row.enabled = validate_scene.active_shot_context(ctx) is not None
        row.operator("lime.add_camera_rig", text="Create Camera (Rig)", icon='OUTLINER_DATA_CAMERA')
        row.operator("lime.duplicate_active_camera", text="", icon='DUPLICATE')

        # Rename cameras in active SHOT's camera collection
        row = layout.row(align=True)
        row.enabled = validate_scene.active_shot_context(ctx) is not None
        row.operator("lime.rename_shot_cameras", text="Rename Cameras", icon='FILE_REFRESH')

        row = layout.row(align=True)
        row.enabled = False
        row.operator("wm.call_menu", text="Camera Background", icon='IMAGE_DATA')

        layout.separator()
        layout.operator("lime.render_invoke", text="Render (F12)", icon='RENDER_STILL')


class LIME_PT_render_camera_list(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Camera List"
    bl_parent_id = "LIME_PT_render_cameras"

    def draw(self, ctx):
        layout = self.layout
        scene = ctx.scene

        row = layout.row(align=True)
        row.template_list("LIME_UL_render_cameras", "", scene, "lime_render_cameras", scene, "lime_render_cameras_index", rows=6)
        col_btns = row.column(align=True)
        col_btns.operator("lime.add_camera_rig_and_sync", text='', icon='ADD')
        del_op = col_btns.operator("lime.delete_camera_rig_and_sync", text='', icon='REMOVE')
        # Pass selected item name to delete
        try:
            idx = getattr(scene, 'lime_render_cameras_index', -1)
            items = getattr(scene, 'lime_render_cameras', None)
            if items is not None and 0 <= idx < len(items):
                del_op.camera_name = items[idx].name
        except Exception:
            pass
        col_btns.separator()
        col_btns.operator("lime.sync_camera_list", text='', icon='FILE_REFRESH')


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


class LIME_OT_sync_camera_list(Operator):
    bl_idname = "lime.sync_camera_list"
    bl_label = "Refresh Cameras"
    bl_description = "Refresh the camera list from the current .blend"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        items = getattr(scene, 'lime_render_cameras', None)
        if items is None:
            self.report({'ERROR'}, 'Camera list storage not available')
            return {'CANCELLED'}
        try:
            items.clear()
            cams = [o for o in bpy.data.objects if getattr(o, "type", None) == 'CAMERA']
            cams.sort(key=lambda o: o.name)
            for cam in cams:
                it = items.add()
                it.name = cam.name
            # Adjust active index to current scene camera when possible
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
            self.report({'WARNING'}, 'Could not refresh camera list')
            return {'CANCELLED'}
        self.report({'INFO'}, f"Cameras: {len(items)}")
        return {'FINISHED'}


class LIME_OT_add_camera_rig_and_sync(Operator):
    bl_idname = "lime.add_camera_rig_and_sync"
    bl_label = "Add Camera (Rig) and Refresh"
    bl_description = "Create a camera rig using Lime operator and refresh the list"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            bpy.ops.lime.add_camera_rig('INVOKE_DEFAULT')
        except Exception:
            # Fallback to execute if invoke is not available
            try:
                bpy.ops.lime.add_camera_rig()
            except Exception:
                self.report({'ERROR'}, 'Failed to add camera rig')
                return {'CANCELLED'}
        try:
            bpy.ops.lime.sync_camera_list()
        except Exception:
            pass
        # Schedule a delayed refresh to capture final renamed camera names
        try:
            import bpy as _bpy3
            def _delayed_sync():
                try:
                    _bpy3.ops.lime.sync_camera_list()
                except Exception:
                    pass
                return None
            _bpy3.app.timers.register(_delayed_sync, first_interval=0.1)
        except Exception:
            pass
        return {'FINISHED'}


class LIME_OT_delete_camera_rig_and_sync(Operator):
    bl_idname = "lime.delete_camera_rig_and_sync"
    bl_label = "Delete Camera (Rig) and Refresh"
    bl_description = "Delete the selected camera rig and refresh the list"
    bl_options = {'REGISTER', 'UNDO'}

    camera_name: StringProperty(name="Camera Name", default="")

    def execute(self, context):
        name = (self.camera_name or '').strip()
        if not name:
            self.report({'WARNING'}, 'No camera selected')
            return {'CANCELLED'}
        try:
            bpy.ops.lime.delete_camera_rig(camera_name=name)
        except Exception:
            self.report({'ERROR'}, f"Failed to delete camera rig: {name}")
            return {'CANCELLED'}
        try:
            bpy.ops.lime.sync_camera_list()
        except Exception:
            pass
        return {'FINISHED'}


def register_camera_list_props():
    bpy.utils.register_class(LimeRenderCamItem)
    bpy.utils.register_class(LIME_UL_render_cameras)
    bpy.utils.register_class(LIME_OT_sync_camera_list)
    bpy.utils.register_class(LIME_OT_add_camera_rig_and_sync)
    bpy.utils.register_class(LIME_OT_delete_camera_rig_and_sync)

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
                # Also select its rig (highest Armature ancestor) and make it active
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
                    # Clear selection
                    try:
                        for ob in context.selected_objects or []:
                            try:
                                ob.select_set(False)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    # Select both rig and camera, with rig active
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

    # Token to detect changes cheaply (names + count)
    bpy.types.Scene.lime_render_cameras_token = StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    # Lightweight auto-sync on depsgraph changes
    def _compute_cam_token() -> str:
        try:
            names = [o.name for o in bpy.data.objects if getattr(o, 'type', None) == 'CAMERA']
            names.sort()
            return f"{len(names)}|" + "|".join(names)
        except Exception:
            return ""

    def _fill_cam_items(scene):
        try:
            items = getattr(scene, 'lime_render_cameras', None)
            if items is None:
                return
            items.clear()
            cams = [o for o in bpy.data.objects if getattr(o, 'type', None) == 'CAMERA']
            cams.sort(key=lambda o: o.name)
            for cam in cams:
                it = items.add()
                it.name = cam.name
            # Keep index on current active camera if present
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
            cur = _compute_cam_token()
            prev = getattr(scene, 'lime_render_cameras_token', '') or ''
            if cur != prev:
                _fill_cam_items(scene)
                scene.lime_render_cameras_token = cur
                # Schedule a short delayed re-check to catch late renames within the same update burst
                try:
                    def _recheck():
                        try:
                            sc = bpy.context.scene
                            if sc is None:
                                return None
                            now = _compute_cam_token()
                            prev2 = getattr(sc, 'lime_render_cameras_token', '') or ''
                            if now != prev2:
                                _fill_cam_items(sc)
                                sc.lime_render_cameras_token = now
                        except Exception:
                            pass
                        return None
                    import bpy as _bpy2
                    _bpy2.app.timers.register(_recheck, first_interval=0.1)
                except Exception:
                    pass
        except Exception:
            pass

    global _CAM_LIST_HANDLER
    if _CAM_LIST_HANDLER is None:
        _CAM_LIST_HANDLER = _cam_depsgraph_update_post
        if _CAM_LIST_HANDLER not in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.append(_CAM_LIST_HANDLER)
    # Initial population
    try:
        scene = bpy.context.scene
        if scene is not None:
            cur = _compute_cam_token()
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
        LIME_OT_delete_camera_rig_and_sync,
        LIME_OT_add_camera_rig_and_sync,
        LIME_OT_sync_camera_list,
        LIME_UL_render_cameras,
        LimeRenderCamItem,
    ):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass


class LIME_PT_render_outputs(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Output Files"
    bl_parent_id = "LIME_PT_render_configs"

    def draw(self, ctx):
        layout = self.layout
        wm = ctx.window_manager
        st = getattr(wm, 'lime_pipeline', None)
        # Use two tight rows (align=True) to avoid the wide grid spacing
        # and keep buttons visually grouped without extra margins.

        def _images_in(dirpath: Path) -> bool:
            try:
                if not dirpath.exists():
                    return False
                for p in dirpath.iterdir():
                    if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.exr', '.tif', '.tiff'}:
                        return True
            except Exception:
                pass
            return False

        # PV
        row_top = layout.row(align=True)
        pv_col = row_top.column(align=True)
        pv_dir = None
        try:
            hydrate_state_from_filepath(st)
            root = Path(getattr(st, 'project_root', '') or '')
            rev = (getattr(st, 'rev_letter', '') or '').upper()
            sc = getattr(st, 'sc_number', None)
            _ramv, folder_type, _scenes, _target, _backups = paths_for_type(root, 'PV', rev, sc)
            pv_dir = folder_type / 'editables'
        except Exception:
            pv_dir = None
        btn = pv_col.row(align=True)
        btn.enabled = bool(pv_dir and _images_in(pv_dir))
        op = btn.operator("lime.open_output_folder", text="Proposal Views", icon='FILE_FOLDER')
        op.ptype = 'PV'

        # REND
        rd_col = row_top.column(align=True)
        rd_dir = None
        try:
            hydrate_state_from_filepath(st)
            root = Path(getattr(st, 'project_root', '') or '')
            rev = (getattr(st, 'rev_letter', '') or '').upper()
            sc = getattr(st, 'sc_number', None)
            _ramv, folder_type, _scenes, _target, _backups = paths_for_type(root, 'REND', rev, sc)
            rd_dir = folder_type / 'editables'
        except Exception:
            rd_dir = None
        btn = rd_col.row(align=True)
        btn.enabled = bool(rd_dir and _images_in(rd_dir))
        op = btn.operator("lime.open_output_folder", text="Render", icon='FILE_FOLDER')
        op.ptype = 'REND'

        # Second row
        row_bottom = layout.row(align=True)

        # SB (placeholder disabled)
        sb_col = row_bottom.column(align=True)
        row = sb_col.row(align=True)
        row.enabled = False
        row.operator("lime.open_output_folder", text="Storyboard", icon='FILE_FOLDER')

        # ANIM (placeholder disabled)
        an_col = row_bottom.column(align=True)
        row = an_col.row(align=True)
        row.enabled = False
        row.operator("lime.open_output_folder", text="Animation", icon='FILE_FOLDER')


__all__ = [
    "LIME_PT_render_configs",
    "LIME_PT_render_settings",
    "LIME_PT_render_cameras",
    "LIME_PT_render_camera_list",
    "LIME_PT_render_outputs",
]
