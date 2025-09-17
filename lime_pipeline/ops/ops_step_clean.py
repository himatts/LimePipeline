import bpy
from bpy.types import Operator


GEOM_TYPES = {"MESH", "CURVE", "SURFACE", "META", "FONT", "POINTCLOUD", "VOLUME"}


def _has_geometry_descendants(root):
    stack = list(getattr(root, "children", []) or [])
    while stack:
        obj = stack.pop()
        if getattr(obj, "type", None) in GEOM_TYPES:
            return True
        ch = getattr(obj, "children", []) or []
        if ch:
            stack.extend(ch)
    return False


def _collect_descendant_geometry(root):
    out = []
    stack = list(getattr(root, "children", []) or [])
    seen = set()
    while stack:
        obj = stack.pop()
        if obj is None:
            continue
        if obj.name in seen:
            continue
        seen.add(obj.name)
        if getattr(obj, "type", None) in GEOM_TYPES:
            out.append(obj)
        ch = getattr(obj, "children", []) or []
        if ch:
            stack.extend(ch)
    return out


def _detect_step_roots(context):
    sel = list(context.selected_objects or [])
    if sel:
        roots = [o for o in sel if getattr(o, "type", None) == 'EMPTY']
        if roots:
            return roots
    # Auto-detect: empties without parent and with geo in descendants, or STEP-like name
    roots = []
    for o in context.scene.objects:
        if getattr(o, "type", None) != 'EMPTY':
            continue
        if o.parent is not None:
            continue
        name = getattr(o, "name", "") or ""
        if name.startswith("STEPFile") or name.startswith("STEPFile -") or _has_geometry_descendants(o):
            roots.append(o)
    return roots


def _ensure_object_mode(context, any_selectable=None):
    try:
        if context.mode != 'OBJECT':
            # Ensure an active object for mode_set
            if any_selectable is not None:
                context.view_layer.objects.active = any_selectable
            bpy.ops.object.mode_set(mode='OBJECT')
    except Exception:
        pass


class LIME_OT_clean_step(Operator):
    bl_idname = "lime.clean_step"
    bl_label = "Clean .STEP"
    bl_description = "Flatten STEP import: unparent geometry (keep transforms), make single-user, clear materials, and remove orphan empties/materials"
    bl_options = {"REGISTER", "UNDO"}

    remove_orphan_empties: bpy.props.BoolProperty(
        name="Remove Orphan Empties",
        description="Remove empty objects that end up with no children",
        default=True,
    )

    def execute(self, context):
        # Snapshot selection/active
        prev_sel = list(context.selected_objects or [])
        prev_active = context.view_layer.objects.active

        roots = _detect_step_roots(context)
        if not roots:
            self.report({'WARNING'}, "Clean .STEP: No STEP roots found (select root empties or import first)")
            return {'CANCELLED'}

        # Collect geometry under roots (unique)
        geom = []
        seen = set()
        for r in roots:
            for o in _collect_descendant_geometry(r):
                if o.name not in seen:
                    geom.append(o)
                    seen.add(o.name)
        if not geom:
            self.report({'WARNING'}, "Clean .STEP: No geometry found under detected roots")
            return {'CANCELLED'}

        # Ensure object mode and select only targets
        _ensure_object_mode(context, geom[0])
        for o in context.selected_objects:
            o.select_set(False)
        for o in geom:
            try:
                o.select_set(True)
            except Exception:
                pass
        context.view_layer.objects.active = geom[0]

        # Unparent while keeping transforms
        try:
            bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
        except Exception:
            pass

        # Make single user for object, data, and materials
        try:
            bpy.ops.object.make_single_user(object=True, obdata=True, material=True, type='SELECTED_OBJECTS')
        except Exception:
            pass

        # Apply rotation and scale to bake transforms (keep location as-is)
        try:
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        except Exception:
            pass

        # Recenter origin to center of mass for cleaned geometry
        try:
            bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS', center='MEDIAN')
        except Exception:
            pass

        # Clear materials on targets and count cleared slots
        mats_cleared_slots = 0
        try:
            for o in geom:
                datab = getattr(o, 'data', None)
                if datab is None or not hasattr(datab, 'materials'):
                    continue
                # Count current non-None slots
                for m in list(datab.materials) if datab.materials else []:
                    if m is not None:
                        mats_cleared_slots += 1
                if hasattr(datab.materials, 'clear'):
                    datab.materials.clear()
        except Exception:
            pass

        # Remove orphaned materials datablocks
        removed_materials = 0
        try:
            # Count/remove zero-user materials
            for m in list(bpy.data.materials):
                try:
                    if m.users == 0:
                        bpy.data.materials.remove(m, do_unlink=True)
                        removed_materials += 1
                except Exception:
                    pass
        except Exception:
            pass

        # Optional: purge more orphans via Outliner op (best-effort)
        try:
            # Try with context override to any OUTLINER area
            win = context.window
            override = None
            if win:
                for area in win.screen.areas:
                    if area.type == 'OUTLINER':
                        override = context.copy()
                        override['area'] = area
                        override['region'] = area.regions[-1]
                        break
            if override is None:
                bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
            else:
                bpy.ops.outliner.orphans_purge(override, do_local_ids=True, do_linked_ids=True, do_recursive=True)
        except Exception:
            pass

        # Optional: remove empty objects under roots that have no geometry in their subtree
        empties_removed = 0
        if self.remove_orphan_empties:
            try:
                candidates = set()
                for r in roots:
                    stack = [r]
                    while stack:
                        o = stack.pop()
                        if getattr(o, 'type', None) == 'EMPTY':
                            candidates.add(o)
                        for ch in getattr(o, 'children', []) or []:
                            stack.append(ch)

                # Iteratively remove any empty whose subtree has no geometry
                def _subtree_has_geo(empty_obj):
                    return _has_geometry_descendants(empty_obj)

                while True:
                    removed_any = False
                    to_remove = [o for o in list(candidates) if not _subtree_has_geo(o)]
                    if not to_remove:
                        break
                    # Remove bottom-up: sort by depth (deeper first)
                    def _depth(o):
                        d = 0
                        p = o.parent
                        while p is not None:
                            d += 1
                            p = p.parent
                        return d
                    for o in sorted(to_remove, key=_depth, reverse=True):
                        try:
                            bpy.data.objects.remove(o, do_unlink=True)
                            empties_removed += 1
                            candidates.discard(o)
                            removed_any = True
                        except Exception:
                            candidates.discard(o)
                    if not removed_any:
                        break
            except Exception:
                pass

        processed = len(geom)

        # Restore previous selection/active (best-effort, skip removed)
        try:
            for o in context.selected_objects:
                o.select_set(False)
            for o in prev_sel:
                if o.name in bpy.data.objects:
                    bpy.data.objects[o.name].select_set(True)
            if prev_active and prev_active.name in bpy.data.objects:
                context.view_layer.objects.active = bpy.data.objects[prev_active.name]
        except Exception:
            pass

        self.report({'INFO'}, f"Clean .STEP: objects={processed}, slots_cleared={mats_cleared_slots}, materials_removed={removed_materials}, empties_removed={empties_removed}")
        return {'FINISHED'}


__all__ = ["LIME_OT_clean_step"]

