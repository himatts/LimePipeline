---
name: blender-api-research
description: Research Blender 4.5 Python API before implementation. Use when adding a new feature or making a relevant modification in operators, panels, property groups, handlers, modal flows, rendering, animation, nodes, or any `bpy`-dependent behavior.
---

# Blender API Research

## Goal
Reduce implementation risk by grounding design decisions in official Blender 4.5 API docs (`https://docs.blender.org/api/4.5/`) before editing code.

## Workflow
1) Define the implementation question as a concrete statement.
   - Example: "How should a modal operator cancel safely and release timers?"
2) Locate official references in Blender 4.5 docs.
   - Use `https://docs.blender.org/api/4.5/search.html?q=<term>`.
   - Prioritize pages for `bpy.types`, `bpy.ops`, `bpy.props`, `bpy.app.handlers`, and relevant data types.
3) Extract constraints that affect implementation.
   - Required context/mode (`poll`, active object, area/region).
   - Lifecycle expectations (`invoke`, `execute`, `modal`, handler persistence).
   - Undo/cancel semantics and side effects.
   - Data access/mutation limits and known gotchas.
4) Map findings to Lime Pipeline architecture.
   - Business rules stay in `core`.
   - Blender mutations stay in `ops`.
   - `ui.draw()` remains side-effect free.
5) Produce an implementation brief before coding.

## Implementation Brief Output
Provide this output in PR/task notes before implementation:
- `Question`: one-line problem statement.
- `API links`: 2-6 official Blender 4.5 URLs used.
- `Chosen approach`: concise design decision.
- `Constraints`: context, lifecycle, undo/cancel, and data-safety notes.
- `Project mapping`: target files/modules in `core`, `ops`, `ui`.
- `Risks`: top regressions to watch.
- `Validation plan`: commands/checklists to run (for example `registration-audit`, `addon-import-smoke`, tests).

## Minimum Quality Bar
- Do not rely on memory for Blender API signatures when docs are available.
- Prefer official Blender 4.5 docs over blog posts or forum summaries.
- If docs are ambiguous, call out the ambiguity explicitly and propose a safe fallback.
