"""
UI utilities for scene dimension checking and measurement unit presets.

Purpose: Display a dimension checker operator and quick buttons to apply standard
measurement units (MM/CM/M/IN/FT) to the current scene.
Key classes: LIME_PT_dimension_utilities, LIME_OT_set_unit_preset.
Depends on: Blender unit settings; optional addon preferences.
Notes: UI-only; unit changes are applied through a lightweight operator.

NOTE(known-issue): Dimension Checker live scaling (parented helper) can be visually
incorrect during interactive scaling without applying transforms. Do not attempt to
address that issue unless explicitly requested; confirm scope first.
"""

import bpy
from bpy.types import Panel, Operator
from bpy.props import EnumProperty

CAT = "Lime Toolbox"
ADDON_PKG = __package__.split('.')[0]

_UNIT_PRESET_ITEMS = [
    ('MM', "Millimeters", "Set scene units to millimeters."),
    ('CM', "Centimeters", "Set scene units to centimeters."),
    ('M', "Meters", "Set scene units to meters."),
    ('IN', "Inches", "Set scene units to inches."),
    ('FT', "Feet", "Set scene units to feet."),
]

_UNIT_PRESET_LABELS = {
    'MM': "mm",
    'CM': "cm",
    'M': "m",
    'IN': "in",
    'FT': "ft",
}

_UNIT_PRESET_SETTINGS = {
    'MM': ('METRIC', 'MILLIMETERS'),
    'CM': ('METRIC', 'CENTIMETERS'),
    'M': ('METRIC', 'METERS'),
    'IN': ('IMPERIAL', 'INCHES'),
    'FT': ('IMPERIAL', 'FEET'),
}

_SCENE_UNIT_TO_PRESET = {value: key for key, value in _UNIT_PRESET_SETTINGS.items()}

_LENGTH_UNIT_DISPLAY = {
    'MILLIMETERS': "Millimeters (mm)",
    'CENTIMETERS': "Centimeters (cm)",
    'METERS': "Meters (m)",
    'INCHES': "Inches (in)",
    'FEET': "Feet (ft)",
}


def _set_scene_units(context, *, system: str, length_unit: str) -> bool:
    scene = getattr(context, "scene", None)
    if scene is None:
        return False
    settings = scene.unit_settings
    settings.system = system
    try:
        settings.length_unit = length_unit
    except Exception:
        pass
    return True


def _format_current_units(scene: bpy.types.Scene | None) -> str | None:
    if scene is None:
        return None
    settings = getattr(scene, "unit_settings", None)
    if settings is None:
        return None
    length_unit = getattr(settings, "length_unit", None)
    if not length_unit:
        return None
    label = _LENGTH_UNIT_DISPLAY.get(length_unit)
    if label is None:
        clean = length_unit.replace('_', ' ').title()
        label = f"{clean}"
    system = getattr(settings, "system", "") or ""
    if system:
        return f"{label} / {system.title()}"
    return label


class LIME_OT_set_unit_preset(Operator):
    """Apply a measurement unit preset to the active scene."""

    bl_idname = "lime.set_unit_preset"
    bl_label = "Set Unit Preset"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Apply a measurement unit preset to the current scene."

    preset: EnumProperty(
        name="Preset",
        description="Measurement unit preset to apply.",
        items=_UNIT_PRESET_ITEMS,
        default='MM',
    )

    def execute(self, context):
        target = str(self.preset)
        mapping = _UNIT_PRESET_SETTINGS.get(target)
        if mapping is None:
            self.report({'ERROR'}, "Unknown unit preset.")
            return {'CANCELLED'}
        if not _set_scene_units(context, system=mapping[0], length_unit=mapping[1]):
            self.report({'ERROR'}, "Unable to update scene units.")
            return {'CANCELLED'}
        state = getattr(context.window_manager, "lime_pipeline", None)
        if state is not None:
            try:
                state.dimension_units_preset = target
            except Exception:
                pass
        label = _UNIT_PRESET_LABELS.get(target, target.lower())
        self.report({'INFO'}, f"Scene units set to {label}.")
        return {'FINISHED'}


class LIME_PT_dimension_utilities(Panel):
    """Panel with dimension checker and measurement unit controls."""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Dimension Utilities"
    bl_idname = "LIME_PT_dimension_utilities"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 1

    @classmethod
    def poll(cls, ctx):
        try:
            addon = ctx.preferences.addons.get(ADDON_PKG)
            if addon is None:
                return True
            return getattr(addon.preferences, "enable_dimension_utilities", True)
        except Exception:
            return True

    def draw(self, ctx):
        layout = self.layout
        wm = ctx.window_manager
        state = getattr(wm, "lime_pipeline", None)

        dim_box = layout.box()
        dim_box.label(text="Dimension Checker")
        if state is not None:
            dim_box.prop(state, "dimension_orientation_mode", text="Orientation Mode")
            lock_row = dim_box.row()
            lock_row.enabled = state.dimension_orientation_mode == 'PCA3D'
            lock_row.prop(state, "dimension_lock_z_up", text="Lock Z-Up")
        op = dim_box.operator("lime.dimension_envelope", text="Dimension Checker", icon='MESH_CUBE')
        if state is not None:
            op.orientation_mode = state.dimension_orientation_mode
            op.lock_z_up = state.dimension_lock_z_up
        dim_box.label(text="Each run creates a new helper; delete manually.", icon='INFO')

        overlay_box = layout.box()
        overlay_box.label(text="Dimension Checker Units")
        if state is not None:
            metric_row = overlay_box.row(align=True)
            metric_row.prop(state, "dimension_show_mm", text="mm", toggle=True)
            metric_row.prop(state, "dimension_show_cm", text="cm", toggle=True)
            metric_row.prop(state, "dimension_show_m", text="m", toggle=True)
            imperial_row = overlay_box.row(align=True)
            imperial_row.prop(state, "dimension_show_in", text="in", toggle=True)
            imperial_row.prop(state, "dimension_show_ft", text="ft", toggle=True)
        overlay_box.label(text="These affect the overlay only.", icon='INFO')

        units_box = layout.box()
        units_box.label(text="Scene Measurement Units")
        scene = getattr(ctx, "scene", None)
        current = _format_current_units(scene)
        if current:
            units_box.label(text=f"Current: {current}")

        settings = None
        active_preset = None
        if scene is not None:
            settings = scene.unit_settings
            active_preset = _SCENE_UNIT_TO_PRESET.get((settings.system, settings.length_unit))
        if active_preset is None and state is not None:
            active_preset = getattr(state, "dimension_units_preset", None)

        metric_row = units_box.row(align=True)
        for key in ('MM', 'CM', 'M'):
            button = metric_row.operator("lime.set_unit_preset", text=_UNIT_PRESET_LABELS[key], depress=(active_preset == key))
            button.preset = key

        imperial_row = units_box.row(align=True)
        for key in ('IN', 'FT'):
            button = imperial_row.operator("lime.set_unit_preset", text=_UNIT_PRESET_LABELS[key], depress=(active_preset == key))
            button.preset = key

        if settings is not None:
            advanced = units_box.column(align=True)
            advanced.use_property_split = True
            advanced.prop(settings, "system", text="System")
            advanced.prop(settings, "length_unit", text="Length")
        layout.separator()
        placeholder = layout.box()
        placeholder.label(text="Reserved for upcoming dimension utilities.", icon='INFO')

__all__ = [
    "LIME_OT_set_unit_preset",
    "LIME_PT_dimension_utilities",
]
