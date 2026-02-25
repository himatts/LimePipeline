---
name: docs-build
description: Build and verify Lime Pipeline MkDocs output. Use when editing docs/, README.md, ARCHITECTURE.md, CONTRIBUTING.md, or mkdocs.yml, and before PRs or releases with user-facing documentation changes.
---

## Inputs
- Poetry environment available.
- Docs dependencies enabled (`poetry install --with docs`).

## Steps
1) Install docs dependencies if needed: `poetry install --with docs`.
2) Build docs: `poetry run mkdocs build`.
3) Optional local preview: `poetry run mkdocs serve`.
4) If navigation changed, verify `mkdocs.yml` includes new pages and assets.
5) Record warnings or broken links in the PR notes.

## Outputs
- Successful MkDocs build (`site/`).
- List of warnings/fixes if any.
