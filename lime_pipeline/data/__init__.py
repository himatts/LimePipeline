"""
Data Templates and Resources

This package provides data templates, constants, and resources used throughout
the Lime Pipeline addon. It includes collection naming conventions, SHOT tree
structures, and other predefined data structures that ensure consistency
across the pipeline.

The data package centralizes naming conventions and structural templates that
are used by UI panels, operators, and scene management utilities to maintain
consistent project organization and naming standards.

Key Features:
- Collection naming constants for canonical SHOT structure
- SHOT tree templates with proper hierarchy definitions
- Camera and background collection naming conventions
- Centralized constants to avoid duplication across modules
- Template data structures for consistent scene creation
"""

from .templates import *

__all__ = [name for name in globals().keys() if name.isupper() or name.endswith("_TREE")]


