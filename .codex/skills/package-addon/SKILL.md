---
name: package-addon
description: Build an installable ZIP for the Lime Pipeline Blender add-on
---

## When to use
Use this skill when preparing a release or sharing an installable build with artists.

## Inputs
- Source tree: repo root
- Target version: synced with `bl_info["version"]` and `CHANGELOG.md`

## Steps
1) Clean previous artifacts: remove `dist/` or any existing ZIPs for Lime Pipeline.
2) Package only the add-on code: zip the `lime_pipeline/` folder (exclude `__pycache__`, `*.pyc`, docs, and tests).
3) Validate registration: ensure `lime_pipeline/__init__.py` imports and registers all classes and handlers referenced by the packaged modules.
4) Smoke check (headless if possible): import `lime_pipeline` in a Python session with Blender modules available; confirm no import-time errors.
5) Name the artifact `lime-pipeline-<version>.zip` and record the hash (e.g., `sha256sum`).

## Outputs
- Installable ZIP placed under `dist/` or a release drop folder
- Recorded hash for integrity verification
