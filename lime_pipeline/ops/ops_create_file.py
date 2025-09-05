import bpy
from bpy.types import Operator


class LIME_OT_create_file(Operator):
    bl_idname = "lime.create_file"
    bl_label = "Create file (first save)"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "First save: creates the .blend at the computed Final Path"

    def execute(self, context):
        st = context.window_manager.lime_pipeline
        prefs = context.preferences.addons[__package__.split('.')[0]].preferences
        from ..core.validate import validate_all

        ok, errors, warns, filename, target_path, backups = validate_all(st, prefs)
        if not ok or not target_path:
            for e in errors:
                self.report({'ERROR'}, e)
            return {'CANCELLED'}

        target_path.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(target_path))
        self.report({'INFO'}, f"Saved: {target_path}")
        return {'FINISHED'}


