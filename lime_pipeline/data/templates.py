"""
Scene Structure Templates and Constants

This module defines the canonical SHOT subtree structure, naming conventions,
and duplication policies used throughout the Lime Pipeline workflow. It provides
the foundational data structures that ensure consistent scene organization
and object duplication behavior.

The templates define the hierarchical structure of SHOT collections, including
camera setups, lighting, main assets, props, and background elements. The
duplication policies control how objects and data blocks are handled during
scene duplication operations.

Key Features:
- Canonical SHOT collection hierarchy with standardized naming
- Collection naming constants for cameras, lights, main assets, and backgrounds
- Duplication policy definitions (DUPLICATE, INSTANCE, SKIP)
- SHOT tree structure templates for consistent scene creation
- Integration with Lime Pipeline naming conventions
- Centralized constants to avoid duplication across modules
"""

# Naming constants
SHOT_ROOT_PATTERN = r"^SHOT (\d{2,3})$"

C_CAM = "00_CAM"
C_LIGHTS = "00_LIGHTS"
C_MAIN_FMT = "01_{ProjectName}_MAIN"
C_PROPS = "02_PROPS"
C_BG = "90_BG"

# Duplication policy values
DUPLICATE = "DUPLICATE"
INSTANCE = "INSTANCE"
SKIP = "SKIP"


SHOT_TREE = [
    {"name": C_CAM, "children": [], "dup_policy": DUPLICATE, "color_tag": "COLOR_04"},     # Green
    {"name": C_LIGHTS, "children": [], "dup_policy": DUPLICATE, "color_tag": "COLOR_03"},  # Yellow
    {"name": C_MAIN_FMT, "children": [], "dup_policy": DUPLICATE, "color_tag": "COLOR_01"},  # Red
    {"name": C_PROPS, "children": [], "dup_policy": DUPLICATE, "color_tag": "COLOR_05"},   # Blue
    {"name": C_BG, "children": [], "dup_policy": DUPLICATE, "color_tag": "COLOR_01"},      # Red
]


