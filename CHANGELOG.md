# Changelog

## [Unreleased] - 2025-09-30
### Added
- AI Render Converter panel for storyboard sketch conversion (Krea + OpenRouter), with manifested outputs.
- AI Asset Organizer panel to suggest names for selected objects and their materials (OpenRouter).
- AI Asset Organizer: optional image context for multimodal models.
- Texture Scan/Report and Adopt/Fix tools to copy external textures into project `RSC/Textures`, relink images, and write JSON manifests.
- Adopt/Fix also centralizes eligible in-project textures that are outside `RSC/Textures` (skips linked/asset-library textures).
- Adopt/Fix naming updated to preserve original filename stems (optional AI stem filter via OpenRouter; optional low-res preview).
- Adopt/Fix naming now enforces a shared structure: `<Project>_<Descriptor>_<MapType>_<NN>.<ext>` regardless of AI output (keeps names consistent inside `rsc/Textures`).
- Added a texture manifest cleanup button to delete `rsc/Textures/_manifests`.

### Changed (LP-00003)
- Simplified Shots UI panel by removing subpanels and leveraging native Blender list controls
- Removed deprecated "Shot Instance" functionality completely
- Relocated "Duplicate Shot" and "Add Missing Collections" as supplementary buttons alongside the main shot list
- Maintained all core shot management functionality while improving UI consistency

### Changed
- AI Render Converter now uses thumbnail grids per section, includes large Image Editor previews, syncs Source Render selections to frames, and deduplicates style imports.
- AI Render Converter adds deletion controls for selected images and batch cleanup with double confirmation.
- AI Render Converter adds output folder access and batch manifest cleanup.
- Textures tools moved to AI Asset Organizer; removed "Organize Textures on Apply".
- AI Asset Organizer object/collection naming now uses PascalCase segments separated by underscores with numeric suffix blocks.

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
