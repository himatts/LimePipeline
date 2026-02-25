---
name: ai-contract-check
description: Validate AI prompt/response contracts and safe-apply behavior. Use when changing AI Asset Organizer prompts/parsers, AI texture organizer staging, AI render conversion flow, or HTTP integration/fallback logic.
---

## Goal
Keep AI-assisted workflows deterministic, safe, and recoverable when APIs fail.

## Contract checks
1) Run AI-related core tests:
   - `python -m unittest tests.test_ai_asset_prompt tests.test_ai_asset_response tests.test_ai_asset_collection_paths tests.test_ai_asset_material_rules -v`
2) Confirm strict parsing and fallback paths still exist (`AI_BLOCKED`, error guards, cancel paths).
3) Verify decision and apply phases remain separated (plan first, mutate only on explicit apply).
4) Verify uniqueness and deterministic target resolution are preserved.
5) Verify guardrails for special object types (for example `LIGHT` and `CAMERA`) remain intentional.

## Fast code scan commands
- `rg -n "AI_BLOCKED|selected_for_apply|resolve|ambig|fallback|cancel" lime_pipeline/ops/ai_asset_organizer lime_pipeline/ops/ops_ai_textures_organizer.py lime_pipeline/ops/ops_ai_render_converter.py`
- `rg -n "json|schema|parse|normalize|unique" lime_pipeline/core/ai_asset_prompt.py lime_pipeline/core/ai_asset_response.py lime_pipeline/core/ai_asset_collection_paths.py`

## Outputs
- Test results and impacted AI modules.
- Explicit note of contract changes (if any).
- Confirmation that apply safety and fallback behavior remain intact.
