import bpy
from bpy.types import Operator

from pathlib import Path

from ..core.paths import paths_for_type
from ..core.naming import (
    resolve_project_name,
    detect_ptype_from_filename,
    parse_blend_details,
    hydrate_state_from_filepath,
)
from ..core import validate_scene
from ..data.templates import C_UTILS_CAM


def _get_editables_dir(state) -> Path:
    # Try to hydrate state from current file if fields are missing
    hydrate_state_from_filepath(state)
    root_str = getattr(state, "project_root", "") or ""
    if not root_str:
        raise RuntimeError("Project Root not configured. Go to Project Org and select the root folder.")
    root = Path(root_str)
    rev = (getattr(state, "rev_letter", "") or "").upper()
    if not rev or len(rev) != 1 or not ('A' <= rev <= 'Z'):
        raise RuntimeError("Rev inválido. Define una letra de revisión (A–Z) en Project Org.")
    sc = getattr(state, "sc_number", None)
    _ramv, folder_type, _scenes, _target, _backups = paths_for_type(root, 'REND', rev, sc)
    editables_dir = folder_type / "editables"
    editables_dir.mkdir(parents=True, exist_ok=True)
    return editables_dir


def _resolve_prj_rev_sc(state):
    """Resolve (project_name, sc_number, rev_letter) prioritizing current .blend filename.

    - Prefer parse from `bpy.data.filepath` via parse_blend_details()
    - Fallback to WindowManager state for any missing component
    """
    project_name = None
    rev = None
    sc = None

    try:
        info = parse_blend_details(bpy.data.filepath or "")
        if info:
            project_name = info.get('project_name') or None
            rev = info.get('rev') or None
            sc = info.get('sc') if info.get('sc') is not None else None
    except Exception:
        pass

    if not project_name:
        try:
            project_name = resolve_project_name(state)
        except Exception:
            project_name = "Project"
    if rev is None:
        try:
            rev = (getattr(state, "rev_letter", "") or "").upper() or None
        except Exception:
            rev = None
    if sc is None:
        try:
            sc = int(getattr(state, "sc_number", 0) or 0)
        except Exception:
            sc = 0
    return project_name, sc, (rev or "")


def _isolate_other_shots(scene, target_shot, include_all=False):
    # Redirige a función deduplicada en validate_scene
    return validate_scene.isolate_shots_temporarily(scene, target_shot, include_all)


class LIME_OT_render_config(Operator):
    bl_idname = "lime.render_config"
    bl_label = "Render Config"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Configure Cycles for consistent renders and adjust output"

    @classmethod
    def poll(cls, ctx):
        # Siempre disponible
        return True

    def execute(self, context):
        scene = context.scene
        st = context.window_manager.lime_pipeline

        # Engine & device
        scene.render.engine = 'CYCLES'
        try:
            scene.cycles.device = 'GPU'
        except Exception:
            pass
        # Try to pick best compute backend
        try:
            prefs = bpy.context.preferences
            cprefs = prefs.addons['cycles'].preferences
            best = None
            for key in ('OPTIX', 'CUDA', 'HIP', 'METAL'):
                try:
                    cprefs.compute_device_type = key
                    best = key
                    break
                except Exception:
                    continue
            # Refresh devices and enable them
            try:
                cprefs.get_devices()
                for dev in cprefs.devices:
                    try:
                        dev.use = True
                    except Exception:
                        pass
            except Exception:
                pass
            if best is None:
                scene.cycles.device = 'CPU'
        except Exception:
            pass

        # Sampling
        try:
            scene.cycles.use_adaptive_sampling = True
            scene.cycles.adaptive_threshold = 0.01
            scene.cycles.preview_samples = 750
            scene.cycles.samples = 750
            scene.cycles.denoiser = 'OPENIMAGEDENOISE'
            context.view_layer.cycles.use_denoising = True
        except Exception:
            pass

        # Viewport denoise on all 3D views
        try:
            for area in context.screen.areas:
                if area.type != 'VIEW_3D':
                    continue
                space = area.spaces.active
                shading = getattr(space, 'shading', None)
                if shading and hasattr(shading, 'use_denoise'):
                    shading.use_denoise = True
        except Exception:
            pass

        # Light paths
        try:
            scene.cycles.max_bounces = 35
            scene.cycles.diffuse_bounces = 35
            scene.cycles.glossy_bounces = 35
            scene.cycles.transmission_bounces = 35
            scene.cycles.transparent_max_bounces = 35
        except Exception:
            pass

        # Performance
        try:
            scene.render.threads_mode = 'FIXED'
            scene.render.threads = 12
            # Persistent data (both legacy and new location)
            try:
                scene.cycles.use_persistent_data = True
            except Exception:
                pass
            try:
                scene.render.use_persistent_data = True
            except Exception:
                pass
        except Exception:
            pass

        # Color management
        try:
            scene.display_settings.display_device = 'sRGB'
            vs = scene.view_settings
            vs.view_transform = 'AgX'
            # Robustly set a High Contrast look if available
            set_ok = False
            try:
                # Preferred exact label
                vs.look = 'High Contrast'
                set_ok = (vs.look == 'High Contrast')
            except Exception:
                set_ok = False
            if not set_ok:
                try:
                    enum_items = vs.bl_rna.properties['look'].enum_items
                    # Try to find any option containing both 'High' and 'Contrast'
                    for it in enum_items:
                        ident = getattr(it, 'identifier', None) or str(it)
                        name = getattr(it, 'name', ident) or ident
                        label = (name or ident) or ''
                        if 'High' in label and 'Contrast' in label:
                            vs.look = getattr(it, 'identifier', label)
                            set_ok = True
                            break
                except Exception:
                    pass
        except Exception:
            pass

        # Output
        scene.render.resolution_x = 1440
        scene.render.resolution_y = 1080
        scene.render.resolution_percentage = 100
        scene.render.fps = 24
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGBA'
        # Ensure render shows in popup window
        try:
            scene.render.display_mode = 'WINDOW'
        except Exception:
            pass
        try:
            editables_dir = _get_editables_dir(st)
            scene.render.filepath = str(editables_dir) + "/"
        except Exception:
            pass

        self.report({'INFO'}, "Render config applied (Cycles)")
        return {'FINISHED'}


class LIME_OT_render_shot(Operator):
    bl_idname = "lime.render_shot"
    bl_label = "Render Shot"
    bl_options = {'REGISTER'}
    bl_description = "Render a still image for the selected SHOT and camera"

    @classmethod
    def poll(cls, ctx):
        shot = validate_scene.active_shot_context(ctx)
        if shot is None:
            return False
        cam_coll = validate_scene.get_shot_child_by_basename(shot, C_UTILS_CAM)
        if cam_coll is None:
            return False
        cams = [obj for obj in cam_coll.objects if getattr(obj, "type", None) == 'CAMERA']
        return len(cams) > 0

    def execute(self, context):
        wm = context.window_manager
        st = wm.lime_pipeline
        scene = context.scene

        shot = validate_scene.active_shot_context(context)
        if shot is None:
            self.report({'ERROR'}, "No active SHOT")
            return {'CANCELLED'}

        cam_name = getattr(st, "selected_camera", None)
        if not cam_name or cam_name == "NONE":
            self.report({'ERROR'}, "Please select a camera")
            return {'CANCELLED'}

        cam_coll = validate_scene.get_shot_child_by_basename(shot, C_UTILS_CAM)
        cam_obj = None
        if cam_coll is not None:
            for obj in cam_coll.objects:
                if getattr(obj, "type", None) == 'CAMERA' and obj.name == cam_name:
                    cam_obj = obj
                    break
        if cam_obj is None:
            self.report({'ERROR'}, f"Camera not found: '{cam_name}'")
            return {'CANCELLED'}

        project_name, sc_number, rev = _resolve_prj_rev_sc(st)
        shot_idx = validate_scene.parse_shot_index(shot.name) or 0
        cameras = [obj for obj in cam_coll.objects if getattr(obj, "type", None) == 'CAMERA']
        cameras.sort(key=lambda o: o.name)
        cam_index = 1
        for i, c in enumerate(cameras, 1):
            if c.name == cam_obj.name:
                cam_index = i
                break
        filename = f"{project_name}_Render_SH{shot_idx:02d}C{cam_index}_SC{sc_number:03d}_Rev_{rev}.png"

        try:
            editables_dir = _get_editables_dir(st)
        except Exception as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        image_path = editables_dir / filename

        original_camera = scene.camera
        restore_vis = _isolate_other_shots(scene, shot, include_all=bool(getattr(st, 'consider_all_shots', False)))
        try:
            scene.camera = cam_obj
            # Ensure PNG format in case config wasn't applied
            try:
                scene.render.image_settings.file_format = 'PNG'
                scene.render.image_settings.color_mode = 'RGBA'
            except Exception:
                pass
            # Render to Render Result (do NOT write to disk automatically)
            try:
                bpy.ops.render.render()
            except Exception:
                bpy.ops.render.render('INVOKE_DEFAULT')
            # Schedule opening the Save dialog after render window returns focus to main window
            def _open_dialog_later():
                try:
                    bpy.ops.lime.save_as_with_template('INVOKE_DEFAULT', ptype='REND')
                except Exception:
                    # Retry a bit later if context isn't ready yet
                    return 0.2
                return None
            try:
                import bpy.app as _app
                _app.timers.register(_open_dialog_later, first_interval=0.05)
            except Exception:
                # As a last resort, try immediate invoke (may fail in render window)
                try:
                    bpy.ops.lime.save_as_with_template('INVOKE_DEFAULT', ptype='REND')
                except Exception:
                    pass
        finally:
            scene.camera = original_camera
            try:
                restore_vis()
            except Exception:
                pass

        self.report({'INFO'}, f"Render completed. Save dialog opened with: {filename}")
        return {'FINISHED'}


class LIME_OT_render_all(Operator):
    bl_idname = "lime.render_all"
    bl_label = "Render All"
    bl_options = {'REGISTER'}
    bl_description = "Render all cameras for all SHOTs"

    @classmethod
    def poll(cls, ctx):
        shots = validate_scene.list_shot_roots(ctx.scene)
        if not shots:
            return False
        for shot, _idx in shots:
            cam_coll = validate_scene.get_shot_child_by_basename(shot, C_UTILS_CAM)
            if cam_coll and any(getattr(o, "type", None) == 'CAMERA' for o in cam_coll.objects):
                return True
        return False

    def invoke(self, context, event):
        wm = context.window_manager
        st = wm.lime_pipeline
        scene = context.scene

        project_name, sc_number, rev = _resolve_prj_rev_sc(st)
        try:
            editables_dir = _get_editables_dir(st)
        except Exception as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}

        self._queue = []
        self._consider_all = bool(getattr(st, 'consider_all_shots', False))
        self._original_camera = scene.camera
        self._orig_path = scene.render.filepath
        self._current_restore = None
        self._render_in_progress = False

        shots = validate_scene.list_shot_roots(scene)
        for shot, shot_idx in shots:
            cam_coll = validate_scene.get_shot_child_by_basename(shot, C_UTILS_CAM)
            if not cam_coll:
                continue
            cameras = [obj for obj in cam_coll.objects if getattr(obj, "type", None) == 'CAMERA']
            if not cameras:
                continue
            cameras.sort(key=lambda o: o.name)
            for cam_index, cam_obj in enumerate(cameras, 1):
                filename = f"{project_name}_Render_SH{shot_idx:02d}C{cam_index}_SC{sc_number:03d}_Rev_{rev}.png"
                out_full = str((editables_dir / filename)).replace('\\', '/')
                self._queue.append((shot, cam_obj, out_full))

        if not self._queue:
            self.report({'WARNING'}, "No cameras to render")
            return {'CANCELLED'}

        self._idx = 0
        self._timer = wm.event_timer_add(0.25, window=context.window)
        wm.modal_handler_add(self)
        self._start_next_render(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'TIMER':
            try:
                running = bpy.app.is_job_running('RENDER')
            except Exception:
                running = False
            if not running and self._render_in_progress:
                # Restore filepath and visibility from previous item
                try:
                    context.scene.render.filepath = self._orig_path
                except Exception:
                    pass
                try:
                    if self._current_restore:
                        self._current_restore()
                        self._current_restore = None
                except Exception:
                    pass
                self._render_in_progress = False
                if self._idx >= len(self._queue):
                    self._finish_batch(context)
                    return {'FINISHED'}
                self._start_next_render(context)
        return {'PASS_THROUGH'}

    def _start_next_render(self, context):
        scene = context.scene
        if self._idx >= len(self._queue):
            return
        shot, cam_obj, out_full = self._queue[self._idx]
        self._idx += 1

        # Isolate other shots for this render if requested
        try:
            if self._current_restore:
                self._current_restore()
        except Exception:
            pass
        self._current_restore = _isolate_other_shots(scene, shot, include_all=self._consider_all)

        try:
            scene.camera = cam_obj
        except Exception:
            pass
        try:
            scene.render.use_file_extension = True
            scene.render.use_overwrite = True
        except Exception:
            pass
        try:
            scene.render.image_settings.file_format = 'PNG'
            scene.render.image_settings.color_mode = 'RGBA'
        except Exception:
            pass
        try:
            scene.render.filepath = out_full
        except Exception:
            pass
        try:
            scene.render.display_mode = 'WINDOW'
        except Exception:
            pass
        try:
            bpy.ops.render.render('INVOKE_DEFAULT', write_still=True)
            self._render_in_progress = True
        except RuntimeError:
            bpy.ops.render.render(write_still=True)
            self._render_in_progress = True

    def _finish_batch(self, context):
        wm = context.window_manager
        scene = context.scene
        try:
            scene.camera = self._original_camera
        except Exception:
            pass
        try:
            scene.render.filepath = self._orig_path
        except Exception:
            pass
        try:
            if self._current_restore:
                self._current_restore()
        except Exception:
            pass
        try:
            wm.event_timer_remove(self._timer)
        except Exception:
            pass
        self.report({'INFO'}, "Renders completed for all SHOTs")

    def execute(self, context):
        wm = context.window_manager
        st = wm.lime_pipeline
        scene = context.scene

        project_name, sc_number, rev = _resolve_prj_rev_sc(st)
        try:
            editables_dir = _get_editables_dir(st)
        except Exception as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}

        original_camera = scene.camera

        shots = validate_scene.list_shot_roots(scene)
        for shot, shot_idx in shots:
            cam_coll = validate_scene.get_shot_child_by_basename(shot, C_UTILS_CAM)
            if not cam_coll:
                self.report({'WARNING'}, f"Skipping {shot.name}: no camera collection")
                continue
            cameras = [obj for obj in cam_coll.objects if getattr(obj, "type", None) == 'CAMERA']
            if not cameras:
                self.report({'WARNING'}, f"Skipping {shot.name}: no cameras")
                continue
            cameras.sort(key=lambda o: o.name)
            for cam_index, cam_obj in enumerate(cameras, 1):
                filename = f"{project_name}_Render_SH{shot_idx:02d}C{cam_index}_SC{sc_number:03d}_Rev_{rev}.png"
                image_path = editables_dir / filename
                orig_path = scene.render.filepath
                try:
                    scene.camera = cam_obj
                    try:
                        scene.render.use_file_extension = True
                        scene.render.use_overwrite = True
                    except Exception:
                        pass
                    out_full = str(image_path).replace('\\', '/')
                    try:
                        scene.render.image_settings.file_format = 'PNG'
                        scene.render.image_settings.color_mode = 'RGBA'
                    except Exception:
                        pass
                    scene.render.filepath = out_full
                    # For batch renders, use blocking call to ensure correct filenames per camera
                    bpy.ops.render.render(write_still=True)
                finally:
                    scene.render.filepath = orig_path

        scene.camera = original_camera
        self.report({'INFO'}, "Renders completed for all SHOTs")
        return {'FINISHED'}


__all__ = [
    "LIME_OT_render_config",
    "LIME_OT_render_shot",
    "LIME_OT_render_all",
]
