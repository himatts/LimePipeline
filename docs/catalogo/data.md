# DATA — Catálogo por archivo

## lime_pipeline/data/__init__.py

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

## lime_pipeline/data/templates.py

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

