# Lime Pipeline UI - AGENTS

## Alcance
Aplica a `lime_pipeline/ui/` y subdirectorios.

## Objetivo
Mantener una UI operativa para produccion: clara, rapida y sin side effects.

## Reglas de rendimiento y separacion
- `draw()` solo compone UI y lee estado; no hace IO de archivos, red o calculos pesados.
- Las mutaciones van en operadores (`ops/`) o handlers, no en paneles.
- Mantener estado en property groups (WindowManager/Scene), no en variables globales opacas.
- Mostrar preflight/preview y estados de error relevantes al usuario.

## Reglas de registro
- Si agregas o renombras paneles/UILists/props, actualizar:
  - `lime_pipeline/ui/__init__.py`
  - `lime_pipeline/__init__.py`
- Mantener coherencia de `bl_parent_id`, `bl_order` y categoria (`Lime Pipeline` vs `Lime Toolbox`).

## QA minimo
- Para nuevas funcionalidades o cambios relevantes de API Blender en paneles/listas, ejecutar primero `blender-api-research`.
- Ejecutar skill `blender-ui-performance-checklist`.
- Ejecutar skill `registration-audit` para validar registro/export.
- Si hay cambios visibles, ejecutar `docs-delta` y documentar impacto.
