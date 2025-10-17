"""
Render Presets Management Operators

This module provides functionality for managing and applying render presets within
the Lime Pipeline workflow. It handles the creation, storage, and application of
render settings configurations for consistent output across projects.

The preset system supports multiple preset slots, versioning, and integration with
Lime Pipeline's property system for seamless preset management and application.

Key Features:
- Multiple preset slots for different render configurations
- Preset versioning and data validation
- Integration with Lime Pipeline property system
- UI state management and refresh handling
- Batch preset application and management
- Error handling for invalid preset data
"""

import json
from typing import Any, Dict, Optional

import bpy
from bpy.types import Operator
from bpy.props import IntProperty, StringProperty, BoolProperty

from ..props import LimeRenderPresetSlot

ADDON_ID = __package__.split('.')[0]
DATA_VERSION = 1
PRESET_SLOT_COUNT = 4


def _tag_ui_redraw(context, area_types=('PROPERTIES', 'VIEW_3D')) -> None:
    """Request redraw for relevant areas so external panels refresh state."""
    try:
        wm = getattr(context, 'window_manager', None) or bpy.context.window_manager
    except Exception:
        wm = None

    if wm is None:
        return

    for window in wm.windows:
        screen = getattr(window, 'screen', None)
        if screen is None:
            continue
        for area in screen.areas:
            if area.type in area_types:
                area.tag_redraw()


def _refresh_cycles_state(scene=None, view_layer=None):
    """Ensure Cycles sessions notice property changes."""
    scene = scene or getattr(bpy.context, 'scene', None)
    view_layer = view_layer or getattr(bpy.context, 'view_layer', None)

    try:
        if scene and hasattr(scene, "update_tag"):
            scene.update_tag()
    except Exception:
        pass

    try:
        if view_layer and hasattr(view_layer, "update_render_passes"):
            view_layer.update_render_passes(scene=scene)
    except Exception:
        pass


def _default_slot_name(index: int) -> str:
    index = max(0, int(index))
    return f"Preset {index + 1}"


def _normalize_slot_name(name: str, index: int) -> str:
    return (name or '').strip() or _default_slot_name(index)


def _slot_has_payload(slot: Optional['LimeRenderPresetSlot']) -> bool:
    if slot is None or getattr(slot, 'is_empty', True):
        return False
    raw = getattr(slot, 'data_json', '')
    return bool(raw and raw.strip())


def _slot_display_name(slot: Optional['LimeRenderPresetSlot'], index: int) -> str:
    if slot is not None:
        raw = getattr(slot, 'name', '')
        if raw:
            cleaned = raw.strip()
            if cleaned:
                return cleaned
    return _default_slot_name(index)


def _reset_slot(slot: Optional['LimeRenderPresetSlot'], index: int):
    if slot is None:
        return
    slot.data_json = ''
    slot.is_empty = True
    slot.data_version = DATA_VERSION
    slot.name = _default_slot_name(index)


RENDER_PROPS = (
    'engine',
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
        slot_index = len(collection) - 1
        slot.name = _default_slot_name(slot_index)
        slot.is_empty = True
        slot.data_version = DATA_VERSION
        slot.data_json = ''
    while len(collection) > count:
        try:
            collection.remove(len(collection) - 1)
        except Exception:
            break
    for idx, slot in enumerate(collection[:count]):
        slot.name = _normalize_slot_name(getattr(slot, 'name', ''), idx)


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


def sync_cycles_denoising_properties(context) -> bool:
    """
    Sincroniza las propiedades de denoising entre scene.cycles y view_layer.cycles.
    Ambas propiedades deben tener el mismo valor para mantener la consistencia.
    """
    if context is None:
        return False

    scene = context.scene
    view_layer = getattr(context, 'view_layer', None)

    if view_layer is None:
        return False

    cy_scene = getattr(scene, 'cycles', None)
    cy_layer = getattr(view_layer, 'cycles', None)

    if cy_scene is None or cy_layer is None:
        return False

    # Si ambas propiedades son diferentes, sincronízalas usando el valor de scene como referencia
    if cy_scene.use_denoising != cy_layer.use_denoising:
        cy_layer.use_denoising = cy_scene.use_denoising
        return True

    return False


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

    # Sincronizar propiedades de denoising después de aplicar cambios
    changed |= sync_cycles_denoising_properties(context)

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
    preset_name: StringProperty(name='Preset Name', default='')

    @classmethod
    def description(cls, context, props):
        try:
            idx = max(0, int(getattr(props, 'slot_index', 0)))
        except Exception:
            idx = 0
        slot = _get_global_slot(context, idx)
        name = _slot_display_name(slot, idx)
        return f'LMB: Save current render settings into "{name}".'

    def invoke(self, context, event):
        if _get_addon_prefs(context) is None:
            self.report({'ERROR'}, 'Addon preferences not available.')
            return {'CANCELLED'}
        ensure_preset_slots(context)
        slot = _get_global_slot(context, self.slot_index)
        self.preset_name = _slot_display_name(slot, self.slot_index)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, 'preset_name', text='Preset Name')

    def execute(self, context):
        if _get_addon_prefs(context) is None:
            self.report({'ERROR'}, 'Addon preferences not available.')
            return {'CANCELLED'}
        ensure_preset_slots(context)
        payload = collect_render_config(context)
        slot = _get_global_slot(context, self.slot_index)
        if slot is None:
            self.report({'ERROR'}, 'Unable to resolve preset slot.')
            return {'CANCELLED'}
        slot.name = _normalize_slot_name(self.preset_name, self.slot_index)
        _store_slot_payload(slot, payload)
        name = _slot_display_name(slot, self.slot_index)
        self.report({'INFO'}, f'Saved preset "{name}".')
        return {'FINISHED'}


class LIME_OT_render_preset_apply(Operator):
    bl_idname = 'lime.render_preset_apply'
    bl_label = 'Apply Render Preset'
    bl_description = 'Apply the saved render preset to the current scene'

    slot_index: IntProperty(name='Slot', default=0, min=0, max=PRESET_SLOT_COUNT - 1)

    @classmethod
    def description(cls, context, props):
        try:
            idx = max(0, int(getattr(props, 'slot_index', 0)))
        except Exception:
            idx = 0
        slot = _get_global_slot(context, idx)
        return _slot_display_name(slot, idx)

    def execute(self, context):
        ensure_preset_slots(context)
        slot = _get_global_slot(context, self.slot_index)
        payload = _load_slot_payload(slot) if slot else None
        if payload and apply_render_config(context, payload):
            name = _slot_display_name(slot, self.slot_index)
            self.report({'INFO'}, f'Applied preset "{name}".')
            return {'FINISHED'}
        name = _default_slot_name(self.slot_index)
        self.report({'WARNING'}, f'No preset data stored for "{name}".')
        return {'CANCELLED'}


class LIME_OT_render_preset_clear(Operator):
    bl_idname = 'lime.render_preset_clear'
    bl_label = 'Clear Render Preset'
    bl_description = 'Clear the stored data in the preset slot'

    slot_index: IntProperty(name='Slot', default=0, min=0, max=PRESET_SLOT_COUNT - 1)

    @classmethod
    def description(cls, context, props):
        try:
            idx = max(0, int(getattr(props, 'slot_index', 0)))
        except Exception:
            idx = 0
        slot = _get_global_slot(context, idx)
        name = _slot_display_name(slot, idx)
        return f'LMB: Clear preset "{name}". A confirmation prompt protects against mistakes.'

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        ensure_preset_slots(context)
        slot = _get_global_slot(context, self.slot_index)
        if slot is None:
            self.report({'ERROR'}, 'Unable to resolve preset slot.')
            return {'CANCELLED'}
        name = _slot_display_name(slot, self.slot_index)
        _reset_slot(slot, self.slot_index)
        self.report({'INFO'}, f'Cleared preset "{name}".')
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
            _reset_slot(slot, idx)
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
            if not _slot_has_payload(src):
                _reset_slot(dst, idx)
                continue
            dst.name = _normalize_slot_name(getattr(src, 'name', ''), idx)
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
            if not _slot_has_payload(src):
                _reset_slot(dst, idx)
                continue
            dst.name = _normalize_slot_name(getattr(src, 'name', ''), idx)
            dst.data_version = src.data_version
            dst.data_json = src.data_json
            dst.is_empty = src.is_empty
        self.report({'INFO'}, 'Updated defaults.')
        return {'FINISHED'}


class LIME_OT_toggle_denoising_property(Operator):
    bl_idname = 'lime.toggle_denoising_property'
    bl_label = 'Toggle Denoising Property'
    bl_description = 'Cambiar y sincronizar propiedades de denoising entre scene y view layer'

    current_value: BoolProperty(name='Current Value', default=False)

    def execute(self, context):
        if context is None:
            return {'CANCELLED'}

        # Acceder directamente a la escena activa por nombre para máxima precisión
        scene = bpy.data.scenes.get("Scene")  # Usar el nombre específico que menciona el usuario

        if scene is None:
            # Fallback al contexto si no encontramos la escena por nombre
            scene = context.scene

        view_layer = getattr(context, 'view_layer', None)

        if view_layer is None:
            return {'CANCELLED'}

        cy_scene = getattr(scene, 'cycles', None)
        cy_layer = getattr(view_layer, 'cycles', None)

        if cy_scene is None or cy_layer is None:
            return {'CANCELLED'}

        # Toggle del valor actual
        new_value = not self.current_value

        # Establecer el valor en scene.cycles (referencia)
        cy_scene.use_denoising = new_value

        # Sincronizar con view_layer.cycles
        cy_layer.use_denoising = new_value

        _refresh_cycles_state(scene=scene, view_layer=view_layer)
        _tag_ui_redraw(context)

        return {'FINISHED'}


class LIME_OT_toggle_preview_denoising_property(Operator):
    bl_idname = 'lime.toggle_preview_denoising_property'
    bl_label = 'Toggle Preview Denoising Property'
    bl_description = 'Cambiar propiedad de denoising para preview en Cycles (independiente del render denoising)'

    current_value: BoolProperty(name='Current Value', default=False)

    def execute(self, context):
        if context is None:
            return {'CANCELLED'}

        # Acceder directamente a la escena activa por nombre para máxima precisión
        scene = bpy.data.scenes.get("Scene")  # Usar el nombre específico que menciona el usuario

        if scene is None:
            # Fallback al contexto si no encontramos la escena por nombre
            scene = context.scene

        cy_scene = getattr(scene, 'cycles', None)

        if cy_scene is None:
            return {'CANCELLED'}

        # Toggle del valor actual
        new_value = not self.current_value

        # Solo afectar el denoising de preview, mantener independencia con render denoising
        cy_scene.use_preview_denoising = new_value

        _refresh_cycles_state(scene=scene)
        _tag_ui_redraw(context)

        return {'FINISHED'}


class LIME_OT_render_apply_resolution_shortcut(Operator):
    bl_idname = 'lime.render_apply_resolution_shortcut'
    bl_label = 'Apply Resolution Shortcut'
    bl_description = 'Apply a preset resolution pair to the active scene render settings'

    base_x: IntProperty(name='Width', default=1920, min=1)
    base_y: IntProperty(name='Height', default=1080, min=1)
    label: StringProperty(name='Label', default='', options={'HIDDEN'})

    @classmethod
    def description(cls, context, props):
        label = getattr(props, 'label', '') or 'Resolution'
        scene = getattr(context, 'scene', None)
        use_uhd = bool(getattr(scene, 'lime_render_shortcut_use_uhd', False)) if scene else False
        suffix = ' (UHD)' if use_uhd else ' (HD)'
        return f'Apply {label}{suffix} resolution shortcut.'

    def execute(self, context):
        scene = context.scene
        render = scene.render
        use_uhd = bool(getattr(scene, 'lime_render_shortcut_use_uhd', False))
        scale = 2 if use_uhd else 1

        # Apply resolution immediately
        render.resolution_x = int(self.base_x * scale)
        render.resolution_y = int(self.base_y * scale)

        # Store base resolution values for UHD toggle auto-update
        wm_state = getattr(context.window_manager, 'lime_pipeline', None)
        if wm_state:
            wm_state.lime_shortcut_base_x = self.base_x
            wm_state.lime_shortcut_base_y = self.base_y

        return {'FINISHED'}

__all__ = [
    'PRESET_SLOT_COUNT',
    'collect_render_config',
    'apply_render_config',
    'sync_cycles_denoising_properties',
    'ensure_preset_slots',
    'LIME_OT_render_preset_save',
    'LIME_OT_render_preset_apply',
    'LIME_OT_render_preset_clear',
    'LIME_OT_render_preset_reset_all',
    'LIME_OT_render_preset_restore_defaults',
    'LIME_OT_render_preset_update_defaults',
    'LIME_OT_toggle_denoising_property',
    'LIME_OT_toggle_preview_denoising_property',
    'LIME_OT_render_apply_resolution_shortcut',
]
