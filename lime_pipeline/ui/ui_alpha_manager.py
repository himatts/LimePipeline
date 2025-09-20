import bpy
from bpy.types import Panel, UIList


CAT = "Lime Toolbox"


class LIME_TB_UL_alpha_events(UIList):
    bl_idname = "LIME_TB_UL_alpha_events"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        event = item
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            icon_map = {
                'LINEAR': 'IPO_LINEAR',
                'BEZIER': 'IPO_BEZIER',
                'EASE_IN': 'IPO_EASE_IN',
                'EASE_OUT': 'IPO_EASE_OUT',
                'EASE_IN_OUT': 'IPO_EASE_IN_OUT',
            }
            row = layout.row(align=True)
            curve_icon = icon_map.get(getattr(event, 'curve', 'LINEAR'), 'IPO_BEZIER')
            # Name (read-only here to avoid bypassing rename operator logic)
            row.label(text=getattr(event, 'name', 'Event'), icon=curve_icon)
            # Brief range info
            try:
                start = int(getattr(event, 'frame_start', 0))
                end = int(getattr(event, 'frame_end', 0))
                row.label(text=f"{start} → {end}")
            except Exception:
                row.label(text="")
            # Invert badge
            try:
                inv = bool(getattr(event, 'invert', False))
            except Exception:
                inv = False
            if inv:
                row.label(text="Invert", icon='ARROW_LEFTRIGHT')
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon='IPO_BEZIER')


class LIME_TB_PT_alpha_manager(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = 'Alpha Manager'
    bl_idname = 'LIME_TB_PT_alpha_manager'

    def draw(self, ctx):
        layout = self.layout
        scene = ctx.scene

        # Warn if Auto Run is disabled (drivers might not evaluate)
        try:
            prefs = bpy.context.preferences
            auto_run = getattr(prefs.filepaths, 'use_scripts_auto_execute', True)
            if not auto_run:
                warn = layout.box()
                warn.alert = True
                warn.label(text="Auto Run Scripts is disabled", icon='ERROR')
                warn.label(text="Enable Preferences > Save & Load > Auto Run Python Scripts")
        except Exception:
            pass

        # Mode controls
        mode_row = layout.row(align=True)
        current_mode = getattr(scene, 'lime_tb_alpha_mode', 'LIVE')
        mode_row.label(text=f"Mode: {current_mode}")
        op_live = mode_row.operator('lime.tb_alpha_set_mode', text='Live (Drivers)', icon='DRIVER')
        op_live.mode = 'LIVE'
        op_bake = mode_row.operator('lime.tb_alpha_set_mode', text='Bake (Keyframes)', icon='KEY_HLT')
        op_bake.mode = 'BAKE'

        layout.separator()

        # Event list and actions
        row = layout.row(align=True)
        row.template_list("LIME_TB_UL_alpha_events", "", scene, "lime_tb_alpha_events", scene, "lime_tb_alpha_events_index", rows=6)
        col_btns = row.column(align=True)
        col_btns.operator('lime.tb_alpha_event_add', text='', icon='ADD')
        col_btns.operator('lime.tb_alpha_event_duplicate', text='', icon='DUPLICATE')
        col_btns.operator('lime.tb_alpha_event_rename', text='', icon='OUTLINER_DATA_FONT')
        col_btns.operator('lime.tb_alpha_event_delete', text='', icon='TRASH')

        events = getattr(scene, 'lime_tb_alpha_events', None)
        idx = getattr(scene, 'lime_tb_alpha_events_index', -1)
        if not events or len(events) == 0:
            box = layout.box()
            box.label(text="No events", icon='INFO')
            box.label(text="Click + to add a fade event.")
            return

        if not (0 <= idx < len(events)):
            return

        event = events[idx]

        # Active event details
        box = layout.box()
        hdr = box.row(align=True)
        hdr.label(text=f"Event: {getattr(event, 'name', '')}")
        hdr.prop(event, 'invert', text='Invert')

        row = box.row(align=True)
        row.prop(event, 'frame_start')
        row.prop(event, 'frame_end')

        row = box.row(align=True)
        row.prop(event, 'curve', text='Curve')

        # Manual refresh helpers
        ref = layout.row(align=True)
        ref.operator('lime.tb_alpha_rebuild', text='Rebuild Drivers', icon='FILE_REFRESH')
        try:
            # Simple current-frame nudge available in UI
            ref.operator('screen.frame_jump', text='', icon='FRAME_PREV').end = False
            ref.operator('screen.frame_jump', text='', icon='FRAME_NEXT').end = False
        except Exception:
            pass

        layout.separator()

        # Assignment tools
        assign_row = layout.row(align=True)
        assign_row.operator('lime.tb_alpha_event_assign', text='Assign Selection', icon='ADD')
        assign_row.operator('lime.tb_alpha_event_unassign', text='Remove Selection', icon='REMOVE')
        assign_row.operator('lime.tb_alpha_event_select_members', text='Select Members', icon='RESTRICT_SELECT_OFF')



__all__ = [
    'LIME_TB_PT_alpha_manager',
    'LIME_TB_UL_alpha_events',
]


