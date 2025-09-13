import bpy
from bpy.types import Panel, UIList, PropertyGroup
from bpy.props import (
    BoolProperty,
    EnumProperty,
    StringProperty,
    IntProperty,
    FloatProperty,
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


# --------------------------
# Noisy Movement UI & props
# --------------------------


def _noise_refresh_affected(scene: bpy.types.Scene, noise_name: str):
    try:
        from lime_pipeline.ops.ops_noise import _objects_with_noise
    except Exception:
        _objects_with_noise = None
    aff = getattr(scene, "lime_tb_noise_affected", None)
    if aff is None:
        return
    aff.clear()
    if _objects_with_noise is None:
        return
    for obj in _objects_with_noise(noise_name) or []:
        it = aff.add()
        it.name = obj.name


def _on_noise_profile_name_update(self, context):
    scene = context.scene
    old = getattr(self, "prev_name", "")
    new = getattr(self, "name", "")
    if not old or not new or old == new:
        self.prev_name = new
        return
    # Rename matching modifiers across scene
    try:
        for obj in bpy.data.objects:
            ad = getattr(obj, "animation_data", None)
            act = getattr(ad, "action", None) if ad else None
            if act is None:
                continue
            for fc in getattr(act, "fcurves", []) or []:
                for m in getattr(fc, "modifiers", []) or []:
                    try:
                        if m.type == 'NOISE' and m.name == old:
                            m.name = new
                    except Exception:
                        pass
    except Exception:
        pass
    self.prev_name = new
    _noise_refresh_affected(scene, new)


def _on_noise_profile_param_update(self, context):
    # Apply current profile settings to all affected objects
    try:
        from lime_pipeline.ops.ops_noise import _apply_profile_to_object, _objects_with_noise
    except Exception:
        return
    scene = context.scene
    try:
        name = self.name
        for obj in _objects_with_noise(name):
            _apply_profile_to_object(obj, self)
    except Exception:
        pass


class LimeTBNoiseAffectedItem(PropertyGroup):
    name: StringProperty(name="Object")


class LimeTBNoiseProfile(PropertyGroup):
    # Name is the anchor across scene
    name: StringProperty(name="Name", description="Noise profile name (used to tag F-Modifiers)", update=_on_noise_profile_name_update)
    prev_name: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    # Location XYZ
    loc_x_enabled: BoolProperty(name="X", default=False, description="Enable noise on Location X", update=_on_noise_profile_param_update)
    loc_y_enabled: BoolProperty(name="Y", default=False, description="Enable noise on Location Y", update=_on_noise_profile_param_update)
    loc_z_enabled: BoolProperty(name="Z", default=False, description="Enable noise on Location Z", update=_on_noise_profile_param_update)
    loc_x_strength: FloatProperty(name="X", default=1.0, description="Noise Strength for Location X", update=_on_noise_profile_param_update)
    loc_y_strength: FloatProperty(name="Y", default=1.0, description="Noise Strength for Location Y", update=_on_noise_profile_param_update)
    loc_z_strength: FloatProperty(name="Z", default=1.0, description="Noise Strength for Location Z", update=_on_noise_profile_param_update)
    loc_x_scale: FloatProperty(name="X", default=1.0, min=0.0, description="Noise Scale for Location X", update=_on_noise_profile_param_update)
    loc_y_scale: FloatProperty(name="Y", default=1.0, min=0.0, description="Noise Scale for Location Y", update=_on_noise_profile_param_update)
    loc_z_scale: FloatProperty(name="Z", default=1.0, min=0.0, description="Noise Scale for Location Z", update=_on_noise_profile_param_update)
    loc_x_phase: FloatProperty(name="X", default=0.0, description="Noise Phase for Location X", update=_on_noise_profile_param_update)
    loc_y_phase: FloatProperty(name="Y", default=0.0, description="Noise Phase for Location Y", update=_on_noise_profile_param_update)
    loc_z_phase: FloatProperty(name="Z", default=0.0, description="Noise Phase for Location Z", update=_on_noise_profile_param_update)

    # Rotation XYZ
    rot_x_enabled: BoolProperty(name="X", default=False, description="Enable noise on Rotation X", update=_on_noise_profile_param_update)
    rot_y_enabled: BoolProperty(name="Y", default=False, description="Enable noise on Rotation Y", update=_on_noise_profile_param_update)
    rot_z_enabled: BoolProperty(name="Z", default=False, description="Enable noise on Rotation Z", update=_on_noise_profile_param_update)
    rot_x_strength: FloatProperty(name="X", default=1.0, description="Noise Strength for Rotation X", update=_on_noise_profile_param_update)
    rot_y_strength: FloatProperty(name="Y", default=1.0, description="Noise Strength for Rotation Y", update=_on_noise_profile_param_update)
    rot_z_strength: FloatProperty(name="Z", default=1.0, description="Noise Strength for Rotation Z", update=_on_noise_profile_param_update)
    rot_x_scale: FloatProperty(name="X", default=1.0, min=0.0, description="Noise Scale for Rotation X", update=_on_noise_profile_param_update)
    rot_y_scale: FloatProperty(name="Y", default=1.0, min=0.0, description="Noise Scale for Rotation Y", update=_on_noise_profile_param_update)
    rot_z_scale: FloatProperty(name="Z", default=1.0, min=0.0, description="Noise Scale for Rotation Z", update=_on_noise_profile_param_update)
    rot_x_phase: FloatProperty(name="X", default=0.0, description="Noise Phase for Rotation X", update=_on_noise_profile_param_update)
    rot_y_phase: FloatProperty(name="Y", default=0.0, description="Noise Phase for Rotation Y", update=_on_noise_profile_param_update)
    rot_z_phase: FloatProperty(name="Z", default=0.0, description="Noise Phase for Rotation Z", update=_on_noise_profile_param_update)

    # Scale XYZ
    scl_x_enabled: BoolProperty(name="X", default=False, description="Enable noise on Scale X", update=_on_noise_profile_param_update)
    scl_y_enabled: BoolProperty(name="Y", default=False, description="Enable noise on Scale Y", update=_on_noise_profile_param_update)
    scl_z_enabled: BoolProperty(name="Z", default=False, description="Enable noise on Scale Z", update=_on_noise_profile_param_update)
    scl_x_strength: FloatProperty(name="X", default=1.0, description="Noise Strength for Scale X", update=_on_noise_profile_param_update)
    scl_y_strength: FloatProperty(name="Y", default=1.0, description="Noise Strength for Scale Y", update=_on_noise_profile_param_update)
    scl_z_strength: FloatProperty(name="Z", default=1.0, description="Noise Strength for Scale Z", update=_on_noise_profile_param_update)
    scl_x_scale: FloatProperty(name="X", default=1.0, min=0.0, description="Noise Scale for Scale X", update=_on_noise_profile_param_update)
    scl_y_scale: FloatProperty(name="Y", default=1.0, min=0.0, description="Noise Scale for Scale Y", update=_on_noise_profile_param_update)
    scl_z_scale: FloatProperty(name="Z", default=1.0, min=0.0, description="Noise Scale for Scale Z", update=_on_noise_profile_param_update)
    scl_x_phase: FloatProperty(name="X", default=0.0, description="Noise Phase for Scale X", update=_on_noise_profile_param_update)
    scl_y_phase: FloatProperty(name="Y", default=0.0, description="Noise Phase for Scale Y", update=_on_noise_profile_param_update)
    scl_z_phase: FloatProperty(name="Z", default=0.0, description="Noise Phase for Scale Z", update=_on_noise_profile_param_update)

    # Frame range
    restrict_range: BoolProperty(name="Restrict Frame Range", default=False, description="Limit when this noise is evaluated. Start/End frames and Blend In/Out.", update=_on_noise_profile_param_update)
    frame_start: IntProperty(name="Start", default=1, min=0, description="Start frame of evaluation range", update=_on_noise_profile_param_update)
    frame_end: IntProperty(name="End", default=250, min=0, description="End frame of evaluation range", update=_on_noise_profile_param_update)
    blend_in: FloatProperty(name="Blend In", default=0.0, min=0.0, description="Frames to ease in", update=_on_noise_profile_param_update)
    blend_out: FloatProperty(name="Blend Out", default=0.0, min=0.0, description="Frames to ease out", update=_on_noise_profile_param_update)


class LIME_TB_UL_noise_names(UIList):
    bl_idname = "LIME_TB_UL_noise_names"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        profile = item
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(profile, 'name', text="", emboss=False, icon='RNDCURVE')
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon='RNDCURVE')


class LIME_TB_UL_noise_objects(UIList):
    bl_idname = "LIME_TB_UL_noise_objects"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        obj_item = item
        layout.prop(obj_item, 'name', text="", emboss=False, icon='OBJECT_DATAMODE')


def register_noise_props():
    bpy.utils.register_class(LimeTBNoiseAffectedItem)
    bpy.utils.register_class(LimeTBNoiseProfile)
    bpy.utils.register_class(LIME_TB_UL_noise_names)
    bpy.utils.register_class(LIME_TB_UL_noise_objects)

    def _on_active_noise_changed(self, context):
        try:
            idx = getattr(self, 'lime_tb_noise_active', -1)
            col = getattr(self, 'lime_tb_noise_profiles', None)
            if col is None:
                return
            aff = getattr(self, 'lime_tb_noise_affected', None)
            if aff is None:
                return
            aff.clear()
            if 0 <= idx < len(col):
                noise_name = col[idx].name
                _noise_refresh_affected(self, noise_name)
        except Exception:
            pass

    bpy.types.Scene.lime_tb_noise_profiles = CollectionProperty(type=LimeTBNoiseProfile)
    bpy.types.Scene.lime_tb_noise_active = IntProperty(name="Active Noise", default=-1, update=_on_active_noise_changed)
    bpy.types.Scene.lime_tb_noise_affected = CollectionProperty(type=LimeTBNoiseAffectedItem)
    bpy.types.Scene.lime_tb_noise_affected_index = IntProperty(name="Affected Index", default=-1, options={'HIDDEN'})


def unregister_noise_props():
    for attr in (
        'lime_tb_noise_profiles',
        'lime_tb_noise_active',
        'lime_tb_noise_affected',
        'lime_tb_noise_affected_index',
    ):
        try:
            delattr(bpy.types.Scene, attr)
        except Exception:
            pass
    for cls in (
        LIME_TB_UL_noise_objects,
        LIME_TB_UL_noise_names,
        LimeTBNoiseProfile,
        LimeTBNoiseAffectedItem,
    ):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass


class LIME_TB_PT_noisy_movement(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = 'Noisy Movement'
    bl_idname = 'LIME_TB_PT_noisy_movement'

    def draw(self, ctx):
        layout = self.layout
        scene = ctx.scene

        # Header actions
        row = layout.row(align=True)
        row.operator('lime.tb_noise_add_profile', text='Add Noise', icon='ADD')
        row.operator('lime.tb_noise_sync', text='Refresh', icon='FILE_REFRESH')

        row = layout.row(align=True)
        row.template_list("LIME_TB_UL_noise_names", "", scene, "lime_tb_noise_profiles", scene, "lime_tb_noise_active", rows=6)
        col_btns = row.column(align=True)
        col_btns.operator('lime.tb_noise_add_profile', text='', icon='ADD')
        col_btns.operator('lime.tb_noise_delete_profile', text='', icon='REMOVE')
        col_btns.separator()
        col_btns.operator('lime.tb_noise_sync', text='', icon='FILE_REFRESH')

        idx = getattr(scene, 'lime_tb_noise_active', -1)
        profiles = getattr(scene, 'lime_tb_noise_profiles', None)
        if profiles is None or not profiles or not (0 <= idx < len(profiles)):
            box = layout.box()
            box.label(text="No Active Noise", icon='INFO')
            box.label(text="Create or select a noise profile.")
            return

        prof = profiles[idx]
        box = layout.box()
        row = box.row(align=True)
        row.label(text=f"Noise Name: {prof.name}")

        # Sections: Location / Rotation / Scale
        def draw_group(container, label_prefix: str, key: str):
            col = container.column(align=True)
            col.label(text=label_prefix)
            # Axis toggles
            row = col.row(align=True)
            row.prop(prof, f"{key}_x_enabled", toggle=True)
            row.prop(prof, f"{key}_y_enabled", toggle=True)
            row.prop(prof, f"{key}_z_enabled", toggle=True)
            # Strength
            row = col.row(align=True)
            row.prop(prof, f"{key}_x_strength")
            row.prop(prof, f"{key}_y_strength")
            row.prop(prof, f"{key}_z_strength")
            # Scale (noise frequency)
            row = col.row(align=True)
            row.prop(prof, f"{key}_x_scale")
            row.prop(prof, f"{key}_y_scale")
            row.prop(prof, f"{key}_z_scale")
            # Phase
            row = col.row(align=True)
            row.prop(prof, f"{key}_x_phase")
            row.prop(prof, f"{key}_y_phase")
            row.prop(prof, f"{key}_z_phase")

        split = box.column(align=True)
        draw_group(split, "Location", "loc")
        draw_group(split, "Rotation", "rot")
        draw_group(split, "Scale", "scl")

        # Restrict Frame Range
        fr = layout.box()
        fr.prop(prof, 'restrict_range', text='Restrict Frame Range')
        sub = fr.column(align=True)
        sub.enabled = prof.restrict_range
        row = sub.row(align=True)
        row.prop(prof, 'frame_start')
        row.prop(prof, 'frame_end')
        row = sub.row(align=True)
        row.prop(prof, 'blend_in')
        row.prop(prof, 'blend_out')

        # Affected objects list
        objs_box = layout.box()
        objs_box.label(text=f"Objects affected by {prof.name}")
        row = objs_box.row(align=True)
        row.template_list("LIME_TB_UL_noise_objects", "", scene, "lime_tb_noise_affected", scene, "lime_tb_noise_affected_index", rows=4)
        col_btns = row.column(align=True)
        col_btns.operator('lime.tb_noise_sync', text='', icon='FILE_REFRESH')
        # Remove selected from noise
        idx_o = getattr(scene, 'lime_tb_noise_affected_index', -1)
        aff = getattr(scene, 'lime_tb_noise_affected', [])
        remove_op = col_btns.operator('lime.tb_noise_remove_from_object', text='', icon='X')
        if 0 <= idx_o < len(aff):
            remove_op.object_name = aff[idx_o].name
        else:
            remove_op.object_name = ""

        layout.operator('lime.tb_noise_apply_to_selected', icon='PLUS')


__all__ += [
    'LIME_TB_PT_noisy_movement',
    'register_noise_props',
    'unregister_noise_props',
]
