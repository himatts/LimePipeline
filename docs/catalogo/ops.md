# OPS — Catálogo por archivo

## lime_pipeline/ops/__init__.py

Lime Pipeline Operators Package

This package contains all the operator classes for the Lime Pipeline addon.
Operators are organized by functionality and provide the main user-facing
actions available in the Lime Pipeline interface.

The operators handle various aspects of pipeline management including:
- Animation parameters and keyframe styling
- Scene organization and collection management
- Camera operations and rig management
- Material and alpha management
- Backup and file operations
- Rendering and dimension utilities

Each operator follows Blender's operator conventions with proper bl_idname,
bl_label, and poll/execute methods for integration with Blender's UI system.

## lime_pipeline/ops/ai_http.py

Shared HTTP helpers for AI integrations (OpenRouter/Krea).

These helpers centralize small request utilities to avoid duplication across ops modules.

## lime_pipeline/ops/ops_add_missing.py

Add Missing Collections Operator

This module provides functionality to add missing collections to maintain proper
scene organization according to Lime Pipeline conventions. It ensures that the
canonical SHOT tree structure exists for the current shot context.

The operator validates that there's an active SHOT context before proceeding,
resolves the project name, and ensures the shot tree exists by adding only
the missing collections rather than recreating the entire structure.

Key Features:
- Validates active SHOT context before execution
- Resolves project name from pipeline settings
- Adds only missing collections to avoid duplication
- Integrates with Lime Pipeline naming conventions
- Provides proper error reporting for invalid contexts

Clases Blender detectadas:

- LIME_OT_add_missing_collections (Operator): bl_idname=lime.add_missing_collections, bl_label=Add Missing Collections

## lime_pipeline/ops/ops_ai_asset_organizer.py

AI Asset Organizer operators.

Suggests and applies names for selected objects/materials/collections with AI,
plus optional safe collection reorganization.

Clases Blender detectadas:

- LIME_TB_OT_ai_asset_suggest_names (Operator): bl_idname=lime_tb.ai_asset_suggest_names, bl_label=AI: Suggest Names
- LIME_TB_OT_ai_asset_apply_names (Operator): bl_idname=lime_tb.ai_asset_apply_names, bl_label=AI: Apply Names
- LIME_TB_OT_ai_asset_scope_preset (Operator): bl_idname=lime_tb.ai_asset_scope_preset, bl_label=AI: Scope Preset
- LIME_TB_OT_ai_asset_refresh_targets (Operator): bl_idname=lime_tb.ai_asset_refresh_targets, bl_label=AI: Refresh Targets
- LIME_TB_OT_ai_asset_resolve_target (Operator): bl_idname=lime_tb.ai_asset_resolve_target, bl_label=AI: Resolve Target
- LIME_TB_OT_ai_asset_set_target_for_item (Operator): bl_idname=lime_tb.ai_asset_set_target_for_item, bl_label=AI: Re-route Object
- LIME_TB_OT_ai_asset_set_target_for_selected (Operator): bl_idname=lime_tb.ai_asset_set_target_for_selected, bl_label=AI: Re-route Selected Objects
- LIME_TB_OT_ai_asset_clear (Operator): bl_idname=lime_tb.ai_asset_clear, bl_label=AI: Clear
- LIME_TB_OT_open_ai_asset_manager (Operator): bl_idname=lime_tb.open_ai_asset_manager, bl_label=Open AI Asset Manager
- LIME_TB_OT_ai_asset_test_connection (Operator): bl_idname=lime_tb.ai_asset_test_connection, bl_label=AI: Test Connection
- LIME_TB_OT_ai_asset_material_debug_report (Operator): bl_idname=lime_tb.ai_asset_material_debug_report, bl_label=AI: Material Debug Report
- LIME_TB_OT_ai_asset_collection_debug_report (Operator): bl_idname=lime_tb.ai_asset_collection_debug_report, bl_label=AI: Collection Debug Report

## lime_pipeline/ops/ops_ai_render_converter.py

AI Render Converter Operators

Implements the render-to-style conversion workflow using Krea (Nano Banana)
and optional prompt rewriting via OpenRouter.

Clases Blender detectadas:

- LIME_OT_ai_render_refresh (Operator): bl_idname=lime.ai_render_refresh, bl_label=AI: Refresh Source
- LIME_OT_ai_render_frame (Operator): bl_idname=lime.ai_render_frame, bl_label=AI: Render Current Frame
- LIME_OT_ai_render_generate (Operator): bl_idname=lime.ai_render_generate, bl_label=AI: Generate Storyboard
- LIME_OT_ai_render_retry (Operator): bl_idname=lime.ai_render_retry, bl_label=AI: Retry Generation
- LIME_OT_ai_render_cancel (Operator): bl_idname=lime.ai_render_cancel, bl_label=AI: Cancel Job
- LIME_OT_ai_render_test_connection (Operator): bl_idname=lime.ai_render_test_connection, bl_label=AI: Test Krea Connection
- LIME_OT_ai_render_add_to_sequencer (Operator): bl_idname=lime.ai_render_add_to_sequencer, bl_label=AI: Add Result to Sequencer
- LIME_OT_ai_render_open_outputs_folder (Operator): bl_idname=lime.ai_render_open_outputs_folder, bl_label=AI: Open Outputs Folder
- LIME_OT_ai_render_delete_selected (Operator): bl_idname=lime.ai_render_delete_selected, bl_label=AI: Delete Selected Image
- LIME_OT_ai_render_delete_batch (Operator): bl_idname=lime.ai_render_delete_batch, bl_label=AI: Delete Image Batch
- LIME_OT_ai_render_open_preview (Operator): bl_idname=lime.ai_render_open_preview, bl_label=AI: Open Image Preview
- LIME_OT_ai_render_import_style (Operator): bl_idname=lime.ai_render_import_style, bl_label=AI: Import Style Image

## lime_pipeline/ops/ops_alpha_manager.py

Alpha Events Manager Operators

This module provides operators for managing alpha (transparency) events and fade
animations for objects in Blender scenes. It handles the creation, management,
and application of alpha events that control object visibility over time.

The system supports multiple alpha modes (fade in/out, dissolve), event management
(add, duplicate, delete, rename), and driver-based animation curve generation.
It integrates with Blender's animation system to create smooth transparency transitions.

Key Features:
- Event-based alpha management with named fade events
- Support for multiple alpha modes (FADE, DISSOLVE)
- Driver-based animation curve generation for smooth transitions
- Object selection and membership management for alpha events
- Frame-accurate alpha keyframe baking and cleanup
- Integration with Blender's animation and driver systems
- Playback-optimized with message filtering during animation playback

Clases Blender detectadas:

- LimeTBAlphaEvent (PropertyGroup)
- LIME_TB_OT_alpha_event_add (Operator): bl_idname=lime.tb_alpha_event_add, bl_label=Add Fade Event
- LIME_TB_OT_alpha_event_duplicate (Operator): bl_idname=lime.tb_alpha_event_duplicate, bl_label=Duplicate Fade Event
- LIME_TB_OT_alpha_event_delete (Operator): bl_idname=lime.tb_alpha_event_delete, bl_label=Delete Fade Event
- LIME_TB_OT_alpha_event_rename (Operator): bl_idname=lime.tb_alpha_event_rename, bl_label=Rename Fade Event
- LIME_TB_OT_alpha_event_assign (Operator): bl_idname=lime.tb_alpha_event_assign, bl_label=Assign Selection
- LIME_TB_OT_alpha_event_unassign (Operator): bl_idname=lime.tb_alpha_event_unassign, bl_label=Remove Selection
- LIME_TB_OT_alpha_event_select_members (Operator): bl_idname=lime.tb_alpha_event_select_members, bl_label=Select Members
- LIME_TB_OT_alpha_set_mode (Operator): bl_idname=lime.tb_alpha_set_mode, bl_label=Switch Alpha Mode
- LIME_TB_OT_alpha_rebuild (Operator): bl_idname=lime.tb_alpha_rebuild, bl_label=Rebuild Drivers

## lime_pipeline/ops/ops_anim_output.py

Animation Render Output Operators

Provides operators to configure Blender's render output path for animation
frames following Lime Pipeline conventions. The operators resolve the active
SHOT, scene number, revision letter, and project root to build folder structures
like:

    Animation/Rev X/SC010_SH03/[test/]{basename}_####

They create missing directories when possible and set the render filepath so
F11 renders write frames into standardized locations. Errors are reported with
actionable guidance when context is incomplete (no SHOT active, missing Rev,
etc.).

Clases Blender detectadas:

- _LimeSetAnimOutput (Operator)
- _LimeSetAnimOutputLocal (Operator)

## lime_pipeline/ops/ops_animation_params.py

Animation Parameters Operators

This module provides operators for applying animation parameters and keyframe styling
to objects in Blender scenes. It handles the application of interpolation and easing
settings from Lime Pipeline animation parameters to selected keyframes.

The main operator applies the current Lime Animation Parameters (interpolation & easing)
to selected keyframes in the active/selected objects, supporting various interpolation
types (BEZIER, LINEAR, CONSTANT) and easing functions (SINE, QUAD, CUBIC, etc.).

Key Features:
- Applies interpolation and easing settings to keyframes
- Supports multiple easing functions for smooth animation curves
- Processes all selected objects and their animation data
- Validates animation parameters before application

Clases Blender detectadas:

- LIME_TB_OT_apply_keyframe_style (Operator): bl_idname=lime.tb_apply_keyframe_style, bl_label=Apply Style to Selected Keyframes

## lime_pipeline/ops/ops_auto_camera_bg.py

Auto Camera Background Operators

This module provides comprehensive functionality for creating and managing automatic
camera background planes that follow the active camera based on timeline markers.
The system creates background planes that automatically fill the camera frame and
update their position, rotation, and scale in real-time.

The auto camera background system supports:
- Automatic background plane creation and placement in SHOT collections
- Real-time tracking of camera movements based on timeline markers
- Configurable distance and padding parameters for frame filling
- Support for both perspective and orthographic cameras
- Live update handlers for smooth animation playback
- Baking of background animations to keyframes for static shots
- Comprehensive cleanup and state management utilities

Key Features:
- Marker-based camera tracking with automatic plane positioning
- Configurable distance and padding for frame coverage control
- Support for multiple background planes per scene
- SHOT-based organization and collection management
- Live update system with performance optimizations
- Bake-to-keyframes functionality for static animation
- Diagnostic and cleanup utilities for troubleshooting
- Comprehensive error handling and user feedback

Clases Blender detectadas:

- LIME_OT_auto_camera_background (Operator): bl_idname=lime.auto_camera_background, bl_label=Auto Camera Background
- LIME_OT_auto_camera_background_refresh (Operator): bl_idname=lime.auto_camera_background_refresh, bl_label=Refresh BG
- LIME_OT_auto_camera_background_toggle_live (Operator): bl_idname=lime.auto_camera_background_toggle_live, bl_label=Toggle Live BG
- LIME_OT_auto_camera_background_bake (Operator): bl_idname=lime.auto_camera_background_bake, bl_label=Bake BG to Keyframes
- LIME_OT_auto_camera_background_cleanup (Operator): bl_idname=lime.auto_camera_background_cleanup, bl_label=Cleanup BG State

## lime_pipeline/ops/ops_backup.py

Backup Creation Operators

This module provides functionality for creating numbered backup copies of Blender files.
It implements an automatic backup system that creates sequentially numbered backup files
in a designated backups folder, preventing accidental overwrites.

The backup system uses a naming convention (Backup_XX_filename) where XX is a
two-digit incremental number. It automatically determines the next available number
and creates the backup in the configured backups directory.

Key Features:
- Automatic sequential backup numbering (Backup_01_, Backup_02_, etc.)
- Configurable backup directory through addon preferences
- Validation of backup directory existence and write permissions
- Integration with Lime Pipeline settings for project-specific backups
- Error handling for file system operations and permission issues

Clases Blender detectadas:

- LIME_OT_create_backup (Operator): bl_idname=lime.create_backup, bl_label=Create Backup

## lime_pipeline/ops/ops_cameras.py

Camera Management Operators

This module provides comprehensive camera management functionality for Lime Pipeline,
including camera rig creation, camera positioning, background management, and
camera list synchronization.

The operators handle various camera-related tasks:
- Camera rig creation and management with proper naming conventions
- Camera positioning and pose operations
- Automatic camera background generation and margin management
- Camera list synchronization and refresh operations
- Render invocation and camera deletion with cleanup

Key Features:
- Automated camera rig creation with armature-based control
- Background plane generation that follows camera movement
- Margin-based background scaling for render framing
- Integration with SHOT-based naming conventions
- Camera list management and synchronization
- Render integration with proper camera validation
- Comprehensive error handling and user feedback

Clases Blender detectadas:

- LIME_OT_set_active_camera (Operator): bl_idname=lime.set_active_camera, bl_label=Set Active Camera
- LIME_OT_render_invoke (Operator): bl_idname=lime.render_invoke, bl_label=Render
- LIME_OT_duplicate_active_camera (Operator): bl_idname=lime.duplicate_active_camera, bl_label=Duplicate Camera
- LIME_OT_rename_shot_cameras (Operator): bl_idname=lime.rename_shot_cameras, bl_label=Rename Cameras
- LIME_OT_delete_camera_rig (Operator): bl_idname=lime.delete_camera_rig, bl_label=Delete Camera
- LIME_OT_pose_camera_rig (Operator): bl_idname=lime.pose_camera_rig, bl_label=Pose Rig
- LIME_OT_sync_camera_list (Operator): bl_idname=lime.sync_camera_list, bl_label=Refresh Cameras
- LIME_OT_delete_camera_rig_and_sync (Operator): bl_idname=lime.delete_camera_rig_and_sync, bl_label=Delete Camera and Refresh
- LIME_OT_reset_margin_alpha (Operator): bl_idname=lime.reset_margin_alpha, bl_label=Reset Alpha
- LIME_OT_retry_camera_margin_backgrounds (Operator): bl_idname=lime.retry_camera_margin_backgrounds, bl_label=Reintentar Márgenes
- LIME_OT_add_simple_camera (Operator): bl_idname=lime.add_simple_camera, bl_label=Create Camera (Simple)
- LIME_OT_add_camera_rig (Operator): bl_idname=lime.add_camera_rig, bl_label=Create Camera (Rig)

## lime_pipeline/ops/ops_comp_view_layer_outputs.py

Compositor utilities for per-View Layer outputs.

Clases Blender detectadas:

- LIME_OT_setup_view_layer_outputs (Operator): bl_idname=lime.setup_view_layer_outputs, bl_label=Setup View Layer Outputs

## lime_pipeline/ops/ops_create_file.py

File Creation Operators

This module provides functionality for the initial creation and saving of Blender files
within the Lime Pipeline workflow. It handles the first save operation with complete
validation of project settings and file paths.

The operator performs comprehensive validation before saving, ensuring that all
Lime Pipeline settings are properly configured, the target path is valid, and
the project structure meets the required conventions.

Key Features:
- Complete project validation before file creation
- Automatic directory creation for target paths
- Integration with Lime Pipeline naming and path conventions
- Comprehensive error reporting for validation failures
- Automatic backup handling during initial save
- User feedback for successful file creation

Clases Blender detectadas:

- LIME_OT_create_file (Operator): bl_idname=lime.create_file, bl_label=Create file (first save)

## lime_pipeline/ops/ops_dimensions.py

Dimension Checker Operators

This module provides dimension checking and measurement functionality for objects in
Blender scenes. It creates visual dimension overlays and helps verify object sizes
and spatial relationships within the Lime Pipeline workflow.

The dimension checker creates measurement helpers and visual indicators for object
dimensions, allowing artists to verify scale and positioning accuracy. It supports
various measurement modes and integrates with Blender's 3D viewport overlay system.

Key Features:
- Visual dimension overlay system with customizable display options
- Object size measurement and verification tools
- Integration with Blender's 3D viewport for real-time dimension checking
- Support for different measurement orientations and modes
- Customizable visual styling for dimension indicators
- Collection-based organization of dimension helpers
- Real-time updates during object manipulation

Clases Blender detectadas:

- LIME_OT_dimension_envelope (Operator): bl_idname=lime.dimension_envelope, bl_label=Dimension Checker

## lime_pipeline/ops/ops_duplicate_scene.py

Scene Duplication Operators

This module provides functionality for duplicating Blender scenes while maintaining
Lime Pipeline conventions and relationships. It handles complex scene duplication
with proper renaming, collection management, and preservation of SHOT structures.

The duplication process involves analyzing scene naming patterns, managing collection
hierarchies, and ensuring that duplicated scenes maintain proper relationships with
their source scenes while following Lime Pipeline organizational principles.

Key Features:
- Intelligent scene duplication with naming pattern recognition
- Collection hierarchy preservation and management
- SHOT structure maintenance across duplicated scenes
- Integration with camera rigs and alpha event systems
- Comprehensive validation and error handling for complex duplications
- Support for sequential scene numbering and organization

Clases Blender detectadas:

- LIME_OT_duplicate_scene_sequential (Operator): bl_idname=lime.duplicate_scene_sequential, bl_label=Duplicate Scene Sequential

## lime_pipeline/ops/ops_folders.py

Folder Management Operators

This module provides functionality for creating and managing critical project folders
within the Lime Pipeline directory structure. It ensures that all necessary directories
exist for proper project organization and file management.

The operators handle folder creation for various project components including backups,
renders, assets, and other critical directories required by the Lime Pipeline workflow.

Key Features:
- Automatic creation of project-critical directory structures
- Integration with Lime Pipeline project root settings
- Validation of existing folder structures before creation
- Error handling for permission and path issues
- Support for both relative and absolute path configurations
- Automatic path resolution from current file context

Clases Blender detectadas:

- LIME_OT_ensure_folders (Operator): bl_idname=lime.ensure_folders, bl_label=Create critical folders
- LIME_OT_open_folder (Operator): bl_idname=lime.open_folder, bl_label=Open folder
- LIME_OT_open_output_folder (Operator): bl_idname=lime.open_output_folder, bl_label=Open output folder

## lime_pipeline/ops/ops_import_layout.py

Layout Import Operators

This module provides functionality for importing layout assets and workspaces from
Lime Pipeline libraries. It handles the import of pre-configured layouts and workspace
setups that accelerate project setup and maintain consistency.

The import system supports configurable library paths, workspace creation, and
integration with Lime Pipeline project structures for rapid scene setup.

Key Features:
- Import of pre-configured layout workspaces from libraries
- Configurable library paths with user preference overrides
- Automatic workspace creation and configuration
- Integration with Lime Pipeline project structure conventions
- Error handling for missing libraries and import failures
- Support for multiple layout configurations

Clases Blender detectadas:

- LIME_OT_import_layout (Operator): bl_idname=lime.import_layout, bl_label=Import Layout

## lime_pipeline/ops/ops_linked_collections.py

Linked Collections Operators

This module provides functionality for managing linked collections from external .blend files.
It allows converting linked objects to local while preserving linked mesh data and configuring material slot links.

Key Features:
- Convert linked objects (MESH and EMPTY) to local for editing
- Preserve linked mesh data (read-only, updates from source)
- Configure material slots to link='OBJECT' level
- Optional material duplication flag
- Process active collection or manual selection
- Comprehensive error handling and reporting

Clases Blender detectadas:

- LIME_OT_localize_linked_collection (Operator): bl_idname=lime.localize_linked_collection, bl_label=Convert Linked Collection to Local (Keep Mesh Linked)

## lime_pipeline/ops/ops_material_alpha_mix.py

Material Alpha Mix Operators

This module provides functionality for mixing materials with transparency based on
object alpha values. It automatically modifies material node trees to incorporate
transparent shaders mixed with existing surface shaders using object alpha information.

The operators handle complex material node tree manipulation, creating proper shader
mixes and connections to maintain material appearance while adding alpha transparency
support for object-level visibility control.

Key Features:
- Automatic material node tree modification for alpha mixing
- Integration with object alpha values for transparency control
- Preservation of existing material properties during mixing
- Support for complex shader node hierarchies
- Validation of material node trees before modification
- Error handling for incompatible material setups

Clases Blender detectadas:

- LIME_OT_apply_object_alpha_mix (Operator): bl_idname=lime.apply_object_alpha_mix, bl_label=Enable Object Alpha Transparency

## lime_pipeline/ops/ops_model_organizer.py

3D Model Organizer Operators

This module provides comprehensive functionality for organizing and managing 3D models
within Blender scenes through the Lime Pipeline Model Organizer panel. It includes
tools for creating controller empties, managing object hierarchies, applying visual
organization, and automating selection workflows.

The model organizer system supports:
- Automatic creation of controller empties for object grouping
- Hierarchy-based visual colorization for quick identification
- Transform application and delta management for scene cleanup
- Automatic selection propagation through object hierarchies
- Location offset detection and transform application utilities

Key Features:
- Controller empty creation with bounds-based sizing and positioning
- Visual hierarchy colorization using HSV color space distribution
- Automatic child selection when parent objects are selected
- Transform-to-deltas application for objects with non-zero locations
- Geometry-based object filtering and hierarchy traversal
- Comprehensive bounds calculation including modifier evaluation
- Error handling and validation for complex object hierarchies
- Integration with Blender's selection and transform systems

Clases Blender detectadas:

- LIME_OT_group_selection_empty (Operator): bl_idname=lime.group_selection_empty, bl_label=Create Controller
- LIME_OT_move_controller (Operator): bl_idname=lime.move_controller, bl_label=Move Controller
- LIME_OT_apply_scene_deltas (Operator): bl_idname=lime.apply_scene_deltas, bl_label=Apply Deltas
- LIME_OT_colorize_parent_groups (Operator): bl_idname=lime.colorize_parent_groups, bl_label=Color Parent Groups

## lime_pipeline/ops/ops_noise.py

Noise Animation Operators

This module provides functionality for generating procedural noise-based animations
and movements for objects in Blender scenes. It creates random or noise-driven
animations for object properties like location, rotation, and scale.

The noise system supports various animation curves, randomization patterns, and
integration with Blender's animation system for creating organic, procedural motion.

Key Features:
- Procedural noise-based animation generation
- Support for multiple object properties (location, rotation, scale)
- Configurable noise patterns and randomization
- Integration with Blender's animation and f-curve system
- Batch processing of multiple objects
- Validation of animation data before modification

Clases Blender detectadas:

- LIME_TB_OT_noise_add_profile (Operator): bl_idname=lime.tb_noise_add_profile, bl_label=Add Noise
- LIME_TB_OT_noise_sync (Operator): bl_idname=lime.tb_noise_sync, bl_label=Refresh
- LIME_TB_OT_noise_apply_to_selected (Operator): bl_idname=lime.tb_noise_apply_to_selected, bl_label=Add Selected Objects to Active Noise
- LIME_TB_OT_noise_remove_from_object (Operator): bl_idname=lime.tb_noise_remove_from_object, bl_label=Remove from Noise
- LIME_TB_OT_noise_remove_selected (Operator): bl_idname=lime.tb_noise_remove_selected, bl_label=Remove Selected Objects from Active Noise
- LIME_TB_OT_noise_rename_profile (Operator): bl_idname=lime.tb_noise_rename_profile, bl_label=Rename Noise
- LIME_TB_OT_noise_group_randomize (Operator): bl_idname=lime.tb_noise_group_randomize, bl_label=Randomize Group Values
- LIME_TB_OT_noise_group_copy (Operator): bl_idname=lime.tb_noise_group_copy, bl_label=Copy Group Values
- LIME_TB_OT_noise_group_paste (Operator): bl_idname=lime.tb_noise_group_paste, bl_label=Paste Group Values
- LIME_TB_OT_noise_delete_profile (Operator): bl_idname=lime.tb_noise_delete_profile, bl_label=Delete Noise

## lime_pipeline/ops/ops_render_presets.py

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

Clases Blender detectadas:

- LIME_OT_render_preset_save (Operator): bl_idname=lime.render_preset_save, bl_label=Save Render Preset
- LIME_OT_render_preset_apply (Operator): bl_idname=lime.render_preset_apply, bl_label=Apply Render Preset
- LIME_OT_render_preset_clear (Operator): bl_idname=lime.render_preset_clear, bl_label=Clear Render Preset
- LIME_OT_render_preset_reset_all (Operator): bl_idname=lime.render_preset_reset_all, bl_label=Reset Render Presets
- LIME_OT_render_preset_restore_defaults (Operator): bl_idname=lime.render_preset_restore_defaults, bl_label=Restore Default Presets
- LIME_OT_render_preset_update_defaults (Operator): bl_idname=lime.render_preset_update_defaults, bl_label=Update Default Presets
- LIME_OT_toggle_denoising_property (Operator): bl_idname=lime.toggle_denoising_property, bl_label=Toggle Denoising Property
- LIME_OT_toggle_preview_denoising_property (Operator): bl_idname=lime.toggle_preview_denoising_property, bl_label=Toggle Preview Denoising Property
- LIME_OT_render_apply_resolution_shortcut (Operator): bl_idname=lime.render_apply_resolution_shortcut, bl_label=Apply Resolution Shortcut

## lime_pipeline/ops/ops_rev.py

Revision Navigation Operators

This module provides functionality for navigating between project revisions using
the Lime Pipeline revision letter system. It allows users to cycle through revision
letters (A-Z) for organizing different versions or iterations of project assets.

The revision system integrates with Lime Pipeline settings to maintain revision
state and provide intuitive navigation between different project versions.

Key Features:
- Alphabetical revision navigation (A-Z)
- Integration with Lime Pipeline settings and state management
- Cyclic navigation with wraparound from Z to A and A to Z
- Validation of revision letter format and constraints
- Error handling for missing or invalid revision settings

Clases Blender detectadas:

- LIME_OT_rev_prev (Operator): bl_idname=lime.rev_prev, bl_label=Previous Revision
- LIME_OT_rev_next (Operator): bl_idname=lime.rev_next, bl_label=Next Revision

## lime_pipeline/ops/ops_save_templates.py

Template Saving Operators

This module provides functionality for saving scene templates and configurations
within the Lime Pipeline workflow. It handles the creation and management of
reusable scene templates for consistent project setup and asset organization.

The template system supports saving current scene state, collection structures,
and project configurations for reuse across different projects and shots.

Key Features:
- Scene template creation and management
- Integration with Lime Pipeline project structure
- Template versioning and organization
- Validation of template data before saving
- Support for different template types and categories
- Error handling for template creation failures

Clases Blender detectadas:

- LIME_OT_save_as_with_template (_SaveTemplateOperatorBase, Operator): bl_idname=lime.save_as_with_template, bl_label=Save As (Template)
- LIME_OT_save_as_with_template_raw (_SaveTemplateOperatorBase, Operator): bl_idname=lime.save_as_with_template_raw, bl_label=Save As Raw (Template)

## lime_pipeline/ops/ops_scene_continuity.py

Scene Continuity Operator

Creates the next scene .blend using the current file's naming, freezing the pose of a
selected SHOT collection and the active camera at a chosen handoff frame. The operator
keeps the original file untouched by saving a copy, undoing local changes, and finally
opening the new file.

Clases Blender detectadas:

- LIME_OT_stage_create_next_scene_file (Operator): bl_idname=lime.stage_create_next_scene_file, bl_label=Create Next Scene File

## lime_pipeline/ops/ops_select_root.py

Project Root Selection Operators

This module provides functionality for selecting and setting the project root directory
within the Lime Pipeline workflow. It handles folder picker dialogs and automatic
detection of project root directories based on naming conventions.

The root selection system integrates with Lime Pipeline preferences and provides
intelligent project root detection by walking up directory trees to find matching
project folder structures.

Key Features:
- Interactive folder picker for project root selection
- Automatic project root detection using naming conventions
- Integration with Lime Pipeline preferences and settings
- Validation of selected directory paths
- Error handling for invalid or inaccessible paths
- Support for development and production project structures

Clases Blender detectadas:

- LIME_OT_pick_root (Operator): bl_idname=lime.pick_root, bl_label=Pick Project Root

## lime_pipeline/ops/ops_shots.py

SHOT Management Operators

This module provides comprehensive functionality for creating, managing, and organizing
SHOT scenes within the Lime Pipeline workflow. SHOTs represent individual scene files
that are organized sequentially for production pipelines.

The operators handle SHOT lifecycle including creation, duplication, validation, and
maintenance of proper SHOT naming conventions and collection structures.

Key Features:
- Automated SHOT creation with proper numbering and naming
- SHOT duplication with intelligent renaming and structure preservation
- Integration with Lime Pipeline project naming conventions
- Validation of SHOT contexts and prerequisites
- Collection tree management for SHOT organization
- Sequential SHOT numbering and tracking
- Error handling and user feedback for SHOT operations

Clases Blender detectadas:

- LIME_OT_new_shot (Operator): bl_idname=lime.new_shot, bl_label=New Shot
- LIME_OT_delete_shot (Operator): bl_idname=lime.delete_shot, bl_label=Delete Shot
- LIME_OT_duplicate_shot (Operator): bl_idname=lime.duplicate_shot, bl_label=Duplicate Shot
- LIME_OT_activate_shot (Operator): bl_idname=lime.activate_shot, bl_label=Activate Shot
- LIME_OT_jump_to_first_shot_marker (Operator): bl_idname=lime.jump_to_first_shot_marker, bl_label=Jump to First Shot Camera Marker
- LIME_OT_render_shots_from_markers (Operator): bl_idname=lime.render_shots_from_markers, bl_label=Render Shots (RAW)

## lime_pipeline/ops/ops_stage_hdri.py

Stage HDRI Operators

Provides quick actions to switch the active scene world between packaged HDRI
variants (contrast and light). Worlds are created on demand, re-used on
subsequent executions, and configured with mapping controls so the Stage panel
can expose rotation/offset tweaking while keeping the original world untouched.

Clases Blender detectadas:

- LIME_OT_stage_set_hdri (Operator): bl_idname=lime.stage_set_hdri, bl_label=Set Stage HDRI

## lime_pipeline/ops/ops_step_clean.py

Production Step Cleanup Operators

This module provides functionality for cleaning up scene elements based on production
pipeline steps. It handles the removal of intermediate objects, cleanup of temporary
data, and preparation of scenes for different stages of the production process.

The cleanup operators support various geometry types and can recursively process
object hierarchies to ensure comprehensive cleanup while preserving essential elements.

Key Features:
- Geometry-based object cleanup with support for multiple object types
- Recursive processing of object hierarchies and children
- Pattern-based object identification for selective cleanup
- Integration with production step tracking and validation
- Preservation of essential objects during cleanup operations
- Comprehensive error handling for complex scene hierarchies

Clases Blender detectadas:

- LIME_OT_clean_step (Operator): bl_idname=lime.clean_step, bl_label=Clean .STEP

## lime_pipeline/ops/ops_texture_adopt.py

Texture Fix/Adopt operator.

Copies external "loose" textures into the project shared folder:
<RAMV>/RSC/Textures

Rules:
- Never modify textures that are linked/library/protected roots.
- Copy (do not move) eligible files and relink Blender image paths.
- Deduplicate by file content hash (sha256) using an on-disk index.
- Write a JSON manifest: originals -> adopted paths and skipped reasons.

Clases Blender detectadas:

- LIME_OT_texture_adopt (Operator): bl_idname=lime.texture_adopt, bl_label=Adopt Textures (Fix)

## lime_pipeline/ops/ops_texture_manifest_cleanup.py

Texture manifest cleanup operator.

Deletes the _manifests folder under the project RSC/Textures directory.
This removes JSON reports and hash index files generated by texture scan/adopt.

Clases Blender detectadas:

- LIME_OT_texture_manifest_cleanup (Operator): bl_idname=lime.texture_manifest_cleanup, bl_label=Delete Texture Manifests

## lime_pipeline/ops/ops_texture_scan.py

Texture Scan/Report operator.

First deliverable for safer texture workflows:
- Detect images used by materials (Image Texture nodes, including nested groups).
- Classify them conservatively into:
  - Protected (linked/library/asset-library roots) -> never touch
  - External user paths (outside project root) -> candidates to adopt
  - In-project / packed / generated / missing -> report only
- Write a JSON report with proposed adoption destinations (no modifications).

Clases Blender detectadas:

- LIME_OT_texture_scan_report (Operator): bl_idname=lime.texture_scan_report, bl_label=Scan Textures (Report)

## lime_pipeline/ops/ops_tooltips.py

Tooltip and Information Display Operators

This module provides functionality for displaying detailed information and tooltips
within the Lime Pipeline interface. It handles the presentation of contextual help,
detailed descriptions, and informational content to users.

The tooltip system supports dynamic content display, clipboard integration for
easy information sharing, and customizable presentation modes for different types
of informational content.

Key Features:
- Dynamic tooltip display with customizable content
- Clipboard integration for easy information copying
- Context-sensitive information presentation
- Support for multi-line text and formatted content
- Integration with Blender's operator description system
- Configurable display modes and interaction options

Clases Blender detectadas:

- LIME_OT_show_text (Operator): bl_idname=lime.show_text, bl_label=Info

## lime_pipeline/ops/ops_view_layers.py

Operators to configure standard view layers for Lime Pipeline shots.

Clases Blender detectadas:

- LIME_OT_create_view_layers (Operator): bl_idname=lime.create_view_layers, bl_label=Create View Layers

