---
name: package-addon
description: Build an installable ZIP for the Lime Pipeline Blender add-on. Use for release candidates, QA handoff to artists, or whenever version/changelog changes must ship as a distributable artifact.
---

## Inputs
- Clean source tree at repo root.
- Target version aligned between `lime_pipeline/__init__.py` and `CHANGELOG.md`.

## Steps
1) Clean previous artifacts: remove stale files under `dist/`.
2) Run tests: `python -m unittest discover tests -v`.
3) If ops/ui changed, run `registration-audit` before packaging.
4) Package only the addon folder (`lime_pipeline/`) into `dist/lime-pipeline-<version>.zip`.
5) Exclude `__pycache__`, `.pyc`, docs, and tests from the ZIP.
6) Compute and record hash: `Get-FileHash dist\\lime-pipeline-<version>.zip -Algorithm SHA256`.

## Outputs
- Installable ZIP artifact in `dist/`.
- SHA256 hash ready for release notes.
