"""
UI to review and apply AI-proposed material renames according to naming rules.

Purpose: Scan materials, show status (VALID/NEEDS_RENAME/etc.), allow filtering and applying
proposed names safely.
Key classes: LIME_TB_PT_ai_material_renamer, LIME_TB_UL_ai_mat_rows.
Depends on: lime_pipeline.props_ai_materials state and ops with prefix lime_tb.ai_*.
Notes: UI-only; heavy logic lives in operators and props definitions.
"""

import bpy
from bpy.types import Panel, UIList


class LIME_TB_UL_ai_mat_rows(UIList):
    """List rows summarizing each material status and proposed name."""
    bl_idname = "LIME_TB_UL_ai_mat_rows"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = item
        scene = context.scene
        state = getattr(scene, 'lime_ai_mat', None)

        row_layout = layout.row(align=True)
        checkbox_col = row_layout.column()
        checkbox_col.enabled = not row.read_only
        checkbox_col.prop(row, "selected_for_apply", text="", emboss=True)

        split = row_layout.split(factor=0.5)
        left = split.column()
        left_row = left.row(align=True)
        left_row.label(text=row.material_name or "<no name>")
        # Status badge (icon only)
        status = (row.status or "").upper()
        icon_map = {
            "VALID": 'CHECKMARK',
            "NEEDS_RENAME": 'INFO',
            "SEQUENCE_GAP": 'ERROR',  # warning-like
            "NAME_COLLISION": 'CANCEL',
            "UNPARSEABLE": 'BLANK1',
        }
        status_key = status.split(":", 1)[0] if status else ""
        left_row.label(text="", icon=icon_map.get(status_key, 'BLANK1'))

        right = split.column()
        # proposed_name editable solo si estado es accionable
        actionable = (status.startswith("NEEDS_RENAME") or status.startswith("NAME_COLLISION")) and not row.read_only
        if actionable:
            right.prop(row, "proposed_name", text="")
        else:
            right.label(text=row.proposed_name if row.proposed_name else "-")

    def filter_items(self, context, data, propname):
        """Filtrar y ordenar items según estado.

        IMPORTANTE: Blender espera (flt_flags, flt_neworder)
        - flt_flags: lista de longitud N con 0 o self.bitflag_filter_item
        - flt_neworder: lista de longitud N con índices reordenados
        """
        scene = context.scene
        state = getattr(scene, 'lime_ai_mat', None)
        rows = getattr(data, propname, [])

        n = len(rows) if rows else 0

        if not rows or n == 0:
            return [], []

        # View filter
        view = getattr(state, 'view_filter', 'NEEDS') if state else 'NEEDS'

        # 1) Flags de visibilidad
        flags = [0] * n
        for i, row in enumerate(rows):
            status = (getattr(row, 'status', '') or '').upper()
            if view == 'ALL':
                visible = True
            elif view == 'CORRECT':
                visible = (status.startswith('VALID'))
            else:  # NEEDS
                visible = (
                    status.startswith('NEEDS_RENAME') or
                    status.startswith('NAME_COLLISION') or
                    status.startswith('UNPARSEABLE') or
                    status.startswith('SEQUENCE_GAP')
                )
            flags[i] = self.bitflag_filter_item if visible else 0

        # 2) Natural sort (visible first, hidden last)
        sort_desc = False
        def sort_key_index(i: int):
            try:
                row = rows[i]
                # Prefer proposed for actionable preview, else current name
                name_to_parse = (getattr(row, 'proposed_name', None) or getattr(row, 'material_name', None) or "")
                if state:
                    _ = state.sort_token
                parts = name_to_parse.split("_")
                if len(parts) >= 4 and parts[0] == "MAT":
                    material_type = parts[1] if len(parts) > 1 else ""
                    version_block = parts[-1] if len(parts) > 2 else "V00"
                    if len(parts) > 3:
                        finish = "_".join(parts[2:-1])
                    elif len(parts) > 2:
                        finish = parts[2]
                    else:
                        finish = ""
                    try:
                        ver_int = int(version_block[1:]) if version_block.startswith("V") and len(version_block) > 1 else 0
                    except Exception:
                        ver_int = 0
                    return (material_type.upper(), finish.upper(), ver_int, i)
                # Fallback ordering using row fields to keep groups together
                material_type = getattr(row, 'material_type', '') or ""
                finish = getattr(row, 'finish', '') or ""
                version_field = getattr(row, 'version_token', '') or ""
                try:
                    if isinstance(version_field, str) and version_field.startswith('V'):
                        ver_int = int(version_field[1:]) if version_field[1:].isdigit() else 0
                    else:
                        ver_int = 0
                except Exception:
                    ver_int = 0
                return (material_type.upper(), finish.upper(), ver_int, i)
            except Exception as e:
                return ("ZZZ", "ZZZ", "ZZZ", 9999, i)

        visible_indices = [i for i, f in enumerate(flags) if f != 0]
        hidden_indices = [i for i, f in enumerate(flags) if f == 0]

        try:
            visible_indices.sort(key=sort_key_index)
        except Exception:
            pass

        neworder = visible_indices + hidden_indices

        return flags, neworder


class LIME_TB_PT_ai_material_renamer(Panel):
    """Panel to visualize AI rename suggestions and apply them in batch."""
    bl_label = "AI Material Renamer"
    bl_idname = "LIME_TB_PT_ai_material_renamer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Lime Toolbox'

    bl_order = 180

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        state = getattr(scene, 'lime_ai_mat', None)
        tag = (scene.get("mat_scene_tag") or "S1")

        # No debug prints in UI; keep clean

        # Scene Tag removed from UI per simplification

        # Botones principales
        col = layout.column(align=True)
        r = col.row(align=True)
        r.operator("lime_tb.ai_scan_materials", text="Search Materials")
        actionable_selected = 0
        if state and state.rows:
            for it in state.rows:
                s = (getattr(it, 'status', '') or '').upper()
                if (
                    (s.startswith('NEEDS_RENAME') or s.startswith('NAME_COLLISION'))
                    and not getattr(it, 'read_only', False)
                    and getattr(it, 'selected_for_apply', False)
                ):
                    actionable_selected += 1
        op_row = r.row()
        op_row.enabled = actionable_selected > 0
        op_row.operator("lime_tb.ai_apply_materials", text="Apply Renames")
        r.operator("lime_tb.ai_clear_materials", text="Clear")

        # View filter controls (no sort descending)
        if state:
            vf = layout.row(align=True)
            vf.prop(state, "view_filter", expand=True)
            sel_row = layout.row(align=True)
            sel_row.enabled = bool(state.rows)
            sel_row.operator("lime_tb.ai_select_all", text="Select All")
            sel_row.operator("lime_tb.ai_select_none", text="Select None")

        # Label de conteo si hay datos
        if state and (state.incorrect_count > 0 or state.total_count > 0):
            layout.label(text=f"Invalid naming pattern: {state.incorrect_count} of {state.total_count}")

        # Botones laterales removidos como solicitado

        # Ensure state is not None (defensive)
        if state is None:
            from ..props_ai_materials import LimeAIMatState
            state = LimeAIMatState()

        layout.template_list("LIME_TB_UL_ai_mat_rows", "", state, "rows", state, "active_index", rows=8)
        # done


__all__ = [
    "LIME_TB_PT_ai_material_renamer",
    "LIME_TB_UL_ai_mat_rows",
]


