---
name: addon-import-smoke
description: Run non-Blender smoke checks for imports and package wiring. Use when touching package structure, `__init__.py` files, module exports, or dependency boundaries that can break addon load.
---

## Goal
Catch import-time regressions early without launching Blender.

## Smoke checks
1) Check forbidden `bpy` imports in core:
   - `rg -n "^(from bpy|import bpy)" lime_pipeline/core --glob '!validate_scene.py'`
2) Compile python files to catch syntax/import statement issues:
   - `Get-ChildItem lime_pipeline -Recurse -Filter *.py | ForEach-Object { python -m py_compile $_.FullName }`
3) Run Blender-agnostic tests:
   - `python -m unittest discover tests -v`

## Notes
- This is a partial smoke check for standard Python.
- Full addon registration still requires Blender runtime (`bpy`, handlers, operator registration).

## Outputs
- Pass/fail result for import boundary checks.
- List of files failing compile/test checks.
