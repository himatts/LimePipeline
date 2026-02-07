---
title: Contexto para IA
---

# AI Context
Resumen esencial para agentes de IA con limite de tokens.

- Que es: Add-on de Blender que estandariza estructura de proyectos, SHOTs, camaras con margenes, renders/proposals, backups y normalizacion de materiales.

- Capas y limites:
  - `core/`: naming, paths, invariantes, validacion, taxonomia de materiales; solo `validate_scene.py` usa `bpy` en import.
  - `scene/`: helpers de estado Blender (SHOT tree, duplicacion con remapeo, camaras con margenes).
  - `ops/`: acciones de usuario; feedback con `self.report`; delega en `core/`/`scene/`.
  - `ui/`: solo layout; sin IO pesado; usar subpanels nativos.

- Flujos clave:
  1. AI Asset Organizer: sugerencia IA + normalizacion + apply-scope (objects/materials/collections).
  2. SHOTs: `create_shot` -> `ensure_shot_tree` -> duplicacion con remapeo.
  3. Primer guardado/Backups: `validate_all` -> `filename/target_path` -> guardar/copiar.
  4. Renders/Proposals: resolver `(project_name, sc, rev)` -> nombre de salida por camara/SHOT.

- Invariantes:
  - Material: `MAT_{TagEscena}_{Familia}_{Acabado}_{V##}` (sin `.001`/`_1`).
  - Raiz de proyecto: `^[A-Z]{2}-\d{5}\s+(.+)$`.
  - Revision: una letra A-Z.
  - Tipos con SC: `PV`, `REND`, `SB`, `ANIM` (1-999); si `free_scene_numbering` es false, multiplo de `prefs.scene_step`.
  - Nombres/rutas se construyen solo via `core`.

- Referencias:
  - ADR-0001 y guia de convenciones: `docs/guias/convenciones-nombres.md`.
  - Catalogo por archivo: `docs/catalogo/`.
  - Vision general: `docs/arquitectura/vision-general.md`.
