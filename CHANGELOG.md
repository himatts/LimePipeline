# Changelog

## [0.2.1] - 2025-09-28
### Changed
- Modularized `lime.duplicate_scene_sequential` into `ops/ops_stage_duplicate_scene.py` and centralized registration.
- Deep isolation on scene duplicate: single-user copies for data, materials, node groups, geometry nodes, actions, and world; remap of constraints/modifiers; cloned Alpha events (drivers rebuilt) and Noise profiles; SHOT-based renaming; cleanup.
- Camera List now scoped to active scene (and prefers active SHOT camera collection), with scene-based token for refresh.
- Removed deprecated helpers and transitional shim from `ops/ops_stage.py`.

## [0.1.9] - 2025-09-17
### Added
- Dimension Utilities panel in the Lime Pipeline tab, moving Dimension Checker out of the 3D Model Organizer.
- Measurement unit presets (mm/cm/m/in/ft) that apply to the active .blend and expose advanced unit settings.

### Feature Flags
- Add-on preference `Enable Dimension Utilities` enables rapid rollback of the new panel if required.
