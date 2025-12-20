# PROPS.PY — Catálogo por archivo

## lime_pipeline/props.py

Core Properties and State Management

This module defines the core property groups and state management for the Lime
Pipeline addon. It provides the data structures that store project settings,
UI state, and configuration options that persist across Blender sessions.

The property system manages project metadata, scene organization settings,
render configurations, and user interface state. It integrates with Blender's
property system to provide persistent storage and UI binding for all Lime
Pipeline functionality.

Key Features:
- Project state management with naming, paths, and revision tracking
- Render preset storage and management with versioning
- Camera selection and scene organization utilities
- UI state management for collapsible panels and user preferences
- Integration with Lime Pipeline core validation and naming systems
- Automatic state synchronization between UI and underlying data
- Support for complex property relationships and update callbacks

Clases Blender detectadas:

- LimeRenderPresetSlot (PropertyGroup)
- LimePipelineState (PropertyGroup)

