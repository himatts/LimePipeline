---
name: blender-api-research
description: Research the Blender Python API for the repository target version before implementation. Use when adding a new feature or making a relevant modification in operators, panels, property groups, handlers, modal flows, rendering, animation, nodes, or any `bpy`-dependent behavior.
---

# Blender API Research

## Goal
Reduce implementation risk by grounding design decisions in official Blender API docs for the repo target version before editing code.

## Workflow
1) Define the implementation question as a concrete statement.
   - Example: "How should a modal operator cancel safely and release timers?"
2) Resolve the target API docs version from `lime_pipeline/__init__.py` `bl_info["blender"]`.
   - For Blender 5.x, prefer `https://docs.blender.org/api/current/`.
   - For pinned migration work, use the matching versioned docs when available.
3) Locate official references in the resolved API docs.
   - Use `https://docs.blender.org/api/current/search.html?q=<term>` or the versioned equivalent.
   - Prioritize pages for `bpy.types`, `bpy.ops`, `bpy.props`, `bpy.app.handlers`, and relevant data types.
4) Extract constraints that affect implementation.
   - Required context/mode (`poll`, active object, area/region).
   - Lifecycle expectations (`invoke`, `execute`, `modal`, handler persistence).
   - Undo/cancel semantics and side effects.
   - Data access/mutation limits and known gotchas.
5) Map findings to Lime Pipeline architecture.
   - Business rules stay in `core`.
   - Blender mutations stay in `ops`.
   - `ui.draw()` remains side-effect free.
6) Produce an implementation brief before coding.

## Implementation Brief Output
Provide this output in PR/task notes before implementation:
- `Question`: one-line problem statement.
- `API version`: target Blender API version used for research.
- `API links`: 2-6 official Blender URLs used.
- `Chosen approach`: concise design decision.
- `Constraints`: context, lifecycle, undo/cancel, and data-safety notes.
- `Project mapping`: target files/modules in `core`, `ops`, `ui`.
- `Risks`: top regressions to watch.
- `Validation plan`: commands/checklists to run (for example `registration-audit`, `addon-import-smoke`, tests).

## Minimum Quality Bar
- Do not rely on memory for Blender API signatures when docs are available.
- Prefer official Blender API docs for the target version over blog posts or forum summaries.
- If docs are ambiguous, call out the ambiguity explicitly and propose a safe fallback.
