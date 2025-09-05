import re
import shutil
from pathlib import Path

import bpy
from bpy.types import Operator


RE_BACKUP = re.compile(r"^Backup_(\d{2})_")


def next_backup_index(backups_dir: Path, base_filename: str) -> int:
    max_idx = 0
    if backups_dir.is_dir():
        for p in backups_dir.glob(f"Backup_*_{base_filename}"):
            m = RE_BACKUP.match(p.name)
            if m:
                max_idx = max(max_idx, int(m.group(1)))
    return max_idx + 1


class LIME_OT_create_backup(Operator):
    bl_idname = "lime.create_backup"
    bl_label = "Create Backup"
    bl_description = "Create a numbered backup (Backup_XX_) in the backups folder"

    def execute(self, context):
        st = context.window_manager.lime_pipeline
        prefs = context.preferences.addons[__package__.split('.')[0]].preferences
        from ..core.validate import validate_all

        ok, errors, warns, filename, target_path, backups = validate_all(st, prefs)
        if not target_path or not target_path.exists():
            self.report({'ERROR'}, "Base file does not exist yet")
            return {'CANCELLED'}

        backups.mkdir(parents=True, exist_ok=True)
        idx = next_backup_index(backups, filename)
        backup_name = f"Backup_{idx:02d}_{filename}"
        backup_path = backups / backup_name

        bpy.ops.wm.save_mainfile()
        shutil.copy2(target_path, backup_path)
        self.report({'INFO'}, f"Backup created: {backup_path.name}")
        return {'FINISHED'}


