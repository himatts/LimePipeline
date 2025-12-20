---
title: Contribuir
---

# Contribuir

Esta guía resume cómo contribuir a Lime Pipeline priorizando estabilidad, consistencia y un ciclo de iteración rápido dentro de Blender.

## Política de tests
- No se deben crear tests nuevos a menos que sea **explícitamente solicitado**.
- La validación principal del add-on es **manual dentro de Blender** (ver sección de entorno de desarrollo).

## Entorno de desarrollo (Cursor + Blender)
Este proyecto se desarrolla principalmente en **Cursor** usando la extensión **Blender Development** (Jacques Lucke) como puente entre el IDE y Blender.

- Guía: `docs/guias/desarrollo-cursor-blender-development.md`.

## Alcance y versiones
- Blender mínimo: 4.5 LTS.
- Python: el que viene con Blender.
- Objetivo del add-on: organización de proyecto, convenciones de nombres, estructura SHOT, utilidades de guardado/backup/render.

## Estructura del repositorio (alto nivel)
- `lime_pipeline/core`: naming, paths, validación (evitar dependencia directa de `bpy` en imports globales).
- `lime_pipeline/data`: plantillas y constantes declarativas.
- `lime_pipeline/scene`: helpers de escena y SHOTs (usa `bpy`).
- `lime_pipeline/ops`: operadores (acciones invocadas desde UI).
- `lime_pipeline/ui`: paneles y UI Lists (solo layout, sin IO pesado).

## Flujo de trabajo
1. Crea una rama desde `main`.
2. Implementa cambios siguiendo los estándares de código.
3. Actualiza documentación si cambias comportamiento o arquitectura.
4. Prueba manualmente en Blender usando Blender Development (ciclo corto de recarga).
5. Abre PR con resumen, racional y capturas si hay cambios en UI.

## Estándares de código
- Idioma: UI y mensajes en inglés. Documentación en español.
- Naming:
  - Clases: `PascalCase`.
  - Constantes: `UPPER_SNAKE_CASE`.
  - Funciones/variables: `snake_case`.
  - Operadores: `LIME_OT_` y `bl_idname` con prefijo `lime.`.
  - Panels: `LIME_PT_` y `LIME_TB_PT_`.
- Imports y tipos:
  - En `core/*`, evita `import bpy` a nivel de módulo.
  - Funciones públicas con type hints explícitos.
- Errores/logging:
  - Evita `except Exception: pass`.
  - En operadores usa `self.report({'ERROR'|'WARNING'|'INFO'}, msg)`.
- UI:
  - `draw()` sin IO pesado ni mutaciones de estado.
  - Prefiere subpanels nativos con `bl_parent_id`.

## Helpers canónicos
- Naming de archivos: `core.naming.make_filename` y `resolve_project_name`.
- Rutas: `core.paths.paths_for_type`.
- Validaciones: `core.validate.validate_all`.
- SHOTs: `scene/scene_utils.py` y `data/templates.py`.

## Checklist de PR (obligatorio)
- [ ] UI y mensajes en inglés.
- [ ] No duplicar literales de rutas/constantes (usar helpers).
- [ ] Sin IO en `draw()`; sin `except` silenciosos.
- [ ] Funciones públicas tipadas y con docstrings breves.
- [ ] Bump de `bl_info["version"]` si hay cambios visibles.
- [ ] Docs actualizadas (`docs/`, `README.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md` si aplica).

## Documentación (MkDocs)
- Previsualización: `mkdocs serve`.
- Build local: `mkdocs build`.
- Catálogo por archivo (auto): `python tools/generate_catalog.py --full`.

## ADRs (decisiones)
- Agrega un ADR nuevo si tomas una decisión estructural importante.
- Ubicación: `docs/arquitectura/decisiones/`.

## Reglas canónicas
- El archivo de reglas canónico está en `.cursor/rules/limepipelinerules.mdc`.
- Si cambias comportamiento visible o arquitectura, actualiza también la documentación.
