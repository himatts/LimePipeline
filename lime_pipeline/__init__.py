bl_info = {
    "name": "Lime Pipeline",
    "author": "Lime",
    "version": (0, 1, 0),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar (N) > Lime Pipeline",
    "description": "Project organization, naming, and first save/backup helpers",
    "category": "System",
}

import bpy

# Registration is centralized here to keep imports stable for future growth
from .prefs import LimePipelinePrefs
from .props import register as register_props, unregister as unregister_props
from .ui import LIME_PT_project_org
from .ops_select_root import LIME_OT_pick_root
from .ops_folders import LIME_OT_ensure_folders, LIME_OT_open_folder
from .ops_create_file import LIME_OT_create_file
from .ops_backup import LIME_OT_create_backup
from .ops_tooltips import LIME_OT_show_text


classes = (
    LimePipelinePrefs,
    LIME_OT_pick_root,
    LIME_OT_ensure_folders,
    LIME_OT_open_folder,
    LIME_OT_create_file,
    LIME_OT_create_backup,
    LIME_OT_show_text,
    LIME_PT_project_org,
)


def register():
    register_props()
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    unregister_props()


