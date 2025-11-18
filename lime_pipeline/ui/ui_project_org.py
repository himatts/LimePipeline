"""
UI to configure project naming (type, revision, scene) and saving helpers.

Purpose: Centralize project root selection, enforce naming invariants, preview filename,
and expose actions to create blend files, backups and folders.
Key classes: LIME_PT_project_org.
Depends on: lime_pipeline.core.validate and ops (save/create/folders).
Notes: UI-only; mirrors architecture invariants for quick validation.
"""

import bpy
from bpy.types import Panel


CAT = "Lime Pipeline"


class LIME_PT_project_org(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Project Organization"
    bl_idname = "LIME_PT_project_org"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 2

    def draw(self, ctx):
        wm = ctx.window_manager
        st = wm.lime_pipeline
        prefs = ctx.preferences.addons[__package__.split('.')[0]].preferences
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        box = layout.box()
        box.label(text="Project Settings")

        step_root = box.column(align=True)
        step_root.use_property_split = False
        root_row = step_root.row(align=True)
        root_row.prop(st, "project_root_display", text="")
        root_row.operator("lime.pick_root", text="", icon='FILE_FOLDER')

        box.separator()

        step_ident = box.column(align=True)
        grid = step_ident.grid_flow(columns=3, even_columns=True, even_rows=False, align=True)

        col_type = grid.column(align=True)
        col_type.alignment = 'CENTER'
        col_type_header = col_type.row()
        col_type_header.alignment = 'CENTER'
        col_type_header.label(text="Type")
        col_type.prop(st, "project_type", text="")

        letter_val = (getattr(st, 'rev_letter', '') or 'A').strip().upper()
        if not letter_val or not ('A' <= letter_val[0] <= 'Z'):
            letter_val = 'A'
        col_rev = grid.column(align=True)
        col_rev.alignment = 'CENTER'
        col_rev_header = col_rev.row()
        col_rev_header.alignment = 'CENTER'
        col_rev_header.label(text="Rev")
        rev_controls = col_rev.row(align=True)
        rev_controls.alignment = 'CENTER'
        rev_controls.operator("lime.rev_prev", text="", icon='TRIA_LEFT')
        letter_slot = rev_controls.row()
        letter_slot.alignment = 'CENTER'
        letter_slot.ui_units_x = 1.5
        letter_slot.label(text=letter_val[0])
        rev_controls.operator("lime.rev_next", text="", icon='TRIA_RIGHT')

        needs_sc = st.project_type not in {'BASE', 'TMP'}
        col_scene = grid.column(align=True)
        col_scene.alignment = 'CENTER'
        col_scene_header = col_scene.row()
        col_scene_header.alignment = 'CENTER'
        col_scene_header.label(text="Scene")
        scene_row = col_scene.row(align=True)
        scene_row.enabled = needs_sc
        scene_row.prop(st, "sc_number", text="")

        box.separator()

        step_toggles = box.column(align=True)
        step_toggles.use_property_split = False
        toggle_split = step_toggles.split(factor=0.5, align=True)
        toggle_split.alignment = 'CENTER'
        row_free = toggle_split.column(align=True)
        row_free.enabled = needs_sc
        row_free.prop(st, "free_scene_numbering", text="Free numbering", toggle=True)
        row_custom = toggle_split.column(align=True)
        row_custom.enabled = needs_sc
        row_custom.prop(st, "use_custom_name", text="Custom name", toggle=True)

        # Optional custom name field below
        custom_col = step_toggles.column(align=True)
        custom_col.enabled = st.use_custom_name
        custom_col.prop(st, "custom_name", text="")
        if st.use_custom_name:
            hint = custom_col.row()
            hint.alignment = 'CENTER'
            hint.label(text="Appends as suffix to the generated filename", icon='OUTLINER_OB_FONT')

        # Compute preview/status once
        from ..core.validate import validate_all
        ok, errors, warns, filename, target_path, backups = validate_all(st, prefs)
        duplicate_errors = []
        display_errors = []
        for msg in errors:
            if (
                msg.startswith("Target .blend")
                or ("already exists" in msg and msg.startswith("Scene SC"))
            ):
                duplicate_errors.append(msg)
            else:
                display_errors.append(msg)
        has_duplicate_only = bool(duplicate_errors) and not display_errors

        # File Preview box simplified: show only filename on a single row
        box_preview = layout.box()
        box_preview.label(text="File Preview")
        row_fn = box_preview.row(align=True)
        row_fn.alignment = 'LEFT'
        row_fn.alert = not filename
        preview_text = filename or "Filename pending"
        row_fn.label(text=preview_text, icon='FILE_BLEND')
        project_root = (getattr(st, "project_root", "") or "").strip()
        if target_path:
            try:
                from pathlib import Path
                parent = str(Path(target_path).parent)
            except Exception:
                parent = target_path
            row_path = box_preview.row(align=True)
            row_path.label(text=parent, icon='FILE_FOLDER')
        elif not project_root:
            row_hint = box_preview.row(align=True)
            row_hint.alert = True
            row_hint.label(text="Select a Project Root to finalize the destination path", icon='ERROR')

        # Status box (checks/warnings)
        box_status = layout.box()
        box_status.label(text="Status")
        status_row = box_status.row()
        status_row.alignment = 'CENTER'
        status_row.alert = not ok and not has_duplicate_only
        if ok:
            status_icon = 'CHECKMARK'
            status_text = "Ready to save"
        elif has_duplicate_only:
            status_icon = 'FILE_CACHE'
            status_text = "Current version already saved"
        else:
            status_icon = 'ERROR'
            status_text = "Needs attention"
        status_row.label(text=status_text, icon=status_icon)
        if has_duplicate_only:
            info_row = box_status.row(align=True)
            info_row.label(
                text="Target blend already exists; adjust revision/scene for a new file.",
                icon='INFO',
            )
        warn_count = len(warns)
        err_count = len(display_errors)
        if warn_count:
            warn_header = box_status.row(align=True)
            warn_header.label(text=f"{warn_count} warning(s)", icon='INFO')
            for w in warns:
                row = box_status.row(align=True)
                row.label(text="", icon='ERROR')
                op = row.operator("lime.show_text", text=w, emboss=False, icon='INFO')
                op.text = w
        if err_count:
            err_header = box_status.row(align=True)
            err_header.alert = True
            err_header.label(text=f"{err_count} blocking issue(s)", icon='CANCEL')
            for e in display_errors:
                row = box_status.row(align=True)
                row.alert = True
                row.label(text="", icon='CANCEL')
                op = row.operator("lime.show_text", text=e, emboss=False, icon='INFO')
                op.text = e

        box3 = layout.box()
        box3.label(text="Actions")
        primary_row = box3.row(align=True)
        blend_row = primary_row.row(align=True)
        blend_row.enabled = ok
        blend_row.operator("lime.create_file", text="Create .blend", icon='FILE_TICK')
        primary_row.operator("lime.create_backup", text="Create Backup", icon='DUPLICATE')
        secondary_row = box3.row(align=True)
        secondary_row.operator("lime.ensure_folders", text="Create Folders", icon='FILE_NEW')
        secondary_row.operator("lime.open_folder", text="Open Folder", icon='FILE_FOLDER')

        # Linked Collections section
        box_linked = layout.box()
        box_linked.label(text="Linked Collections")
        box_linked.operator("lime.localize_linked_collection", icon='LIBRARY_DATA_DIRECT')
