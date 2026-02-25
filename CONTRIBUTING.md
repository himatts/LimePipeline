# Contributing to Lime Pipeline (Blender add-on)

Thank you for contributing! This guide explains how to propose changes while preserving stability and consistency.

## Testing policy
- Do not add new tests unless explicitly requested.
- The primary validation loop is manual testing inside Blender during development.

## Local development (Cursor + Blender)
This add-on is developed primarily in the Cursor IDE using the **Blender Development** extension by **Jacques Lucke** (*Tools to simplify Blender development*).

Typical workflow:
1. Start Blender from the IDE.
2. Install/enable the add-on once.
3. Iterate quickly by reloading the add-on or running the current file from the Command Palette (search for `Blender:`).

See `docs/guias/desarrollo-cursor-blender-development.md` for details.

## Scope and versions
- Blender minimum version: 4.5.0
- Python: Blender bundled
- Add-on goals: project organization, canonical naming, SHOT structure, save/backup/render utilities
- AI Asset Organizer v2: object/material/collection naming, hierarchy-aware target resolution, ambiguity handling, preview counters, apply-scope filters, and optional collection organization
- AI Asset Organizer context text is creative guidance by default; material tags can be requested either with explicit override directives (`force tag: X`, `fixed tag: X`) or with add-tag intent (for example "add/agrega un tag"), which triggers automatic tag inference from object context
- AI Asset Organizer v2 object/collection format: PascalCase segments separated by underscores (numeric suffix as `_NN`)
- AI Textures Organizer is a standalone Lime Toolbox panel with staged flow (Analyze -> Refine -> Apply)
- Texture Scan/Adopt must preserve external protected libraries (Asset Libraries + XPBR) and in local mode write under `<local_project_root>/rsc/Textures`
- AI Material Renamer is fully retired; use AI Asset Organizer for AI material workflows
- AI Render Converter UI includes thumbnail grids per section, large previews, cleanup tools, and output access
- Linked Collections localization UI lives in 3D Model Organizer (Lime Toolbox); scope is selection-first, with recursive active-collection fallback for linked/override targets; conversion preserves hierarchy, makes objects local, and keeps mesh data linked
- Linked Collections UI must expose preflight context (scope + candidate counts + unavailable reason) before execution; large conversions trigger confirmation
- `Resync Object Materials` lives in the same Linked Data Localization section and is selection-only: it reloads used libraries and copies mesh DATA materials back to OBJECT-level slots on eligible editable meshes
- 3D Model Organizer `Apply Deltas` and location-offset warning are selection-scoped (not whole-scene)
- Dimension Checker behavior: each run creates a new helper; manual cleanup is expected
- Dimension Checker overlay units are user-configurable (mm/cm/m/in/ft)
- Dimension Checker helpers parent to the active object and update live on scale
- Dimension Checker overlay warns about unapplied scale (yellow labels)
- Cameras panel supports adding Camera Rigs or Simple Cameras inside the active SHOT

## Repository layout (high level)
- `lime_pipeline/core`: naming, paths, validation, parsing (no hard `bpy` dependency), including AI organizer pure helpers (`ai_asset_prompt`, `ai_asset_collection_paths`, `ai_asset_material_rules`)
- `lime_pipeline/data`: declarative templates/constants (e.g., SHOT_TREE)
- `lime_pipeline/scene`: Blender scene helpers (collections/SHOTs)
- `lime_pipeline/ops`: Blender operators (UI-triggered actions), including `ops/ai_asset_organizer/` subpackage for AI organizer orchestration
- `lime_pipeline/ui`: Panels and UI drawing

See ARCHITECTURE.md for details.

## Development workflow
1. Create a feature branch from `main`.
2. Implement changes following rules below.
3. Update docs if applicable: AGENTS.md, ARCHITECTURE.md, this file, README.md.
4. Manually test in Blender (preferred) using Blender Development.
5. Open a Pull Request; include:
   - Summary and rationale (the "why")
   - Affected modules
   - Screenshots/GIFs (UI changes)
   - Check PR checklist (below)

## Coding standards
- Language: English for UI, messages, and comments.
- Naming:
  - Classes: `PascalCase`
  - Constants: `UPPER_SNAKE_CASE`
  - Functions/variables: `snake_case`
  - Operators: class prefix `LIME_OT_`, `bl_idname` prefixed with `lime.`
  - Panels: class prefix `LIME_PT_`
- Types and imports:
  - Use `from __future__ import annotations` where useful
  - Public functions have explicit type annotations
  - In `core/*`, do not import `bpy` at module level; if needed, import locally in functions
- Errors/logging:
  - Avoid `except Exception: pass`; report meaningful errors
  - In operators, prefer `self.report({'ERROR'|'WARNING'|'INFO'}, msg)` for user feedback
- UI performance and structure:
  - Prefer native subpanels (parent with `bl_parent_id` children) instead of ad-hoc collapsible boxes
  - `draw()` must not perform heavy IO or mutate state; hydrate via handlers or cached state
- Paths and naming:
  - File naming via `core.naming.make_filename` and `resolve_project_name`
  - Paths via `core.paths.paths_for_type`
  - Do not duplicate literals like RAMV base directory

## PR checklist (must)
- [ ] UI and messages in English
- [ ] No duplicated literals for paths/constants (use helpers)
- [ ] No duplicated logic (reuse `core`/`scene`)
- [ ] No IO in `draw()`; no silent `except`
- [ ] Public functions typed; short docstrings on "why"
- [ ] Bump `bl_info["version"]` if user-facing behavior changes
- [ ] Docs updated if visible behavior or structure changed (README, ARCHITECTURE, CONTRIBUTING)

## Existing tests (optional)
The repo contains unit tests for `core/` logic (including AI organizer helper modules). Use:
- `python -m unittest discover tests -v`

## AI Asset Organizer smoke checklist
- Select objects with materials and run **Suggest Names (AI)**; verify editable rows and read-only handling.
- In SHOT-structured scenes, verify target resolution prioritizes the current SHOT branch and shows full destination paths.
- Validate ambiguous destination handling: unresolved rows must show candidate paths and require confirmation (or be skipped on apply).
- Use **Apply Scope** presets/toggles (All / Only Objects / Only Materials / Only Collections) and verify only enabled types are applied.
- Apply selected rows and verify uniqueness handling for objects/materials/collections.
- Enable **Organize Collections on Apply** and verify deep destination paths are created when missing.
- Verify apply is partial-safe: ambiguous objects are skipped while unambiguous operations still execute.
- Run **Analyze Textures**, **Refine Suggestions (AI)**, and **Apply Texture Plan** from AI Textures Organizer and verify manifests are written under `rsc/Textures/_manifests`.

## Commit style
- Conventional summary preferred: feat:, fix:, chore:, refactor:, docs:
- Keep commits scoped; one concern per commit

## Deprecation policy
- Mark deprecated features, keep for one minor release, remove next minor

## Security and paths
- Enforce path length limits (warn/block) from preferences
- Never write outside computed target directories
- Keep API keys only in local `.env` (never in tracked files or Blender preferences)

## How to search before adding
- Check if helpers already exist in `core/naming.py`, `core/paths.py`, `core/validate.py`, `scene/scene_utils.py`, `data/templates.py`
- If similar exists, extend or reuse instead of duplicating

## Canonical rules file
- The canonical rules for agents live in: `AGENTS.md`.

Thanks for keeping Lime Pipeline robust and consistent!

