# Lime Pipeline – AGENTS

## Alcance
Este archivo aplica a todo el repositorio. Complementa las reglas descritas en `lime_pipeline/generalrules.md` y `ARCHITECTURE.md`.

## Contexto del proyecto
- Add-on de Blender 4.5 LTS para estandarizar nombres, rutas, backups y flujos de SHOT/renders.
- Módulos: `core` (naming/paths/validación), `data` (constantes), `scene` (SHOT helpers), `ops` (operadores), `ui` (paneles) y registro central en `lime_pipeline/__init__.py`.

## Setup rápido
- Python >= 3.10.
- Instalar dependencias de docs: `poetry install --with docs`.
- Docs: `poetry run mkdocs build` (o `mkdocs serve` para vista local).
- Define y documenta comandos de lint/test cuando estén disponibles; ejecútalos antes de abrir PR.

## Reglas de trabajo
- Respeta los límites de módulos: `core` sin `bpy` en imports de módulo (excepto `validate_scene.py`), UI ligera sin IO en `draw()`, y evita duplicar constantes/regex (usa `core`/`data`).
- Texto visible al usuario (labels, tooltips, `report`) en inglés. Código y comentarios en inglés.
- No agregues dependencias sin justificación.
- Actualiza docs (`README.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`) cuando cambie el comportamiento visible.

## Checklist de registro / __init__.py (¡no olvidar!)
Cada vez que:
- muevas o renombres funciones/clases, o reorganices módulos,
- cambies un operador (crear/renombrar/clase nueva) en `ops/`,
- agregues/edites paneles o UI lists en `ui/`,
debes revisar y, si aplica, actualizar los `__init__.py` correspondientes:
1) `lime_pipeline/__init__.py` – listas de registro y handlers.
2) `lime_pipeline/ops/__init__.py` – imports y `__all__` de operadores.
3) `lime_pipeline/ui/__init__.py` – imports, `__all__`, y funciones `register_*`/`unregister_*`.
Confirma que las clases/props nuevas sigan siendo registradas y exportadas; elimina imports huérfanos si se movieron.

## PR y QA
- Incluye resultados de tests/lint ejecutados.
- Si el cambio afecta al usuario, considera bump de versión en `bl_info["version"]` y notas en CHANGELOG.

## Skills disponibles (uso bajo demanda)
- `.codex/skills/package-addon/SKILL.md`: empaquetar el add-on en ZIP instalable y validar registro.
- `.codex/skills/validate-naming/SKILL.md`: checklist rápido de nombres/rutas y verificación de `__init__.py` tras mover operadores/UI.
- `.codex/skills/docs-build/SKILL.md`: build y verificación de la documentación MkDocs.
