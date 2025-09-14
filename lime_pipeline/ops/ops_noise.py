import bpy
import random
from bpy.types import Operator


def _ensure_action(obj: bpy.types.Object) -> bpy.types.Action | None:
    try:
        ad = obj.animation_data
        if ad is None:
            ad = obj.animation_data_create()
        if ad.action is None:
            act = bpy.data.actions.new(name=f"{obj.name}_Action")
            ad.action = act
        return ad.action
    except Exception:
        return None


def _ensure_fcurve(act: bpy.types.Action, data_path: str, index: int) -> bpy.types.FCurve | None:
    try:
        fc = act.fcurves.find(data_path, index=index)
        if fc is None:
            fc = act.fcurves.new(data_path, index=index)
        return fc
    except Exception:
        return None


def _find_noise_modifier(fc: bpy.types.FCurve, noise_name: str) -> bpy.types.FModifier | None:
    try:
        for m in fc.modifiers:
            if m.type == 'NOISE' and m.name == noise_name:
                return m
    except Exception:
        pass
    return None


def _ensure_noise_modifier(fc: bpy.types.FCurve, noise_name: str) -> bpy.types.FModifier | None:
    try:
        m = _find_noise_modifier(fc, noise_name)
        if m is None:
            m = fc.modifiers.new(type='NOISE')
            m.name = noise_name
        return m
    except Exception:
        return None


def _axes_triplet(enabled_x: bool, enabled_y: bool, enabled_z: bool):
    return (
        (0, enabled_x),
        (1, enabled_y),
        (2, enabled_z),
    )


def _axis_settings(profile, group_key: str, axis: int):
    # group_key in {"loc", "rot", "scl"}
    ax = "xyz"[axis]
    enabled = getattr(profile, f"{group_key}_{ax}_enabled")
    strength = getattr(profile, f"{group_key}_{ax}_strength")
    phase = getattr(profile, f"{group_key}_{ax}_phase")
    scale = getattr(profile, f"{group_key}_{ax}_scale", 1.0)
    return enabled, strength, phase, scale


def _apply_profile_to_object(obj: bpy.types.Object, profile) -> int:
    """Ensure FCurves and NOISE modifiers exist per enabled axes and update params.
    Returns number of modifiers updated/created.
    """
    if obj is None:
        return 0
    total = 0
    act = _ensure_action(obj)
    if act is None:
        return 0

    def handle_group(group_key: str, data_path: str):
        nonlocal total
        for axis in (0, 1, 2):
            en, strength, phase, scale = _axis_settings(profile, group_key, axis)
            if not en:
                # If it exists, mute it (do not delete)
                fc = act.fcurves.find(data_path, index=axis)
                if fc is not None:
                    m = _find_noise_modifier(fc, profile.name)
                    if m is not None:
                        m.mute = True
                continue
            fc = _ensure_fcurve(act, data_path, index=axis)
            if fc is None:
                continue
            m = _ensure_noise_modifier(fc, profile.name)
            if m is None:
                continue
            m.mute = False
            # Frame range
            try:
                m.use_restricted_range = bool(profile.restrict_range)
                if profile.restrict_range:
                    m.frame_start = int(profile.frame_start)
                    m.frame_end = int(profile.frame_end)
                    m.blend_in = float(profile.blend_in)
                    m.blend_out = float(profile.blend_out)
            except Exception:
                pass
            # Params
            try:
                m.strength = float(strength)
                m.phase = float(phase)
                # Noise Scale (frequency)
                if hasattr(m, 'scale'):
                    m.scale = float(scale)
            except Exception:
                pass
            total += 1

    handle_group("loc", "location")
    handle_group("rot", "rotation_euler")
    handle_group("scl", "scale")
    return total


def _objects_with_noise(noise_name: str) -> list[bpy.types.Object]:
    objs = []
    for obj in bpy.data.objects:
        ad = getattr(obj, "animation_data", None)
        if ad is None or getattr(ad, "action", None) is None:
            continue
        act = ad.action
        found = False
        for fc in getattr(act, "fcurves", []) or []:
            for m in getattr(fc, "modifiers", []) or []:
                if getattr(m, "type", None) == 'NOISE' and getattr(m, "name", "") == noise_name:
                    found = True
                    break
            if found:
                break
        if found:
            objs.append(obj)
    return objs


class LIME_TB_OT_noise_add_profile(Operator):
    bl_idname = "lime.tb_noise_add_profile"
    bl_label = "Add Noise"
    bl_description = "Create a new named noise profile and make it active."

    def execute(self, context):
        scene = context.scene
        if scene is None:
            return {'CANCELLED'}
        col = getattr(scene, "lime_tb_noise_profiles", None)
        if col is None:
            self.report({'ERROR'}, "Noise properties not registered")
            return {'CANCELLED'}

        # Create unique name Noise.001, Noise.002, ...
        base = "Noise"
        existing = {p.name for p in col}
        name = base
        idx = 1
        while name in existing:
            name = f"{base}.{idx:03d}"
            idx += 1
        item = col.add()
        item.name = name
        # Defaults: enable Location XYZ
        item.loc_x_enabled = True
        item.loc_y_enabled = True
        item.loc_z_enabled = True
        scene.lime_tb_noise_active = len(col) - 1
        self.report({'INFO'}, f"Added noise profile: {name}")
        return {'FINISHED'}


class LIME_TB_OT_noise_sync(Operator):
    bl_idname = "lime.tb_noise_sync"
    bl_label = "Refresh"
    bl_description = "Scan the scene to sync noise names and affected objects."

    def execute(self, context):
        scene = context.scene
        col = getattr(scene, "lime_tb_noise_profiles", None)
        aff = getattr(scene, "lime_tb_noise_affected", None)
        if col is None or aff is None:
            return {'CANCELLED'}
        # Build set of names from profiles and scene modifiers
        names = {p.name for p in col}
        for obj in bpy.data.objects:
            ad = getattr(obj, "animation_data", None)
            if ad is None or getattr(ad, "action", None) is None:
                continue
            for fc in getattr(ad.action, "fcurves", []) or []:
                for m in getattr(fc, "modifiers", []) or []:
                    if getattr(m, "type", None) == 'NOISE':
                        names.add(m.name)
        # Ensure collection reflects names
        # Remove unknown profiles
        i = 0
        while i < len(col):
            if col[i].name not in names:
                col.remove(i)
                # Adjust active index
                if scene.lime_tb_noise_active >= len(col):
                    scene.lime_tb_noise_active = max(0, len(col) - 1)
                continue
            i += 1
        # Add missing
        existing = {p.name for p in col}
        for nm in sorted(names):
            if nm not in existing:
                item = col.add()
                item.name = nm
        # Refresh affected cache for active
        idx = getattr(scene, "lime_tb_noise_active", -1)
        aff.clear()
        if 0 <= idx < len(col):
            noise_name = col[idx].name
            for obj in _objects_with_noise(noise_name):
                it = aff.add()
                it.name = obj.name
        return {'FINISHED'}


class LIME_TB_OT_noise_apply_to_selected(Operator):
    bl_idname = "lime.tb_noise_apply_to_selected"
    bl_label = "Add Selected Objects to Active Noise"
    bl_description = (
        "Apply the active noise to the current selection based on enabled axes."
    )

    def execute(self, context):
        scene = context.scene
        col = getattr(scene, "lime_tb_noise_profiles", None)
        if col is None or not col:
            self.report({'WARNING'}, "No active noise")
            return {'CANCELLED'}
        idx = getattr(scene, "lime_tb_noise_active", -1)
        if not (0 <= idx < len(col)):
            self.report({'WARNING'}, "No active noise")
            return {'CANCELLED'}
        profile = col[idx]
        objs = context.selected_objects or []
        if not objs:
            self.report({'WARNING'}, "No selected objects")
            return {'CANCELLED'}
        total = 0
        for obj in objs:
            total += _apply_profile_to_object(obj, profile)
        # Refresh affected cache
        try:
            aff = scene.lime_tb_noise_affected
            aff.clear()
            for obj in _objects_with_noise(profile.name):
                it = aff.add()
                it.name = obj.name
        except Exception:
            pass
        self.report({'INFO'}, f"Noise applied: {total} modifiers updated")
        return {'FINISHED'}


class LIME_TB_OT_noise_remove_from_object(Operator):
    bl_idname = "lime.tb_noise_remove_from_object"
    bl_label = "Remove from Noise"
    bl_description = "Remove this object's link to the active noise (delete matching modifiers)."

    object_name: bpy.props.StringProperty(options={'HIDDEN'})

    def execute(self, context):
        scene = context.scene
        col = scene.lime_tb_noise_profiles
        idx = scene.lime_tb_noise_active
        if not (0 <= idx < len(col)):
            return {'CANCELLED'}
        noise_name = col[idx].name
        obj = bpy.data.objects.get(self.object_name)
        if obj is None:
            return {'CANCELLED'}
        ad = getattr(obj, "animation_data", None)
        act = getattr(ad, "action", None) if ad else None
        if act is None:
            return {'CANCELLED'}
        removed = 0
        for fc in list(getattr(act, "fcurves", []) or []):
            for m in list(getattr(fc, "modifiers", []) or []):
                try:
                    if m.type == 'NOISE' and m.name == noise_name:
                        fc.modifiers.remove(m)
                        removed += 1
                except Exception:
                    pass
        # Update affected cache
        try:
            aff = scene.lime_tb_noise_affected
            aff.clear()
            for o in _objects_with_noise(noise_name):
                it = aff.add()
                it.name = o.name
        except Exception:
            pass
        self.report({'INFO'}, f"Removed {removed} modifiers from {obj.name}")
        return {'FINISHED'}


class LIME_TB_OT_noise_remove_selected(Operator):
    bl_idname = "lime.tb_noise_remove_selected"
    bl_label = "Remove Selected Objects from Active Noise"
    bl_description = "Delete all Noise modifiers with the active noise name from the current selection."

    def execute(self, context):
        scene = context.scene
        col = getattr(scene, "lime_tb_noise_profiles", None)
        idx = getattr(scene, "lime_tb_noise_active", -1)
        if col is None or not (0 <= idx < len(col)):
            self.report({'WARNING'}, "No active noise")
            return {'CANCELLED'}
        noise_name = col[idx].name
        objs = context.selected_objects or []
        if not objs:
            self.report({'WARNING'}, "No selected objects")
            return {'CANCELLED'}
        total_removed = 0
        for obj in objs:
            ad = getattr(obj, "animation_data", None)
            act = getattr(ad, "action", None) if ad else None
            if act is None:
                continue
            for fc in list(getattr(act, "fcurves", []) or []):
                for m in list(getattr(fc, "modifiers", []) or []):
                    try:
                        if m.type == 'NOISE' and m.name == noise_name:
                            fc.modifiers.remove(m)
                            total_removed += 1
                    except Exception:
                        pass
        # Refresh affected cache
        try:
            aff = scene.lime_tb_noise_affected
            aff.clear()
            for o in _objects_with_noise(noise_name):
                it = aff.add()
                it.name = o.name
        except Exception:
            pass
        self.report({'INFO'}, f"Removed {total_removed} modifiers from selected objects")
        return {'FINISHED'}


class LIME_TB_OT_noise_rename_profile(Operator):
    bl_idname = "lime.tb_noise_rename_profile"
    bl_label = "Rename Noise"
    bl_description = "Rename the active noise profile and update all matching modifiers."

    new_name: bpy.props.StringProperty(name="Name")

    def execute(self, context):
        scene = context.scene
        col = scene.lime_tb_noise_profiles
        idx = scene.lime_tb_noise_active
        if not (0 <= idx < len(col)):
            return {'CANCELLED'}
        old = col[idx].name
        new = self.new_name.strip()
        if not new:
            self.report({'WARNING'}, "Name cannot be empty")
            return {'CANCELLED'}
        # Ensure unique within profiles
        if any(p.name == new for p in col if p != col[idx]):
            self.report({'WARNING'}, "A profile with that name already exists")
            return {'CANCELLED'}
        # Update modifiers
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
        col[idx].name = new
        # Refresh affected cache
        try:
            aff = scene.lime_tb_noise_affected
            aff.clear()
            for o in _objects_with_noise(new):
                it = aff.add()
                it.name = o.name
        except Exception:
            pass
        self.report({'INFO'}, f"Renamed noise '{old}' to '{new}'")
        return {'FINISHED'}


class LIME_TB_OT_noise_group_randomize(Operator):
    bl_idname = "lime.tb_noise_group_randomize"
    bl_label = "Randomize Group Values"
    bl_description = "Assign random values to Strength, Scale and Phase for X/Y/Z of this group."

    group: bpy.props.EnumProperty(items=[('loc', 'Location', ''), ('rot', 'Rotation', ''), ('scl', 'Scale', '')])

    # Simple ranges; adjust in last operator panel if invoked
    strength_min: bpy.props.FloatProperty(name="Strength Min", default=-1.0)
    strength_max: bpy.props.FloatProperty(name="Strength Max", default=1.0)
    scale_min: bpy.props.FloatProperty(name="Scale Min", default=0.25, min=0.0)
    scale_max: bpy.props.FloatProperty(name="Scale Max", default=2.0, min=0.0)
    phase_min: bpy.props.FloatProperty(name="Phase Min", default=-3.1416)
    phase_max: bpy.props.FloatProperty(name="Phase Max", default=3.1416)

    def execute(self, context):
        scene = context.scene
        col = getattr(scene, "lime_tb_noise_profiles", None)
        idx = getattr(scene, "lime_tb_noise_active", -1)
        if col is None or not (0 <= idx < len(col)):
            self.report({'WARNING'}, "No active noise")
            return {'CANCELLED'}
        prof = col[idx]
        g = self.group
        # Helper to set triplets
        def set_triplet(prop_suffix: str, min_v: float, max_v: float):
            setattr(prof, f"{g}_x_{prop_suffix}", random.uniform(min_v, max_v))
            setattr(prof, f"{g}_y_{prop_suffix}", random.uniform(min_v, max_v))
            setattr(prof, f"{g}_z_{prop_suffix}", random.uniform(min_v, max_v))

        set_triplet('strength', self.strength_min, self.strength_max)
        set_triplet('scale', self.scale_min, self.scale_max)
        set_triplet('phase', self.phase_min, self.phase_max)
        self.report({'INFO'}, f"Randomized {g} values")
        return {'FINISHED'}


class LIME_TB_OT_noise_group_copy(Operator):
    bl_idname = "lime.tb_noise_group_copy"
    bl_label = "Copy Group Values"
    bl_description = "Copy Strength, Scale and Phase for X/Y/Z of this group to clipboard."

    group: bpy.props.EnumProperty(items=[('loc', 'Location', ''), ('rot', 'Rotation', ''), ('scl', 'Scale', '')])

    def execute(self, context):
        scene = context.scene
        wm = context.window_manager
        col = getattr(scene, "lime_tb_noise_profiles", None)
        idx = getattr(scene, "lime_tb_noise_active", -1)
        if col is None or not (0 <= idx < len(col)):
            self.report({'WARNING'}, "No active noise")
            return {'CANCELLED'}
        prof = col[idx]
        g = self.group
        vals = [
            getattr(prof, f"{g}_x_strength"), getattr(prof, f"{g}_y_strength"), getattr(prof, f"{g}_z_strength"),
            getattr(prof, f"{g}_x_scale"),    getattr(prof, f"{g}_y_scale"),    getattr(prof, f"{g}_z_scale"),
            getattr(prof, f"{g}_x_phase"),    getattr(prof, f"{g}_y_phase"),    getattr(prof, f"{g}_z_phase"),
        ]
        try:
            wm.lime_tb_noise_clip_values = vals
            wm.lime_tb_noise_clip_valid = True
        except Exception:
            self.report({'ERROR'}, "Clipboard properties not available")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Copied {g} values")
        return {'FINISHED'}


class LIME_TB_OT_noise_group_paste(Operator):
    bl_idname = "lime.tb_noise_group_paste"
    bl_label = "Paste Group Values"
    bl_description = "Paste Strength, Scale and Phase from clipboard into this group."

    group: bpy.props.EnumProperty(items=[('loc', 'Location', ''), ('rot', 'Rotation', ''), ('scl', 'Scale', '')])

    def execute(self, context):
        scene = context.scene
        wm = context.window_manager
        col = getattr(scene, "lime_tb_noise_profiles", None)
        idx = getattr(scene, "lime_tb_noise_active", -1)
        if col is None or not (0 <= idx < len(col)):
            self.report({'WARNING'}, "No active noise")
            return {'CANCELLED'}
        if not getattr(wm, 'lime_tb_noise_clip_valid', False):
            self.report({'WARNING'}, "Clipboard is empty")
            return {'CANCELLED'}
        vals = list(getattr(wm, 'lime_tb_noise_clip_values', []))
        if len(vals) != 9:
            self.report({'WARNING'}, "Clipboard has unexpected format")
            return {'CANCELLED'}
        prof = col[idx]
        g = self.group
        # Assign in same order as copied
        try:
            prof[f"{g}_x_strength"], prof[f"{g}_y_strength"], prof[f"{g}_z_strength"], \
            prof[f"{g}_x_scale"], prof[f"{g}_y_scale"], prof[f"{g}_z_scale"], \
            prof[f"{g}_x_phase"], prof[f"{g}_y_phase"], prof[f"{g}_z_phase"] = vals
        except Exception:
            # Fallback explicit sets in case item assignment unsupported
            setattr(prof, f"{g}_x_strength", vals[0]); setattr(prof, f"{g}_y_strength", vals[1]); setattr(prof, f"{g}_z_strength", vals[2])
            setattr(prof, f"{g}_x_scale", vals[3]);    setattr(prof, f"{g}_y_scale", vals[4]);    setattr(prof, f"{g}_z_scale", vals[5])
            setattr(prof, f"{g}_x_phase", vals[6]);    setattr(prof, f"{g}_y_phase", vals[7]);    setattr(prof, f"{g}_z_phase", vals[8])
        self.report({'INFO'}, f"Pasted {g} values")
        return {'FINISHED'}


class LIME_TB_OT_noise_delete_profile(Operator):
    bl_idname = "lime.tb_noise_delete_profile"
    bl_label = "Delete Noise"
    bl_description = "Delete the active noise profile and remove its Noise modifiers from all objects."

    def execute(self, context):
        scene = context.scene
        col = getattr(scene, "lime_tb_noise_profiles", None)
        if not col:
            return {'CANCELLED'}
        idx = getattr(scene, "lime_tb_noise_active", -1)
        if not (0 <= idx < len(col)):
            return {'CANCELLED'}
        name = col[idx].name
        # Remove matching modifiers from all objects
        removed = 0
        for obj in bpy.data.objects:
            ad = getattr(obj, "animation_data", None)
            act = getattr(ad, "action", None) if ad else None
            if act is None:
                continue
            for fc in list(getattr(act, "fcurves", []) or []):
                for m in list(getattr(fc, "modifiers", []) or []):
                    try:
                        if m.type == 'NOISE' and m.name == name:
                            fc.modifiers.remove(m)
                            removed += 1
                    except Exception:
                        pass
        # Remove profile from collection
        col.remove(idx)
        # Adjust active index
        if idx >= len(col):
            scene.lime_tb_noise_active = len(col) - 1
        else:
            scene.lime_tb_noise_active = idx
        # Clear affected cache and leave empty
        try:
            scene.lime_tb_noise_affected.clear()
        except Exception:
            pass
        self.report({'INFO'}, f"Deleted noise '{name}' and removed {removed} modifiers")
        return {'FINISHED'}


__all__ = [
    "LIME_TB_OT_noise_add_profile",
    "LIME_TB_OT_noise_sync",
    "LIME_TB_OT_noise_apply_to_selected",
    "LIME_TB_OT_noise_remove_from_object",
    "LIME_TB_OT_noise_remove_selected",
    "LIME_TB_OT_noise_rename_profile",
    "LIME_TB_OT_noise_group_randomize",
    "LIME_TB_OT_noise_group_copy",
    "LIME_TB_OT_noise_group_paste",
    "LIME_TB_OT_noise_delete_profile",
]
