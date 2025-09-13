import bpy
from bpy.types import Operator
from bpy.props import IntProperty, StringProperty


class LIME_OT_apply_preset_placeholder(Operator):
    bl_idname = "lime.apply_preset_placeholder"
    bl_label = "Preset"
    bl_description = "Placeholder de preset simplificado"

    preset_index: IntProperty(name="Preset", default=1, min=1, max=5)
    tooltip: StringProperty(name="Tooltip", default="")

    @classmethod
    def description(cls, context, properties):
        try:
            idx = int(getattr(properties, 'preset_index', 1))
        except Exception:
            idx = 1
        return f"Preset {idx}"

    def invoke(self, context, event):
        # Solo mostrar un tooltip informativo por ahora
        self.report({'INFO'}, f"Preset {self.preset_index} (placeholder)")
        return {'FINISHED'}


__all__ = [
    "LIME_OT_apply_preset_placeholder",
]


