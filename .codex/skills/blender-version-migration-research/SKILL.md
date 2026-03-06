---
name: blender-version-migration-research
description: Research and plan Blender add-on migrations between Blender versions. Use when upgrading Lime Pipeline or another addon across Blender releases, comparing official API/release-note changes, identifying breaking changes, mapping repo modules to risk areas, and producing a migration plan before editing code.
---

# Blender Version Migration Research

## Goal
Produce a migration brief grounded in official Blender docs before changing code for a version upgrade.

## Inputs
- Source Blender version.
- Target Blender version.
- Repo path.
- Packaging target: legacy add-on or extension.

## Workflow
1) Inventory addon surfaces used by the repo.
   - Registration, `PropertyGroup`, `AddonPreferences`, `Panel`, `UIList`, operators, handlers, timers, draw handlers, sequencer, nodes, linked libraries, file IO, and network usage.
2) Search official Blender release notes for every major/minor version crossed.
   - Start at `https://developer.blender.org/docs/release_notes/`.
3) Validate current APIs in official docs for the target version.
   - Prefer `https://docs.blender.org/api/current/` for active Blender 5.x work.
4) Map each repo module into one of four buckets.
   - Unchanged.
   - Deprecated but safe.
   - Needs adaptation.
   - Likely broken.
5) Record links for every claimed breaking or deprecated area.
6) Produce a migration brief before implementation.

## Required Output
- `Executive summary`: migration difficulty and overall recommendation.
- `Risk map`: high-risk modules and why.
- `API delta`: what stayed stable, what changed, and what is ambiguous.
- `Implementation order`: safest sequence of work.
- `Validation plan`: exact tests and Blender runtime smoke checks.

## Quality Bar
- Use official Blender sources for compatibility claims.
- Distinguish confirmed breaks from optional cleanup.
- Call out ambiguity instead of guessing.
- Connect every risk back to actual repo code, not generic Blender advice.
