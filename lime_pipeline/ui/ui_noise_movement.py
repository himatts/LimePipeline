import bpy
from bpy.types import Panel, UIList, PropertyGroup
from bpy.props import (
    BoolProperty,
    StringProperty,
    IntProperty,
    FloatProperty,
    FloatVectorProperty,
    CollectionProperty,
)


CAT = "Lime Toolbox"


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
    for obj in _objects_with_noise(noise_name, scene) or []:
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
        for obj in _objects_with_noise(name, scene):
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
    # Clipboard (WindowManager)
    bpy.types.WindowManager.lime_tb_noise_clip_values = FloatVectorProperty(size=9, options={'HIDDEN', 'SKIP_SAVE'})
    bpy.types.WindowManager.lime_tb_noise_clip_valid = BoolProperty(options={'HIDDEN'}, default=False)


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
    # Clipboard cleanup
    for attr in (
        'lime_tb_noise_clip_values',
        'lime_tb_noise_clip_valid',
    ):
        try:
            delattr(bpy.types.WindowManager, attr)
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
            header = col.row(align=True)
            header.label(text=label_prefix)
            header.alignment = 'RIGHT'
            # Header tools: randomize, copy, paste
            rnd = header.operator('lime.tb_noise_group_randomize', text='', icon='RNDCURVE')
            rnd.group = key
            cpy = header.operator('lime.tb_noise_group_copy', text='', icon='COPYDOWN')
            cpy.group = key
            pst = header.operator('lime.tb_noise_group_paste', text='', icon='PASTEDOWN')
            pst.group = key
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

        row = layout.row(align=True)
        row.operator('lime.tb_noise_apply_to_selected', icon='PLUS')
        row.operator('lime.tb_noise_remove_selected', icon='REMOVE')


__all__ = [
    'LIME_TB_PT_noisy_movement',
    'register_noise_props',
    'unregister_noise_props',
]
