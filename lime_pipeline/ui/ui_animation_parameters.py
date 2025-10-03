import bpy
from bpy.types import Panel, UIList, PropertyGroup
from bpy.props import (
    BoolProperty,
    EnumProperty,
    StringProperty,
    IntProperty,
    FloatProperty,
    FloatVectorProperty,
    CollectionProperty,
    PointerProperty,
)


CAT = "Lime Toolbox"


# Internal state for handler management
_ANIM_HANDLER = None


def _supports_easing(interp: str) -> bool:
    easing_types = {
        'SINE', 'QUAD', 'CUBIC', 'QUART', 'QUINT', 'EXPO', 'CIRC', 'BACK', 'BOUNCE', 'ELASTIC'
    }
    return interp in easing_types


def _apply_to_keyframes_at_frame(scene: bpy.types.Scene, frame: float) -> None:
    try:
        if scene is None:
            return
        if not getattr(scene, "lime_anim_enabled", False):
            return
        interp = getattr(scene, "lime_anim_interpolation", 'BEZIER')
        easing = getattr(scene, "lime_anim_easing", 'AUTO')

        # If using only Blender's native defaults (CONSTANT/LINEAR/BEZIER) and no special easing,
        # preferences already handle it. Only post-process when we have extended types or explicit easing.
        needs_post = _supports_easing(interp) or easing != 'AUTO'
        if not needs_post:
            return

        obj = bpy.context.active_object
        if obj is None:
            return
        ad = getattr(obj, "animation_data", None)
        if ad is None:
            return
        act = getattr(ad, "action", None)
        if act is None:
            return
        for fc in getattr(act, "fcurves", []) or []:
            kfs = getattr(fc, "keyframe_points", None)
            if not kfs:
                continue
            changed = False
            for kp in kfs:
                try:
                    if abs(kp.co.x - frame) < 1e-6:
                        # Apply interpolation
                        if kp.interpolation != interp:
                            kp.interpolation = interp
                            changed = True
                        # Apply easing only if supported by this interpolation
                        if hasattr(kp, "easing"):
                            if _supports_easing(interp):
                                if kp.easing != easing:
                                    kp.easing = easing
                                    changed = True
                            else:
                                # Ensure easing is AUTO when not applicable
                                if kp.easing != 'AUTO':
                                    kp.easing = 'AUTO'
                                    changed = True
                except Exception:
                    # Be tolerant to any curve/point that rejects changes
                    pass
            if changed:
                try:
                    fc.update()
                except Exception:
                    pass
    except Exception:
        # Keep the handler resilient
        pass


def _depsgraph_update_post(_depsgraph):
    # Attempt to post-process at current frame for the active scene
    scene = bpy.context.scene
    if scene is None:
        return
    _apply_to_keyframes_at_frame(scene, float(scene.frame_current))


def _install_handler():
    global _ANIM_HANDLER
    if _ANIM_HANDLER is None:
        _ANIM_HANDLER = _depsgraph_update_post
        if _ANIM_HANDLER not in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.append(_ANIM_HANDLER)


def _remove_handler():
    global _ANIM_HANDLER
    if _ANIM_HANDLER is not None:
        try:
            bpy.app.handlers.depsgraph_update_post.remove(_ANIM_HANDLER)
        except Exception:
            pass
        _ANIM_HANDLER = None


def _on_enabled_update(self, _context):
    try:
        prefs = bpy.context.preferences.edit
        if self.lime_anim_enabled:
            # Store previous default interpolation to restore when disabled
            prev = getattr(prefs, "keyframe_new_interpolation_type", 'BEZIER')
            self.lime_anim_prev_pref = prev
            # Apply supported defaults via preferences
            interp = getattr(self, "lime_anim_interpolation", 'BEZIER')
            if interp in {'CONSTANT', 'LINEAR', 'BEZIER'}:
                prefs.keyframe_new_interpolation_type = interp
            _install_handler()
        else:
            # Restore user's preference if we overrode it
            prev = getattr(self, "lime_anim_prev_pref", "")
            if prev:
                try:
                    bpy.context.preferences.edit.keyframe_new_interpolation_type = prev
                except Exception:
                    pass
            self.lime_anim_prev_pref = ""
            _remove_handler()
    except Exception:
        pass


def _on_interpolation_update(self, _context):
    # When enabled and using one of Blender's native defaults, update preference immediately
    try:
        if getattr(self, "lime_anim_enabled", False):
            interp = getattr(self, "lime_anim_interpolation", 'BEZIER')
            if interp in {'CONSTANT', 'LINEAR', 'BEZIER'}:
                try:
                    bpy.context.preferences.edit.keyframe_new_interpolation_type = interp
                except Exception:
                    pass
            # Ensure handler is installed for extended/easing cases
            _install_handler()
    except Exception:
        pass


def _on_easing_update(self, _context):
    # No immediate preference change; post-processing handles it
    try:
        if getattr(self, "lime_anim_enabled", False):
            _install_handler()
    except Exception:
        pass


def register_anim_params_props():
    # Hidden helper to restore user pref on disable
    bpy.types.Scene.lime_anim_prev_pref = StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    bpy.types.Scene.lime_anim_enabled = BoolProperty(
        name="Enabled",
        default=False,
        description=(
            "When ON, newly inserted keyframes use the selected interpolation & easing."
        ),
        update=_on_enabled_update,
    )

    # Interpolation types per Blender keyframe API
    interp_items = [
        ('CONSTANT', 'Constant', 'Interpolation mode for newly inserted keyframes when enabled.', 'IPO_CONSTANT', 0),
        ('LINEAR',   'Linear',   'Interpolation mode for newly inserted keyframes when enabled.', 'IPO_LINEAR',   1),
        ('BEZIER',   'Bezier',   'Interpolation mode for newly inserted keyframes when enabled.', 'IPO_BEZIER',   2),
        ('SINE',     'Sine',     'Interpolation mode for newly inserted keyframes when enabled.', 'IPO_SINE',     3),
        ('QUAD',     'Quad',     'Interpolation mode for newly inserted keyframes when enabled.', 'IPO_QUAD',     4),
        ('CUBIC',    'Cubic',    'Interpolation mode for newly inserted keyframes when enabled.', 'IPO_CUBIC',    5),
        ('QUART',    'Quart',    'Interpolation mode for newly inserted keyframes when enabled.', 'IPO_QUART',    6),
        ('QUINT',    'Quint',    'Interpolation mode for newly inserted keyframes when enabled.', 'IPO_QUINT',    7),
        ('EXPO',     'Expo',     'Interpolation mode for newly inserted keyframes when enabled.', 'IPO_EXPO',     8),
        ('CIRC',     'Circ',     'Interpolation mode for newly inserted keyframes when enabled.', 'IPO_CIRC',     9),
        ('BACK',     'Back',     'Interpolation mode for newly inserted keyframes when enabled.', 'IPO_BACK',    10),
        ('BOUNCE',   'Bounce',   'Interpolation mode for newly inserted keyframes when enabled.', 'IPO_BOUNCE',  11),
        ('ELASTIC',  'Elastic',  'Interpolation mode for newly inserted keyframes when enabled.', 'IPO_ELASTIC', 12),
    ]
    bpy.types.Scene.lime_anim_interpolation = EnumProperty(
        name="Interpolation",
        description="Interpolation mode for newly inserted keyframes when enabled.",
        items=interp_items,
        default='BEZIER',
        update=_on_interpolation_update,
    )

    bpy.types.Scene.lime_anim_easing = EnumProperty(
        name="Easing",
        description="Easing mode applied to supported interpolations when enabled.",
                        items=[
            ("AUTO", "Auto", "Automatically choose easing for the selected interpolation", "IPO_EASE_IN_OUT", 0),
            ("EASE_IN", "Ease In", "Ease in", "IPO_EASE_IN", 1),
            ("EASE_OUT", "Ease Out", "Ease out", "IPO_EASE_OUT", 2),
            ("EASE_IN_OUT", "Ease In Out", "Ease in and out", "IPO_EASE_IN_OUT", 3),
        ],
        default='AUTO',
        update=_on_easing_update,
    )


def unregister_anim_params_props():
    # Remove handler if still installed
    _remove_handler()
    for attr in (
        "lime_anim_easing",
        "lime_anim_interpolation",
        "lime_anim_enabled",
        "lime_anim_prev_pref",
    ):
        try:
            delattr(bpy.types.Scene, attr)
        except Exception:
            pass


class LIME_TB_PT_animation_params(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = 'Animation Parameters'
    bl_idname = 'LIME_TB_PT_animation_params'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, ctx):
        layout = self.layout
        scene = ctx.scene
        col = layout.column(align=True)

        row = col.row(align=True)
        row.prop(scene, 'lime_anim_interpolation', text='')
        # Disable Easing selector when interpolation does not support easing
        sub = row.row(align=True)
        sub.enabled = _supports_easing(scene.lime_anim_interpolation)
        sub.prop(scene, 'lime_anim_easing', text='')

        row.prop(scene, 'lime_anim_enabled', text='')
        col.separator()
        col.operator('lime.tb_apply_keyframe_style', text='Apply to Selected Keyframes', icon='IPO_BEZIER')


__all__ = [
    'LIME_TB_PT_animation_params',
    'register_anim_params_props',
    'unregister_anim_params_props',
]

