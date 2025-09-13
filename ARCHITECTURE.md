# Lime Pipeline – Architecture

This document describes the high-level architecture, responsibilities per module, key flows, and invariants.

## Overview
Lime Pipeline is a Blender add-on that standardizes project structure and naming: assists with first save/backup, SHOT collections, render/proposal view outputs, and folder navigation.

## Modules and boundaries

### core (pure-ish Python)
- Files: `core/naming.py`, `core/paths.py`, `core/validate.py`, `core/validate_scene.py` (uses bpy), `core/__init__.py`
- Responsibilities:
  - Naming: normalize project names, build canonical filenames, detect/parse .blend names
  - Paths: map project type + rev + scene to folder targets
  - Validate: sanity checks for save operations (errors/warnings, path length)
  - Scene validation helpers (selection/shot context); note: this file uses bpy
- Rules:
  - No `bpy` imports at module level except in `validate_scene.py` where it's inherently needed; prefer local imports
  - Constants and regex live here (single source of truth)

### data
- Files: `data/templates.py`
- Responsibilities:
  - Declarative templates/constants (e.g., `SHOT_TREE`, collection names and colors)
- Rules:
  - No imperative code; only data structures

### scene
- Files: `scene/scene_utils.py`
- Responsibilities:
  - Create/instance/duplicate SHOT collections and subtrees based on templates
  - Renaming and remapping for duplicated objects
- Dependencies:
  - Uses `bpy` and consumes `data/templates.py` and `core/validate_scene.py`

### ops (operators)
- Files: `ops/*`
- Responsibilities:
  - User actions (create folders/files, backups, renders, proposal views, camera rigs, select root, stage lights)
- Rules:
  - UI feedback via `self.report`
  - Delegate naming/validation/paths to `core`; do not duplicate

### ui (panels)
- Files: `ui/*`
- Responsibilities:
  - Layout and user interactions; no heavy IO
- Rules:
  - Prefer Blender native subpanels for sections (parent/child panels) instead of manual collapsible boxes
  - `draw()` must be fast (no disk scans/hydration); use handlers or cached state

### Registration
- File: `lime_pipeline/__init__.py`
- Central class registration and `load_post` handler to hydrate state from current .blend
- UI uses parent panels with subpanels (`bl_parent_id`) for Settings/Cameras/Outputs (Render) and List/Tools (Shots)

## Key flows

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
- Project Root matches `RE_PROJECT_DIR = ^[A-Z]{2}-\d{5}\s+(.+)$`
- Revision letter is a single A–Z
- Types requiring scene number: `PV, REND, SB, ANIM`
- Scene number: 1–999; if `free_scene_numbering` is false, must be multiple of `prefs.scene_step`
- Paths and names built only through `core` helpers

## Constants and single sources of truth
- RAMV base dir: build via `core.paths.paths_for_type` (do not duplicate literals)
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
- Canonical rules file: `.cursor/rules/limepipelinerules.mdc` (source of truth for editing/architecture rules).
- If user-visible behavior or architecture changes, also update: `README.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`.
