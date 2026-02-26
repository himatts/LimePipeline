# Lime Pipeline - Architecture

This document describes the high-level architecture, responsibilities per module, key flows, and invariants.

## Overview
Lime Pipeline is a Blender add-on that standardizes project structure and naming: assists with first save/backup, SHOT collections, render/proposal view outputs, folder navigation, material normalization, and AI render conversion to storyboard sketches.

## Modules and boundaries

### core (pure-ish Python)
- Files: `core/material_naming.py`, `core/material_quality.py`, `core/asset_naming.py`, `core/collection_resolver.py`, `core/ai_asset_prompt.py`, `core/ai_asset_collection_paths.py`, `core/ai_asset_material_rules.py`, `core/ai_asset_response.py`, `core/naming.py`, `core/paths.py`, `core/validate.py`, `core/validate_scene.py`, `core/env_config.py`, `core/__init__.py`
- Responsibilities:
  - Material naming helpers: parse/build MAT_{TagEscena}_{Familia}_{Acabado}_{V##}, normalize components, enforce version blocks
  - Material quality heuristics: score existing names, classify excellence vs review needs, surface taxonomy-aligned hints
  - Collection destination resolver: deterministic ranking/ambiguity for full hierarchy paths (SHOT-aware)
  - AI organizer prompt/schema and JSON contract helpers (`ai_asset_prompt`)
  - AI organizer collection-path normalization and candidate serialization helpers (`ai_asset_collection_paths`)
  - AI organizer material normalization guardrails, context-tag override parsing, and add-tag intent detection (`ai_asset_material_rules`)
  - Project naming: normalize project names, build canonical filenames, detect/parse .blend names
  - Paths: map project type + rev + scene to folder targets
  - Validation: sanity checks for save operations (errors/warnings, path length)
  - Environment config: load local `.env` values for API credentials (OpenRouter/Krea)
  - Texture workspace helpers: shared texture-root resolution for cloud/local mode and protected external texture roots (including XPBR library path)
  - Scene validation helpers (selection/shot context); note: this file uses bpy
- Rules:
  - Only `validate_scene.py` imports `bpy` at module import time; the rest keep it local when needed
  - Constants and regex live here (single source of truth)

### data
- Files: `data/templates.py`
- Responsibilities:
  - Declarative templates/constants (e.g., `SHOT_TREE`, collection names and colors)
- Rules:
  - No imperative code; only data structures

### props
- Files: `props.py` (WindowManager state), `props_ai_assets.py` (Scene-scoped AI asset organizer proposals), `props_ai_renders.py` (Scene-scoped AI render conversion state)
- Responsibilities:
  - Centralize PropertyGroup definitions for persistent add-on state
  - Expose editable collections (`Scene.lime_ai_assets` for AI Asset Organizer, `Scene.lime_ai_textures` for AI Textures Organizer)
  - Store AI render converter paths, prompts, previews, and job status (`Scene.lime_ai_render`)

### scene
- Files: `scene/scene_utils.py`
- Responsibilities:
  - Create/instance/duplicate SHOT collections and subtrees based on templates
  - Renaming and remapping for duplicated objects
  - Camera background margin guides: `ensure_camera_margin_backgrounds` helper for automatic setup
- Dependencies:
  - Uses `bpy` and consumes `data/templates.py` and `core/validate_scene.py`

### ops (operators)
- Files: `ops/*`
- Responsibilities:
  - User actions (create folders/files, backups, renders, proposal views, camera rigs, select root, stage lights, material normalization)
- Highlights:
- `ops/ai_asset_organizer/*`: modular AI Asset Organizer package (`operators_*`, `runtime_api`, `planner`, `target_resolver`, `scene_snapshot`, `material_probe`, `openrouter_client`) with `ops_ai_asset_organizer.py` as compatibility shim
- `ops_ai_render_converter.py`: AI render conversion (source frame render, prompt rewriting, Krea job creation/polling, download, manifest)
- Camera operations (`ops_cameras.py`): rig and simple camera creation in SHOT camera collections, automatic margin background setup on camera creation/duplication
- Rules:
  - UI feedback via `self.report`
  - Delegate naming/validation/paths to `core`; do not duplicate

### ui (panels)
- Files: `ui/*`
- Responsibilities:
  - Layout and user interactions; no heavy IO
- Highlights:
  - `ui_ai_render_converter.py`: Lime Pipeline panel for AI Render Converter (source detection, thumbnail grids, large previews, generate/retry, cleanup, output access)
- `ui_model_organizer.py`: 3D Model Organizer (Lime Toolbox) hosts Linked Data Localization actions at the end of the panel; linked-localization prioritizes selected objects and falls back to recursive active-collection scan (linked/override aware), localizes objects while keeping mesh data linked, and realizes selected collection instances into local hierarchies; `Resync Object Materials` is selection-only and reloads used libraries before copying mesh DATA materials into OBJECT-level slots for editable meshes with external mesh data; the UI shows preflight diagnostics and large operations require confirmation; Apply Deltas status/action is selection-scoped
- `ui_ai_asset_organizer.py`: Lime Toolbox panel for naming/organization (objects/materials/collections) and focused popup manager; planned collections are surfaced as editable virtual rows synced with object target paths
- `ui_ai_textures_organizer.py`: standalone Lime Toolbox panel for staged texture workflow (Analyze -> Refine -> Apply) with editable hints and explicit apply
- Dimension Utilities panel (`ui_dimension_utilities.py`) hosts the Dimension Checker UI, overlay unit visibility toggles, and measurement unit presets (mm/cm/m/in/ft); each run creates a new helper, which remains until manually removed and updates live when its active parent is scaled; overlay text turns yellow when targets have unapplied scale
- Rules:
  - Prefer Blender native subpanels for sections (parent/child panels) instead of manual collapsible boxes
  - `draw()` must be fast (no disk scans/hydration); use handlers or cached state

### Registration
- File: `lime_pipeline/__init__.py`
- Central class registration and `load_post` handler to hydrate state from current .blend
- UI uses parent panels with subpanels (`bl_parent_id`) for Settings/Cameras/Outputs (Render) and List/Tools (Shots)

## Key flows


### AI Connectivity Check
1. OpenRouter connectivity for naming workflows is exposed as `lime_tb.ai_asset_test_connection`.
2. Add-on preferences use that operator as the canonical "Test Connection" entry point.

### AI Asset Organizer v2 (AI-assisted)
1. User clicks **Suggest Names (AI)** from Lime Toolbox.
2. Operator collects selected objects/materials and optional non-SHOT collections from selection ownership.
3. Prompt includes hierarchy/context metadata (`parent_id`, `children_count`, `shared_data_users`, collection paths, scene hierarchy) and enforces strict JSON output; object entries may optionally return `target_collection_hint`.
4. Response parsing is strict: every requested ID must be returned exactly once, with valid strings and sanitized optional hints; partial/invalid payloads are rejected (no partial apply).
5. Suggestions are written to `Scene.lime_ai_assets.items` with row status (`NORMALIZED`, `INVALID`, `NORMALIZED_RELINK`, `NORMALIZED_FALLBACK`, read-only) plus destination metadata (`target_collection_path`, `target_status`, ranked candidates).
6. Request batching uses a dynamic prompt-budget cap (instead of a fixed per-category cap) and deterministic ordering to reduce order-dependent variability.
7. A local deterministic resolver analyzes the full collection tree to choose destination paths (`AUTO`) or mark unresolved cases (`AMBIGUOUS`), prioritizing SHOT branch context.
8. Preview counters are computed from a unified planner before apply (`planned_renames_*`, material relinks/orphan removals, deep-path collections to create, objects to move, ambiguous/skipped counts).
9. **Apply Selected** renames selected rows with uniqueness guarantees and Apply Scope filters (objects/materials/collections):
   - Objects: PascalCase segments separated by underscores, numeric suffix as `_NN`, deterministic uniqueness.
   - Materials: `MAT_*` validation, existing-name reuse, relink-first strategy, and local orphan cleanup after relink when safe.
   - Collections: canonical (normalized/case-insensitive) matching before create/rename to prevent near-duplicate branches.
10. Optional post-apply organization links objects to resolved target paths, enforces a single editable primary collection per object (while preserving read-only memberships), creates missing subcollection paths when required, and skips ambiguous objects until confirmed.
11. Ambiguous rows can be resolved explicitly from the panel using full collection paths.

### AI Render Converter (Storyboard)
1. Resolve current frame and expected source render path under Storyboard/editables/AI/sources.
2. If missing, render the current frame to the source path.
3. Select a style reference image (optional) and choose conversion mode (Sketch or Sketch + Details).
   - The panel filters assets per section and supports large Image Editor previews.
4. For Sketch + Details, rewrite user details via OpenRouter and build the final prompt.
5. Upload source/style assets to Krea and create a generation job (Nano Banana / Pro).
6. Poll job status with backoff until completed, then download results.
7. Save outputs under Storyboard/editables/AI/outputs and update the per-frame manifest.
8. Optionally add the result image to the Video Sequencer.

### First save (Create .blend)
1. User selects Project Root, Project Type, Rev letter, Scene (if required)
2. UI calls `core.validate.validate_all(state, prefs)`
   - Validates invariants; builds `filename` and `target_path`
3. Operator `ops_create_file` writes via `bpy.ops.wm.save_as_mainfile(filepath=target_path)`

### Backups
1. `ops_backup` resolves `backups` directory via `validate_all`
2. Creates `Backup_XX_` file and copies current .blend after saving

### SHOTs structure
1. `scene_utils.create_shot` creates root `SHOT ##`
2. `scene_utils.ensure_shot_tree` applies `data/SHOT_TREE` under SHOT
3. `duplicate_shot` creates mirrored collections and object duplicates with remapping

### Proposal Views / Renders
1. Resolve `(project_name, sc, rev)` from current file or state
2. Build output filename per camera and shot
3. Optionally isolate the active SHOT (hide others) during capture/render
4. Save image to `editables` folder for corresponding project type

## Invariants
- Material names follow `MAT_{TagEscena}_{Familia}_{Acabado}_{V##}` (no `_1`/`.001` suffixes)
- Project Root matches `RE_PROJECT_DIR = ^[A-Z]{2}-\d{5}\s+(.+)$`
- Revision letter is a single A-Z
- Types requiring scene number: `PV, REND, SB, ANIM`
- Scene number: 1-999; if `free_scene_numbering` is false, must be multiple of `prefs.scene_step`
- Paths and names built only through `core` helpers

## Constants and single sources of truth
- RAMV base dir: build via `core.paths.paths_for_type` (do not duplicate literals)
- Material families enum: `core.material_naming.ALLOWED_FAMILIES`
- Tokens by project type: `core.naming.TOKENS_BY_PTYPE`
- Filename scheme: `core.naming.make_filename`

## Version compatibility
- Blender 4.5+
- Access to Cycles/ColorManagement guarded by capability checks; degrade gracefully

## Error handling
- No silent exceptions; prefer logging and `self.report`
- UI shows warnings/errors produced by `validate_all`

## Internationalization
- Base language: English for UI/messages
- Future: use Blender i18n translations if bilingual UI is required

## Future improvements
- Central `constants.py` to host shared literals/regex
- Lightweight logging util (toggle in preferences)
- Unit tests for `core` and optional smoke tests in CI

## Canonical rules and docs maintenance
- Canonical rules for agents: `AGENTS.md` (source of truth for editing workflow rules)
- If user-visible behavior or architecture changes, also update: `README.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`


