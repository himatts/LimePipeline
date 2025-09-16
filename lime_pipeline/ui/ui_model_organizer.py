import bpy
from bpy.types import Panel, Operator
from bpy.props import BoolProperty


CAT = "Lime Pipeline"


class LIME_OT_group_selection_empty(Operator):
    """Create an empty centered on the selection bounds and preserve transforms."""
    bl_idname = "lime.group_selection_empty"
    bl_label = "Group Selection (Empty)"
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
        empty_name = "Selection Group" if len(selection) > 1 else f"{selection[0].name} Group"
        empty = bpy.data.objects.new(empty_name, None)
        base_collection.objects.link(empty)
        empty.empty_display_type = 'PLAIN_AXES'
        empty.location = cursor.location

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

        # Selection feedback
        for obj in list(context.selected_objects):
            obj.select_set(False)
        for obj in selection:
            obj.select_set(True)
        empty.select_set(True)
        context.view_layer.objects.active = empty

        if self.debug:
            print("[Lime][GroupSelectionEmpty] ---- Done ----")
        self.report({'INFO'}, f"Created empty '{empty.name}' and bounds cube for the selection.")
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

        box = layout.box()
        box.label(text="Importers")
        # Directly invoke the sTEPper operator if installed
        # This shows a standard operator button; Blender will handle missing-operator errors.
        row = box.row(align=True)
        row.operator("import_scene.occ_import_step", text="Import STEP (.step)", icon='IMPORT')

        box = layout.box()
        box.label(text="Cleanup")
        row = box.row(align=True)
        row.operator("lime.clean_step", text="Clean .STEP", icon='FILE_REFRESH')
        row = box.row(align=True)
        row.operator("lime.group_selection_empty", text="Group Selection (Empty)", icon='OUTLINER_OB_EMPTY')


__all__ = [
    "LIME_OT_group_selection_empty",
    "LIME_PT_model_organizer",
]
