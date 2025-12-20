# PROPS_AI_MATERIALS.PY — Catálogo por archivo

## lime_pipeline/props_ai_materials.py

AI Material Properties and State Management

This module defines the property groups and state management for the AI Material
Renamer feature within Lime Pipeline. It handles material scanning results,
rename proposals, and user selection state for batch material operations.

The AI material system provides a complete workflow for analyzing existing materials,
proposing improved names based on AI analysis, and applying the approved changes.
The property system manages material metadata, rename proposals, and user selection
states throughout the renaming workflow.

Key Features:
- Material scan results storage with rename proposals and status tracking
- Selection management for batch operations on large material sets
- Integration with Lime Pipeline naming conventions and validation
- Status categorization (VALID, NEEDS_RENAME, etc.) for workflow management
- Read-only material detection for library and linked materials
- Dynamic selection updates with automatic preview refresh
- Support for material type and finish classification

Clases Blender detectadas:

- LimeAIMatRow (PropertyGroup)
- LimeAIMatState (PropertyGroup)

