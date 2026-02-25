# Lime Pipeline Ops - AGENTS

## Alcance
Aplica a `lime_pipeline/ops/` excepto donde exista un `AGENTS.md` mas especifico.

## Objetivo
Implementar acciones Blender seguras, reversibles cuando sea posible, y coherentes con el registro central.

## Reglas de operadores
- `bl_idname` debe usar prefijo `lime.` y mantenerse estable.
- Mantener `bl_label`, `bl_description` y `report` en ingles.
- Delegar reglas de negocio a `core`; no duplicar validaciones complejas en operadores.
- En operadores modales, soportar cancelacion y limpiar timers/estado.
- IO/red solo dentro de `execute`/`invoke`/modal; nunca en import global.
- Cualquier cambio de clase requiere revisar `ops/__init__.py` y `lime_pipeline/__init__.py`.

## Reglas para flujos IA en ops
- Mantener separacion decision vs aplicacion (analyze/refine/apply).
- Preservar rutas de fallback (`AI_BLOCKED`, errores de API, cancelaciones).
- No aplicar cambios destructivos automaticamente sin estado previo o seleccion explicita.

## QA minimo
- Para nuevas funcionalidades o cambios relevantes de API Blender en operadores, ejecutar primero `blender-api-research`.
- Ejecutar `python -m unittest discover tests -v` cuando se toque logica compartida.
- Ejecutar skill `registration-audit` cuando se agregue/mueva/renombre operadores.
- Ejecutar `addon-import-smoke` si cambian imports, `__all__` o empaquetado.
