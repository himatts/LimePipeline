---
name: docs-build
description: Build and verify the MkDocs documentation
---

## When to use
Use before publishing docs or after changing guides/architecture files.

## Inputs
- Poetry environment with docs extras available

## Steps
1) Install docs dependencies: `poetry install --with docs`.
2) Build docs: `poetry run mkdocs build`.
3) (Optional) Preview locally: `poetry run mkdocs serve`.
4) If navigation or new pages were added, ensure links from `mkdocs.yml` resolve and include any new images/assets.

## Outputs
- Successful MkDocs build (site/ directory)
- Notes on any broken links or warnings
