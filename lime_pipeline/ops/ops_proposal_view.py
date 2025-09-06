import bpy
from bpy.types import Operator
from bpy.props import EnumProperty

from pathlib import Path
import re

from ..core import validate_scene
from ..core.paths import paths_for_type
from ..core.naming import resolve_project_name
from ..data.templates import C_UTILS_CAM


def _get_editables_dir(state) -> Path:
    root = Path(getattr(state, "project_root", "") or "")
    rev = (getattr(state, "rev_letter", "") or "").upper()
    sc = getattr(state, "sc_number", None)
    _ramv, folder_type, _scenes, _target, _backups = paths_for_type(root, 'PV', rev, sc)
    editables_dir = folder_type / "editables"
    editables_dir.mkdir(parents=True, exist_ok=True)
    return editables_dir


def _find_view3d_area_and_region(context):
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return area, region
    return None, None


class LIME_OT_proposal_view_config(Operator):
    bl_idname = "lime.proposal_view_config"
    bl_label = "Proposal View Config"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Ajusta render y viewport para capturas estilo clay"

    @classmethod
    def poll(cls, ctx):
        st = getattr(ctx.window_manager, "lime_pipeline", None)
        if st is None:
            return False
        if getattr(st, "project_type", None) != 'PV':
            return False
        try:
            is_saved = bool(bpy.data.filepath)
        except Exception:
            is_saved = False
        if not is_saved:
            return False
        return True

    def execute(self, context):
        st = context.window_manager.lime_pipeline
        scene = context.scene

        # Output properties
        scene.render.resolution_x = 1440
        scene.render.resolution_y = 1080
        scene.render.resolution_percentage = 100
        scene.render.fps = 24
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGBA'

        # Set output base path (folder); filenames se fijan por operador de captura
        try:
            editables_dir = _get_editables_dir(st)
            scene.render.filepath = str(editables_dir) + "/"
        except Exception:
            pass

        # Viewport clay config on all 3D views
        try:
            for area in context.screen.areas:
                if area.type != 'VIEW_3D':
                    continue
                space = area.spaces.active
                if getattr(space, "type", None) != 'VIEW_3D':
                    continue
                shading = space.shading
                shading.type = 'SOLID'
                shading.light = 'STUDIO'
                shading.use_scene_lights = False
                shading.use_scene_world = False
                shading.color_type = 'SINGLE'
                shading.single_color = (0.8, 0.8, 0.8)
                shading.show_shadows = True
                shading.show_cavity = True
                shading.cavity_type = 'BOTH'
                space.overlay.show_overlays = False
        except Exception:
            pass

        self.report({'INFO'}, "Preset de Proposal View aplicado")
        return {'FINISHED'}


class LIME_OT_take_pv_shot(Operator):
    bl_idname = "lime.take_pv_shot"
    bl_label = "Take PV Shot"
    bl_options = {'REGISTER'}
    bl_description = "Captura PNG del viewport desde la cámara seleccionada del SHOT activo"

    @classmethod
    def poll(cls, ctx):
        st = getattr(ctx.window_manager, "lime_pipeline", None)
        if st is None or getattr(st, "project_type", None) != 'PV':
            return False
        try:
            is_saved = bool(bpy.data.filepath)
        except Exception:
            is_saved = False
        if not is_saved:
            return False
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
            self.report({'ERROR'}, "No hay SHOT activo")
            return {'CANCELLED'}

        cam_name = getattr(st, "selected_camera", None)
        if not cam_name or cam_name == "NONE":
            self.report({'ERROR'}, "Seleccione una cámara")
            return {'CANCELLED'}

        cam_coll = validate_scene.get_shot_child_by_basename(shot, C_UTILS_CAM)
        cam_obj = None
        if cam_coll is not None:
            for obj in cam_coll.objects:
                if getattr(obj, "type", None) == 'CAMERA' and obj.name == cam_name:
                    cam_obj = obj
                    break
        if cam_obj is None:
            self.report({'ERROR'}, f"Cámara '{cam_name}' no encontrada")
            return {'CANCELLED'}

        # Prepare naming
        project_name = resolve_project_name(st)
        shot_idx = validate_scene.parse_shot_index(shot.name) or 0
        cameras = [obj for obj in cam_coll.objects if getattr(obj, "type", None) == 'CAMERA']
        cameras.sort(key=lambda o: o.name)
        cam_index = 1
        for i, c in enumerate(cameras, 1):
            if c.name == cam_obj.name:
                cam_index = i
                break
        sc_number = getattr(st, "sc_number", 0) or 0
        rev = (getattr(st, "rev_letter", "") or "").upper()
        filename = f"{project_name}_PV_SH{shot_idx:02d}C{cam_index}_SC{sc_number:03d}_Rev_{rev}.png"

        editables_dir = _get_editables_dir(st)
        image_path = editables_dir / filename

        # Ensure scene uses this camera
        original_camera = scene.camera
        scene.camera = cam_obj

        # Try to switch a 3D view to camera for consistent view_context render
        area, region = _find_view3d_area_and_region(context)
        override = None
        if area and region:
            override = context.copy()
            override["area"] = area
            override["region"] = region
            try:
                bpy.ops.view3d.view_camera(override)
            except Exception:
                override = None

        # Render OpenGL to file
        orig_path = scene.render.filepath
        try:
            scene.render.filepath = str(image_path.with_suffix(''))
            if override is not None:
                bpy.ops.render.opengl(override, write_still=True, view_context=True)
            else:
                bpy.ops.render.opengl(write_still=True, view_context=False)
        finally:
            scene.render.filepath = orig_path
            scene.camera = original_camera

        self.report({'INFO'}, f"Capturado: {filename}")
        return {'FINISHED'}


class LIME_OT_take_all_pv_shots(Operator):
    bl_idname = "lime.take_all_pv_shots"
    bl_label = "Take All PV Shots"
    bl_options = {'REGISTER'}
    bl_description = "Captura PNG del viewport para todas las cámaras de todos los SHOTs"

    @classmethod
    def poll(cls, ctx):
        st = getattr(ctx.window_manager, "lime_pipeline", None)
        if st is None or getattr(st, "project_type", None) != 'PV':
            return False
        try:
            is_saved = bool(bpy.data.filepath)
        except Exception:
            is_saved = False
        if not is_saved:
            return False
        shots = validate_scene.list_shot_roots(ctx.scene)
        if not shots:
            return False
        for shot, _idx in shots:
            cam_coll = validate_scene.get_shot_child_by_basename(shot, C_UTILS_CAM)
            if cam_coll and any(getattr(o, "type", None) == 'CAMERA' for o in cam_coll.objects):
                return True
        return False

    def execute(self, context):
        wm = context.window_manager
        st = wm.lime_pipeline
        scene = context.scene

        project_name = resolve_project_name(st)
        sc_number = getattr(st, "sc_number", 0) or 0
        rev = (getattr(st, "rev_letter", "") or "").upper()
        editables_dir = _get_editables_dir(st)

        original_camera = scene.camera

        shots = validate_scene.list_shot_roots(scene)
        for shot, shot_idx in shots:
            cam_coll = shot.children.get(C_UTILS_CAM)
            if not cam_coll:
                self.report({'WARNING'}, f"Omitiendo {shot.name}: sin colección de cámaras")
                continue
            cameras = [obj for obj in cam_coll.objects if getattr(obj, "type", None) == 'CAMERA']
            if not cameras:
                self.report({'WARNING'}, f"Omitiendo {shot.name}: sin cámaras")
                continue
            cameras.sort(key=lambda o: o.name)
            for cam_index, cam_obj in enumerate(cameras, 1):
                filename = f"{project_name}_PV_SH{shot_idx:02d}C{cam_index}_SC{sc_number:03d}_Rev_{rev}.png"
                image_path = editables_dir / filename
                scene.camera = cam_obj
                orig_path = scene.render.filepath
                try:
                    scene.render.filepath = str(image_path.with_suffix(''))
                    bpy.ops.render.opengl(write_still=True, view_context=False)
                finally:
                    scene.render.filepath = orig_path

        scene.camera = original_camera
        self.report({'INFO'}, "Capturas completadas para todos los SHOTs")
        return {'FINISHED'}


class LIME_OT_add_camera_rig(Operator):
    bl_idname = "lime.add_camera_rig"
    bl_label = "Crear Cámara (Rig)"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Añade un rig de cámara a la colección 00_UTILS_CAM del SHOT activo"

    rig_type: EnumProperty(
        name="Tipo de Rig",
        items=(
            ('DOLLY', "Dolly", "Rig tipo Dolly"),
            ('CRANE', "Crane", "Rig tipo Crane"),
            ('2D', "2D", "Rig 2D"),
        ),
        default='DOLLY',
    )

    @classmethod
    def poll(cls, ctx):
        shot = validate_scene.active_shot_context(ctx)
        return shot is not None

    def execute(self, context):
        shot = validate_scene.active_shot_context(context)
        if shot is None:
            self.report({'ERROR'}, "No hay SHOT activo")
            return {'CANCELLED'}

        cam_coll = validate_scene.get_shot_child_by_basename(shot, C_UTILS_CAM)
        if cam_coll is None:
            self.report({'ERROR'}, "El SHOT activo no tiene colección de cámaras")
            return {'CANCELLED'}

        # Info previa: cantidad de cámaras existentes y número de SHOT
        try:
            cams_before = [o for o in cam_coll.objects if getattr(o, "type", None) == 'CAMERA']
            existing_cam_count = len(cams_before)
            before_cam_names = set(o.name for o in cams_before)
        except Exception:
            existing_cam_count = 0
            before_cam_names = set()
        print(f"[LimePV] AddCameraRig: shot={shot.name}, existing_cam_count={existing_cam_count}, before_cam_names={sorted(list(before_cam_names))}")
        try:
            shot_idx = validate_scene.parse_shot_index(shot.name) or 0
        except Exception:
            shot_idx = 0

        # Activate the camera collection as target
        target_layer = None
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
            target_layer = _find_layer(root_layer, cam_coll)
            if target_layer is not None:
                context.view_layer.active_layer_collection = target_layer
        except Exception:
            pass

        # Operador confirmado: object.build_camera_rig(mode=...)
        created = False
        last_error = None
        mode = self.rig_type
        if mode == '2D':
            mode_candidates = ['TWO_D', '2D']
        else:
            mode_candidates = [mode]

        # Localizar una VIEW_3D para ejecutar el operador
        win = None
        area = None
        region = None
        for w in context.window_manager.windows:
            for a in w.screen.areas:
                if a.type == 'VIEW_3D':
                    r = next((rg for rg in a.regions if rg.type == 'WINDOW'), None)
                    if r is not None:
                        win = w
                        area = a
                        region = r
                        break
            if win:
                break
        print(f"[LimePV] View3D located: win={bool(win)}, area={bool(area)}, region={bool(region)}")

        # Guardar lista de objetos antes para detectar nuevos (por nombre)
        before_objs = {obj.name for obj in bpy.data.objects}
        print(f"[LimePV] Objects before: {len(before_objs)}")

        # Asegurar modo OBJECT en contexto 3D
        try:
            if win and area and region:
                with bpy.context.temp_override(window=win, area=area, region=region, scene=context.scene, view_layer=context.view_layer):
                    bpy.ops.object.mode_set(mode='OBJECT')
            else:
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

        # Verificar operador disponible
        build_op = getattr(bpy.ops.object, 'build_camera_rig', None)
        if build_op is None:
            last_error = "Operador object.build_camera_rig no encontrado"
            print("[LimePV] build_camera_rig operator NOT found")
        else:
            print(f"[LimePV] build_camera_rig operator available, mode candidates={mode_candidates}")
            for m in mode_candidates:
                try:
                    if win and area and region:
                        with bpy.context.temp_override(window=win, area=area, region=region, scene=context.scene, view_layer=context.view_layer):
                            res = bpy.ops.object.build_camera_rig('EXEC_DEFAULT', mode=m)
                    else:
                        res = bpy.ops.object.build_camera_rig('EXEC_DEFAULT', mode=m)
                    print(f"[LimePV] build_camera_rig result for mode={m}: {res}")
                    if res == {'FINISHED'}:
                        created = True
                        break
                except Exception as ex:
                    last_error = str(ex)
                    print(f"[LimePV] build_camera_rig error for mode={m}: {last_error}")
                    continue

        if not created:
            msg = "No se pudo crear la cámara. ¿Está habilitado 'Add Camera Rigs'?"
            if last_error:
                msg += f" ({last_error})"
            self.report({'ERROR'}, msg)
            print(f"[LimePV] Creation failed: {msg}")
            return {'CANCELLED'}

        # Renombrar única y directamente la(s) cámara(s) nuevas (sin re-link ni tocar rig)
        try:
            after_names = {obj.name for obj in bpy.data.objects}
            new_obj_names = [name for name in after_names if name not in before_objs]
            new_objs = [bpy.data.objects[name] for name in new_obj_names]
            print(f"[LimePV] New objects: {[ (o.name, getattr(o,'type',None)) for o in new_objs ]}")
            new_cams = [o for o in new_objs if getattr(o, "type", None) == 'CAMERA']
            if not new_cams:
                print("[LimePV] No new camera objects detected; aborting rename")
            else:
                new_cams.sort(key=lambda o: o.name)
                next_idx = existing_cam_count + 1
                for cam in new_cams:
                    try:
                        target_name = f"SHOT_{shot_idx:02d}_CAMERA_{next_idx}"
                        while target_name in bpy.data.objects.keys():
                            next_idx += 1
                            target_name = f"SHOT_{shot_idx:02d}_CAMERA_{next_idx}"
                        print(f"[LimePV] Simple rename camera {cam.name} -> {target_name}")
                        cam.name = target_name
                        if getattr(cam, "data", None) is not None:
                            cam.data.name = target_name + ".Data"
                        next_idx += 1
                    except Exception as ex:
                        print(f"[LimePV] Simple rename error: {ex}")
        except Exception:
            pass

        self.report({'INFO'}, f"Cámara creada en {shot.name}/{C_UTILS_CAM}")
        return {'FINISHED'}

    def invoke(self, context, event):
        # Mostrar diálogo para seleccionar tipo de rig
        return context.window_manager.invoke_props_dialog(self)


__all__ = [
    "LIME_OT_proposal_view_config",
    "LIME_OT_take_pv_shot",
    "LIME_OT_take_all_pv_shots",
    "LIME_OT_add_camera_rig",
]


