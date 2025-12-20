# SCENE — Catálogo por archivo

## lime_pipeline/scene/__init__.py

Scene Management Utilities

This package provides utilities for managing Blender scene structure and SHOT
organization within the Lime Pipeline workflow. It handles scene creation,
SHOT collection management, and camera background generation.

The scene utilities support complex scene duplication, collection hierarchy
management, and automatic background plane creation that follows camera
movements based on timeline markers.

Key Features:
- SHOT collection creation and management with proper naming conventions
- Scene duplication with intelligent object and data block handling
- Camera background plane generation with automatic positioning
- Collection hierarchy traversal and validation utilities
- Integration with Lime Pipeline project naming and structure

## lime_pipeline/scene/scene_utils.py

Scene Utilities for SHOT Management

This module provides comprehensive utilities for managing Blender scene structure
and SHOT collections within the Lime Pipeline workflow. It handles scene creation,
SHOT organization, duplication, and camera background generation.

The SHOT system provides structured scene organization with numbered collections
(SHOT 001, SHOT 002, etc.) that contain all assets for individual shots or
sequences. The utilities support complex scene duplication, collection hierarchy
management, and automatic background plane creation that follows camera movements.

Key Features:
- SHOT collection creation with canonical naming and structure
- Scene duplication with intelligent object and data block handling
- Camera background plane generation with automatic positioning and scaling
- Collection hierarchy traversal and validation utilities
- Object parenting and constraint preservation during duplication
- Integration with Lime Pipeline project naming conventions
- Comprehensive error handling for complex scene operations
- Support for nested collection hierarchies and object relationships

