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
from .ui import LIME_PT_internal_setup
from .ui import LIME_PT_proposal_view
from .ui import LIME_PT_stage_setup
from .ops.ops_select_root import LIME_OT_pick_root
from .ops.ops_folders import LIME_OT_ensure_folders, LIME_OT_open_folder
from .ops.ops_create_file import LIME_OT_create_file
from .ops.ops_backup import LIME_OT_create_backup
from .ops.ops_tooltips import LIME_OT_show_text
from .ops.ops_shots import (
    LIME_OT_new_shot,
    LIME_OT_shot_instance,
    LIME_OT_duplicate_shot,
)
from .ops.ops_add_missing import (
    LIME_OT_add_missing_collections,
)
from .ops.ops_proposal_view import (
    LIME_OT_proposal_view_config,
    LIME_OT_take_pv_shot,
    LIME_OT_take_all_pv_shots,
    LIME_OT_add_camera_rig,
)
from .ops.ops_import_layout import (
    LIME_OT_import_layout,
)
from .ops.ops_stage import (
    LIME_OT_stage_main_light,
    LIME_OT_stage_aux_light,
)


classes = (
    LimePipelinePrefs,
    LIME_OT_pick_root,
    LIME_OT_ensure_folders,
    LIME_OT_open_folder,
    LIME_OT_create_file,
    LIME_OT_create_backup,
    LIME_OT_show_text,
    LIME_OT_proposal_view_config,
    LIME_OT_take_pv_shot,
    LIME_OT_take_all_pv_shots,
    LIME_OT_add_camera_rig,
    LIME_OT_import_layout,
    LIME_OT_stage_main_light,
    LIME_OT_stage_aux_light,
    LIME_PT_project_org,
    LIME_PT_internal_setup,
    LIME_PT_proposal_view,
    LIME_PT_stage_setup,
    LIME_OT_new_shot,
    LIME_OT_shot_instance,
    LIME_OT_duplicate_shot,
    LIME_OT_add_missing_collections,
)


def register():
    register_props()
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    unregister_props()


