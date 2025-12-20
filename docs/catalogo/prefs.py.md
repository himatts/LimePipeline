# PREFS.PY — Catálogo por archivo

## lime_pipeline/prefs.py

Addon Preferences and Configuration

This module defines the Lime Pipeline addon preferences interface and configuration
options. It provides user-configurable settings for project paths, validation rules,
and feature toggles that customize the addon behavior for different studio environments.

The preferences system integrates with Blender's addon preferences framework and
provides persistent storage for user settings across Blender sessions. Settings
include project root paths, validation thresholds, feature toggles, and API
configurations for external services.

Key Features:
- Project root path configuration for production and development environments
- Validation thresholds for path length warnings and errors
- Scene numbering step configuration for consistent numbering
- Feature toggles for optional functionality (dimension utilities, auto-normalization)
- API configuration for external services (OpenRouter for AI features)
- Render preset storage and management
- Integration with Blender's native preferences system

