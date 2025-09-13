import bpy
from bpy.types import Panel

from ..core import validate_scene


CAT = "Lime Pipeline"


class LIME_PT_shots(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Shots"
    bl_idname = "LIME_PT_shots"
    bl_order = 1

    def draw(self, ctx):
        # Container panel: subpanels handle content
        pass


class LIME_PT_shots_list(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Shot List"
    bl_idname = "LIME_PT_shots_list"
    bl_parent_id = "LIME_PT_shots"

    def draw(self, ctx):
        layout = self.layout
        active = validate_scene.active_shot_context(ctx)
        shots = validate_scene.list_shot_roots(ctx.scene)
        # Fallback: scan recursively if root-level list is empty
        if not shots:
            def _scan(coll):
                items = []
                try:
                    idx = validate_scene.parse_shot_index(coll.name)
                except Exception:
                    idx = None
                if idx is not None:
                    items.append((coll, idx))
                else:
                    try:
                        for ch in getattr(coll, 'children', []) or []:
                            items.extend(_scan(ch))
                    except Exception:
                        pass
                return items
            try:
                shots = _scan(ctx.scene.collection)
                shots.sort(key=lambda t: t[1])
            except Exception:
                shots = []
        if not shots:
            row = layout.row()
            row.enabled = False
            row.label(text="No SHOTs", icon='INFO')
            return
        for shot, idx in shots:
            row = layout.row(align=True)
            try:
                del_op = row.operator("lime.delete_shot", text="", icon='TRASH')
                del_op.shot_name = shot.name
            except Exception:
                dummy = row.row()
                dummy.enabled = False
                dummy.label(text="", icon='TRASH')
            icon = 'CHECKMARK' if active == shot else 'OUTLINER_COLLECTION'
            op = row.operator("lime.activate_shot", text=shot.name, icon=icon)
            op.shot_name = shot.name


class LIME_PT_shots_tools(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Shot Tools"
    bl_idname = "LIME_PT_shots_tools"
    bl_parent_id = "LIME_PT_shots"

    def draw(self, ctx):
        layout = self.layout
        col = layout.column(align=True)
        col.operator("lime.new_shot", text="New Shot", icon='ADD')

        row = layout.row(align=True)
        can_instance, msg_i = validate_scene.can_instance_shot(ctx)
        row.enabled = can_instance
        row.operator("lime.shot_instance", text="Shot Instance", icon='OUTLINER_COLLECTION')
        if not can_instance and msg_i:
            hint = layout.row(align=True)
            hint.label(text=msg_i, icon='INFO')

        row = layout.row(align=True)
        can_dup, msg_d = validate_scene.can_duplicate_shot(ctx)
        row.enabled = can_dup
        row.operator("lime.duplicate_shot", text="Duplicate Shot", icon='DUPLICATE')
        if not can_dup and msg_d:
            hint = layout.row(align=True)
            hint.label(text=msg_d, icon='INFO')

        row = layout.row(align=True)
        row.enabled = validate_scene.active_shot_context(ctx) is not None
        row.operator("lime.add_missing_collections", text="Add Missing Collections", icon='FILE_REFRESH')


