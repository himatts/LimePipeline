# Lime Pipeline - AGENTS

## Alcance
Este archivo aplica a todo el repositorio y define las reglas globales para agentes.
Los `AGENTS.md` anidados agregan reglas especificas para su subarbol.
La arquitectura y decisiones tecnicas se detallan en `ARCHITECTURE.md`.

## Contexto del proyecto
- Add-on de Blender 4.5 LTS para estandarizar naming, rutas, backups y flujos de SHOT/render.
- Enfoque de producto: reducir error humano con reglas deterministas y preflight antes de aplicar cambios.
- Modulos principales: `core`, `data`, `scene`, `ops`, `ui`, con registro central en `lime_pipeline/__init__.py`.

## Mapa de modulos
- `lime_pipeline/core`: reglas de naming/paths/validacion y helpers Blender-agnostic.
- `lime_pipeline/data`: constantes y plantillas declarativas.
- `lime_pipeline/scene`: utilidades de SHOT y estructura de escena.
- `lime_pipeline/ops`: operadores y mutaciones de estado.
- `lime_pipeline/ui`: paneles/listas con UI ligera.
- `lime_pipeline/__init__.py`: registro, handlers y orquestacion.

## Reglas globales (no negociables)
- `core` no debe importar `bpy` en nivel modulo, excepto `core/validate_scene.py`.
- `ui` debe ser ligera: no IO pesado, red ni calculos costosos en `draw()`.
- No dupliques regex o constantes de negocio: reutiliza `core` y `data`.
- Texto visible al usuario (labels, tooltips, `report`) en ingles.
- Codigo y comentarios en ingles.
- No agregues dependencias nuevas sin justificar impacto.

## Roles de agente recomendados
- Arquitectura/Navegacion: protege fronteras de modulos y decisiones de arquitectura.
- Guardian Naming/Paths: protege invariantes de `core.naming`, `core.paths`, `core.validate`.
- Blender Ops/Registro: protege `bl_idname`, handlers y listas de registro.
- UI/Operacion: protege claridad y rendimiento de paneles.
- IA/Contratos: protege contratos JSON, fallback y separacion decision/aplicacion.
- Release/Docs: protege versionado, changelog, docs y artefactos instalables.

## Flujo recomendado por tipo de cambio
- Nueva funcionalidad o modificacion relevante con `bpy`: ejecutar primero `blender-api-research`.
- Cambios en `core/`: ejecutar skills `core-tests` y `addon-import-smoke`.
- Cambios en `ops/` o `ui/`: ejecutar skill `registration-audit`.
- Cambios en flujos IA (`ai_asset`, `ai_textures`, `ai_render`): ejecutar `ai-contract-check`.
- Cambios visibles al usuario: ejecutar `docs-delta` y luego `docs-build`.
- Preparacion de release: ejecutar `release-bump` y `package-addon`.

## Setup y comandos base
- Python `>= 3.10`.
- Instalar docs: `poetry install --with docs`.
- Tests base: `python -m unittest discover tests -v`.
- Build docs: `poetry run mkdocs build`.

## Checklist de registro / __init__.py (obligatorio)
Cada vez que muevas, renombres o agregues operadores/paneles:
1) Revisar `lime_pipeline/__init__.py` (imports, listas de clases, handlers).
2) Revisar `lime_pipeline/ops/__init__.py` (imports y `__all__`).
3) Revisar `lime_pipeline/ui/__init__.py` (imports, `__all__`, `register_*`, `unregister_*`).
4) Eliminar imports huerfanos y confirmar que toda clase nueva se exporta y registra.

## PR y QA
- Incluir comandos ejecutados y resumen de resultados.
- Si el cambio altera comportamiento visible, evaluar bump de `bl_info["version"]` y actualizar `CHANGELOG.md`.

## Skills disponibles (uso bajo demanda)
- `.codex/skills/core-tests/SKILL.md`
- `.codex/skills/blender-api-research/SKILL.md`
- `.codex/skills/registration-audit/SKILL.md`
- `.codex/skills/addon-import-smoke/SKILL.md`
- `.codex/skills/ai-contract-check/SKILL.md`
- `.codex/skills/blender-ui-performance-checklist/SKILL.md`
- `.codex/skills/docs-delta/SKILL.md`
- `.codex/skills/docs-build/SKILL.md`
- `.codex/skills/release-bump/SKILL.md`
- `.codex/skills/package-addon/SKILL.md`
- `.codex/skills/validate-naming/SKILL.md`
