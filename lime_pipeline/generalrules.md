# Lime Pipeline – Project Rules Index

This file is a short index. The actual scoped rules live in separate files and are auto-attached by Cursor when relevant.

## Scoped rules (auto-attached)
- Core boundaries: @.cursor/rules/core-boundaries.mdc
- UI panels: @.cursor/rules/ui-panels.mdc
- Ops/operators: @.cursor/rules/ops-operators.mdc
- Scene helpers: @.cursor/rules/scene-helpers.mdc
- UI Toolbox: @.cursor/rules/ui-toolbox.mdc

## Global minimal architecture/invariants (always on)
- See: @.cursor/rules/00-architecture-and-invariants.mdc

## Templates & PR checklist (manual/agent requested)
- Templates: @.cursor/rules/templates.mdc
- PR checklist: @.cursor/rules/pr-checklist.mdc

## Docs maintenance
- Canonical rules live in this folder (`.cursor/rules/*`).
- Update `README.md`, `ARCHITECTURE.md`, and `CONTRIBUTING.md` when visible behavior or structure changes.

---

# Purpose
- Keep this rule short; details live in @ARCHITECTURE.md and scoped rules.

# Architecture (high-level)
- Modules: core, data, scene, ops, ui.
- UI/messages in English; future-friendly for Blender i18n. Code, comments, identifiers in English.
- Prefer native Blender UI elements; avoid custom widgets/drawing unless necessary.

# Invariants (single source of truth)
- Project root matches `^[A-Z]{2}-\d{5}\s+(.+)$`
- Revision letter is exactly one A–Z
- PV/REND/SB/ANIM require SC (1–999); unless `free_scene_numbering`, SC must be multiple of `scene_step`

# References
@ARCHITECTURE.md

---

## Core Rules
- Do not import `bpy` at module level; local imports inside functions only.
- Constants/regex live here. Reuse `core.naming` + `core.paths` + `core.validate`; avoid duplication.
- Public functions: typed + short docstrings.

## Canonical Helpers
@lime_pipeline/core/naming.py
@lime_pipeline/core/paths.py
@lime_pipeline/core/validate.py

---

## Operators Rules
### Conventions
- Class prefix `LIME_OT_` and `bl_idname` prefixed `lime.*`.
- Delegate naming/paths/validate to `core`; no RAMV literals or formatting duplication.
- User feedback via `self.report({'ERROR'|'WARNING'|'INFO'}, msg)`.
- Labels, descriptions (`bl_label`, `bl_description`), property names and messages must be in English.
- Avoid silent `except`; log or report.

### Templates (invoke manually when creating a new operator)
- Use @templates for a starter skeleton.

---

## UI Panels Rules
### View3D / Image Editor panels
- `draw()` no IO/hydration, no state mutation; keep fast and deterministic.
- Messages/tooltips in EN. Code, comments, identifiers in English. Show warnings from `core.validate`.
- Reuse properties from `WindowManager.lime_pipeline`; do not scan disk.
- Prefer native Blender UI elements (layout, operators, props); avoid custom GPU drawing or non-standard widgets unless strictly necessary.

### References
@lime_pipeline/ui/ui_render_configs.py
@lime_pipeline/ui/ui_project_org.py

---

## UI Toolbox Rules
### Purpose
- The **Lime Toolbox** tab is the home for upcoming tools related to **animation** and **materials**.
- Out of scope: touching saves/paths/renders logic.

### Alignment
- Keep UI text **in English**.
- **Fast UI**: no blocking operations, keep draw lightweight.
- **No IO or state mutation in `draw()`**.

### Naming & Structure
- Panels: `LIME_TB_PT_*`.
- Operators: `LIME_TB_OT_*`, with `bl_idname = "lime.tb_*"`.
- Keep Toolbox modules separate from Pipeline ones. If Toolbox needs properties later, create a dedicated `PropertyGroup` (e.g., `WindowManager.lime_toolbox`).

### MVP Status
- Placeholder only. No heavy logic. The button should only `report({'INFO'}, ...)`.

### Acceptance Checklist
- Add-on installs & enables without errors.
- **Lime Toolbox** tab is visible in the Sidebar (N) within View3D.
- Clicking **Do Nothing (WIP)** shows an INFO message.
- Existing Lime Pipeline panels work unchanged.

---

## Scene Helpers
### Guidelines
- Create/duplicate SHOT preserving `SH##_*` prefixes and color tags.
- Duplicate camera/light data to isolate shots; remap parenting/constraints.
- Keep object/data names in sync when renaming.

### References
@lime_pipeline/scene/scene_utils.py
@lime_pipeline/data/templates.py

---

## Templates
Handy code templates (operators, panels) for Lime Pipeline

### Operator template (Python)
```python
import bpy
from bpy.types import Operator

class LIME_OT_example(Operator):
    bl_idname = "lime.example"
    bl_label = "Example"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Short, actionable description in EN"

    def execute(self, context):
        # Delegate to core/scene helpers where possible
        self.report({'INFO'}, "Done")
        return {'FINISHED'}
```

### Panel template (Python)
```python
import bpy
from bpy.types import Panel
CAT = "Lime Pipeline"

class LIME_PT_example(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT
    bl_label = "Example"
    bl_order = 99
    def draw(self, ctx):
        layout = self.layout
        layout.label(text="Hello")
```

---

## PR Checklist
- UI/messages in EN. Code, comments, identifiers in English.
- Prefer native Blender UI elements; avoid custom GPU drawing unless strictly necessary.
- No duplicated literals for paths/constants (use core helpers)
- No duplicated logic; reuse `core`/`scene`
- No IO in `draw()`; no silent `except`
- Typed public functions; short "why" docstrings
- Bump `bl_info["version"]` if user-facing behavior changes
- Docs updated (README, ARCHITECTURE, CONTRIBUTING)

### Tests
- Unit (core): naming, paths, validate
- Optional smoke: Blender headless for key flows