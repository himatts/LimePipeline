"""
UI to review and apply AI-proposed material renames according to naming rules.

This panel is lightweight; heavy logic resides in operators and property definitions.
"""

from __future__ import annotations

import bpy
from bpy.types import Panel, UIList


class LIME_TB_UL_ai_mat_rows(UIList):
    """Render each material entry with quality indicators and quick actions."""

    bl_idname = "LIME_TB_UL_ai_mat_rows"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        """
        Simplified material row UI.
        
        Flow:
        1. Check the checkbox to select for rename
        2. Edit the proposed name if needed (always editable)
        3. Press "Apply Renames" to apply all checked materials
        """
        if not item or not hasattr(item, "material_name"):
            return

        row = item
        scene = context.scene
        state = getattr(scene, "lime_ai_mat", None)

        read_only = bool(getattr(row, "read_only", False))
        material_name = getattr(row, "material_name", "") or "<no name>"
        status_value = (getattr(row, "status", "") or "").upper()
        proposed_name = getattr(row, "proposed_name", "") or ""
        quality_score = float(getattr(row, "quality_score", 0.0) or 0.0)

        row_layout = layout.row(align=True)
        row_layout.use_property_split = False
        row_layout.use_property_decorate = False

        # Checkbox
        checkbox_col = row_layout.column(align=True)
        checkbox_col.ui_units_x = 1.0
        checkbox_col.enabled = not read_only
        if hasattr(row, "selected_for_apply"):
            checkbox_col.prop(row, "selected_for_apply", text="", emboss=True)
        else:
            checkbox_col.label(text="", icon="BLANK1")

        # Material name
        name_col = row_layout.column(align=True)
        name_col.ui_units_x = 5.0
        name_row = name_col.row(align=True)
        name_row.label(text=material_name)
        # Show linked icon if read-only
        if read_only:
            name_row.label(text="", icon="LIBRARY_DATA_DIRECT")

        # Status icon + text
        status_col = row_layout.column(align=True)
        status_col.ui_units_x = 3.0
        icon_map = {
            "VALID": "CHECKMARK",
            "NEEDS_RENAME": "INFO",
            "NAME_COLLISION": "CANCEL",
            "REVIEW": "QUESTION",
            "UNPARSEABLE": "ERROR",
            "SEQUENCE_GAP": "ERROR",
        }
        status_labels = {
            "VALID": "Valid",
            "NEEDS_RENAME": "Needs rename",
            "NAME_COLLISION": "Collision",
            "REVIEW": "Review",
            "UNPARSEABLE": "Error",
            "SEQUENCE_GAP": "Gap",
        }
        status_key = status_value.split(":")[0] if status_value else "UNPARSEABLE"
        icon_key = icon_map.get(status_key, "BLANK1")
        status_text = status_labels.get(status_key, status_key.title())
        status_row = status_col.row(align=True)
        status_row.label(text=status_text, icon=icon_key)

        # Quality score
        quality_col = row_layout.column(align=True)
        quality_col.ui_units_x = 2.0
        quality_col.label(text=f"{quality_score:.2f}")

        # Proposed name (ALWAYS editable unless read_only)
        proposal_col = row_layout.column(align=True)
        proposal_col.ui_units_x = 7.0
        if read_only:
            proposal_row = proposal_col.row(align=True)
            proposal_row.label(text=proposed_name if proposed_name else "—")
            proposal_row.label(text="(Linked)", icon="INFO")
        else:
            if hasattr(row, "proposed_name"):
                proposal_col.prop(row, "proposed_name", text="")
            else:
                proposal_col.label(text=proposed_name if proposed_name else "—")

    def filter_items(self, context, data, propname):
        scene = context.scene
        state = getattr(scene, "lime_ai_mat", None)
        rows = getattr(data, propname, [])

        if not rows:
            return [], []

        view = getattr(state, "view_filter", "NEEDS") if state else "NEEDS"
        flags = [0] * len(rows)
        for i, row in enumerate(rows):
            if not row:
                continue
            status_value = (getattr(row, "status", "") or "").upper()
            if view == "ALL":
                visible = True
            elif view == "CORRECT":
                visible = status_value.startswith("VALID") or status_value.startswith("REVIEW")
            else:  # NEEDS
                visible = any(
                    status_value.startswith(prefix)
                    for prefix in ("NEEDS_RENAME", "NAME_COLLISION", "UNPARSEABLE", "SEQUENCE_GAP", "REVIEW")
                )
            flags[i] = self.bitflag_filter_item if visible else 0

        def sort_key(idx: int):
            row = rows[idx]
            if not row:
                return (5, 0.0, idx)

            status_value = (getattr(row, "status", "") or "").upper()
            quality_score = float(getattr(row, "quality_score", 0.0) or 0.0)
            material_name = getattr(row, "material_name", "") or ""

            if status_value.startswith(("NEEDS_RENAME", "NAME_COLLISION")):
                priority = 0
            elif status_value.startswith("REVIEW"):
                priority = 1
            elif status_value.startswith("UNPARSEABLE"):
                priority = 2
            else:
                priority = 3

            return (priority, -quality_score, material_name.lower(), idx)

        visible_indices = [i for i, flag in enumerate(flags) if flag]
        hidden_indices = [i for i, flag in enumerate(flags) if not flag]

        visible_indices.sort(key=sort_key)
        hidden_indices.sort()

        new_order = visible_indices + hidden_indices
        return flags, new_order


class LIME_TB_PT_ai_material_renamer(Panel):
    """Compact panel listing scan summary and entry point to the manager dialog."""

    bl_label = "AI Material Renamer"
    bl_idname = "LIME_TB_PT_ai_material_renamer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lime Toolbox"
    bl_order = 180

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        state = getattr(scene, "lime_ai_mat", None)

        col = layout.column(align=True)
        col.operator("lime_tb.open_ai_material_manager", text="Open AI Material Manager", icon="WINDOW")

        if not state or not state.rows:
            layout.label(text="No materials scanned", icon="INFO")
            return

        box = layout.box()
        total_rows = len(state.rows)
        box.label(text=f"Total: {total_rows}", icon="MATERIAL")

        rename_count = sum(1 for r in state.rows if getattr(r, "needs_rename", False))
        review_count = sum(1 for r in state.rows if getattr(r, "review_requested", False))
        valid_count = sum(1 for r in state.rows if (getattr(r, "status", "") or "").upper().startswith("VALID"))
        linked_count = sum(1 for r in state.rows if getattr(r, "read_only", False))
        
        status_text = f"Needs rename: {rename_count}  Valid: {valid_count}"
        if review_count > 0:
            status_text += f"  Review: {review_count}"
        box.label(text=status_text)
        
        # Show warning if there are linked materials
        if linked_count > 0:
            linked_box = layout.box()
            linked_box.alert = True
            linked_row = linked_box.row(align=True)
            linked_row.label(text=f"{linked_count} linked material(s) cannot be renamed", icon="LIBRARY_DATA_DIRECT")
            linked_row = linked_box.row(align=True)
            linked_row.label(text="Use 'Convert Linked Collection to Local' first", icon="INFO")

        # Quality distribution - simplified
        excellent = sum(1 for r in state.rows if getattr(r, "quality_label", "") == "excellent")
        good = sum(1 for r in state.rows if getattr(r, "quality_label", "") == "good")
        if excellent > 0 or good > 0:
            quality_text = f"Quality: {excellent}✓ excellent, {good} good"
            box.label(text=quality_text)

        if state.scene_context:
            box.label(text=f"Scene: {state.scene_context[:40]}", icon="INFO")


__all__ = [
    "LIME_TB_PT_ai_material_renamer",
    "LIME_TB_UL_ai_mat_rows",
]
