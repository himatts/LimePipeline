# PROPS_AI_ASSETS.PY — Catálogo por archivo

## lime_pipeline/props_ai_assets.py

AI Asset Organizer properties and state.

Stores AI-generated rename proposals for selected objects, materials and collections, including optional image context.
Also stores destination-resolution metadata for object rows (`target_collection_path`, `target_status`, candidate payload),
preview counters, apply-scope filters, and opt-in automation toggles:
- include collections in AI suggestions
- organize collections on apply
This module is intentionally UI-agnostic; panels and operators consume the state.

Clases Blender detectadas:

- LimeAIAssetItem (PropertyGroup)
- LimeAIAssetState (PropertyGroup)
