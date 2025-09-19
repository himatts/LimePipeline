import json
from typing import Any, Dict, Optional

import bpy
from bpy.types import Operator
from bpy.props import IntProperty

from ..props import LimeRenderPresetSlot

ADDON_ID = __package__.split('.')[0]
DATA_VERSION = 1
PRESET_SLOT_COUNT = 4

RENDER_PROPS = (
    'engine',
    'resolution_x',
    'resolution_y',
    'resolution_percentage',
    'film_transparent',
    'threads_mode',
    'threads',
    'use_persistent_data',
    'use_single_layer',
    'fps',
    'fps_base',
)

OUTPUT_PROPS = (
    'use_file_extension',
    'use_overwrite',
    'use_compositing',
    'use_sequencer',
)

IMAGE_SETTINGS_PROPS = (
    'file_format',
    'color_mode',
    'color_depth',
    'compression',
)

COLOR_MANAGEMENT_PROPS = (
    'view_transform',
    'look',
    'exposure',
    'gamma',
)

CYCLES_SCENE_PROPS = (
    'feature_set',
    'device',
    'use_preview_adaptive_sampling',
    'preview_adaptive_threshold',
    'preview_samples',
    'use_preview_denoising',
    'preview_denoiser',
    'preview_denoising_input_passes',
    'preview_denoising_prefilter',
    'preview_denoising_quality',
    'use_adaptive_sampling',
    'adaptive_threshold',
    'samples',
    'use_denoising',
    'denoiser',
    'max_bounces',
    'glossy_bounces',
    'diffuse_bounces',
    'transmission_bounces',
    'volume_bounces',
    'transparent_max_bounces',
)

CYCLES_VIEW_LAYER_PROPS = (
    'use_denoising',
)

UNIT_SETTINGS_PROPS = (
    'system',
    'scale_length',
)


def _get_addon_prefs(context=None):
    try:
        prefs = (context or bpy.context).preferences
        addon = prefs.addons.get(ADDON_ID)
        if addon:
            return addon.preferences
    except Exception:
        pass
    return None


def _ensure_collection_size(collection, count: int):
    if collection is None:
        return
    count = max(0, int(count))
    while len(collection) < count:
        slot = collection.add()
        slot_index = len(collection)
        if not slot.name:
            slot.name = f"Preset {slot_index}"
        slot.is_empty = True
        slot.data_version = DATA_VERSION
        slot.data_json = ""
    while len(collection) > count:
        try:
            collection.remove(len(collection) - 1)
        except Exception:
            break
    for idx, slot in enumerate(collection[:count], 1):
        if not slot.name:
            slot.name = f"Preset {idx}"


def ensure_preset_slots(context=None, ensure_scene=False) -> int:
    prefs = _get_addon_prefs(context)
    if prefs is None:
        return 0
    count = PRESET_SLOT_COUNT
    _ensure_collection_size(getattr(prefs, 'global_render_presets', None), count)
    _ensure_collection_size(getattr(prefs, 'defaults_render_presets', None), count)
    return count


def _collect_props(obj, props) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for name in props:
        try:
            value = getattr(obj, name)
        except Exception:
            continue
        if isinstance(value, (str, int, float, bool)):
            data[name] = value
    return data


def collect_render_config(context) -> Dict[str, Any]:
    scene = context.scene
    render = scene.render
    ensure_preset_slots(context)

    image_settings = _collect_props(render.image_settings, IMAGE_SETTINGS_PROPS)
    payload: Dict[str, Any] = {
        'data_version': DATA_VERSION,
        'render': _collect_props(render, RENDER_PROPS + OUTPUT_PROPS),
        'image_settings': image_settings,
        'color_management': _collect_props(scene.view_settings, COLOR_MANAGEMENT_PROPS),
        'unit_settings': _collect_props(scene.unit_settings, UNIT_SETTINGS_PROPS),
    }
    if image_settings:  # ensure mode/depth are reapplied even if Blender tweaks defaults
        meta = payload.setdefault('image_settings_meta', {})
        mode = image_settings.get('color_mode')
        if mode:
            meta['color_mode'] = mode
        depth = image_settings.get('color_depth')
        if depth:
            meta['color_depth'] = depth

    cy_scene = getattr(scene, 'cycles', None)
    if cy_scene is not None:
        payload['cycles_scene'] = _collect_props(cy_scene, CYCLES_SCENE_PROPS)
    view_layer = getattr(context, 'view_layer', None)
    cy_layer = getattr(view_layer, 'cycles', None) if view_layer else None
    if cy_layer is not None:
        payload['cycles_view_layer'] = _collect_props(cy_layer, CYCLES_VIEW_LAYER_PROPS)
    return payload


def _apply_props(target, data: Dict[str, Any]) -> bool:
    changed = False
    for key, value in data.items():
        try:
            setattr(target, key, value)
            changed = True
        except Exception:
            continue
    return changed


def apply_render_config(context, payload: Dict[str, Any]) -> bool:
    if not payload:
        return False
    scene = context.scene
    render = scene.render
    changed = False

    render_data = payload.get('render', {})
    if render_data:
        changed |= _apply_props(render, render_data)

    image_data = payload.get('image_settings', {})
    if image_data:
        changed |= _apply_props(render.image_settings, image_data)
        meta = payload.get('image_settings_meta', {})
        color_mode = meta.get('color_mode')
        color_depth = meta.get('color_depth')
        try:
            if color_mode:
                render.image_settings.color_mode = color_mode
            if color_depth:
                render.image_settings.color_depth = color_depth
        except Exception:
            pass

    color_data = payload.get('color_management', {})
    if color_data:
        changed |= _apply_props(scene.view_settings, color_data)

    unit_data = payload.get('unit_settings', {})
    if unit_data:
        changed |= _apply_props(scene.unit_settings, unit_data)

    cy_scene = getattr(scene, 'cycles', None)
    scene_data = payload.get('cycles_scene', {})
    if cy_scene is not None and scene_data:
        changed |= _apply_props(cy_scene, scene_data)

    view_layer = getattr(context, 'view_layer', None)
    cy_layer = getattr(view_layer, 'cycles', None) if view_layer else None
    layer_data = payload.get('cycles_view_layer', {})
    if layer_data:
        if cy_layer is not None:
            changed |= _apply_props(cy_layer, layer_data)
        elif cy_scene is not None:
            changed |= _apply_props(cy_scene, layer_data)

    return changed


def _get_global_slot(context, index: int) -> Optional[LimeRenderPresetSlot]:
    prefs = _get_addon_prefs(context)
    if prefs is None:
        return None
    collection = getattr(prefs, 'global_render_presets', None)
    if collection is None:
        return None
    if index >= len(collection):
        _ensure_collection_size(collection, index + 1)
    try:
        return collection[index]
    except Exception:
        return None


def _get_defaults_slot(context, index: int) -> Optional[LimeRenderPresetSlot]:
    prefs = _get_addon_prefs(context)
    if prefs is None:
        return None
    collection = getattr(prefs, 'defaults_render_presets', None)
    if collection is None:
        return None
    if index >= len(collection):
        _ensure_collection_size(collection, index + 1)
    try:
        return collection[index]
    except Exception:
        return None


def _load_slot_payload(slot: LimeRenderPresetSlot) -> Optional[Dict[str, Any]]:
    if slot is None or slot.is_empty:
        return None
    raw = slot.data_json or ''
    if not raw.strip():
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return None


def _store_slot_payload(slot: LimeRenderPresetSlot, payload: Dict[str, Any]):
    slot.data_version = payload.get('data_version', DATA_VERSION)
    slot.data_json = json.dumps(payload, sort_keys=True)
    slot.is_empty = False


class LIME_OT_render_preset_save(Operator):
    bl_idname = 'lime.render_preset_save'
    bl_label = 'Save Render Preset'
    bl_description = 'Save the current render configuration into the selected preset slot'

    slot_index: IntProperty(name='Slot', default=0, min=0, max=PRESET_SLOT_COUNT - 1)

    @classmethod
    def description(cls, _context, props):
        try:
            idx = max(0, int(getattr(props, 'slot_index', 0)))
        except Exception:
            idx = 0
        return f'LMB: Save current render settings into Global preset {idx + 1}.'

    def execute(self, context):
        prefs = _get_addon_prefs(context)
        if prefs is None:
            self.report({'ERROR'}, 'Addon preferences not available.')
            return {'CANCELLED'}
        ensure_preset_slots(context)
        payload = collect_render_config(context)
        slot = _get_global_slot(context, self.slot_index)
        if slot is None:
            self.report({'ERROR'}, 'Unable to resolve preset slot.')
            return {'CANCELLED'}
        _store_slot_payload(slot, payload)
        display_idx = self.slot_index + 1
        self.report({'INFO'}, f"Saved preset {display_idx}.")
        return {'FINISHED'}


class LIME_OT_render_preset_apply(Operator):
    bl_idname = 'lime.render_preset_apply'
    bl_label = 'Apply Render Preset'
    bl_description = 'Apply the saved render preset to the current scene'

    slot_index: IntProperty(name='Slot', default=0, min=0, max=PRESET_SLOT_COUNT - 1)

    @classmethod
    def description(cls, _context, props):
        try:
            idx = max(0, int(getattr(props, 'slot_index', 0)))
        except Exception:
            idx = 0
        return f'LMB: Apply Global preset {idx + 1} to the current scene.'

    def execute(self, context):
        ensure_preset_slots(context)
        slot = _get_global_slot(context, self.slot_index)
        payload = _load_slot_payload(slot) if slot else None
        if payload and apply_render_config(context, payload):
            display_idx = self.slot_index + 1
            self.report({'INFO'}, f"Applied preset {display_idx}.")
            return {'FINISHED'}
        self.report({'WARNING'}, 'No preset data to apply.')
        return {'CANCELLED'}


class LIME_OT_render_preset_clear(Operator):
    bl_idname = 'lime.render_preset_clear'
    bl_label = 'Clear Render Preset'
    bl_description = 'Clear the stored data in the preset slot'

    slot_index: IntProperty(name='Slot', default=0, min=0, max=PRESET_SLOT_COUNT - 1)

    @classmethod
    def description(cls, _context, props):
        try:
            idx = max(0, int(getattr(props, 'slot_index', 0)))
        except Exception:
            idx = 0
        return f'LMB: Clear Global preset {idx + 1}. A confirmation prompt protects against mistakes.'

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        ensure_preset_slots(context)
        slot = _get_global_slot(context, self.slot_index)
        if slot is None:
            self.report({'ERROR'}, 'Unable to resolve preset slot.')
            return {'CANCELLED'}
        slot.data_json = ''
        slot.is_empty = True
        slot.data_version = DATA_VERSION
        display_idx = self.slot_index + 1
        self.report({'INFO'}, f"Cleared preset {display_idx}.")
        return {'FINISHED'}


class LIME_OT_render_preset_reset_all(Operator):
    bl_idname = 'lime.render_preset_reset_all'
    bl_label = 'Reset Render Presets'
    bl_description = 'Clear all global preset slots'

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        count = ensure_preset_slots(context)
        for idx in range(count):
            slot = _get_global_slot(context, idx)
            if slot is None:
                continue
            slot.data_json = ''
            slot.is_empty = True
            slot.data_version = DATA_VERSION
        self.report({'INFO'}, 'Reset presets.')
        return {'FINISHED'}


class LIME_OT_render_preset_restore_defaults(Operator):
    bl_idname = 'lime.render_preset_restore_defaults'
    bl_label = 'Restore Default Presets'
    bl_description = 'Restore global presets from the defaults backup'

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        prefs = _get_addon_prefs(context)
        if prefs is None:
            self.report({'ERROR'}, 'Addon preferences not available.')
            return {'CANCELLED'}
        count = ensure_preset_slots(context)
        for idx in range(count):
            src = _get_defaults_slot(context, idx)
            dst = _get_global_slot(context, idx)
            if dst is None:
                continue
            if src is None or src.is_empty or not src.data_json:
                dst.data_json = ''
                dst.is_empty = True
                dst.data_version = DATA_VERSION
            else:
                dst.name = src.name or dst.name
                dst.data_version = src.data_version
                dst.data_json = src.data_json
                dst.is_empty = src.is_empty
        self.report({'INFO'}, 'Restored defaults.')
        return {'FINISHED'}


class LIME_OT_render_preset_update_defaults(Operator):
    bl_idname = 'lime.render_preset_update_defaults'
    bl_label = 'Update Default Presets'
    bl_description = 'Overwrite defaults with the current global presets'

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        prefs = _get_addon_prefs(context)
        if prefs is None:
            self.report({'ERROR'}, 'Addon preferences not available.')
            return {'CANCELLED'}
        count = ensure_preset_slots(context)
        for idx in range(count):
            src = _get_global_slot(context, idx)
            dst = _get_defaults_slot(context, idx)
            if dst is None:
                continue
            if src is None or src.is_empty or not src.data_json:
                dst.data_json = ''
                dst.is_empty = True
                dst.data_version = DATA_VERSION
                if not dst.name:
                    dst.name = f'Preset {idx + 1}'
            else:
                dst.name = src.name or dst.name or f'Preset {idx + 1}'
                dst.data_version = src.data_version
                dst.data_json = src.data_json
                dst.is_empty = src.is_empty
        self.report({'INFO'}, 'Updated defaults.')
        return {'FINISHED'}


__all__ = [
    'PRESET_SLOT_COUNT',
    'collect_render_config',
    'apply_render_config',
    'ensure_preset_slots',
    'LIME_OT_render_preset_save',
    'LIME_OT_render_preset_apply',
    'LIME_OT_render_preset_clear',
    'LIME_OT_render_preset_reset_all',
    'LIME_OT_render_preset_restore_defaults',
    'LIME_OT_render_preset_update_defaults',
]

