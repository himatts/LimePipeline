"""Declarative templates and constants for scene structure.

This module defines the canonical SHOT subtree and duplication policies.
"""

# Naming constants
SHOT_ROOT_PATTERN = r"^SHOT (\d{2,3})$"

C_UTILS_CAM = "00_UTILS_CAM"
C_UTILS_LIGHTS = "00_UTILS_LIGHTS"
C_LIGHTS_MAIN = "00_LIGHTS_MAIN"
C_LIGHTS_AUX = "00_LIGHTS_AUX"
C_MAIN_FMT = "01_{ProjectName}_MAIN"
C_PROPS = "10_PROPS"
C_PROP_PLACEHOLDER = "10_PROP_NAME"
C_FX = "20_FX"
C_RIGS = "30_RIGS"
C_BG = "90_BG"

# Duplication policy values
DUPLICATE = "DUPLICATE"
INSTANCE = "INSTANCE"
SKIP = "SKIP"


SHOT_TREE = [
    {"name": C_UTILS_CAM, "children": [], "dup_policy": DUPLICATE, "color_tag": "COLOR_04"},  # Green
    {
        "name": C_UTILS_LIGHTS,
        "children": [
            {"name": C_LIGHTS_MAIN, "children": [], "dup_policy": DUPLICATE, "color_tag": "COLOR_03"},  # Yellow
            {"name": C_LIGHTS_AUX, "children": [], "dup_policy": DUPLICATE, "color_tag": "COLOR_03"},   # Yellow
        ],
        "dup_policy": DUPLICATE,
        "color_tag": "COLOR_03",  # Yellow
    },
    {"name": C_MAIN_FMT, "children": [], "dup_policy": DUPLICATE, "color_tag": "COLOR_01"},  # Red
    {
        "name": C_PROPS,
        "children": [
            {"name": C_PROP_PLACEHOLDER, "children": [], "dup_policy": DUPLICATE, "is_placeholder": True, "color_tag": "COLOR_05"},
        ],
        "dup_policy": DUPLICATE,
        "color_tag": "COLOR_05",  # Blue
    },
    {"name": C_FX, "children": [], "dup_policy": DUPLICATE, "color_tag": "COLOR_07"},   # Pink
    {"name": C_RIGS, "children": [], "dup_policy": DUPLICATE, "color_tag": "COLOR_06"}, # Purple
    {"name": C_BG, "children": [], "dup_policy": DUPLICATE, "color_tag": "COLOR_01"},   # Red
]


