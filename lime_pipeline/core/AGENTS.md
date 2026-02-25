# Lime Pipeline Core - AGENTS

## Alcance
Aplica a `lime_pipeline/core/` y subdirectorios.

## Objetivo
Mantener reglas de pipeline Blender-agnostic, testeables y deterministas.

## Reglas
- No importar `bpy` en nivel modulo, excepto en `validate_scene.py`.
- Mantener invariantes de naming/path/validacion en `core`; no moverlos a `ops` o `ui`.
- Evitar efectos secundarios en import (sin IO o red en global scope).
- Si cambias contratos (retornos, errores, warnings), actualiza consumidores y tests.
- Mantener compatibilidad de parseo/hidratacion cuando cambies formatos de filename/path.

## QA minimo
- Ejecutar `python -m unittest discover tests -v`.
- Para cambios de AI core, ejecutar:
  - `python -m unittest tests.test_ai_asset_prompt tests.test_ai_asset_response tests.test_ai_asset_collection_paths tests.test_ai_asset_material_rules -v`
- Verificar imports prohibidos:
  - `rg -n "^(from bpy|import bpy)" lime_pipeline/core --glob '!validate_scene.py'`

## Integracion con skills
- Usar `core-tests` para cambios en reglas base.
- Usar `addon-import-smoke` cuando haya cambios en imports, paquetes o `__init__.py`.
