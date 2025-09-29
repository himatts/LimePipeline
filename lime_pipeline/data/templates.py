"""Declarative templates and constants for scene structure.

This module defines the canonical SHOT subtree and duplication policies.
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


