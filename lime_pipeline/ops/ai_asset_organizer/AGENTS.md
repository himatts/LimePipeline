# AI Asset Organizer - AGENTS

## Alcance
Aplica a `lime_pipeline/ops/ai_asset_organizer/`.

## Objetivo
Proteger el contrato de sugerencias IA y la aplicacion segura sobre objetos, materiales y colecciones.

## Reglas de contrato y parsing
- Mantener contrato JSON estricto entre prompt y parser.
- Si cambia el schema, actualizar parser, normalizacion y tests en el mismo cambio.
- No confiar ciegamente en salida IA: validar tipos, campos y longitudes antes de aplicar.

## Reglas de aplicacion segura
- Mantener separacion entre planificacion (decision) y apply (mutacion).
- Preservar unicidad determinista de nombres y resolucion determinista de targets.
- Casos ambiguos deben quedar en estado resoluble por usuario, no auto-forzados.
- Conservar guardrails para objetos especiales (por ejemplo LIGHT/CAMERA) salvo decision explicita documentada.

## Registro y export surface
- Si agregas o renombras operadores o helpers publicos, revisar:
  - `lime_pipeline/ops/ai_asset_organizer/__init__.py`
  - `lime_pipeline/ops/__init__.py`
  - `lime_pipeline/__init__.py`

## QA minimo
- Ejecutar:
  - `python -m unittest tests.test_ai_asset_prompt tests.test_ai_asset_response tests.test_ai_asset_collection_paths tests.test_ai_asset_material_rules -v`
- Ejecutar skill `ai-contract-check`.
- Ejecutar skill `registration-audit` si cambian clases de operador.
