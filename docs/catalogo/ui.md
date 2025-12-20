# UI — Catálogo por archivo

## lime_pipeline/ui/__init__.py

(sin docstring de módulo)

## lime_pipeline/ui/ui_ai_material_renamer.py

UI to review and apply AI-proposed material renames according to naming rules.

This panel is lightweight; heavy logic resides in operators and property definitions.

Clases Blender detectadas:

- LIME_TB_UL_ai_mat_rows (UIList): bl_idname=LIME_TB_UL_ai_mat_rows
- LIME_TB_PT_ai_material_renamer (Panel): bl_idname=LIME_TB_PT_ai_material_renamer, bl_label=AI Material Renamer, bl_space_type=VIEW_3D, bl_region_type=UI, bl_category=Lime Toolbox

## lime_pipeline/ui/ui_alpha_manager.py

UI to manage alpha fade events using Driver or Keyframe modes.

Purpose: Create and edit alpha events with start/end frames and direction (in/out),
rebuild drivers when needed, and provide assignment utilities.
Key classes: LIME_TB_PT_alpha_manager, LIME_TB_UL_alpha_events.
Depends on: lime_pipeline.ops.ops_alpha_manager (operators and props).
Notes: UI-only; warns if Auto Run Scripts is disabled.

Clases Blender detectadas:

- LIME_TB_UL_alpha_events (UIList): bl_idname=LIME_TB_UL_alpha_events
- LIME_TB_PT_alpha_manager (Panel): bl_idname=LIME_TB_PT_alpha_manager, bl_label=Alpha Manager, bl_space_type=VIEW_3D, bl_region_type=UI

## lime_pipeline/ui/ui_animation_parameters.py

UI to set interpolation/easing defaults for new keyframes and post-process frames.

Purpose: Let users choose interpolation and easing; install a depsgraph handler to
apply styles to keyframes at the current frame when enabled.
Key classes: LIME_TB_PT_animation_params.
Depends on: Blender keyframe preferences; operators lime.tb_apply_keyframe_style.
Notes: UI-only; handler is resilient and can be toggled.

Clases Blender detectadas:

- LIME_TB_PT_animation_params (Panel): bl_idname=LIME_TB_PT_animation_params, bl_label=Animation Parameters, bl_space_type=VIEW_3D, bl_region_type=UI

## lime_pipeline/ui/ui_cameras_manager.py

UI panels and lists for managing render cameras and their margin/background overlays.

Purpose: Provide a viewport panel to list, add, duplicate, delete and sync camera rigs, and
configure margins/background images opacity per alias.
Key classes: LIME_PT_render_cameras, LIME_UL_render_cameras, LimeRenderCamItem.
Depends on: lime_pipeline.core.validate_scene, lime_pipeline.scene.scene_utils.
Notes: UI-only; behavior is delegated to operators (e.g. lime.add_camera_rig, lime.sync_camera_list).

Clases Blender detectadas:

- LIME_PT_render_cameras (Panel): bl_idname=LIME_PT_render_cameras, bl_label=Cameras, bl_space_type=VIEW_3D, bl_region_type=UI
- LimeRenderCamItem (PropertyGroup)
- LIME_UL_render_cameras (UIList): bl_idname=LIME_UL_render_cameras

## lime_pipeline/ui/ui_dimension_utilities.py

UI utilities for scene dimension checking and measurement unit presets.

Purpose: Display a dimension checker operator and quick buttons to apply standard
measurement units (MM/CM/M/IN/FT) to the current scene.
Key classes: LIME_PT_dimension_utilities, LIME_OT_set_unit_preset.
Depends on: Blender unit settings; optional addon preferences.
Notes: UI-only; unit changes are applied through a lightweight operator.

Clases Blender detectadas:

- LIME_OT_set_unit_preset (Operator): bl_idname=lime.set_unit_preset, bl_label=Set Unit Preset
- LIME_PT_dimension_utilities (Panel): bl_idname=LIME_PT_dimension_utilities, bl_label=Dimension Utilities, bl_space_type=VIEW_3D, bl_region_type=UI

## lime_pipeline/ui/ui_experimental.py

UI for experimental Lime Toolbox features.

Currently: exposes the Scene Continuity handoff operator in an isolated panel so it
can be used without cluttering stable tools. Marked experimental because the freeze
logic is still evolving.

Clases Blender detectadas:

- LIME_TB_PT_experimental (Panel): bl_idname=LIME_TB_PT_experimental, bl_label=Experimental, bl_space_type=VIEW_3D, bl_region_type=UI

## lime_pipeline/ui/ui_image_editor_save.py

Image Editor panel to save outputs with normalized names and RAW variants.

Purpose: Provide quick buttons to save Render Result and images using project templates,
including RAW variants intended for post-production workflows.
Key classes: LIME_PT_image_save_as.
Depends on: operators lime.save_as_with_template and lime.save_as_with_template_raw.
Notes: UI-only; operators handle naming and path logic.

Clases Blender detectadas:

- LIME_PT_image_save_as (Panel): bl_idname=LIME_PT_image_save_as, bl_label=Save As, bl_space_type=IMAGE_EDITOR, bl_region_type=UI

## lime_pipeline/ui/ui_model_organizer.py

UI panel to organize imported 3D models and scene controllers.

Purpose: Provide actions to import STEP, clean geometry, create controller empties,
apply deltas, colorize parent groups, and manage library linking/override/relocate.
Key classes: LIME_PT_model_organizer.
Depends on: ops.ops_model_organizer and related operators.
Notes: UI-only; shows status for location offsets and actions availability.

Clases Blender detectadas:

- LIME_PT_model_organizer (Panel): bl_idname=LIME_PT_model_organizer, bl_label=3D Model Organizer, bl_space_type=VIEW_3D, bl_region_type=UI

## lime_pipeline/ui/ui_noise_movement.py

UI for noise movement profiles applied to object transforms.

Purpose: Define reusable noise profiles (Location/Rotation/Scale) and apply/sync them to
selected or affected objects via operators from ops.ops_noise.
Key classes: LIME_TB_PT_noisy_movement, LIME_TB_UL_noise_names, LIME_TB_UL_noise_objects,
             LimeTBNoiseProfile, LimeTBNoiseAffectedItem.
Depends on: lime_pipeline.ops.ops_noise (apply/sync helpers).
Notes: UI-only; this module manages properties and delegates heavy logic to ops.

Clases Blender detectadas:

- LimeTBNoiseAffectedItem (PropertyGroup)
- LimeTBNoiseProfile (PropertyGroup)
- LIME_TB_UL_noise_names (UIList): bl_idname=LIME_TB_UL_noise_names
- LIME_TB_UL_noise_objects (UIList): bl_idname=LIME_TB_UL_noise_objects
- LIME_TB_PT_noisy_movement (Panel): bl_idname=LIME_TB_PT_noisy_movement, bl_label=Noisy Movement, bl_space_type=VIEW_3D, bl_region_type=UI

Dependencias internas: lime_pipeline.ops.ops_noise

## lime_pipeline/ui/ui_project_org.py

UI to configure project naming (type, revision, scene) and saving helpers.

Purpose: Centralize project root selection, enforce naming invariants, preview filename,
and expose actions to create blend files, backups and folders.
Key classes: LIME_PT_project_org.
Depends on: lime_pipeline.core.validate and ops (save/create/folders).
Notes: UI-only; mirrors architecture invariants for quick validation.

Clases Blender detectadas:

- LIME_PT_project_org (Panel): bl_idname=LIME_PT_project_org, bl_label=Project Organization, bl_space_type=VIEW_3D, bl_region_type=UI

## lime_pipeline/ui/ui_render_configs.py

UI for render presets, resolution shortcuts, and output utilities.

Purpose: Apply/save/clear global render presets, toggle denoising, set resolution via
shortcuts (with UHD toggle), and open output folders.
Key classes: LIME_PT_render_configs, LIME_PT_render_preset_actions, LIME_PT_render_outputs.
Depends on: ops.ops_render_presets and core naming/paths helpers.
Notes: UI-only; reads addon preferences and scene settings.

Clases Blender detectadas:

- LIME_PT_render_configs (Panel): bl_idname=LIME_PT_render_configs, bl_label=Render Configs, bl_space_type=VIEW_3D, bl_region_type=UI
- LIME_PT_render_preset_actions (Panel): bl_label=Preset Maintenance, bl_space_type=VIEW_3D, bl_region_type=UI
- LIME_PT_render_outputs (Panel): bl_label=Output Files, bl_space_type=VIEW_3D, bl_region_type=UI

## lime_pipeline/ui/ui_shots.py

UI to manage SHOT collections: list, create, duplicate, delete and sync.

Purpose: Provide a panel and list to manage SHOT roots, support isolation of active SHOT
in the view layer, and keep the UI in sync using a depsgraph handler.
Key classes: LIME_PT_shots, LIME_UL_shots; Operators: lime.sync_shot_list, lime.new_shot_and_sync,
lime.delete_shot_and_sync, lime.duplicate_shot_and_sync, lime.isolate_active_shot.
Depends on: lime_pipeline.core.validate_scene for detection and parsing.
Notes: UI-only; operators handle scene modifications.

Clases Blender detectadas:

- LIME_PT_shots (Panel): bl_idname=LIME_PT_shots, bl_label=Shots, bl_space_type=VIEW_3D, bl_region_type=UI
- LimeShotItem (PropertyGroup)
- LIME_UL_shots (UIList): bl_idname=LIME_UL_shots
- LIME_OT_sync_shot_list (Operator): bl_idname=lime.sync_shot_list, bl_label=Refresh SHOTs
- LIME_OT_new_shot_and_sync (Operator): bl_idname=lime.new_shot_and_sync, bl_label=New Shot and Refresh
- LIME_OT_delete_shot_and_sync (Operator): bl_idname=lime.delete_shot_and_sync, bl_label=Delete Shot and Refresh
- LIME_OT_duplicate_shot_and_sync (Operator): bl_idname=lime.duplicate_shot_and_sync, bl_label=Duplicate Shot and Refresh
- LIME_OT_isolate_active_shot (Operator): bl_idname=lime.isolate_active_shot, bl_label=Isolate Active Shot

## lime_pipeline/ui/ui_stage_setup.py

UI to set up stage elements for an active SHOT and auto camera backgrounds.

Purpose: Provide scene duplication for SHOTs, import layout helpers, and controls to
initialize, refresh and toggle live auto camera background planes.
Key classes: LIME_PT_stage_setup.
Depends on: lime_pipeline.core.validate_scene and ops for stage/background automation.
Notes: UI-only; disables actions when there is no active SHOT.

Clases Blender detectadas:

- LIME_PT_stage_setup (Panel): bl_idname=LIME_PT_stage_setup, bl_label=Stage, bl_space_type=VIEW_3D, bl_region_type=UI

