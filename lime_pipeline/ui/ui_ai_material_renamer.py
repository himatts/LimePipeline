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
        if not item or not hasattr(item, "material_name"):
            return

        row = item
        scene = context.scene
        state = getattr(scene, "lime_ai_mat", None)

        read_only = bool(getattr(row, "read_only", False))
        material_name = getattr(row, "material_name", "") or "<no name>"
        status_value = (getattr(row, "status", "") or "").upper()
        confidence = float(getattr(row, "confidence", 0.5) or 0.0)
        proposed_name = getattr(row, "proposed_name", "") or ""
        quality_label = (getattr(row, "quality_label", "") or "").title()
        quality_score = float(getattr(row, "quality_score", 0.0) or 0.0)
        review_requested = bool(getattr(row, "review_requested", False))
        force_reanalysis = bool(getattr(state, "force_reanalysis", False)) if state else False

        if force_reanalysis:
            actionable = not read_only
        else:
            actionable = (
                not read_only
                and (
                    status_value.startswith("NEEDS_RENAME")
                    or status_value.startswith("NAME_COLLISION")
                    or review_requested
                )
            )

        row_layout = layout.row(align=True)

        checkbox_col = row_layout.column(align=True)
        checkbox_col.scale_x = 1.0
        checkbox_col.enabled = not read_only
        if hasattr(row, "selected_for_apply"):
            checkbox_col.prop(row, "selected_for_apply", text="", emboss=True)
        else:
            checkbox_col.label(text="", icon="BLANK1")

        name_col = row_layout.column(align=True)
        name_col.scale_x = 2.8
        name_col.label(text=material_name)

        status_col = row_layout.column(align=True)
        status_col.scale_x = 1.3
        icon_map = {
            "VALID": "CHECKMARK",
            "NEEDS_RENAME": "INFO",
            "SEQUENCE_GAP": "ERROR",
            "NAME_COLLISION": "CANCEL",
            "UNPARSEABLE": "BLANK1",
            "REVIEW": "QUESTION",
        }
        status_key = status_value.split(":", 1)[0] if status_value else ""
        icon_key = icon_map.get(status_key, "BLANK1")
        status_text = status_value.replace("VALID:", "").replace("_", " ") if status_value else "—"
        status_col.label(text=status_text, icon=icon_key)

        quality_col = row_layout.column(align=True)
        quality_col.scale_x = 1.7
        quality_text = f"{quality_label or 'Unknown'} ({quality_score:.2f})"
        if review_requested:
            quality_col.label(text=quality_text, icon="OUTLINER_DATA_GP_LAYER")
        else:
            quality_col.label(text=quality_text)

        confidence_col = row_layout.column(align=True)
        confidence_col.scale_x = 1.1
        confidence_col.label(text=f"Conf: {confidence:.1f}")

        proposal_col = row_layout.column(align=True)
        proposal_col.scale_x = 2.6
        if actionable and hasattr(row, "proposed_name"):
            proposal_col.prop(row, "proposed_name", text="")
        else:
            proposal_col.label(text=proposed_name if proposed_name else "-")

        if not read_only and material_name != "<no name>":
            action_row = layout.row(align=True)
            action_row.scale_y = 1.0

            review_col = action_row.column(align=True)
            review_col.scale_x = 1.2
            op = review_col.operator(
                "lime_tb.ai_toggle_review",
                text="Review",
                depress=review_requested,
                emboss=True,
            )
            op.material_name = material_name

            normalize_col = action_row.column(align=True)
            normalize_col.scale_x = 1.3
            normalize_col.enabled = actionable
            op = normalize_col.operator("lime_tb.ai_normalize_to_closest", text="Normalize", emboss=True)
            op.material_name = material_name

            keep_col = action_row.column(align=True)
            keep_col.scale_x = 1.2
            keep_col.enabled = actionable
            op = keep_col.operator("lime_tb.ai_keep_proposal", text="Keep", emboss=True)
            op.material_name = material_name

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
        box.label(text=f"Materials: {total_rows}", icon="MATERIAL")

        rename_count = sum(1 for r in state.rows if getattr(r, "needs_rename", False))
        review_count = sum(1 for r in state.rows if getattr(r, "review_requested", False))
        box.label(text=f"Needs rename: {rename_count}  |  Review: {review_count}")

        excellent = sum(1 for r in state.rows if getattr(r, "quality_label", "") == "excellent")
        good = sum(1 for r in state.rows if getattr(r, "quality_label", "") == "good")
        box.label(text=f"Quality: {excellent} excellent, {good} good")

        if state.scene_context:
            box.label(text=f"Context: {state.scene_context[:48]}...", icon="INFO")


__all__ = [
    "LIME_TB_PT_ai_material_renamer",
    "LIME_TB_UL_ai_mat_rows",
]
