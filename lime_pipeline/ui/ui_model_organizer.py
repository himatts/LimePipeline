import bpy
from bpy.types import Panel, Operator
from bpy.props import BoolProperty


CAT = "Lime Pipeline"


_LOCATION_EPSILON = 1e-4


def _objects_with_location_offset(scene):
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
        import bmesh

        # Ignore existing empties in selection to compute true geometry bounds
        selection = [obj for obj in (context.selected_objects or []) if obj.type != 'EMPTY']
        if not selection:
            self.report({'WARNING'}, "Select at least one object to group.")
            return {'CANCELLED'}

        # Cache world transforms to restore after parenting
        original_matrices = {obj: obj.matrix_world.copy() for obj in selection}

        # Compute world-space AABB using evaluated geometry (includes modifiers)
        depsgraph = context.evaluated_depsgraph_get()
        min_x = min_y = min_z = float('inf')
        max_x = max_y = max_z = float('-inf')

        def _accum_point(p):
            nonlocal min_x, min_y, min_z, max_x, max_y, max_z
            if p.x < min_x: min_x = p.x
            if p.y < min_y: min_y = p.y
            if p.z < min_z: min_z = p.z
            if p.x > max_x: max_x = p.x
            if p.y > max_y: max_y = p.y
            if p.z > max_z: max_z = p.z

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

        # Create a unit cube and scale to the AABB extents (world-aligned)
        bounds_mesh = bpy.data.meshes.new("SelectionBoundsMesh")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(bounds_mesh)
        bm.free()

        cube_name = "Selection Bounds" if len(selection) > 1 else f"{selection[0].name} Bounds"
        cube = bpy.data.objects.new(cube_name, bounds_mesh)
        base_collection.objects.link(cube)
        cube.display_type = 'WIRE'
        cube.hide_render = True
        cube.location = center
        cube.rotation_euler = (0.0, 0.0, 0.0)
        cube.scale = (1.0, 1.0, 1.0)
        cube.dimensions = Vector((size_x, size_y, size_z))

        if self.debug:
            print(f"[Lime] Cube at {tuple(cube.matrix_world.translation)} dimensions {tuple(cube.dimensions)}")

        # Move 3D cursor to cube center
        cursor = context.scene.cursor
        cursor.location = cube.location.copy()

        # Create the grouping empty at cursor
        empty = bpy.data.objects.new("CONTROLLER", None)
        base_collection.objects.link(empty)
        empty.empty_display_type = 'PLAIN_AXES'
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
        for obj in selection:
            obj.parent = empty
            obj.matrix_parent_inverse = parent_inverse.copy()
            # Restore original world transform to avoid any drift
            obj.matrix_world = original_matrices[obj]
            if self.debug:
                new_loc = obj.matrix_world.translation
                old_loc = original_matrices[obj].translation
                dx, dy, dz = (new_loc - old_loc)
                print(f"[Lime] '{obj.name}' delta after parenting: ({dx:.6f}, {dy:.6f}, {dz:.6f})")

        # Keep the visual bounds cube under the empty as reference
        cube.parent = empty
        cube.matrix_parent_inverse = parent_inverse.copy()

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
        self.report({'INFO'}, f"Created empty '{empty.name}' and bounds cube for the selection.")
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
        offenders = _objects_with_location_offset(scene)
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




def _set_scene_units(context, *, system: str, length_unit: str) -> bool:
    scene = context.scene
    if scene is None:
        return False
    settings = scene.unit_settings
    settings.system = system
    try:
        settings.length_unit = length_unit
    except Exception:
        pass
    return True


class LIME_OT_set_units_centimeters(Operator):
    """Switch the scene measurement units to centimeters."""

    bl_idname = "lime.set_units_centimeters"
    bl_label = "Set Units to Centimeters"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Set the scene measurement units to centimeters."

    def execute(self, context):
        if not _set_scene_units(context, system='METRIC', length_unit='CENTIMETERS'):
            self.report({'ERROR'}, "Unable to set scene units to centimeters.")
            return {'CANCELLED'}
        self.report({'INFO'}, "Scene units set to centimeters.")
        return {'FINISHED'}


class LIME_OT_set_units_millimeters(Operator):
    """Switch the scene measurement units to millimeters."""

    bl_idname = "lime.set_units_millimeters"
    bl_label = "Set Units to Millimeters"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Set the scene measurement units to millimeters."

    def execute(self, context):
        if not _set_scene_units(context, system='METRIC', length_unit='MILLIMETERS'):
            self.report({'ERROR'}, "Unable to set scene units to millimeters.")
            return {'CANCELLED'}
        self.report({'INFO'}, "Scene units set to millimeters.")
        return {'FINISHED'}


class LIME_OT_set_units_inches(Operator):
    """Switch the scene measurement units to inches."""

    bl_idname = "lime.set_units_inches"
    bl_label = "Set Units to Inches"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Set the scene measurement units to inches."

    def execute(self, context):
        if not _set_scene_units(context, system='IMPERIAL', length_unit='INCHES'):
            self.report({'ERROR'}, "Unable to set scene units to inches.")
            return {'CANCELLED'}
        self.report({'INFO'}, "Scene units set to inches.")
        return {'FINISHED'}


class LIME_PT_model_organizer(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "3D Model Organizer"
    bl_idname = "LIME_PT_model_organizer"
    bl_order = 50

    def draw(self, ctx):
        layout = self.layout

        layout.operator("import_scene.occ_import_step", text="Import STEP (.step)", icon='IMPORT')
        layout.operator("lime.clean_step", text="Clean .STEP", icon='FILE_REFRESH')

        offsets = _objects_with_location_offset(ctx.scene)
        status_row = layout.row()
        if offsets:
            status_row.label(text=f"Offsets detected: {len(offsets)} object(s)", icon='ERROR')
        else:
            status_row.label(text="All object locations zeroed", icon='CHECKMARK')
        apply_row = layout.row()
        apply_row.enabled = bool(offsets)
        apply_row.operator("lime.apply_scene_deltas", text="Apply Deltas", icon='FILE_TICK')

        layout.operator("lime.group_selection_empty", text="Create Controller", icon='OUTLINER_OB_EMPTY')
        layout.operator("lime.move_controller", text="Move Controller", icon='EMPTY_ARROWS')


        dim_col = layout.column()
        dim_col.label(text="Dimension Checker")
        state = getattr(ctx.window_manager, "lime_pipeline", None)
        if state is not None:
            dim_col.prop(state, "dimension_orientation_mode", text="Orientation Mode")
            lock_row = dim_col.row()
            lock_row.enabled = state.dimension_orientation_mode == 'PCA3D'
            lock_row.prop(state, "dimension_lock_z_up", text="Lock Z-Up")
        op = dim_col.operator("lime.dimension_envelope", text="Dimension Checker", icon='MESH_CUBE')
        if state is not None:
            op.orientation_mode = state.dimension_orientation_mode
            op.lock_z_up = state.dimension_lock_z_up

        unit_row = layout.row(align=True)
        unit_row.operator("lime.set_units_centimeters", text="cm")
        unit_row.operator("lime.set_units_millimeters", text="mm")
        unit_row.operator("lime.set_units_inches", text="in")

__all__ = [
    "LIME_OT_group_selection_empty",
    "LIME_OT_move_controller",
    "LIME_OT_apply_scene_deltas",
    "LIME_OT_set_units_centimeters",
    "LIME_OT_set_units_millimeters",
    "LIME_OT_set_units_inches",
    "LIME_PT_model_organizer",
]

