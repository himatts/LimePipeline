"""
SHOT Management Operators

This module provides comprehensive functionality for creating, managing, and organizing
SHOT scenes within the Lime Pipeline workflow. SHOTs represent individual scene files
that are organized sequentially for production pipelines.

The operators handle SHOT lifecycle including creation, duplication, validation, and
maintenance of proper SHOT naming conventions and collection structures.

Key Features:
- Automated SHOT creation with proper numbering and naming
- SHOT duplication with intelligent renaming and structure preservation
- Integration with Lime Pipeline project naming conventions
- Validation of SHOT contexts and prerequisites
- Collection tree management for SHOT organization
- Sequential SHOT numbering and tracking
- Error handling and user feedback for SHOT operations
"""

from __future__ import annotations

from pathlib import Path

import bpy
from bpy.types import Operator
from bpy.props import StringProperty

from ..core import validate_scene
from ..core.naming import resolve_project_name
from ..data.templates import C_CAM
from ..ops.ops_save_templates import (
    _camera_index_for_shot,
    _ensure_editables_raw_dir,
    _resolve_prj_rev_sc,
)
from ..scene.scene_utils import create_shot, duplicate_shot, ensure_shot_tree

try:
    # Imported lazily to avoid hard dependency at module import time
    from ..ui import ui_shots  # type: ignore
except Exception:  # pragma: no cover - Blender env dependent
    ui_shots = None


class LIME_OT_new_shot(Operator):
    bl_idname = "lime.new_shot"
    bl_label = "New Shot"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        ok, _ = validate_scene.can_create_new_shot(ctx.scene)
        return ok

    def execute(self, context):
        scene = context.scene
        st = context.window_manager.lime_pipeline
        project_name = resolve_project_name(st)
        idx = validate_scene.next_shot_index(scene)
        try:
            create_shot(scene, idx, project_name)
        except Exception as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        self.report({'INFO'}, f"Created SHOT {idx:02d}")
        return {'FINISHED'}


class LIME_OT_delete_shot(Operator):
    bl_idname = "lime.delete_shot"
    bl_label = "Delete Shot"
    bl_description = "Delete the entire SHOT collection and its contents"
    bl_options = {'REGISTER', 'UNDO'}

    shot_name: StringProperty(name="Shot Name", default="")

    @classmethod
    def poll(cls, ctx):
        return True

    def _remove_collection_recursive(self, coll: bpy.types.Collection):
        # Remove all objects in this collection
        try:
            for obj in list(coll.objects):
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except Exception:
                    pass
        except Exception:
            pass
        # Recurse into children first
        try:
            for child in list(coll.children):
                self._remove_collection_recursive(child)
        except Exception:
            pass
        # Finally, remove the collection itself
        try:
            bpy.data.collections.remove(coll, do_unlink=True)
        except Exception:
            pass

    def execute(self, context):
        name = (self.shot_name or '').strip()
        if not name:
            self.report({'ERROR'}, "No SHOT name provided")
            return {'CANCELLED'}
        # Validate it's a shot root
        shot_coll = bpy.data.collections.get(name)
        if shot_coll is None:
            self.report({'ERROR'}, f"SHOT not found: {name}")
            return {'CANCELLED'}
        shots = [c for c, _ in validate_scene.list_shot_roots(context.scene)]
        if shot_coll not in shots:
            self.report({'ERROR'}, f"Not a SHOT root: {name}")
            return {'CANCELLED'}
        # Remove recursively
        try:
            self._remove_collection_recursive(shot_coll)
        except Exception as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        self.report({'INFO'}, f"Deleted SHOT: {name}")
        return {'FINISHED'}


class LIME_OT_duplicate_shot(Operator):
    bl_idname = "lime.duplicate_shot"
    bl_label = "Duplicate Shot"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, ctx):
        ok, _ = validate_scene.can_duplicate_shot(ctx)
        return ok

    def execute(self, context):
        scene = context.scene
        src = validate_scene.active_shot_context(context)
        if src is None:
            self.report({'ERROR'}, "No SHOT context")
            return {'CANCELLED'}
        dst_idx = validate_scene.next_shot_index(scene)
        try:
            duplicate_shot(scene, src, dst_idx)
        except Exception as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        self.report({'INFO'}, f"Duplicated {src.name} -> SHOT {dst_idx:02d}")
        return {'FINISHED'}


class LIME_OT_activate_shot(Operator):
    bl_idname = "lime.activate_shot"
    bl_label = "Activate Shot"
    bl_options = {'REGISTER', 'UNDO'}

    shot_name: StringProperty(name="Shot Name", default="")

    def execute(self, context):
        name = (self.shot_name or '').strip()
        if not name:
            self.report({'ERROR'}, "Invalid SHOT name")
            return {'CANCELLED'}
        # Find collection and activate in Outliner/View Layer
        target = next((c for c in context.scene.collection.children if c.name == name), None)
        if target is None:
            self.report({'ERROR'}, f"SHOT not found: {name}")
            return {'CANCELLED'}
        # Activate corresponding layer collection
        try:
            def _find_layer(layer, wanted):
                if layer.collection == wanted:
                    return layer
                for ch in layer.children:
                    found = _find_layer(ch, wanted)
                    if found:
                        return found
                return None

            root_layer = context.view_layer.layer_collection
            lc = _find_layer(root_layer, target)
            if lc is not None:
                context.view_layer.active_layer_collection = lc
        except Exception:
            pass

        self.report({'INFO'}, f"Active: {name}")
        return {'FINISHED'}


class LIME_OT_jump_to_first_shot_marker(Operator):
    bl_idname = "lime.jump_to_first_shot_marker"
    bl_label = "Jump to First Shot Camera Marker"
    bl_description = "Set current frame to the first timeline marker whose camera belongs to the target SHOT"
    bl_options = {'REGISTER'}

    shot_name: StringProperty(name="Shot Name", default="")

    @classmethod
    def poll(cls, ctx):
        return True

    def execute(self, context):
        scene = context.scene
        # Resolve shot by name or from context
        shot = None
        name = (self.shot_name or '').strip()
        if name:
            shot = bpy.data.collections.get(name)
        if shot is None:
            shot = validate_scene.active_shot_context(context)
        if shot is None:
            self.report({'WARNING'}, "No SHOT context to jump to markers")
            return {'CANCELLED'}

        # Collect cameras that belong to the SHOT subtree
        def _iter_coll_tree(root):
            stack = [root]
            seen = set()
            while stack:
                c = stack.pop()
                ident = c.as_pointer() if hasattr(c, 'as_pointer') else id(c)
                if ident in seen:
                    continue
                seen.add(ident)
                yield c
                try:
                    stack.extend(list(c.children))
                except Exception:
                    pass

        cameras = []
        for coll in _iter_coll_tree(shot):
            try:
                for obj in coll.objects:
                    if getattr(obj, 'type', None) == 'CAMERA':
                        cameras.append(obj)
            except Exception:
                pass

        if not cameras:
            self.report({'WARNING'}, f"No cameras found in SHOT '{shot.name}'")
            return {'CANCELLED'}

        allowed = set(cameras)
        # Build camera name prefixes for this SHOT (02d and 03d width)
        try:
            from ..core import validate_scene as _vs
            idx = _vs.parse_shot_index(getattr(shot, 'name', '') or '') or 0
        except Exception:
            idx = 0
        prefixes = []
        if idx > 0:
            prefixes = [f"SHOT_{idx:02d}_CAMERA_", f"SHOT_{idx:03d}_CAMERA_"]

        # Gather candidate frames: markers with camera in allowed or matching name prefixes
        try:
            markers = sorted(scene.timeline_markers, key=lambda m: m.frame)
        except Exception:
            markers = list(scene.timeline_markers)

        current = int(getattr(scene, 'frame_current', 0) or 0)
        future_frames = []
        all_frames = []
        for marker in markers:
            cam = getattr(marker, 'camera', None)
            if not cam:
                continue
            ok = cam in allowed
            if not ok and prefixes:
                try:
                    n = getattr(cam, 'name', '') or ''
                    ok = any(n.startswith(p) for p in prefixes)
                except Exception:
                    ok = False
            if not ok:
                continue
            f = int(marker.frame)
            all_frames.append(f)
            if f >= current:
                future_frames.append(f)

        target_frame = None
        if future_frames:
            target_frame = min(future_frames)
        elif all_frames:
            target_frame = min(all_frames)

        if target_frame is None:
            self.report({'WARNING'}, f"No camera markers for SHOT '{shot.name}'")
            return {'CANCELLED'}

        try:
            scene.frame_set(target_frame)
        except Exception:
            self.report({'ERROR'}, "Failed to set frame")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Jumped to frame {target_frame} for '{shot.name}'")
        return {'FINISHED'}


class LIME_OT_render_shots_from_markers(Operator):
    bl_idname = "lime.render_shots_from_markers"
    bl_label = "Render Shots (RAW)"
    bl_description = "Render una imagen RAW por cada marcador de cámara en cada SHOT (modal, cancelable)"
    bl_options = {'REGISTER'}

    _state = None
    _raw_dir: Path | None = None
    _tasks: list[dict] | None = None
    _timer = None
    _renders_done = 0
    _scene = None
    _prev_frame = 0
    _prev_camera = None
    _prev_filepath = ""
    _rendering_task = None  # Holds info while a render window is running
    _ui_guard_prev = None

    def _iter_coll_tree(self, root):
        stack = [root]
        seen = set()
        while stack:
            c = stack.pop()
            ident = c.as_pointer() if hasattr(c, "as_pointer") else id(c)
            if ident in seen:
                continue
            seen.add(ident)
            yield c
            try:
                stack.extend(list(c.children))
            except Exception:
                pass

    def _collect_shot_cameras(self, shot):
        cams = []
        for coll in self._iter_coll_tree(shot):
            try:
                for obj in coll.objects:
                    if getattr(obj, "type", None) == "CAMERA":
                        cams.append(obj)
            except Exception:
                pass
        return cams

    def _collect_markers_for_shot(self, scene, shot, allowed_cameras):
        try:
            shot_idx = validate_scene.parse_shot_index(getattr(shot, "name", "") or "") or 0
        except Exception:
            shot_idx = 0
        prefixes = []
        if shot_idx > 0:
            prefixes = [f"SHOT_{shot_idx:02d}_CAMERA_", f"SHOT_{shot_idx:03d}_CAMERA_"]

        try:
            timeline_markers = sorted(scene.timeline_markers, key=lambda m: m.frame)
        except Exception:
            timeline_markers = list(scene.timeline_markers)

        seen = set()
        result = []
        for marker in timeline_markers:
            cam = getattr(marker, "camera", None)
            if cam is None:
                continue
            ok = cam in allowed_cameras
            if not ok and prefixes:
                try:
                    nm = getattr(cam, "name", "") or ""
                    ok = any(nm.startswith(pfx) for pfx in prefixes)
                except Exception:
                    ok = False
            if not ok:
                continue
            frame = int(marker.frame)
            key = (frame, cam.as_pointer() if hasattr(cam, "as_pointer") else id(cam))
            if key in seen:
                continue
            seen.add(key)
            result.append((frame, cam, marker))
        return result

    def _build_raw_path(self, shot, camera, frame: int) -> Path:
        project_name, sc_number, rev = _resolve_prj_rev_sc(self._state)
        try:
            shot_idx = validate_scene.parse_shot_index(getattr(shot, "name", "") or "") or 0
        except Exception:
            shot_idx = 0
        cam_idx = _camera_index_for_shot(shot, camera) if shot and camera else 1
        filename = f"RAW_{project_name}_Render_SH{shot_idx:02d}C{cam_idx}_SC{sc_number:03d}_Rev_{rev}.png"
        return self._raw_dir / filename

    def _prepare_tasks(self, context) -> bool:
        wm = context.window_manager
        state = getattr(wm, "lime_pipeline", None)
        if state is None:
            self.report({"ERROR"}, "Estado Lime Pipeline no disponible. Abre Project Organization primero.")
            return False
        self._state = state

        try:
            self._raw_dir = Path(_ensure_editables_raw_dir(state, "REND"))
        except Exception as ex:
            self.report({"ERROR"}, f"No se pudo preparar la carpeta RAW: {ex}")
            return False

        scene = context.scene
        shots = validate_scene.list_shot_roots(scene)
        if not shots:
            self.report({"WARNING"}, "No hay SHOTs en la escena.")
            return False

        self._scene = scene
        self._prev_frame = int(getattr(scene, "frame_current", 0) or 0)
        self._prev_camera = getattr(scene, "camera", None)
        self._prev_filepath = getattr(scene.render, "filepath", "")
        self._renders_done = 0

        tasks: list[dict] = []
        for shot, _idx in shots:
            cameras = self._collect_shot_cameras(shot)
            if not cameras:
                self.report({"WARNING"}, f"No cameras found in SHOT '{shot.name}'")
                continue
            markers = self._collect_markers_for_shot(scene, shot, set(cameras))
            if not markers:
                self.report({"WARNING"}, f"No camera markers for SHOT '{shot.name}'")
                continue
            tasks.append({
                "shot": shot,
                "markers": markers,
                "index": 0,
                "restore": None,
            })

        if not tasks:
            self.report({"WARNING"}, "No se encontraron cámaras/marcadores válidos.")
            return False

        self._tasks = tasks
        return True

    def _finish(self, context, cancelled: bool):
        wm = context.window_manager
        if self._timer is not None:
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None

        try:
            if self._scene is not None:
                self._scene.frame_set(self._prev_frame)
        except Exception:
            pass
        try:
            if self._scene is not None:
                self._scene.camera = self._prev_camera
        except Exception:
            pass
        try:
            if self._scene is not None:
                self._scene.render.filepath = self._prev_filepath
        except Exception:
            pass

        if self._tasks:
            for task in self._tasks:
                restore = task.get("restore")
                if restore:
                    try:
                        restore()
                    except Exception:
                        pass

        try:
            if ui_shots is not None and self._ui_guard_prev is not None:
                ui_shots.RENDER_SHOTS_GUARD = self._ui_guard_prev
        except Exception:
            pass
        finally:
            self._ui_guard_prev = None

        if not cancelled and self._renders_done > 0:
            self.report({"INFO"}, f"Render RAW completado: {self._renders_done} imagen(es).")

    def _process_next(self, context) -> bool:
        if not self._tasks:
            return True

        task = self._tasks[0]
        markers = task["markers"]
        idx = task["index"]

        # If a render is still running (INVOKE_DEFAULT), wait until it finishes
        if self._rendering_task is not None:
            try:
                if bpy.app.is_job_running("RENDER"):
                    return False
            except Exception:
                # If we cannot detect, fall through and assume finished
                pass
            # Render finished
            self._renders_done += 1
            task["index"] += 1
            self._rendering_task = None
            return False

        # If current shot finished, cleanup and move forward
        while idx >= len(markers):
            restore = task.get("restore")
            if restore:
                try:
                    restore()
                except Exception:
                    pass
            self._tasks.pop(0)
            if not self._tasks:
                return True
            task = self._tasks[0]
            markers = task["markers"]
            idx = task["index"]

        if task.get("restore") is None:
            task["restore"] = validate_scene.isolate_shots_temporarily(self._scene, task["shot"], include_all=False)

        frame, cam, _marker = markers[idx]

        try:
            self._scene.frame_set(frame)
        except Exception:
            self.report({"ERROR"}, f"Failed to set frame {frame} for '{task['shot'].name}'")
            task["index"] += 1
            return False

        try:
            self._scene.camera = cam
        except Exception:
            self.report({"ERROR"}, f"Could not set camera '{cam.name}' for '{task['shot'].name}'")
            task["index"] += 1
            return False

        try:
            filepath = self._build_raw_path(task["shot"], cam, frame)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            self._scene.render.filepath = filepath.as_posix()
        except Exception as ex:
            self.report({"ERROR"}, f"Cannot prepare filepath for '{task['shot'].name}': {ex}")
            task["index"] += 1
            return False

        try:
            result = bpy.ops.render.render('INVOKE_DEFAULT', write_still=True)
            cancelled = (result == {'CANCELLED'}) or ('CANCELLED' in result and 'RUNNING_MODAL' not in result)
            if cancelled:
                self.report({"ERROR"}, f"Render cancelled for {task['shot'].name} at frame {frame} (result: {result})")
                task["index"] += 1
                return False

            if result == {'FINISHED'} or 'FINISHED' in result:
                self._renders_done += 1
                task["index"] += 1
                return False

            # When INVOKE_DEFAULT succeeds it usually returns RUNNING_MODAL; track until completion
            self._rendering_task = {"shot": task["shot"], "frame": frame}
            return False
        except Exception as ex:
            self.report({"ERROR"}, f"Render failed for {task['shot'].name} at frame {frame}: {ex}")
            task["index"] += 1
            return False

    def invoke(self, context, event):
        if not self._prepare_tasks(context):
            return {'CANCELLED'}

        if ui_shots is not None:
            try:
                self._ui_guard_prev = getattr(ui_shots, "RENDER_SHOTS_GUARD", False)
                ui_shots.RENDER_SHOTS_GUARD = True
            except Exception:
                self._ui_guard_prev = None

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        self.report({"INFO"}, "Render RAW iniciado. Pulsa ESC para cancelar.")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'ESC'}:
            self.report({"WARNING"}, "Render RAW cancelado por el usuario.")
            self._finish(context, cancelled=True)
            return {'CANCELLED'}

        if event.type == 'TIMER':
            try:
                done = self._process_next(context)
            except Exception as ex:
                self.report({"ERROR"}, f"Error procesando render: {ex}")
                self._finish(context, cancelled=True)
                return {'CANCELLED'}
            if done:
                self._finish(context, cancelled=False)
                return {'FINISHED'}

        return {'PASS_THROUGH'}
