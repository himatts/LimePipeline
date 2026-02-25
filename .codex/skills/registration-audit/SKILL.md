---
name: registration-audit
description: Audit Blender registration/export wiring after operator or UI changes. Use when adding, renaming, moving, or deleting classes in `ops/`, `ui/`, or any place that affects `lime_pipeline/__init__.py`, `ops/__init__.py`, and `ui/__init__.py`.
---

## Goal
Prevent broken addon registration due to missing imports, stale exports, or orphaned class references.

## Audit steps
1) List changed operator/UI classes:
   - `rg -n "^class\\s+LIME_[A-Z0-9_]+\\(" lime_pipeline/ops lime_pipeline/ui`
2) Check module export surfaces:
   - `rg -n "LIME_[A-Z0-9_]+" lime_pipeline/ops/__init__.py lime_pipeline/ui/__init__.py`
3) Check central registration/import wiring:
   - `rg -n "LIME_[A-Z0-9_]+" lime_pipeline/__init__.py`
4) Check operator idnames stay under `lime.` namespace:
   - `rg -n "bl_idname\\s*=\\s*\"lime\\.[^\"]+\"" lime_pipeline/ops`
5) Remove orphan imports and add missing exports in the three `__init__.py` files.
6) Optionally run full tests after refactors: `python -m unittest discover tests -v`.

## Outputs
- Confirmed list of audited classes.
- Missing or removed registration entries.
- Duplicate or invalid `bl_idname` findings when detected.
