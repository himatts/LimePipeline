# Contributing to Lime Pipeline (Blender add-on)

Thank you for contributing! This guide explains how to propose changes while preserving stability and consistency.

## Scope and versions
- Blender minimum version: 4.5.0
- Python: Blender bundled (PEP 8–ish; see Style below)
- Add-on goals: project organization, canonical naming, SHOT structure, save/backup/render utilities

## Repository layout (high level)
- `lime_pipeline/core`: naming, paths, validation, parsing (no hard `bpy` dependency)
- `lime_pipeline/data`: declarative templates/constants (e.g., SHOT_TREE)
- `lime_pipeline/scene`: Blender scene helpers (collections/SHOTs)
- `lime_pipeline/ops`: Blender operators (UI-triggered actions)
- `lime_pipeline/ui`: Panels and UI drawing

See ARCHITECTURE.md for details.

## Development workflow
1. Create a feature branch from `main`.
2. Implement changes following rules below.
3. Update docs if applicable: `.cursorrules`, `.cursor/rules/limepipelinerules.mdc`, ARCHITECTURE.md, this file, README.md.
4. Run tests (core unit tests) and smoke tests if changed behavior.
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

## Tests
- Unit (no Blender):
  - `core/naming.py` (normalize/parse/make_filename)
  - `core/paths.py` (paths_for_type)
  - `core/validate.py` (validate_all with fakes)
- Smoke (optional): run Blender headless for key flows
  - Example: `blender -b -P tests/smoke_render.py`

## Commit style
- Conventional summary preferred: feat:, fix:, chore:, refactor:, docs:
- Keep commits scoped; one concern per commit

## Deprecation policy
- Mark deprecated features, keep for one minor release, remove next minor

## Security and paths
- Enforce path length limits (warn/block) from preferences
- Never write outside computed target directories

## How to search before adding
- Check if helpers already exist in `core/naming.py`, `core/paths.py`, `core/validate.py`, `scene/scene_utils.py`, `data/templates.py`
- If similar exists, extend or reuse instead of duplicating

## Canonical rules file
- The canonical rules live in: `.cursor/rules/limepipelinerules.mdc`.
- `.cursorrules` may exist for editor compatibility, but the source of truth is `limepipelinerules.mdc`.

Thanks for keeping Lime Pipeline robust and consistent!
