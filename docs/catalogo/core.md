# CORE — Catálogo por archivo

## lime_pipeline/core/__init__.py

Core utilities for Lime Pipeline.

This package centralizes naming and scene validation helpers used across UI and ops.

## lime_pipeline/core/asset_naming.py

Asset naming helpers for Lime Pipeline.

This module provides small, Blender-agnostic helpers used by tools that rename
scene assets (objects/materials). It intentionally avoids `bpy` imports so it
can be unit-tested outside Blender.

## lime_pipeline/core/material_naming.py

Material naming utilities for Lime Pipeline.

Defines helpers for the schema `MAT_{MaterialType}_{MaterialFinish}_{Version}`.

## lime_pipeline/core/material_quality.py

Material name quality evaluation utilities.

Provides heuristics to score how well an existing material name preserves
taxonomy semantics and conforms to Lime Pipeline conventions.

## lime_pipeline/core/material_reconciliation.py

Material Reconciliation Logic

Evaluates AI-proposed material names against the taxonomy index and determines
reconciliation actions (Accept, Normalize, or Manual Review).

Key functions:
- reconcile_proposal(): Compare proposal vs taxonomy, return action and reasoning
- find_closest_taxonomy_match(): Find nearest taxonomy type/finish by similarity
- is_experimental(): Determine if proposal is plausible but non-indexed
- apply_batch_normalization(): Intelligently normalize groups of non-indexed materials

## lime_pipeline/core/material_taxonomy.py

Material taxonomy utilities for Lime Pipeline AI Material Renamer.

Provides external taxonomy loading and inference helpers for material classification.

## lime_pipeline/core/naming.py

Project and Scene Naming Utilities

This module provides comprehensive utilities for Lime Pipeline project and scene naming
conventions, filename parsing, and project root detection. It handles the canonical
naming scheme used throughout the pipeline for consistent file organization.

The naming system supports project identification (XX-##### format), scene numbering
(SC###), revision tracking (Rev A-Z), and automatic project type detection from
filenames. It includes utilities for normalizing project names, parsing file metadata,
and finding project roots within directory structures.

Key Features:
- Project name normalization with diacritic removal and special character handling
- Canonical filename format: {ProjectName}_{Type}_SC{###}_Rev_{Letter}
- Bidirectional mapping between project types and filename tokens
- Automatic project root detection by walking up directory trees
- Scene metadata parsing from .blend filenames
- Windows reserved character filtering and path safety
- Integration with RAMV directory structure conventions

## lime_pipeline/core/paths.py

Project Path and Directory Structure Utilities

This module defines the canonical directory structure for Lime Pipeline projects
following the RAMV (Rendering-Animation-Media-Video) organizational standard.
It provides utilities for constructing project paths based on project type, revision,
and scene requirements.

The RAMV structure organizes projects hierarchically:
- Project Root (XX-##### format)
  - 2. Graphic & Media/
    - 3. Rendering-Animation-Video/
      - 3D Base Model/Rev X/
      - Proposal Views/Rev X/scenes/
      - Renders/Rev X/scenes/
      - Storyboard/Rev X/scenes/
      - Animation/Rev X/scenes/
      - tmp/Rev X/

Key Features:
- Canonical RAMV directory path construction
- Project type-based directory mapping (BASE, PV, REND, SB, ANIM, TMP)
- Automatic scenes directory creation for applicable project types
- Backups directory management per revision
- Integration with Lime Pipeline naming conventions
- Path validation and error handling for missing directories

## lime_pipeline/core/validate.py

UI State Validation and Path Resolution

This module provides comprehensive validation for Lime Pipeline UI state and automatic
path resolution for project file placement. It validates project settings, computes
target paths, and ensures compliance with Lime Pipeline naming and organizational
conventions.

The validation system checks project root validity, revision letters, scene numbers,
directory structure compliance, and file path constraints before allowing file
creation or project operations to proceed.

Key Features:
- Complete UI state validation with detailed error reporting
- Automatic project path resolution following RAMV structure
- Scene number validation with step constraints and existence checking
- Project root validation with pattern matching and studio invariants
- Path length validation with configurable warning and error thresholds
- Duplicate file detection and prevention
- Integration with Lime Pipeline preferences and settings
- Comprehensive error categorization (errors vs warnings)

## lime_pipeline/core/validate_scene.py

Scene and SHOT Validation Utilities

This module provides comprehensive utilities for validating Blender scene structure
and managing SHOT collections within the Lime Pipeline workflow. It handles SHOT
detection, indexing, hierarchy validation, and scene organization according to
Lime Pipeline conventions.

The SHOT system provides scene organization with numbered collections (SHOT 001,
SHOT 002, etc.) that contain all assets for individual shots or sequences. The
validation system ensures proper SHOT structure, active shot detection, and
hierarchical relationships between collections.

Key Features:
- SHOT collection detection and parsing with numeric indexing
- Active SHOT context resolution from selection and camera data
- Collection hierarchy validation and traversal utilities
- SHOT duplication and creation support with proper naming
- Scene isolation for focused SHOT processing
- Integration with Blender's collection and layer systems
- Comprehensive error handling for malformed scene structures
- Support for complex nested collection hierarchies

