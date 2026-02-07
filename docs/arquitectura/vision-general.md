---
title: Visión general
---

# Arquitectura de alto nivel

Lime Pipeline se organiza en capas con responsabilidades claras y límites estables. La UI nunca hace IO pesado y las reglas canónicas viven en `core/`.

```
UI (ui/) -> OPS (ops/) -> SCENE (scene/) -> CORE (core/)
```

## Capas y responsabilidades

### core (Python “puro”)
- Naming, paths, validación e invariantes.
- No debe depender de `bpy` a nivel de módulo (excepto `validate_scene.py`).

### data
- Plantillas y constantes declarativas (ej. SHOT_TREE).
- Sin lógica imperativa.

### scene
- Helpers con efectos en escena (SHOTs, duplicado, backgrounds de cámara).
- Consume `data/` y validaciones de `core/`.

### ops
- Operadores Blender (acciones de usuario).
- Delegan naming/validación/paths a `core` y helpers de `scene`.

### ui
- Panels/UILists y layout.
- No muta estado ni realiza IO pesado en `draw()`.

## Flujos clave

### First save (Create .blend)
1. Usuario define Project Root/Type/Rev/Scene.
2. UI llama `core.validate.validate_all`.
3. `ops_create_file` guarda con `bpy.ops.wm.save_as_mainfile`.

### SHOTs
1. `scene_utils.create_shot` crea SHOT ###.
2. `scene_utils.ensure_shot_tree` aplica `SHOT_TREE`.
3. `duplicate_shot` clona estructura y objetos con remapping.

### AI Asset Organizer (material workflow)
1. `Suggest Names (AI)` analiza selección activa (objetos/materiales y colecciones opcionales).
2. Propuestas se guardan en `Scene.lime_ai_assets.items`.
3. `Apply Selected` aplica cambios con `Apply Scope` para limitar a materiales.
4. La conectividad IA se valida con `lime_tb.ai_asset_test_connection`.

## Invariantes y reglas
- Materiales: `MAT_{TagEscena}_{Familia}_{Acabado}_{V##}`.
- Proyecto: `^[A-Z]{2}-\d{5}\s+(.+)$`.
- Revisiones: una letra A-Z.
- Tipos que requieren SC: `PV, REND, SB, ANIM`.
- Numeración de escena: 1–999 (o libre si `free_scene_numbering`).

## Compatibilidad y errores
- Blender 4.5+.
- No se silencian excepciones; se reporta vía `self.report` en operadores.

## Referencias
- Decisiones: `docs/arquitectura/decisiones/`.
- Convenciones: `docs/guias/convenciones-nombres.md`.
- Catálogo de módulos: `docs/catalogo/`.
