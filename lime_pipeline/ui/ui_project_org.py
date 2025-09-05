import bpy
from bpy.types import Panel


CAT = "Lime Pipeline"


class LIME_PT_project_org(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Project Organization"
    bl_idname = "LIME_PT_project_org"
    bl_order = 0

    def draw(self, ctx):
        wm = ctx.window_manager
        st = wm.lime_pipeline
        prefs = ctx.preferences.addons[__package__.split('.')[0]].preferences
        layout = self.layout

        box = layout.box()
        box.label(text="Project Settings")

        row = box.row(align=True)
        row.prop(st, "project_root", text="Project Root")

        box.prop(st, "project_type", text="Project Type")
        box.prop(st, "rev_letter", text="Revision (A–Z)")

        needs_sc = st.project_type not in {'BASE', 'TMP'}
        row = box.row(align=True)
        row.enabled = needs_sc
        row.prop(st, "sc_number", text="Scene #")
        row.prop(st, "free_scene_numbering", text="Free numbering", toggle=True)

        row = box.row(align=True)
        row.prop(st, "use_custom_name", text="Custom Project Name", toggle=True)
        sub = row.row(align=True)
        sub.enabled = st.use_custom_name
        sub.prop(st, "custom_name", text="Name")

        box2 = layout.box()
        box2.label(text="Status & Preview")
        from ..core.validate import validate_all
        ok, errors, warns, filename, target_path, backups = validate_all(st, prefs)
        icon = 'CHECKMARK' if ok else 'ERROR'
        box2.label(text=("Ready to save" if ok else "Not ready"), icon=icon)
        if not ok:
            for e in errors:
                row = box2.row(align=True)
                row.alignment = 'LEFT'
                row.label(text="", icon='CANCEL')
                op = row.operator("lime.show_text", text=e, emboss=False)
                op.text = e
        for w in warns:
            row = box2.row(align=True)
            row.alignment = 'LEFT'
            row.label(text="", icon='ERROR')
            op = row.operator("lime.show_text", text=w, emboss=False)
            op.text = w

        split = box2.split(factor=0.22, align=True)
        split.label(text="Final Path:")
        right = split.row(align=True)
        right.alignment = 'LEFT'
        right.label(text=(str(target_path) if target_path else ""))
        op = right.operator("lime.show_text", text="", icon='COPYDOWN', emboss=False)
        op.text = str(target_path) if target_path else ""

        split = box2.split(factor=0.22, align=True)
        split.label(text="Filename:")
        right = split.row(align=True)
        right.alignment = 'LEFT'
        right.label(text=(filename or ""))
        op = right.operator("lime.show_text", text="", icon='COPYDOWN', emboss=False)
        op.text = filename or ""

        box3 = layout.box()
        box3.label(text="Actions")
        row = box3.row()
        row.enabled = ok
        row.operator("lime.create_file", text="Create file", icon='FILE_TICK')
        row = box3.row(align=True)
        row.operator("lime.create_backup", text="Create Backup", icon='DUPLICATE')
        row = box3.row(align=True)
        row.operator("lime.ensure_folders", text="Create missing folders", icon='FILE_NEW')
        row.operator("lime.open_folder", text="Open target folder", icon='FILE_FOLDER')


