"""
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
"""

from . import scene_utils

__all__ = ["scene_utils"]


