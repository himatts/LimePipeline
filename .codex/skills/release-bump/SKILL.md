---
name: release-bump
description: Prepare versioned release updates for Lime Pipeline. Use when user-visible behavior changes require bumping `bl_info["version"]`, updating `CHANGELOG.md`, and producing release-ready QA notes.
---

## Goal
Create a consistent release increment with traceable version notes and build artifacts.

## Steps
1) Choose bump level (patch/minor/major) based on user-visible impact.
2) Update `bl_info["version"]` in `lime_pipeline/__init__.py`.
3) Add dated entry in `CHANGELOG.md` summarizing user-facing changes.
4) Run QA baseline:
   - `python -m unittest discover tests -v`
   - `poetry run mkdocs build`
5) If ops/ui changed, run `registration-audit`.
6) Build artifact with `package-addon` and record SHA256 hash.

## Outputs
- Updated version tuple.
- Changelog entry for the release.
- QA command summary and artifact hash.
