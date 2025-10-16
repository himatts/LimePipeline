import bpy
from bpy.types import Panel, UIList, PropertyGroup, Operator
from bpy.props import (
    StringProperty,
    CollectionProperty,
    IntProperty,
)

from ..core import validate_scene


CAT = "Lime Pipeline"


_SHOTS_HANDLER = None


class LIME_PT_shots(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Shots"
    bl_options = {"DEFAULT_CLOSED"}
    bl_idname = "LIME_PT_shots"
    bl_order = 4

    def draw(self, ctx):
        layout = self.layout
        scene = ctx.scene
        st = ctx.window_manager.lime_pipeline

        # Solo Shot Active toggle
        row = layout.row()
        row.prop(st, "solo_shot_activo", text="Solo Shot Activo",
                icon='RESTRICT_VIEW_ON' if getattr(st, 'solo_shot_activo', False) else 'RESTRICT_VIEW_OFF')

        # Main shot list with controls
        row = layout.row(align=True)
        row.template_list("LIME_UL_shots", "", scene, "lime_shots", scene, "lime_shots_index", rows=6)

        # All controls in single column
        col = row.column(align=True)
        col.operator("lime.new_shot_and_sync", text='', icon='ADD')
        del_op = col.operator("lime.delete_shot_and_sync", text='', icon='REMOVE')
        try:
            idx = getattr(scene, 'lime_shots_index', -1)
            items = getattr(scene, 'lime_shots', None)
            if items is not None and 0 <= idx < len(items):
                del_op.shot_name = items[idx].name
        except Exception:
            pass
        col.separator()
        col.operator("lime.sync_shot_list", text='', icon='FILE_REFRESH')
        col.operator("lime.duplicate_shot_and_sync", text='', icon='DUPLICATE')
        col.operator("lime.add_missing_collections", text='', icon='WARNING_LARGE')




class LimeShotItem(PropertyGroup):
    name: StringProperty(name="SHOT")


class LIME_UL_shots(UIList):
    bl_idname = "LIME_UL_shots"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        active_shot = validate_scene.active_shot_context(context)
        is_active = False
        try:
            is_active = (active_shot is not None and active_shot.name == item.name)
        except Exception:
            pass
        layout.label(text=item.name, icon='CHECKMARK' if is_active else 'OUTLINER_COLLECTION')


class LIME_OT_sync_shot_list(Operator):
    bl_idname = "lime.sync_shot_list"
    bl_label = "Refresh SHOTs"
    bl_description = "Refresh the SHOT list from the current scene"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        items = getattr(scene, 'lime_shots', None)
        if items is None:
            self.report({'ERROR'}, 'SHOT list storage not available')
            return {'CANCELLED'}
        try:
            items.clear()
            pairs = validate_scene.list_shot_roots(scene)
            if not pairs:
                # Fallback recursive scan as in old UI
                def _scan(coll):
                    found = []
                    try:
                        idx = validate_scene.parse_shot_index(coll.name)
                    except Exception:
                        idx = None
                    if idx is not None:
                        found.append((coll, idx))
                    else:
                        for ch in getattr(coll, 'children', []) or []:
                            found.extend(_scan(ch))
                    return found
                try:
                    pairs = _scan(scene.collection)
                    pairs.sort(key=lambda t: t[1])
                except Exception:
                    pairs = []
            for coll, _idx in pairs:
                it = items.add()
                it.name = coll.name
            # Try to sync active index with current active shot
            try:
                active = validate_scene.active_shot_context(context)
                if active is not None:
                    for i, it in enumerate(items):
                        if it.name == active.name:
                            scene.lime_shots_index = i
                            break
            except Exception:
                pass
        except Exception:
            self.report({'WARNING'}, 'Could not refresh SHOT list')
            return {'CANCELLED'}
        self.report({'INFO'}, f"SHOTs: {len(items)}")
        return {'FINISHED'}


class LIME_OT_new_shot_and_sync(Operator):
    bl_idname = "lime.new_shot_and_sync"
    bl_label = "New Shot and Refresh"
    bl_description = "Create a SHOT using Lime operator and refresh the list"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            bpy.ops.lime.new_shot()
        except Exception:
            self.report({'ERROR'}, 'Failed to create SHOT')
            return {'CANCELLED'}
        try:
            bpy.ops.lime.sync_shot_list()
        except Exception:
            pass
        return {'FINISHED'}


class LIME_OT_delete_shot_and_sync(Operator):
    bl_idname = "lime.delete_shot_and_sync"
    bl_label = "Delete Shot and Refresh"
    bl_description = "Delete the selected SHOT and refresh the list"
    bl_options = {'REGISTER', 'UNDO'}

    shot_name: StringProperty(name="SHOT Name", default="")

    def execute(self, context):
        name = (self.shot_name or '').strip()
        scene = context.scene
        # Compute the desired next selection before deletion
        next_name = ''
        try:
            items = getattr(scene, 'lime_shots', None)
            idx = getattr(scene, 'lime_shots_index', -1)
            if items is not None and 0 <= idx < len(items):
                if idx + 1 < len(items):
                    next_name = items[idx + 1].name
                elif idx - 1 >= 0:
                    next_name = items[idx - 1].name
        except Exception:
            next_name = ''
        if not name:
            self.report({'WARNING'}, 'No SHOT selected')
            return {'CANCELLED'}
        try:
            bpy.ops.lime.delete_shot(shot_name=name)
        except Exception:
            self.report({'ERROR'}, f"Failed to delete SHOT: {name}")
            return {'CANCELLED'}
        try:
            bpy.ops.lime.sync_shot_list()
        except Exception:
            pass
        # Try to select the next/previous item after deletion
        try:
            items2 = getattr(scene, 'lime_shots', None)
            if items2 is not None and next_name:
                for i, it in enumerate(items2):
                    if it.name == next_name:
                        scene.lime_shots_index = i
                        break
        except Exception:
            pass
        return {'FINISHED'}


class LIME_OT_duplicate_shot_and_sync(Operator):
    bl_idname = "lime.duplicate_shot_and_sync"
    bl_label = "Duplicate Shot and Refresh"
    bl_description = "Duplicate the active SHOT and refresh the list"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            bpy.ops.lime.duplicate_shot()
        except Exception:
            self.report({'ERROR'}, 'Failed to duplicate SHOT')
            return {'CANCELLED'}
        try:
            bpy.ops.lime.sync_shot_list()
        except Exception:
            pass
        return {'FINISHED'}


class LIME_OT_isolate_active_shot(Operator):
    bl_idname = "lime.isolate_active_shot"
    bl_label = "Isolate Active Shot"
    bl_description = "Hide all SHOT collections except the active one in View Layer"
    bl_options = {'REGISTER', 'UNDO'}

    shot_name: bpy.props.StringProperty(name="Shot Name", default="")

    @classmethod
    def poll(cls, ctx):
        return True

    def execute(self, context):
        scene = context.scene
        st = context.window_manager.lime_pipeline

        # Check if solo mode is enabled
        if not getattr(st, 'solo_shot_activo', False):
            return {'FINISHED'}

        # Find active shot - use provided name if available, otherwise find from context
        active_shot = None
        if self.shot_name:
            active_shot = bpy.data.collections.get(self.shot_name)
        else:
            active_shot = validate_scene.active_shot_context(context)

        if active_shot is None:
            self.report({'WARNING'}, "No active SHOT to isolate")
            return {'CANCELLED'}

        # Get all shot roots
        shots = validate_scene.list_shot_roots(scene)
        other_shots = [s for s, _ in shots if s != active_shot]

        # Hide other shots in View Layer
        try:
            def _find_layer_collection(layer, coll):
                if layer and layer.collection == coll:
                    return layer
                for ch in getattr(layer, 'children', []):
                    found = _find_layer_collection(ch, coll)
                    if found:
                        return found
                return None

            def _iter_layer_subtree(root_layer):
                if root_layer is None:
                    return
                stack = [root_layer]
                while stack:
                    lc = stack.pop()
                    yield lc
                    try:
                        stack.extend(list(lc.children))
                    except Exception:
                        pass

            vl = context.view_layer
            base = vl.layer_collection if vl else None

            # Hide other shots
            for shot_coll in other_shots:
                lc = _find_layer_collection(base, shot_coll)
                if lc is not None:
                    # Hide the entire subtree
                    for sub_lc in _iter_layer_subtree(lc):
                        try:
                            sub_lc.exclude = True
                        except Exception:
                            pass

            # Ensure active shot is visible
            active_lc = _find_layer_collection(base, active_shot)
            if active_lc is not None:
                for sub_lc in _iter_layer_subtree(active_lc):
                    try:
                        sub_lc.exclude = False
                    except Exception:
                        pass

            self.report({'INFO'}, f"Isolated SHOT: {active_shot.name}")

        except Exception as ex:
            self.report({'ERROR'}, f"Failed to isolate shot: {str(ex)}")
            return {'CANCELLED'}

        return {'FINISHED'}


def register_shot_list_props():
    bpy.utils.register_class(LimeShotItem)
    bpy.utils.register_class(LIME_UL_shots)
    bpy.utils.register_class(LIME_OT_sync_shot_list)
    bpy.utils.register_class(LIME_OT_new_shot_and_sync)
    bpy.utils.register_class(LIME_OT_delete_shot_and_sync)
    bpy.utils.register_class(LIME_OT_duplicate_shot_and_sync)
    bpy.utils.register_class(LIME_OT_isolate_active_shot)

    bpy.types.Scene.lime_shots = CollectionProperty(type=LimeShotItem)

    def _on_active_shot_index(self, context):
        try:
            idx = getattr(self, 'lime_shots_index', -1)
            items = getattr(self, 'lime_shots', None)
            if items is None or not (0 <= idx < len(items)):
                return
            name = items[idx].name
            try:
                bpy.ops.lime.activate_shot(shot_name=name)
            except Exception:
                pass
            # Apply shot isolation if solo mode is active
            try:
                st = context.window_manager.lime_pipeline
                if getattr(st, 'solo_shot_activo', False):
                    bpy.ops.lime.isolate_active_shot(shot_name=name)
            except Exception:
                pass
        except Exception:
            pass

    bpy.types.Scene.lime_shots_index = IntProperty(
        name="Active SHOT Index",
        default=-1,
        options={'HIDDEN'},
        update=_on_active_shot_index,
    )

    # Token for change detection (names + count)
    bpy.types.Scene.lime_shots_token = StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def _compute_shots_token(scene) -> str:
        try:
            pairs = validate_scene.list_shot_roots(scene)
            if not pairs:
                # fallback recursive
                def _scan(coll):
                    found = []
                    try:
                        idx = validate_scene.parse_shot_index(coll.name)
                    except Exception:
                        idx = None
                    if idx is not None:
                        found.append((coll, idx))
                    else:
                        for ch in getattr(coll, 'children', []) or []:
                            found.extend(_scan(ch))
                    return found
                try:
                    pairs = _scan(scene.collection)
                    pairs.sort(key=lambda t: t[1])
                except Exception:
                    pairs = []
            names = [c.name for c, _ in pairs]
            return f"{len(names)}|" + "|".join(names)
        except Exception:
            return ""

    def _fill_shot_items(scene):
        try:
            items = getattr(scene, 'lime_shots', None)
            if items is None:
                return
            items.clear()
            pairs = validate_scene.list_shot_roots(scene)
            if not pairs:
                # fallback recursive
                def _scan(coll):
                    found = []
                    try:
                        idx = validate_scene.parse_shot_index(coll.name)
                    except Exception:
                        idx = None
                    if idx is not None:
                        found.append((coll, idx))
                    else:
                        for ch in getattr(coll, 'children', []) or []:
                            found.extend(_scan(ch))
                    return found
                try:
                    pairs = _scan(scene.collection)
                    pairs.sort(key=lambda t: t[1])
                except Exception:
                    pairs = []
            for coll, _idx in pairs:
                it = items.add()
                it.name = coll.name
            # Sync active index to current active shot
            try:
                active = validate_scene.active_shot_context(bpy.context)
                if active is not None:
                    for i, it in enumerate(items):
                        if it.name == active.name:
                            scene.lime_shots_index = i
                            break
            except Exception:
                pass
        except Exception:
            pass

    def _shots_depsgraph_update_post(_deps):
        scene = bpy.context.scene
        if scene is None:
            return
        try:
            cur = _compute_shots_token(scene)
            prev = getattr(scene, 'lime_shots_token', '') or ''
            if cur != prev:
                _fill_shot_items(scene)
                scene.lime_shots_token = cur
        except Exception:
            pass

    global _SHOTS_HANDLER
    if _SHOTS_HANDLER is None:
        _SHOTS_HANDLER = _shots_depsgraph_update_post
        if _SHOTS_HANDLER not in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.append(_SHOTS_HANDLER)
    # Initial population
    try:
        scene = bpy.context.scene
        if scene is not None:
            cur = _compute_shots_token(scene)
            if cur != (getattr(scene, 'lime_shots_token', '') or ''):
                _fill_shot_items(scene)
                scene.lime_shots_token = cur
    except Exception:
        pass


def unregister_shot_list_props():
    for attr in (
        'lime_shots',
        'lime_shots_index',
        'lime_shots_token',
    ):
        try:
            delattr(bpy.types.Scene, attr)
        except Exception:
            pass
    global _SHOTS_HANDLER
    if _SHOTS_HANDLER is not None:
        try:
            bpy.app.handlers.depsgraph_update_post.remove(_SHOTS_HANDLER)
        except Exception:
            pass
        _SHOTS_HANDLER = None
    for cls in (
        LIME_OT_duplicate_shot_and_sync,
        LIME_OT_delete_shot_and_sync,
        LIME_OT_new_shot_and_sync,
        LIME_OT_sync_shot_list,
        LIME_OT_isolate_active_shot,
        LIME_UL_shots,
        LimeShotItem,
    ):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
