---
name: docs-delta
description: Determine and apply documentation updates required by code changes. Use when behavior, UI flow, setup, naming/path rules, or release process changes are visible to users or contributors.
---

## Goal
Keep docs aligned with real addon behavior after each meaningful change.

## Steps
1) Inspect changed files: `git diff --name-only`.
2) Map each visible change to docs targets:
   - Behavior or workflow changes -> `README.md`, `ARCHITECTURE.md`
   - Contributor workflow or QA changes -> `CONTRIBUTING.md`, `AGENTS.md`
   - Release-visible notes -> `CHANGELOG.md`
3) Update only the sections affected by the diff.
4) Run docs verification: `poetry run mkdocs build`.
5) If no docs update is needed, document the reason explicitly in the PR summary.

## Outputs
- List of updated docs files.
- Short rationale linking code changes to doc changes.
- MkDocs build status.
