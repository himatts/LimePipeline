---
title: Contexto para IA
---

# AI Context
Resumen esencial para agentes de IA con límite de tokens.

- Qué es: Add-on de Blender que estandariza estructura de proyectos, SHOTs, cámaras con márgenes, renders/proposals, backups y normalización de materiales.

- Capas y límites:
  - `core/`: naming, paths, invariantes, validación, taxonomía de materiales; solo `validate_scene.py` usa `bpy` en import.
  - `scene/`: helpers de estado Blender (SHOT tree, duplicación con remapeo, cámaras con márgenes).
  - `ops/`: acciones de usuario; feedback con `self.report`; delega en `core/`/`scene/`.
  - `ui/`: solo layout; sin IO pesado; usar subpanels nativos.

- Flujos clave:
  1. AI Material Renamer: detección local + scoring de calidad → consulta selectiva → edición/aplicación → reorden.
  2. SHOTs: `create_shot` → `ensure_shot_tree` → duplicación con remapeo.
  3. Primer guardado/Backups: `validate_all` → `filename/target_path` → guardar/copiar.
  4. Renders/Proposals: resolver `(project_name, sc, rev)` → nombre de salida por cámara/SHOT.

- Invariantes:
  - Material: `MAT_{TagEscena}_{Familia}_{Acabado}_{V##}` (sin `.001`/`_1`).
  - Raíz de proyecto: `^[A-Z]{2}-\d{5}\s+(.+)$`.
  - Revisión: una letra A–Z.
  - Tipos con SC: `PV`, `REND`, `SB`, `ANIM` (1–999); si `free_scene_numbering` es false, múltiplo de `prefs.scene_step`.
  - Nombres/rutas se construyen solo vía `core`.

- Referencias:
  - ADR-0001 y guía de convenciones: `docs/guias/convenciones-nombres.md`.
  - Catálogo por archivo: `docs/catalogo/`.
  - Visión general: `docs/arquitectura/vision-general.md`.

