---
name: core-tests
description: Run Blender-agnostic unit tests for Lime Pipeline core logic. Use when editing files under `lime_pipeline/core/`, changing naming/path/validation behavior, or updating shared AI contract helpers covered by tests.
---

## Goal
Validate core business rules quickly and provide a PR-ready test summary.

## Test commands
1) Full suite:
   - `python -m unittest discover tests -v`
2) Naming/path focused subset:
   - `python -m unittest tests.test_asset_naming tests.test_texture_naming tests.test_texture_paths tests.test_texture_workspace tests.test_collection_resolver -v`
3) AI contract subset:
   - `python -m unittest tests.test_ai_asset_prompt tests.test_ai_asset_response tests.test_ai_asset_collection_paths tests.test_ai_asset_material_rules -v`

## Expectations
- Add or update tests whenever an invariant changes.
- Do not accept behavior changes in `core` without test coverage.
- Report failures with affected module + invariant, not only stack traces.

## Outputs
- Commands executed.
- Pass/fail summary.
- New or updated tests linked to changed behavior.
