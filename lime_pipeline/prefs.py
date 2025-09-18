import bpy
from bpy.types import AddonPreferences
from bpy.props import StringProperty, IntProperty, BoolProperty


ADDON_PKG = __package__


class LimePipelinePrefs(AddonPreferences):
    bl_idname = ADDON_PKG

    default_projects_root: StringProperty(
        name="Default Projects Root",
        subtype='DIR_PATH',
        default=r"G:\\Unidades compartidas\\2. EX-Projects",
        description="Production projects root used in the studio",
    )
    dev_test_root: StringProperty(
        name="Dev/Test Root",
        subtype='DIR_PATH',
        default=r"D:\\Lime Testing",
        description="Local path used as initial directory for folder picker",
    )
    scene_step: IntProperty(
        name="Scene Step",
        default=10,
        min=1,
        max=100,
        description="Step used when suggesting scene numbers (multiples)",
    )
    path_warn_len: IntProperty(name="Warn at length", default=200, min=50, max=400, description="Show a warning when target path exceeds this length")
    path_block_len: IntProperty(name="Block at length", default=240, min=60, max=400, description="Block saving when target path exceeds this length")
    remember_last_rev: BoolProperty(name="Remember last Rev", default=True, description="Remember last used revision letter across sessions")
    libraries_override_dir: StringProperty(
        name="Libraries Override",
        subtype='DIR_PATH',
        default="",
        description=(
            "Optional: override path for Lime library .blend files. "
            "If set, 'lime_pipeline_lib.blend' is read from here"
        ),
    )
    enable_dimension_utilities: BoolProperty(
        name="Enable Dimension Utilities",
        description="Toggle the Dimension Utilities panel (Dimension Checker and measurement presets).",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "default_projects_root")
        col.prop(self, "dev_test_root")
        col.separator()
        col.prop(self, "scene_step")
        col.prop(self, "path_warn_len")
        col.prop(self, "path_block_len")
        col.prop(self, "remember_last_rev")
        col.prop(self, "enable_dimension_utilities")
        col.separator()
        col.prop(self, "libraries_override_dir")


