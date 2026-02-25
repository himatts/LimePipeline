---
name: validate-naming
description: Validate naming and path rules before save/render workflows. Use when changing naming logic, path generation, first-save operators, backup flows, or SHOT/render conventions.
---

## Inputs
- Active project state (project type, revision, scene number, root mode).
- Access to `core.naming`, `core.paths`, `core.validate`, and material naming helpers.

## Steps
1) Generate expected filename/path tokens using `core.naming.make_filename` and `core.paths.paths_for_type`.
2) Run `core.validate.validate_all(state, prefs)` and capture errors/warnings.
3) Validate material naming proposals with `core.material_naming` helpers.
4) Confirm first-save/backups path outcomes match current pipeline rules.
5) If operators or UI moved, run `registration-audit` to verify `__init__.py` coherence.

## Outputs
- Checklist of naming/path issues and suggested fixes.
- Confirmation that registration files remain consistent after related changes.
