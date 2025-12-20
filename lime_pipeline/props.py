"""
Core Properties and State Management

This module defines the core property groups and state management for the Lime
Pipeline addon. It provides the data structures that store project settings,
UI state, and configuration options that persist across Blender sessions.

The property system manages project metadata, scene organization settings,
render configurations, and user interface state. It integrates with Blender's
property system to provide persistent storage and UI binding for all Lime
Pipeline functionality.

Key Features:
- Project state management with naming, paths, and revision tracking
- Render preset storage and management with versioning
- Camera selection and scene organization utilities
- UI state management for collapsible panels and user preferences
- Integration with Lime Pipeline core validation and naming systems
- Automatic state synchronization between UI and underlying data
- Support for complex property relationships and update callbacks
"""

import bpy
from bpy.types import PropertyGroup
from bpy.props import (
    StringProperty,
    BoolProperty,
    IntProperty,
    EnumProperty,
    PointerProperty,
)

from .ops.ops_dimensions import DEFAULT_ORIENTATION_MODE, ORIENTATION_MODE_ITEMS

PROJECT_TYPES = [
    ('BASE', "3D Base Model", "Single base .blend, no SC", 0),
    ('PV',   "Proposal Views", "Scenes under Revision", 1),
    ('REND', "Renders",        "Scenes under Revision", 2),
    ('SB',   "Storyboard",     "Scenes under Revision", 3),
    ('ANIM', "Animation",      "Scenes under Revision", 4),
    ('TMP',  "Temporal",       "Tmp under Revision",    5),
]

UNIT_PRESET_ITEMS = [
    ('MM', "Millimeters (mm)", "Apply metric millimeters.", 0),
    ('CM', "Centimeters (cm)", "Apply metric centimeters.", 1),
    ('M', "Meters (m)", "Apply metric meters.", 2),
    ('IN', "Inches (in)", "Apply imperial inches.", 3),
    ('FT', "Feet (ft)", "Apply imperial feet.", 4),
]


def _local_desktop_fallback() -> str:
    try:
        from pathlib import Path as _P
        return str((_P.home() / "Desktop").resolve())
    except Exception:
        return ""


def _local_base_dir() -> str:
    try:
        import bpy as _bpy
        prefs = _bpy.context.preferences.addons[__package__.split('.')[0]].preferences
        base = getattr(prefs, "local_projects_root", "") or ""
    except Exception:
        base = ""
    return base or _local_desktop_fallback()


def _sanitize_local_folder_name(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return "LocalProject"
    try:
        from .core.naming import normalize_project_name as _normalize
        cleaned = _normalize(text)
        return cleaned or "LocalProject"
    except Exception:
        return text or "LocalProject"


def _sync_local_project_root(state) -> None:
    if not getattr(state, "use_local_project", False):
        return
    try:
        from pathlib import Path as _P
    except Exception:
        _P = None  # type: ignore
    folder = _sanitize_local_folder_name(getattr(state, "local_project_name", ""))
    base = _local_base_dir()
    if _P is None:
        state.project_root = folder
        return
    state.project_root = str(_P(base) / folder) if base else folder


def _on_local_project_name_update(self, context):
    if getattr(self, "use_local_project", False):
        _sync_local_project_root(self)


def _on_use_local_project_update(self, context):
    if getattr(self, "use_local_project", False):
        current_root = getattr(self, "project_root", "") or ""
        if current_root:
            self.shared_root_snapshot = current_root
        name = (getattr(self, "local_project_name", "") or "").strip()
        if not name:
            try:
                from pathlib import Path as _P
                base_name = _P(current_root).name if current_root else ""
            except Exception:
                base_name = ""
            self.local_project_name = base_name or "Local Project"
        _sync_local_project_root(self)
    else:
        cached = getattr(self, "shared_root_snapshot", "") or ""
        if cached:
            self.project_root = cached


def _on_selected_camera_update(self, context):
    try:
        name = getattr(self, "selected_camera", "") or ""
        if name and name != "NONE":
            cam = bpy.data.objects.get(name)
            if cam is not None and getattr(cam, "type", None) == 'CAMERA':
                context.scene.camera = cam
    except Exception:
        pass


def _on_auto_select_hierarchy_update(self, context):
    try:
        from .ops.ops_model_organizer import enable_auto_select_hierarchy, disable_auto_select_hierarchy
        if getattr(self, "auto_select_hierarchy", False):
            enable_auto_select_hierarchy()
        else:
            disable_auto_select_hierarchy()
    except Exception:
        pass



class LimeRenderPresetSlot(PropertyGroup):
    name: StringProperty(name="Name", default="")
    is_empty: BoolProperty(name="Is Empty", default=True, options={'HIDDEN'})
    data_version: IntProperty(name="Data Version", default=1, options={'HIDDEN'})
    data_json: StringProperty(name="Data", default="", options={'HIDDEN'})


class LimePipelineState(PropertyGroup):
    project_root: StringProperty(name="Project Root", subtype='DIR_PATH', description="Select the project root folder named 'XX-##### Project Name'")
    def _get_project_root_display(self):
        try:
            from .core.naming import RE_PROJECT_DIR
            from pathlib import Path as _P
            val = getattr(self, 'project_root', '') or ''
            if not val:
                return ''
            name = _P(val).name
            return name if RE_PROJECT_DIR.match(name) else name
        except Exception:
            return getattr(self, 'project_root', '') or ''
    def _set_project_root_display(self, value):
        try:
            # When user types/pastes only the project name, reconstruct full path
            from pathlib import Path as _P
            from .prefs import LimePipelinePrefs  # type: ignore
        except Exception:
            self.project_root = value
            return
        # Try to rebuild from default root if looks like a project name
        try:
            import bpy
            prefs = bpy.context.preferences.addons[__package__.split('.')[0]].preferences
            base = getattr(prefs, 'default_projects_root', '') or ''
            if base:
                # If value looks like a name (no path separators), join to base
                if ('/' not in value) and ('\\' not in value):
                    full = str(_P(base) / value)
                    self.project_root = full
                    return
        except Exception:
            pass
        self.project_root = value
    project_root_display: StringProperty(name="Project Root", get=_get_project_root_display, set=_set_project_root_display, description="Project name (root shown as folder name only)")
    use_local_project: BoolProperty(
        name="Local Project Mode",
        description="Save outside the shared projects root (Desktop/local workflow)",
        default=False,
        update=_on_use_local_project_update,
    )
    shared_root_snapshot: StringProperty(
        name="Shared Root Snapshot",
        description="Internal: remembers last shared project root when toggling local mode",
        default="",
        options={'HIDDEN'},
    )
    local_project_name: StringProperty(
        name="Local Project Name",
        description="Manual project name used when working locally",
        default="",
        update=_on_local_project_name_update,
    )
    project_type: EnumProperty(name="Project Type", items=PROJECT_TYPES, default='REND', description="Type of project work: affects naming and target folders")
    # Sync helpers between letter and index
    def _on_rev_index_update(self, context):
        # Prevent recursive update loops when syncing with rev_letter
        if getattr(self, "_updating_rev", False):
            return
        try:
            setattr(self, "_updating_rev", True)
            idx = int(getattr(self, "rev_index", 1))
            if idx < 1:
                idx = 1
            if idx > 26:
                idx = 26
            self.rev_letter = chr(ord('A') + (idx - 1))
        except Exception:
            pass
        finally:
            setattr(self, "_updating_rev", False)

    # Note: rev_letter is the source-of-truth value used elsewhere in the addon.
    # We only update rev_letter when rev_index changes (one-way sync) to avoid
    # recursive update loops.

    rev_letter: StringProperty(name="Rev", default="A", maxlen=1, description="Revision letter A–Z")
    rev_index: IntProperty(name="Rev", default=1, min=1, max=26, step=1, description="Revision as stepper (A–Z)", update=_on_rev_index_update)
    sc_number: IntProperty(name="SC", default=10, min=1, max=999, step=10, description="Scene number (001–999). Suggested multiples of Scene Step")
    free_scene_numbering: BoolProperty(name="Free SC numbering", default=False, description="Allow any scene number; ignore Scene Step multiple rule")
    use_custom_name: BoolProperty(name="Use Custom Name", default=False, description="Override project name derived from root folder")
    custom_name: StringProperty(name="Custom Project Name", description="Letters/digits only; will be normalized to TitleCase")
    preview_name: StringProperty(name="Preview Name", options={'HIDDEN'})
    preview_path: StringProperty(name="Preview Path", subtype='FILE_PATH', options={'HIDDEN'})
    render_version: IntProperty(
        name="Render Version",
        description="Optional render version (0 = none)",
        default=0,
        min=0,
        max=99,
    )
    render_descriptor: StringProperty(
        name="Render Descriptor",
        description="Optional descriptor word for render naming",
        default="",
    )
    view_layer_output_format: EnumProperty(
        name="View Layer Output",
        description="Formato de salida para exportar View Layers",
        items=[
            ("EXR", "OpenEXR", "OpenEXR RGBA (Half) con codec DWAA"),
            ("PNG", "PNG", "PNG RGBA 16-bit"),
        ],
        default="EXR",
    )
    # Dynamic camera selection for Proposal Views
    def _camera_items(self, context):
        try:
            from .core import validate_scene
            from .data import templates
        except Exception:
            return [("NONE", "No Camera", "", 0)]
        items = []
        try:
            shot = validate_scene.active_shot_context(context)
            if shot is not None:
                base = getattr(templates, "C_CAM", "00_CAM")
                cam_coll = validate_scene.get_shot_child_by_basename(shot, base)
                if cam_coll is not None:
                    cams = [obj for obj in cam_coll.objects if getattr(obj, "type", None) == 'CAMERA']
                    # Stable order by name
                    cams.sort(key=lambda o: o.name)
                    for idx, cam in enumerate(cams, 1):
                        items.append((cam.name, f"Cam {idx}: {cam.name}", "", idx))
        except Exception:
            pass
        return items or [("NONE", "No Camera", "", 0)]

    selected_camera: EnumProperty(name="Camera", items=_camera_items, update=_on_selected_camera_update)

    # Scene continuity (Stage panel)
    scene_continuity_frame_mode: EnumProperty(
        name="Handoff Frame",
        description="Frame to sample when creating the next scene file",
        items=(
            ("CURRENT", "Current Frame", "Use the current frame as handoff"),
            ("SCENE_END", "Scene End", "Use scene frame_end as handoff"),
        ),
        default="CURRENT",
    )
    def _shot_enum_items(self, context):
        try:
            from .core import validate_scene as _vs
        except Exception:
            return [("NONE", "No SHOTs found", "", 0)]
        scene = getattr(context, "scene", None)
        if scene is None:
            return [("NONE", "No SHOTs found", "", 0)]
        try:
            items = [("NONE", "No SHOTs found", "", 0)]
            for idx, (coll, sh_idx) in enumerate(_vs.list_shot_roots(scene), 1):
                name = getattr(coll, "name", f"SHOT {sh_idx:02d}") or f"SHOT {sh_idx:02d}"
                items.append((name, name, "", idx))
            return items
        except Exception:
            return [("NONE", "No SHOTs found", "", 0)]

    scene_continuity_shot_name: EnumProperty(
        name="Continuity Shot",
        description="SHOT root (top-level) whose pose will seed the next scene",
        items=_shot_enum_items,
        default=0,
    )

    # Visibility behavior during renders and proposal views
    consider_all_shots: BoolProperty(
        name="Consider all SHOTs",
        description=(
            "If unchecked, other SHOTs will be temporarily hidden during render/capture "
            "so only the target SHOT is visible."
        ),
        default=False,
    )

    auto_select_hierarchy: BoolProperty(
        name="Auto Select Children",
        description="Selecting an object will also select all of its descendants.",
        default=False,
        update=_on_auto_select_hierarchy_update,
    )

    def _on_solo_shot_activo_update(self, context):
        try:
            if getattr(self, 'solo_shot_activo', False):
                # When enabling solo mode, isolate the current active shot
                # Find the currently selected shot in the UI list
                scene = context.scene
                try:
                    idx = getattr(scene, 'lime_shots_index', -1)
                    items = getattr(scene, 'lime_shots', None)
                    if items is not None and 0 <= idx < len(items):
                        shot_name = items[idx].name
                        bpy.ops.lime.isolate_active_shot(shot_name=shot_name)
                    else:
                        # Fallback to context-based detection
                        bpy.ops.lime.isolate_active_shot()
                except Exception:
                    # Fallback to context-based detection
                    bpy.ops.lime.isolate_active_shot()
            else:
                # When disabling solo mode, show all shots again
                scene = context.scene
                try:
                    def _find_layer_collection(layer, coll):
                        if layer and layer.collection == coll:
                            return layer
                        for ch in getattr(layer, 'children', []):
                            found = _find_layer_collection(ch, coll)
                            if found:
                                return found
                        return None

                    def _iter_layer_subtree(root_layer):
                        if root_layer is None:
                            return
                        stack = [root_layer]
                        while stack:
                            lc = stack.pop()
                            yield lc
                            try:
                                stack.extend(list(lc.children))
                            except Exception:
                                pass

                    from .core import validate_scene
                    shots = validate_scene.list_shot_roots(scene)
                    vl = context.view_layer
                    base = vl.layer_collection if vl else None

                    # Show all shots
                    for shot_coll, _ in shots:
                        lc = _find_layer_collection(base, shot_coll)
                        if lc is not None:
                            for sub_lc in _iter_layer_subtree(lc):
                                try:
                                    sub_lc.exclude = False
                                except Exception:
                                    pass
                except Exception:
                    pass
        except Exception:
            pass

    # Shot isolation mode for panel
    solo_shot_activo: BoolProperty(
        name="Solo Shot Activo",
        description="When enabled, only the active SHOT collection remains visible in the View Layer",
        default=False,
        update=_on_solo_shot_activo_update,
    )

    def _on_jump_to_first_shot_marker_update(self, context):
        try:
            # Trigger jump only when enabling the toggle
            if not getattr(self, 'jump_to_first_shot_marker', False):
                return
            import bpy  # local import per core rules
            scene = context.scene
            shot_name = ''
            try:
                idx = getattr(scene, 'lime_shots_index', -1)
                items = getattr(scene, 'lime_shots', None)
                if items is not None and 0 <= idx < len(items):
                    shot_name = items[idx].name
            except Exception:
                shot_name = ''
            if not shot_name:
                try:
                    from .core import validate_scene
                    active = validate_scene.active_shot_context(context)
                    if active is not None:
                        shot_name = active.name
                except Exception:
                    pass
            if shot_name:
                try:
                    bpy.ops.lime.jump_to_first_shot_marker(shot_name=shot_name)
                except Exception:
                    pass
        except Exception:
            pass

    jump_to_first_shot_marker: BoolProperty(
        name="Jump to First Shot Marker",
        description=(
            "When enabled, switching/activating a SHOT in Solo mode will jump the timeline "
            "to the first camera marker that belongs to that SHOT."
        ),
        default=False,
        update=_on_jump_to_first_shot_marker_update,
    )

    # (Removed) UI collapsible flags for Render Configs; now using subpanels

    # UI collapsible sections for Shots panel
    ui_shots_show_list: BoolProperty(
        name="Show Shot List",
        description="Show/Hide the list of SHOTs",
        default=True,
        options={'HIDDEN'},
    )
    ui_shots_show_tools: BoolProperty(
        name="Show Shot Tools",
        description="Show/Hide the shot tools section",
        default=True,
        options={'HIDDEN'},
    )
    dimension_orientation_mode: EnumProperty(
        name="Dimension Orientation",
        description="Preferred orientation mode for the Dimension Checker.",
        items=ORIENTATION_MODE_ITEMS,
        default=DEFAULT_ORIENTATION_MODE,
    )
    dimension_lock_z_up: BoolProperty(
        name="Dimension Lock Z-Up",
        description="Force global Z upright when using PCA orientations.",
        default=False,
    )
    dimension_show_mm: BoolProperty(
        name="Show Millimeters",
        description="Show millimeters in Dimension Checker overlay.",
        default=True,
    )
    dimension_show_cm: BoolProperty(
        name="Show Centimeters",
        description="Show centimeters in Dimension Checker overlay.",
        default=True,
    )
    dimension_show_m: BoolProperty(
        name="Show Meters",
        description="Show meters in Dimension Checker overlay.",
        default=True,
    )
    dimension_show_in: BoolProperty(
        name="Show Inches",
        description="Show inches in Dimension Checker overlay.",
        default=True,
    )
    dimension_show_ft: BoolProperty(
        name="Show Feet",
        description="Show feet in Dimension Checker overlay.",
        default=True,
    )


    dimension_units_preset: EnumProperty(
        name="Units Preset",
        description="Last applied measurement unit preset for Dimension Utilities.",
        items=UNIT_PRESET_ITEMS,
        default='MM',
        options={'HIDDEN'},
    )

    # Resolution shortcut properties for UHD toggle auto-update
    lime_shortcut_base_x: IntProperty(
        name="Base Resolution X",
        description="Base X resolution value for UHD toggle calculations",
        default=1920,
        min=1,
        options={'HIDDEN'},
    )
    lime_shortcut_base_y: IntProperty(
        name="Base Resolution Y",
        description="Base Y resolution value for UHD toggle calculations",
        default=1080,
        min=1,
        options={'HIDDEN'},
    )

def _safe_register(cls):
    """Register class handling retained state during live reloads."""
    try:
        bpy.utils.register_class(cls)
    except ValueError:
        bpy.utils.unregister_class(cls)
        bpy.utils.register_class(cls)


def register():
    _safe_register(LimeRenderPresetSlot)
    _safe_register(LimePipelineState)
    if hasattr(bpy.types.WindowManager, "lime_pipeline"):
        del bpy.types.WindowManager.lime_pipeline
    bpy.types.WindowManager.lime_pipeline = PointerProperty(type=LimePipelineState)


def unregister():
    if hasattr(bpy.types.WindowManager, "lime_pipeline"):
        del bpy.types.WindowManager.lime_pipeline
    try:
        bpy.utils.unregister_class(LimePipelineState)
    except RuntimeError:
        pass
    try:
        bpy.utils.unregister_class(LimeRenderPresetSlot)
    except RuntimeError:
        pass

__all__ = [
    "LimeRenderPresetSlot",
    "LimePipelineState",
    "register",
    "unregister",
]



