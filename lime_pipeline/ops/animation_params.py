import bpy
from bpy.types import Operator


class LIME_TB_OT_apply_keyframe_style(Operator):
    bl_idname = "lime.tb_apply_keyframe_style"
    bl_label = "Apply Style to Selected Keyframes"
    bl_description = (
        "Apply the current Lime Animation Parameters (Interpolation & Easing) "
        "to selected keyframes in the active/selected objects."
    )

    def execute(self, context):
        scene = context.scene
        if scene is None:
            return {'CANCELLED'}
        interp = getattr(scene, "lime_anim_interpolation", 'BEZIER')
        easing = getattr(scene, "lime_anim_easing", 'AUTO')

        easing_supported = {
            'SINE', 'QUAD', 'CUBIC', 'QUART', 'QUINT', 'EXPO', 'CIRC', 'BACK', 'BOUNCE', 'ELASTIC'
        }
        supports_easing = interp in easing_supported

        def apply_to_action(act: bpy.types.Action) -> int:
            changed_points = 0
            if act is None:
                return 0
            for fc in getattr(act, "fcurves", []) or []:
                kfs = getattr(fc, "keyframe_points", None)
                if not kfs:
                    continue
                curve_changed = False
                for kp in kfs:
                    try:
                        if getattr(kp, "select_control_point", False):
                            if kp.interpolation != interp:
                                kp.interpolation = interp
                                curve_changed = True
                                changed_points += 1
                            if hasattr(kp, "easing"):
                                if supports_easing:
                                    if kp.easing != easing:
                                        kp.easing = easing
                                        curve_changed = True
                                else:
                                    # Keep AUTO when easing doesn't apply
                                    if kp.easing != 'AUTO':
                                        kp.easing = 'AUTO'
                                        curve_changed = True
                    except Exception:
                        pass
                if curve_changed:
                    try:
                        fc.update()
                    except Exception:
                        pass
            return changed_points

        total_changed = 0
        # Operate on active + selected objects (unique set)
        objs = set(context.selected_objects or [])
        if context.active_object is not None:
            objs.add(context.active_object)
        if not objs:
            # Fallback: try active object from context if selection empty
            if context.active_object is not None:
                objs = {context.active_object}
        for obj in objs:
            ad = getattr(obj, "animation_data", None)
            if ad is None:
                continue
            total_changed += apply_to_action(getattr(ad, "action", None))

        self.report({'INFO'}, f"Keyframes styled: {total_changed}")
        return {'FINISHED'}


__all__ = [
    "LIME_TB_OT_apply_keyframe_style",
]