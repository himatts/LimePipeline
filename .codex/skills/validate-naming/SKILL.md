---
name: validate-naming
description: Quick check of naming and paths before saves or renders
---

## When to use
Run before changing naming rules, save operators, or SHOT/Render workflows.

## Inputs
- Open .blend with current project type, revision, and scene number
- Access to `core` helpers

## Steps
1) Generate expected tokens via `core.naming.make_filename` and `core.paths.paths_for_type` for the active state.
2) Call `core.validate.validate_all(state, prefs)` to surface errors/warnings before saving or rendering.
3) For materials, reuse `core.material_naming` helpers to normalize proposals and check family/finish/version blocks.
4) If operators or UI panels were moved/renamed, verify corresponding `__init__.py` files still import/register the right classes (root, `ops/`, `ui/`).
5) Summarize findings (errors, warnings, suggested renames) for the PR or release notes.

## Outputs
- Checklist of naming/path issues and proposed fixes
- Confirmation that registration files remain consistent after changes
