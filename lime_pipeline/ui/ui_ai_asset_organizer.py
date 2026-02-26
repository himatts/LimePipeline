"""UI panel for AI-assisted asset naming in Lime Toolbox."""

from __future__ import annotations

import re

from bpy.types import Panel, UIList


_SHOT_ROOT_RE = re.compile(r"^SHOT \d{2,3}$")
_SHOT_CHILD_RE = re.compile(r"^SH\d{2,3}_")


class LIME_TB_UL_ai_asset_items(UIList):
    bl_idname = "LIME_TB_UL_ai_asset_items"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if not item:
            return

        row_layout = layout.row(align=True)
        row_layout.use_property_split = False
        row_layout.use_property_decorate = False

        read_only = bool(getattr(item, "read_only", False))
        item_type = (getattr(item, "item_type", "OBJECT") or "OBJECT").upper()
        status = (getattr(item, "status", "") or "").upper()
        target_status = (getattr(item, "target_status", "") or "NONE").upper()
        target_path = (getattr(item, "target_collection_path", "") or "").strip()

        if item_type == "OBJECT":
            type_icon = "OBJECT_DATA"
        elif item_type == "COLLECTION":
            type_icon = "OUTLINER_COLLECTION"
        elif item_type == "PLANNED_COLLECTION":
            type_icon = "NEWFOLDER"
        else:
            type_icon = "MATERIAL"
        if read_only:
            type_icon = "LIBRARY_DATA_DIRECT"

        status_icon = "BLANK1"
        if status == "INVALID":
            status_icon = "ERROR"
        elif status == "AI_EXACT":
            status_icon = "CHECKMARK"
        elif status.startswith("NORMALIZED"):
            status_icon = "FILE_REFRESH"
        elif status == "PLANNED_CREATE":
            status_icon = "ADD"

        checkbox_col = row_layout.column(align=True)
        checkbox_col.ui_units_x = 1.0
        checkbox_col.enabled = not read_only
        checkbox_col.prop(item, "selected_for_apply", text="")

        name_col = row_layout.column(align=True)
        name_col.ui_units_x = 6.0
        name_col.label(text=getattr(item, "original_name", "") or "<no name>", icon=type_icon)

        status_col = row_layout.column(align=True)
        status_col.ui_units_x = 1.0
        status_col.label(text="", icon=status_icon)

        proposal_col = row_layout.column(align=True)
        proposal_col.ui_units_x = 8.0
        if read_only:
            proposal_col.label(text=getattr(item, "suggested_name", "") or "-")
        else:
            proposal_col.prop(item, "suggested_name", text="")

        target_col = row_layout.column(align=True)
        target_col.ui_units_x = 12.0
        if item_type == "OBJECT":
            target_icon = "BLANK1"
            if target_status == "AUTO":
                target_icon = "OUTLINER_COLLECTION"
            elif target_status == "CONFIRMED":
                target_icon = "CHECKMARK"
            elif target_status == "AMBIGUOUS":
                target_icon = "QUESTION"
            elif target_status == "SKIPPED":
                target_icon = "ERROR"
            target_col.label(text=target_path or "-", icon=target_icon)
        elif item_type == "PLANNED_COLLECTION":
            target_col.label(text="Will be created", icon="ADD")
        else:
            target_col.label(text="-")

        action_col = row_layout.column(align=True)
        action_col.ui_units_x = 2.6
        if item_type == "OBJECT":
            action_row = action_col.row(align=True)
            op = action_row.operator("lime_tb.ai_asset_set_target_for_item", text="", icon="OUTLINER_COLLECTION")
            op.item_id = getattr(item, "item_id", "")
            if target_status in {"AMBIGUOUS", "SKIPPED"}:
                op = action_row.operator("lime_tb.ai_asset_resolve_target", text="", icon="QUESTION")
                op.item_id = getattr(item, "item_id", "")
        else:
            action_col.label(text="", icon="BLANK1")


class LIME_TB_PT_ai_asset_organizer(Panel):
    bl_label = "AI Asset Organizer"
    bl_idname = "LIME_TB_PT_ai_asset_organizer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lime Toolbox"
    bl_order = 175

    def draw(self, context):
        draw_ai_asset_organizer_content(self.layout, context, for_popup=False)


def draw_ai_asset_organizer_content(layout, context, *, for_popup: bool = False) -> None:
    scene = context.scene
    state = getattr(scene, "lime_ai_assets", None)
    if state is None:
        layout.label(text="AI state unavailable", icon="ERROR")
    else:
        selected_objects = list(getattr(context, "selected_objects", None) or [])
        selected_mats = set()
        selected_cols = set()
        scene_root = getattr(scene, "collection", None)
        for obj in selected_objects:
            for slot in getattr(obj, "material_slots", []) or []:
                mat = getattr(slot, "material", None)
                if mat is not None:
                    selected_mats.add(mat)
            for coll in list(getattr(obj, "users_collection", []) or []):
                if coll is None:
                    continue
                if scene_root is not None and coll == scene_root:
                    continue
                name = getattr(coll, "name", "") or ""
                if _SHOT_ROOT_RE.match(name) or _SHOT_CHILD_RE.match(name):
                    continue
                selected_cols.add(coll)

        summary = f"Selection: {len(selected_objects)} object(s), {len(selected_mats)} material(s)"
        if getattr(state, "include_collections", True):
            summary += f", {len(selected_cols)} collection(s)"
        layout.label(text=summary, icon="RESTRICT_SELECT_OFF")

        if not for_popup:
            open_row = layout.row(align=True)
            open_row.operator("lime_tb.open_ai_asset_manager", text="Open in Window", icon="WINDOW")

        context_box = layout.box()
        context_box.label(text="Context", icon="TEXT")
        context_box.prop(state, "context", text="")
        context_actions = context_box.row(align=True)
        try:
            maxlen = int(type(state).bl_rna.properties["context"].length_max)
        except Exception:
            maxlen = 0
        current_len = len(getattr(state, "context", "") or "")
        if maxlen > 0:
            context_actions.label(text=f"{current_len}/{maxlen}")
        else:
            context_actions.label(text=f"{current_len} chars")
        layout.prop(state, "use_image_context", text="Use Image Context")
        if getattr(state, "use_image_context", False):
            layout.prop(state, "image_path", text="Image")
        layout.prop(state, "include_collections", text="Include Collections")
        layout.prop(state, "use_active_collections_only", text="Use Active Collections Only")
        layout.prop(state, "organize_collections", text="Organize Collections on Apply")
        layout.label(text="Note: names and context are sent to OpenRouter.", icon="INFO")

        if getattr(state, "last_error", ""):
            box = layout.box()
            box.alert = True
            box.label(text=str(state.last_error), icon="ERROR")

        if getattr(state, "is_busy", False):
            layout.label(text="Working...", icon="TIME")

        row = layout.row(align=True)
        row.enabled = not getattr(state, "is_busy", False)
        row.operator("lime_tb.ai_asset_suggest_names", text="Suggest Names (AI)", icon="FILE_REFRESH")
        row.operator("lime_tb.ai_asset_clear", text="Clear", icon="TRASH")

        scope_box = layout.box()
        scope_box.label(text="Apply Scope", icon="FILTER")
        scope_toggles = scope_box.row(align=True)
        scope_toggles.prop(state, "apply_scope_objects", text="Objects", toggle=True)
        scope_toggles.prop(state, "apply_scope_materials", text="Materials", toggle=True)
        scope_toggles.prop(state, "apply_scope_collections", text="Collections", toggle=True)

        apply_row = layout.row()
        apply_row.scale_y = 1.25
        apply_row.enabled = bool(getattr(state, "items", None)) and not getattr(state, "is_busy", False)
        apply_row.operator("lime_tb.ai_asset_apply_names", text="Apply Selected", icon="CHECKMARK")

        if getattr(state, "items", None):
            fallback_count = sum(
                1
                for row in list(getattr(state, "items", []) or [])
                if getattr(row, "item_type", "") == "OBJECT"
                and (getattr(row, "status", "") or "").upper() == "NORMALIZED_FALLBACK"
            )
            preview_box = layout.box()
            preview_box.label(
                text=(
                    f"Will rename {getattr(state, 'planned_renames_objects', 0)} objects, "
                    f"{getattr(state, 'planned_renames_materials', 0)} materials, "
                    f"{getattr(state, 'planned_renames_collections', 0)} collections"
                ),
                icon="INFO",
            )
            preview_box.label(
                text=(
                    f"Will create {getattr(state, 'planned_collections_created', 0)} collections, "
                    f"move {getattr(state, 'planned_objects_moved', 0)} objects, "
                    f"skip {getattr(state, 'planned_objects_skipped_ambiguous', 0)} ambiguous"
                ),
                icon="OUTLINER_COLLECTION",
            )
            preview_box.label(
                text=(
                    f"Will relink {getattr(state, 'planned_material_relinks', 0)} materials, "
                    f"remove up to {getattr(state, 'planned_material_orphans_removed', 0)} orphan(s)"
                ),
                icon="MATERIAL",
            )
            if fallback_count > 0:
                preview_box.label(
                    text=f"Neutral fallback object names: {fallback_count}",
                    icon="INFO",
                )
            ambiguous_count = int(getattr(state, "planned_ambiguities_objects", 0) or 0)
            if ambiguous_count > 0:
                amb_box = layout.box()
                amb_box.alert = True
                amb_box.label(
                    text=f"{ambiguous_count} object(s) require target confirmation",
                    icon="ERROR",
                )
            layout.separator()
            layout.template_list(
                "LIME_TB_UL_ai_asset_items",
                "",
                state,
                "items",
                state,
                "active_index",
                rows=12 if for_popup else 6,
            )

    if for_popup:
        return

    layout.label(text="Texture tools moved to AI Textures Organizer panel.", icon="INFO")


__all__ = [
    "draw_ai_asset_organizer_content",
    "LIME_TB_PT_ai_asset_organizer",
    "LIME_TB_UL_ai_asset_items",
]
