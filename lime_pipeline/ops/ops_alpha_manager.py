from __future__ import annotations

import re
from typing import Iterable, Sequence

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Operator, PropertyGroup

ALPHA_PROP_PREFIX = "lp_alpha_event_"
ALPHA_FCURVE_GROUP = "Lime Alpha Events"
OBJECT_EVENTS_PROP = "lp_alpha_events"
OBJECT_EVENTS_DELIM = "|"  # Storage delimiter for multiple slugs in a single ID prop
OBJECT_BAKE_FRAMES_PROP = "_lp_alpha_bake_frames"
OBJECT_BAKED_FLAG_PROP = "_lp_alpha_baked"
DEFAULT_EVENT_NAME = "Fade"
DEFAULT_EVENT_DURATION = 24
CURVE_ITEMS = [
    ('LINEAR', 'Linear', 'Use linear interpolation between start and end.', 'IPO_LINEAR', 0),
    ('BEZIER', 'Bezier', 'Use bezier interpolation.', 'IPO_BEZIER', 1),
    ('EASE_IN', 'Ease In', 'Slow start, fast finish.', 'IPO_SINE', 2),
    ('EASE_OUT', 'Ease Out', 'Fast start, slow finish.', 'IPO_BACK', 3),
    ('EASE_IN_OUT', 'Ease In/Out', 'Slow start and end.', 'IPO_EASE_IN_OUT', 4),
]
FRAME_TOLERANCE = 1e-4

# Debug toggle (set to True to get verbose prints)
_ALPHA_DEBUG = False

def _alpha_log(msg: str) -> None:
    if _ALPHA_DEBUG:
        try:
            print(f"[LP][Alpha] {msg}")
        except Exception:
            pass


def _scene_from_context(context) -> bpy.types.Scene | None:
    if context and getattr(context, "scene", None) is not None:
        return context.scene
    return bpy.context.scene


def _slugify(name: str, existing: set[str]) -> str:
    base = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip()).strip("_").lower()
    if not base:
        base = "event"
    slug = base
    suffix = 1
    while slug in existing:
        slug = f"{base}_{suffix:02d}"
        suffix += 1
    return slug


def _unique_event_name(scene: bpy.types.Scene, name: str, exclude: PropertyGroup | None = None) -> str:
    events = getattr(scene, "lime_tb_alpha_events", [])
    existing = {evt.name for evt in events if evt is not exclude}
    if name not in existing:
        return name
    suffix = 2
    while True:
        candidate = f"{name} {suffix:02d}"
        if candidate not in existing:
            return candidate
        suffix += 1


def _prop_name(slug: str) -> str:
    return f"{ALPHA_PROP_PREFIX}{slug}"


def _ensure_scene_action(scene: bpy.types.Scene) -> bpy.types.Action | None:
    ad = scene.animation_data
    if ad is None:
        ad = scene.animation_data_create()
    if ad.action is None:
        ad.action = bpy.data.actions.new(name="LP_SceneAlphaEvents")
    return ad.action


def _get_event_fcurve(scene: bpy.types.Scene, prop_name: str) -> bpy.types.FCurve | None:
    ad = scene.animation_data
    action = getattr(ad, "action", None) if ad else None
    if action is None:
        return None
    data_path = f'"{prop_name}"'
    fc = action.fcurves.find(f'["{prop_name}"]')
    if fc is None:
        fc = action.fcurves.find(data_path)
    return fc


def _ensure_event_fcurve(scene: bpy.types.Scene, prop_name: str) -> bpy.types.FCurve | None:
    action = _ensure_scene_action(scene)
    if action is None:
        return None
    fc = action.fcurves.find(f'["{prop_name}"]')
    if fc is None:
        fc = action.fcurves.new(data_path=f'["{prop_name}"]')
    if fc.group is None:
        group = action.groups.get(ALPHA_FCURVE_GROUP)
        if group is None:
            group = action.groups.new(name=ALPHA_FCURVE_GROUP)
        fc.group = group
    return fc


def _write_event_keyframes(fc: bpy.types.FCurve, start: int, end: int) -> None:
    kfs = fc.keyframe_points
    if len(kfs) != 2:
        kfs.clear()
        kfs.add(count=2)
    kfs[0].co = (float(start), 0.0)
    kfs[0].handle_left = (float(start) - 1.0, 0.0)
    kfs[0].handle_right = (float(start) + 1.0, 0.0)
    kfs[-1].co = (float(end), 1.0)
    kfs[-1].handle_left = (float(end) - 1.0, 1.0)
    kfs[-1].handle_right = (float(end) + 1.0, 1.0)
    fc.update()


def _apply_curve_settings(fc: bpy.types.FCurve | None, curve: str) -> None:
    if fc is None:
        return
    kfs = fc.keyframe_points
    if not kfs:
        return
    if curve == 'LINEAR':
        for kp in kfs:
            kp.interpolation = 'LINEAR'
    else:
        for kp in kfs:
            kp.interpolation = 'BEZIER'
            if hasattr(kp, 'easing'):
                kp.easing = 'AUTO'
        if hasattr(kfs[0], 'easing'):
            if curve == 'EASE_IN':
                kfs[0].easing = 'EASE_IN'
            elif curve == 'EASE_OUT':
                kfs[0].easing = 'EASE_OUT'
            elif curve == 'EASE_IN_OUT':
                kfs[0].easing = 'EASE_OUT'
        if len(kfs) > 1 and hasattr(kfs[-1], 'easing'):
            if curve == 'EASE_IN':
                kfs[-1].easing = 'EASE_IN'
            elif curve == 'EASE_OUT':
                kfs[-1].easing = 'EASE_OUT'
            elif curve == 'EASE_IN_OUT':
                kfs[-1].easing = 'EASE_IN'
    fc.update()


def ensure_event_tracks(scene: bpy.types.Scene | None, event: 'LimeTBAlphaEvent', reset_keys: bool = False) -> None:
    if scene is None or event is None or not event.slug:
        return
    if event.frame_end <= event.frame_start:
        event.frame_end = event.frame_start + 1
    prop_name = _prop_name(event.slug)
    if prop_name not in scene:
        scene[prop_name] = 0.0
    fc = _ensure_event_fcurve(scene, prop_name)
    if fc is None:
        return
    if reset_keys or len(fc.keyframe_points) < 2:
        _write_event_keyframes(fc, event.frame_start, event.frame_end)
    else:
        fc.keyframe_points[0].co.x = float(event.frame_start)
        fc.keyframe_points[-1].co.x = float(event.frame_end)
        fc.update()
    _apply_curve_settings(fc, event.curve)
    # Touch scene tag so fcurves update
    try:
        scene.animation_data.action.use_fake_user = scene.animation_data.action.use_fake_user
    except Exception:
        pass
    # Force evaluation at current frame and refresh viewport
    try:
        scene.frame_set(scene.frame_current)
    except Exception:
        pass
    try:
        if hasattr(bpy.context, "view_layer"):
            bpy.context.view_layer.update()
    except Exception:
        pass


def find_event_by_slug(scene: bpy.types.Scene, slug: str) -> 'LimeTBAlphaEvent | None':
    events = getattr(scene, "lime_tb_alpha_events", [])
    for event in events:
        if event.slug == slug:
            return event
    return None


def create_event(scene: bpy.types.Scene, name: str | None = None) -> 'LimeTBAlphaEvent':
    events = scene.lime_tb_alpha_events
    new_event = events.add()
    base_name = name or DEFAULT_EVENT_NAME
    new_event.name = _unique_event_name(scene, base_name, exclude=new_event)
    existing_slugs = {evt.slug for evt in events if evt is not new_event and getattr(evt, "slug", "")}
    new_event.slug = _slugify(new_event.name, existing_slugs)
    current = int(scene.frame_current)
    new_event.frame_start = current
    new_event.frame_end = current + DEFAULT_EVENT_DURATION
    new_event.curve = 'LINEAR'
    new_event.invert = False
    ensure_event_tracks(scene, new_event, reset_keys=True)
    return new_event


def duplicate_event(scene: bpy.types.Scene, event: 'LimeTBAlphaEvent') -> 'LimeTBAlphaEvent':
    events = scene.lime_tb_alpha_events
    new_event = events.add()
    new_event.name = _unique_event_name(scene, f"{event.name}", exclude=new_event)
    existing_slugs = {evt.slug for evt in events if evt is not new_event and getattr(evt, "slug", "")}
    new_event.slug = _slugify(new_event.name, existing_slugs)
    new_event.frame_start = event.frame_start
    new_event.frame_end = event.frame_end
    new_event.curve = event.curve
    new_event.invert = event.invert
    ensure_event_tracks(scene, new_event, reset_keys=True)
    src_fc = _get_event_fcurve(scene, _prop_name(event.slug))
    dst_fc = _ensure_event_fcurve(scene, _prop_name(new_event.slug))
    if src_fc and dst_fc:
        dst_fc.keyframe_points.clear()
        dst_fc.keyframe_points.add(count=len(src_fc.keyframe_points))
        for idx, kp in enumerate(src_fc.keyframe_points):
            dst = dst_fc.keyframe_points[idx]
            dst.co = kp.co
            dst.handle_left = kp.handle_left
            dst.handle_right = kp.handle_right
            dst.interpolation = kp.interpolation
            if hasattr(dst, 'easing') and hasattr(kp, 'easing'):
                dst.easing = kp.easing
        dst_fc.update()
    _apply_curve_settings(dst_fc, new_event.curve)
    return new_event


def delete_event(scene: bpy.types.Scene, event: 'LimeTBAlphaEvent') -> int:
    slug = event.slug
    prop_name = _prop_name(slug) if slug else ""
    removed = 0
    if prop_name and prop_name in scene:
        try:
            del scene[prop_name]
        except Exception:
            pass
    fc = _get_event_fcurve(scene, prop_name)
    action = scene.animation_data.action if scene.animation_data else None
    if fc and action:
        action.fcurves.remove(fc)
    for obj in scene.objects:
        slugs = _get_object_event_slugs(obj)
        if slug in slugs:
            slugs = [s for s in slugs if s != slug]
            _store_object_event_slugs(obj, slugs)
            rebuild_object_driver(scene, obj)
            removed += 1
    events = scene.lime_tb_alpha_events
    try:
        index = list(events).index(event)
    except ValueError:
        index = scene.lime_tb_alpha_events_index
    events.remove(index)
    scene.lime_tb_alpha_events_index = min(max(index, 0), len(events) - 1) if events else -1
    return removed


def rename_event(scene: bpy.types.Scene, event: 'LimeTBAlphaEvent', new_name: str) -> tuple[bool, str]:
    name = new_name.strip()
    if not name:
        return False, "Name cannot be empty"
    name = _unique_event_name(scene, name, exclude=event)
    existing_slugs = {evt.slug for evt in scene.lime_tb_alpha_events if evt is not event}
    new_slug = _slugify(name, existing_slugs)
    old_slug = event.slug
    if not old_slug:
        event.name = name
        event.slug = new_slug
        ensure_event_tracks(scene, event)
        return True, f"Event renamed to {name}"
    if old_slug == new_slug:
        event.name = name
        return True, f"Event renamed to {name}"
    old_prop = _prop_name(old_slug)
    new_prop = _prop_name(new_slug)
    value = scene.get(old_prop, 0.0)
    scene[new_prop] = value
    fc = _get_event_fcurve(scene, old_prop)
    if fc:
        fc.data_path = f'["{new_prop}"]'
    if old_prop in scene:
        try:
            del scene[old_prop]
        except Exception:
            pass
    event.slug = new_slug
    event.name = name
    ensure_event_tracks(scene, event)
    affected = 0
    for obj in scene.objects:
        slugs = _get_object_event_slugs(obj)
        if old_slug in slugs:
            slugs = [new_slug if s == old_slug else s for s in slugs]
            _store_object_event_slugs(obj, slugs)
            rebuild_object_driver(scene, obj)
            affected += 1
    return True, f"Event renamed to {name} (updated {affected} objects)"


def _get_object_event_event_list_from_string(raw: str) -> list[str]:
    parts = [p.strip() for p in str(raw).split(OBJECT_EVENTS_DELIM)]
    parts = [p for p in parts if p]
    # Deduplicate preserving order
    return list(dict.fromkeys(parts))


def _get_object_event_slugs(obj: bpy.types.Object) -> list[str]:
    raw = obj.get(OBJECT_EVENTS_PROP, None)
    if raw is None:
        return []
    # Preferred storage: single delimited string
    if isinstance(raw, str):
        return _get_object_event_event_list_from_string(raw)
    # Backward compatibility: list/tuple/iterable of strings
    if isinstance(raw, (list, tuple)):
        values = [str(v) for v in raw if isinstance(v, (str, bytes)) and v]
        return list(dict.fromkeys(values))
    # Fallback: attempt iteration (IDPropArray-like)
    try:
        values = [str(v) for v in raw if v]
        return list(dict.fromkeys(values))
    except Exception:
        return []


def _store_object_event_slugs(obj: bpy.types.Object, slugs: Sequence[str]) -> None:
    unique = [s for s in list(dict.fromkeys(slugs)) if s]
    if unique:
        # Store as a single delimited string for robustness
        obj[OBJECT_EVENTS_PROP] = OBJECT_EVENTS_DELIM.join(unique)
    elif OBJECT_EVENTS_PROP in obj:
        del obj[OBJECT_EVENTS_PROP]


def _build_driver_expression(events: Sequence['LimeTBAlphaEvent']) -> str:
    """Build a driver expression that supports multiple events with proper invert semantics.

    Semantics:
    - Non-inverted events contribute opacity via union: base = 1 - Π(1 - ev)
    - Inverted events act as cutters: cut = Π(1 - ev)
    - Final alpha = base * cut

    This ensures that an inverted event outside its active range (ev=0) is neutral (cut=1),
    avoiding the undesired behavior of forcing visibility to 1.0 before it starts.
    """
    if not events:
        return "0.0"
    non_inv_terms: list[str] = []
    inv_terms: list[str] = []
    for idx, event in enumerate(events):
        var = f"ev{idx}"
        if getattr(event, 'invert', False):
            # Cutter factor multiplies by (1 - ev)
            inv_terms.append(f"(1 - {var})")
        else:
            # Base union factor uses (1 - ev) inside the product, and subtracts from 1
            non_inv_terms.append(f"(1 - {var})")
    base_expr = "0.0" if not non_inv_terms else f"(1 - (" + " * ".join(non_inv_terms) + "))"
    cut_expr = "1.0" if not inv_terms else "(" + " * ".join(inv_terms) + ")"
    return f"({base_expr}) * ({cut_expr})"


def rebuild_object_driver(scene: bpy.types.Scene, obj: bpy.types.Object) -> None:
    slugs = _get_object_event_slugs(obj)
    valid_events: list[LimeTBAlphaEvent] = []
    cleaned_slugs: list[str] = []
    for slug in slugs:
        event = find_event_by_slug(scene, slug)
        if event is None:
            continue
        ensure_event_tracks(scene, event)
        valid_events.append(event)
        cleaned_slugs.append(slug)
    if cleaned_slugs != slugs:
        _store_object_event_slugs(obj, cleaned_slugs)
        slugs = cleaned_slugs
    try:
        obj.driver_remove('color', 3)
    except Exception:
        pass
    if not valid_events:
        obj.color[3] = 0.0
        return
    fcurve = obj.driver_add('color', 3)
    drv = fcurve.driver
    drv.type = 'SCRIPTED'
    while drv.variables:
        drv.variables.remove(drv.variables[0])
    for idx, event in enumerate(valid_events):
        var = drv.variables.new()
        var.name = f"ev{idx}"
        target = var.targets[0]
        target.id_type = 'SCENE'
        target.id = scene
        target.data_path = f'["{_prop_name(event.slug)}"]'
    drv.expression = _build_driver_expression(valid_events)
    try:
        fcurve.update()
    except Exception:
        pass
    # Nudge depsgraph/viewport so the effect is visible immediately
    try:
        obj.update_tag()
    except Exception:
        pass
    try:
        scene.frame_set(scene.frame_current)
    except Exception:
        pass
    try:
        if hasattr(bpy.context, "view_layer"):
            bpy.context.view_layer.update()
    except Exception:
        pass


# LIVE sync handler: write evaluated event values into scene ID props each frame
_ALPHA_LIVE_HANDLER = None

def _alpha_live_frame_change_post(scene: bpy.types.Scene):
    try:
        mode = getattr(scene, 'lime_tb_alpha_mode', 'LIVE')
    except Exception:
        mode = 'LIVE'
    if mode != 'LIVE':
        return
    events = getattr(scene, 'lime_tb_alpha_events', [])
    if not events:
        return
    frame = float(scene.frame_current)
    _alpha_log(f"frame_change_post: frame={frame} events={len(events)}")
    updated = False
    for event in events:
        slug = getattr(event, 'slug', '')
        if not slug:
            continue
        prop = _prop_name(slug)
        try:
            value = evaluate_event(scene, event, frame)
            prev = float(scene.get(prop, 0.0))
            _alpha_log(f"  evt={slug} prev={prev:.6f} eval={value:.6f}")
            if abs(prev - value) > 1e-6:
                scene[prop] = value
                updated = True
                _alpha_log(f"  -> wrote scene['{prop}']={value:.6f}")
        except Exception:
            continue
    if updated:
        # Touch objects that use alpha so viewport notices
        try:
            # Tag scene so depsgraph knows an ID prop changed that drivers depend on
            scene.update_tag()
        except Exception:
            pass
        # During playback, avoid forcing a full view layer update
        try:
            scr = getattr(bpy.context, "screen", None)
            if scr and getattr(scr, "is_animation_playing", False):
                return
        except Exception:
            pass
        try:
            if hasattr(bpy.context, 'view_layer'):
                bpy.context.view_layer.update()
        except Exception:
            pass

def enable_alpha_live_handler():
    global _ALPHA_LIVE_HANDLER
    if _ALPHA_LIVE_HANDLER is None:
        _ALPHA_LIVE_HANDLER = _alpha_live_frame_change_post
    try:
        if _ALPHA_LIVE_HANDLER not in bpy.app.handlers.frame_change_post:
            bpy.app.handlers.frame_change_post.append(_ALPHA_LIVE_HANDLER)
            _alpha_log("Enabled frame_change_post handler")
    except Exception:
        pass

def disable_alpha_live_handler():
    global _ALPHA_LIVE_HANDLER
    try:
        if _ALPHA_LIVE_HANDLER in bpy.app.handlers.frame_change_post:
            bpy.app.handlers.frame_change_post.remove(_ALPHA_LIVE_HANDLER)
            _alpha_log("Disabled frame_change_post handler")
    except Exception:
        pass


def rebuild_all_drivers(scene: bpy.types.Scene) -> int:
    count = 0
    for obj in scene.objects:
        if _get_object_event_slugs(obj):
            rebuild_object_driver(scene, obj)
            count += 1
    return count


def rebuild_drivers_for_event(scene: bpy.types.Scene, slug: str) -> int:
    count = 0
    for obj in scene.objects:
        if slug in _get_object_event_slugs(obj):
            rebuild_object_driver(scene, obj)
            count += 1
    return count


def assign_event_to_objects(scene: bpy.types.Scene, event: 'LimeTBAlphaEvent', objects: Iterable[bpy.types.Object]) -> int:
    assigned = 0
    for obj in objects:
        if obj is None:
            continue
        slugs = _get_object_event_slugs(obj)
        if event.slug in slugs:
            continue
        slugs.append(event.slug)
        _store_object_event_slugs(obj, slugs)
        rebuild_object_driver(scene, obj)
        assigned += 1
    return assigned


def remove_event_from_objects(scene: bpy.types.Scene, event: 'LimeTBAlphaEvent', objects: Iterable[bpy.types.Object]) -> int:
    removed = 0
    for obj in objects:
        slugs = _get_object_event_slugs(obj)
        if event.slug not in slugs:
            continue
        slugs = [s for s in slugs if s != event.slug]
        _store_object_event_slugs(obj, slugs)
        rebuild_object_driver(scene, obj)
        removed += 1
    return removed


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def evaluate_event(scene: bpy.types.Scene, event: 'LimeTBAlphaEvent', frame: float) -> float:
    prop_name = _prop_name(event.slug)
    fc = _get_event_fcurve(scene, prop_name)
    if fc:
        return _clamp(fc.evaluate(frame))
    return _clamp(float(scene.get(prop_name, 0.0)))


def combined_alpha(scene: bpy.types.Scene, events: Sequence['LimeTBAlphaEvent'], frame: float) -> float:
    """Mirror of driver-side expression in Python for baking.

    - base = 1 - Π(1 - ev_non_inverted)
    - cut  = Π(1 - ev_inverted)
    - alpha = base * cut
    """
    if not events:
        return 0.0
    base_product = 1.0
    have_base = False
    cut_product = 1.0
    for event in events:
        value = evaluate_event(scene, event, frame)
        if getattr(event, 'invert', False):
            # Cutter
            cut_product *= (1.0 - value)
        else:
            have_base = True
            base_product *= (1.0 - value)
    base = 0.0 if not have_base else (1.0 - base_product)
    alpha = base * cut_product
    return _clamp(alpha)


def _color_fcurve(obj: bpy.types.Object) -> bpy.types.FCurve | None:
    ad = obj.animation_data
    action = getattr(ad, "action", None) if ad else None
    if action is None:
        return None
    return action.fcurves.find('color', index=3)


def bake_alpha(scene: bpy.types.Scene, objects: Iterable[bpy.types.Object], frame_step: int = 1) -> tuple[int, list[str]]:
    baked = 0
    skipped: list[str] = []
    step = max(1, frame_step)
    for obj in objects:
        slugs = _get_object_event_slugs(obj)
        events = [find_event_by_slug(scene, slug) for slug in slugs]
        events = [evt for evt in events if evt is not None]
        if not events:
            continue
        fc = _color_fcurve(obj)
        if fc and OBJECT_BAKE_FRAMES_PROP not in obj:
            skipped.append(obj.name)
            continue
        start = min(evt.frame_start for evt in events)
        end = max(evt.frame_end for evt in events)
        if start > end:
            start, end = end, start
        frames = list(range(start - 1, end + 2, step))
        values = [combined_alpha(scene, events, frame) for frame in frames]
        try:
            obj.driver_remove('color', 3)
        except Exception:
            pass
        obj.animation_data_create()
        for frame, value in zip(frames, values):
            obj.color[3] = value
            obj.keyframe_insert(data_path='color', index=3, frame=float(frame))
        obj[OBJECT_BAKE_FRAMES_PROP] = frames
        obj[OBJECT_BAKED_FLAG_PROP] = True
        baked += 1
    return baked, skipped


def unbake_alpha(scene: bpy.types.Scene, objects: Iterable[bpy.types.Object]) -> int:
    restored = 0
    for obj in objects:
        if not obj.get(OBJECT_BAKED_FLAG_PROP):
            continue
        frames = list(obj.get(OBJECT_BAKE_FRAMES_PROP, []))
        fc = _color_fcurve(obj)
        if fc:
            for frame in frames:
                for kp in list(fc.keyframe_points):
                    if abs(kp.co.x - float(frame)) < FRAME_TOLERANCE:
                        fc.keyframe_points.remove(kp)
            if not fc.keyframe_points:
                action = obj.animation_data.action if obj.animation_data else None
                if action:
                    action.fcurves.remove(fc)
        if OBJECT_BAKE_FRAMES_PROP in obj:
            del obj[OBJECT_BAKE_FRAMES_PROP]
        if OBJECT_BAKED_FLAG_PROP in obj:
            del obj[OBJECT_BAKED_FLAG_PROP]
        rebuild_object_driver(scene, obj)
        restored += 1
    return restored


def _on_event_frames_update(self: 'LimeTBAlphaEvent', context) -> None:
    if getattr(self, "_lp_lock_frames", False):
        return
    setattr(self, "_lp_lock_frames", True)
    try:
        scene = _scene_from_context(context)
        ensure_event_tracks(scene, self)
    finally:
        setattr(self, "_lp_lock_frames", False)


def _on_event_curve_update(self: 'LimeTBAlphaEvent', context) -> None:
    scene = _scene_from_context(context)
    if scene is None or not self.slug:
        return
    fc = _ensure_event_fcurve(scene, _prop_name(self.slug))
    _apply_curve_settings(fc, self.curve)


def _on_event_invert_update(self: 'LimeTBAlphaEvent', context) -> None:
    scene = _scene_from_context(context)
    if scene is None or not self.slug:
        return
    rebuild_drivers_for_event(scene, self.slug)


class LimeTBAlphaEvent(PropertyGroup):
    slug: StringProperty(name="Slug", default="", options={'HIDDEN'})
    name: StringProperty(name="Name", default="Fade", description="Display name for the fade event.")
    frame_start: IntProperty(
        name="Start",
        description="Start frame where the fade begins (value 0).",
        default=1,
        update=_on_event_frames_update,
    )
    frame_end: IntProperty(
        name="End",
        description="End frame where the fade reaches 1.",
        default=24,
        update=_on_event_frames_update,
    )
    curve: EnumProperty(
        name="Curve",
        description="Interpolation curve used between start and end.",
        items=CURVE_ITEMS,
        default='LINEAR',
        update=_on_event_curve_update,
    )
    invert: BoolProperty(
        name="Invert",
        description="Invert the fade so 1 keeps the object visible and 0 hides it.",
        default=False,
        update=_on_event_invert_update,
    )


class LIME_TB_OT_alpha_event_add(Operator):
    bl_idname = "lime.tb_alpha_event_add"
    bl_label = "Add Fade Event"
    bl_description = "Create a new fade event on the current scene."

    def execute(self, context):
        scene = context.scene
        event = create_event(scene)
        scene.lime_tb_alpha_events_index = len(scene.lime_tb_alpha_events) - 1
        self.report({'INFO'}, f"Added event '{event.name}'")
        return {'FINISHED'}


class LIME_TB_OT_alpha_event_duplicate(Operator):
    bl_idname = "lime.tb_alpha_event_duplicate"
    bl_label = "Duplicate Fade Event"
    bl_description = "Duplicate the active fade event, including its animation."

    def execute(self, context):
        scene = context.scene
        events = scene.lime_tb_alpha_events
        idx = scene.lime_tb_alpha_events_index
        if not events or not (0 <= idx < len(events)):
            self.report({'WARNING'}, "No active event to duplicate")
            return {'CANCELLED'}
        new_event = duplicate_event(scene, events[idx])
        scene.lime_tb_alpha_events_index = len(events) - 1
        self.report({'INFO'}, f"Duplicated event as '{new_event.name}'")
        return {'FINISHED'}


class LIME_TB_OT_alpha_event_delete(Operator):
    bl_idname = "lime.tb_alpha_event_delete"
    bl_label = "Delete Fade Event"
    bl_description = "Remove the active fade event and detach it from all objects."

    @classmethod
    def poll(cls, context):
        events = getattr(context.scene, 'lime_tb_alpha_events', None)
        return events and len(events) > 0

    def execute(self, context):
        scene = context.scene
        idx = scene.lime_tb_alpha_events_index
        events = scene.lime_tb_alpha_events
        if not events or not (0 <= idx < len(events)):
            self.report({'WARNING'}, "No active event to delete")
            return {'CANCELLED'}
        removed = delete_event(scene, events[idx])
        self.report({'INFO'}, f"Deleted event and updated {removed} objects")
        return {'FINISHED'}


class LIME_TB_OT_alpha_event_rename(Operator):
    bl_idname = "lime.tb_alpha_event_rename"
    bl_label = "Rename Fade Event"
    bl_description = "Rename the active fade event."

    new_name: StringProperty(name="Name", description="New event name")

    def invoke(self, context, event):
        scene = context.scene
        idx = scene.lime_tb_alpha_events_index
        events = scene.lime_tb_alpha_events
        if not events or not (0 <= idx < len(events)):
            self.report({'WARNING'}, "No active event to rename")
            return {'CANCELLED'}
        self.new_name = events[idx].name
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        scene = context.scene
        idx = scene.lime_tb_alpha_events_index
        events = scene.lime_tb_alpha_events
        if not events or not (0 <= idx < len(events)):
            self.report({'WARNING'}, "No active event to rename")
            return {'CANCELLED'}
        ok, msg = rename_event(scene, events[idx], self.new_name)
        if not ok:
            self.report({'WARNING'}, msg)
            return {'CANCELLED'}
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class LIME_TB_OT_alpha_event_assign(Operator):
    bl_idname = "lime.tb_alpha_event_assign"
    bl_label = "Assign Selection"
    bl_description = "Assign the selected objects to the active fade event."

    def execute(self, context):
        scene = context.scene
        events = scene.lime_tb_alpha_events
        idx = scene.lime_tb_alpha_events_index
        if not events or not (0 <= idx < len(events)):
            self.report({'WARNING'}, "No active event selected")
            return {'CANCELLED'}
        event = events[idx]
        objects = context.selected_objects
        if not objects:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}
        assigned = assign_event_to_objects(scene, event, objects)
        if assigned == 0:
            self.report({'INFO'}, "Objects already assigned")
        else:
            self.report({'INFO'}, f"Assigned {assigned} objects")
        return {'FINISHED'}


class LIME_TB_OT_alpha_event_unassign(Operator):
    bl_idname = "lime.tb_alpha_event_unassign"
    bl_label = "Remove Selection"
    bl_description = "Remove the selected objects from the active fade event."

    def execute(self, context):
        scene = context.scene
        events = scene.lime_tb_alpha_events
        idx = scene.lime_tb_alpha_events_index
        if not events or not (0 <= idx < len(events)):
            self.report({'WARNING'}, "No active event selected")
            return {'CANCELLED'}
        event = events[idx]
        objects = context.selected_objects
        if not objects:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}
        removed = remove_event_from_objects(scene, event, objects)
        self.report({'INFO'}, f"Removed {removed} objects")
        return {'FINISHED'}


class LIME_TB_OT_alpha_event_select_members(Operator):
    bl_idname = "lime.tb_alpha_event_select_members"
    bl_label = "Select Members"
    bl_description = "Select all objects that use the active fade event."

    def execute(self, context):
        scene = context.scene
        events = scene.lime_tb_alpha_events
        idx = scene.lime_tb_alpha_events_index
        if not events or not (0 <= idx < len(events)):
            self.report({'WARNING'}, "No active event selected")
            return {'CANCELLED'}
        members = [obj for obj in scene.objects if events[idx].slug in _get_object_event_slugs(obj)]
        if not members:
            self.report({'INFO'}, "Event has no objects")
            return {'CANCELLED'}
        for obj in scene.objects:
            obj.select_set(False)
        for obj in members:
            obj.select_set(True)
        context.view_layer.objects.active = members[0]
        self.report({'INFO'}, f"Selected {len(members)} objects")
        return {'FINISHED'}


class LIME_TB_OT_alpha_set_mode(Operator):
    bl_idname = "lime.tb_alpha_set_mode"
    bl_label = "Switch Alpha Mode"
    bl_description = "Switch between live drivers and baked keyframes for all alpha-managed objects."

    mode: EnumProperty(items=[('LIVE', 'Live', ''), ('BAKE', 'Bake', '')])

    def execute(self, context):
        scene = context.scene
        objects = [obj for obj in scene.objects if _get_object_event_slugs(obj)]
        if self.mode == 'BAKE':
            baked, skipped = bake_alpha(scene, objects)
            if baked == 0:
                self.report({'WARNING'}, "Nothing to bake")
                return {'CANCELLED'}
            if skipped:
                self.report({'WARNING'}, f"Skipped objects with existing keyframes: {', '.join(skipped)}")
            self.report({'INFO'}, f"Baked {baked} objects")
        else:
            restored = unbake_alpha(scene, objects)
            if restored == 0:
                self.report({'WARNING'}, "Nothing to restore")
                return {'CANCELLED'}
            self.report({'INFO'}, f"Restored drivers on {restored} objects")
        scene.lime_tb_alpha_mode = self.mode
        # Toggle live handler and force a depsgraph update
        try:
            if self.mode == 'LIVE':
                enable_alpha_live_handler()
            else:
                disable_alpha_live_handler()
        except Exception:
            pass
        try:
            if hasattr(bpy.context, "view_layer"):
                bpy.context.view_layer.update()
        except Exception:
            pass
        return {'FINISHED'}


class LIME_TB_OT_alpha_rebuild(Operator):
    bl_idname = "lime.tb_alpha_rebuild"
    bl_label = "Rebuild Drivers"
    bl_description = "Rebuild drivers for all objects assigned to fade events."

    def execute(self, context):
        count = rebuild_all_drivers(context.scene)
        self.report({'INFO'}, f"Rebuilt {count} drivers")
        return {'FINISHED'}


CLASSES = (
    LimeTBAlphaEvent,
    LIME_TB_OT_alpha_event_add,
    LIME_TB_OT_alpha_event_duplicate,
    LIME_TB_OT_alpha_event_delete,
    LIME_TB_OT_alpha_event_rename,
    LIME_TB_OT_alpha_event_assign,
    LIME_TB_OT_alpha_event_unassign,
    LIME_TB_OT_alpha_event_select_members,
    LIME_TB_OT_alpha_set_mode,
    LIME_TB_OT_alpha_rebuild,
)


def register_alpha_props():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.lime_tb_alpha_events = CollectionProperty(type=LimeTBAlphaEvent)
    bpy.types.Scene.lime_tb_alpha_events_index = IntProperty(default=-1)
    bpy.types.Scene.lime_tb_alpha_mode = EnumProperty(
        name="Alpha Mode",
        description="Indicates whether the alpha manager is using live drivers or baked keyframes.",
        items=[('LIVE', 'Live (Drivers)', ''), ('BAKE', 'Bake (Keyframes)', '')],
        default='LIVE',
    )
    # Enable handler by default when registering (default mode is LIVE)
    try:
        enable_alpha_live_handler()
    except Exception:
        pass


def unregister_alpha_props():
    for attr in (
        'lime_tb_alpha_events',
        'lime_tb_alpha_events_index',
        'lime_tb_alpha_mode',
    ):
        if hasattr(bpy.types.Scene, attr):
            delattr(bpy.types.Scene, attr)
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    try:
        disable_alpha_live_handler()
    except Exception:
        pass


__all__ = [
    'LimeTBAlphaEvent',
    'register_alpha_props',
    'unregister_alpha_props',
    'LIME_TB_OT_alpha_event_add',
    'LIME_TB_OT_alpha_event_duplicate',
    'LIME_TB_OT_alpha_event_delete',
    'LIME_TB_OT_alpha_event_rename',
    'LIME_TB_OT_alpha_event_assign',
    'LIME_TB_OT_alpha_event_unassign',
    'LIME_TB_OT_alpha_event_select_members',
    'LIME_TB_OT_alpha_set_mode',
    'LIME_TB_OT_alpha_rebuild',
]
