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

        box = layout.box()
        box.label(text="Project Settings")

        row = box.row(align=True)
        # Show only project folder name; still stores full path underneath
        row.prop(st, "project_root_display", text="Project Root")
        pick = row.operator("lime.pick_root", text="", icon='FILE_FOLDER')

        # Vertical layout: Type, Rev (letters), Scene; labels left-aligned
        row = box.row(align=True)
        col_left = row.column(align=True)
        col_right = row.column(align=True)

        # Labels
        col_left.label(text="Type")
        col_left.label(text="Rev")
        col_left.label(text="Scene")

        # Controls
        col_right.prop(st, "project_type", text="")
        rev_row = col_right.row(align=True)
        # Show letter read-only with prev/next arrows
        letter_val = (getattr(st, 'rev_letter', '') or 'A').strip().upper()
        if not letter_val or not ('A' <= letter_val[0] <= 'Z'):
            letter_val = 'A'
        rev_row.label(text=letter_val[0])
        op_prev = rev_row.operator("lime.rev_prev", text="", icon='TRIA_LEFT')
        op_next = rev_row.operator("lime.rev_next", text="", icon='TRIA_RIGHT')

        needs_sc = st.project_type not in {'BASE', 'TMP'}
        sc_row = col_right.row(align=True)
        sc_row.enabled = needs_sc
        sc_row.prop(st, "sc_number", text="")

        # Toggles on same row with shorter labels
        row_toggle = box.row(align=True)
        row_toggle.enabled = needs_sc
        row_toggle.prop(st, "free_scene_numbering", text="Free numbering", toggle=True)
        row_toggle.prop(st, "use_custom_name", text="Custom name", toggle=True)

        # Optional custom name field below
        sub = box.row(align=True)
        sub.enabled = st.use_custom_name
        sub.prop(st, "custom_name", text="Name")

        # Compute preview/status once
        from ..core.validate import validate_all
        ok, errors, warns, filename, target_path, backups = validate_all(st, prefs)

        # File Preview box simplified: show only filename on a single row
        box_preview = layout.box()
        box_preview.label(text="File Preview")
        row_fn = box_preview.row(align=True)
        row_fn.alignment = 'LEFT'
        row_fn.label(text=(filename or ""))

        # Status box (checks/warnings)
        box_status = layout.box()
        box_status.label(text="Status")
        icon = 'CHECKMARK' if ok else 'ERROR'
        box_status.label(text=("Ready to save" if ok else "Not ready"), icon=icon)
        if not ok:
            for e in errors:
                row = box_status.row(align=True)
                row.alignment = 'LEFT'
                row.label(text="", icon='CANCEL')
                op = row.operator("lime.show_text", text=e, emboss=False)
                op.text = e
        for w in warns:
            row = box_status.row(align=True)
            row.alignment = 'LEFT'
            row.label(text="", icon='ERROR')
            op = row.operator("lime.show_text", text=w, emboss=False)
            op.text = w

        box3 = layout.box()
        box3.label(text="Actions")
        row = box3.row()
        row.enabled = ok
        row.operator("lime.create_file", text="Create .blend", icon='FILE_TICK')
        row = box3.row(align=True)
        row.operator("lime.create_backup", text="Create Backup", icon='DUPLICATE')
        row = box3.row(align=True)
        row.operator("lime.ensure_folders", text="Create Folders", icon='FILE_NEW')
        row.operator("lime.open_folder", text="Open Folder", icon='FILE_FOLDER')

