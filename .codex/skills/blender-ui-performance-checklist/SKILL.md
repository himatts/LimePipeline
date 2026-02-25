---
name: blender-ui-performance-checklist
description: Run a focused UI performance and separation checklist for Blender panels. Use when editing files in `lime_pipeline/ui/`, changing panel hierarchy, or adding UI lists/properties tied to operators.
---

## Goal
Keep panel draw paths fast and side-effect free.

## Checklist
1) Ensure `draw()` does not do filesystem/network/heavy operations.
2) Ensure state mutation stays in operators, not panel draw code.
3) Ensure panel hierarchy (`bl_parent_id`, `bl_order`, category) remains coherent.
4) Ensure new UI classes/props are registered and unregistered correctly.
5) Ensure user feedback surfaces preflight/error state clearly.

## Fast scan commands
- `rg -n "def draw\\(" lime_pipeline/ui`
- `rg -n "open\\(|Path\\(|requests\\.|http|urllib|json\\.load|subprocess|thread" lime_pipeline/ui`
- `rg -n "bl_parent_id|bl_order|bl_category" lime_pipeline/ui`

## Follow-up
- Run `registration-audit` for registration/export checks.
- Run `docs-delta` if panel behavior or user instructions changed.

## Outputs
- Checklist pass/fail notes per UI file touched.
- Registration/doc follow-up status.
