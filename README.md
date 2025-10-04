# Lime Pipeline (Blender 4.5 LTS add-on)

Lime Pipeline es un add-on de Blender orientado a estudios y equipos que buscan orden y consistencia en la produccion. Su proposito es estandarizar la organizacion de proyectos y escenas para reducir friccion operativa y errores humanos.

De forma practica, el add-on:
- Centraliza la configuracion del proyecto (raiz, tipo, revision y escena) y genera nombres limpios y consistentes.
- Asiste en el primer guardado, rutas objetivo y backups numerados.
- Crea y gestiona estructuras de SHOT dentro de la escena, incluyendo instanciado y duplicado de shots con politicas claras.
- Presenta paneles en el Sidebar para flujo de archivos y preparacion interna de la escena.
- Ofrece un Material Manager manual-first (Scan -> Correct -> Apply) para mantener nombres MAT_S# sin sufijos duplicados.
- Incluye un AI Material Renamer asistido por IA (OpenRouter + Gemini) para proponer y aplicar nombres de materiales cumpliendo el esquema MAT_S# de forma automática y eficiente.
- Permite medir selecciones con el Dimension Checker desde el panel Dimension Utilities, incluyendo presets de unidades.

- Target: Blender 4.5 LTS
- Paneles: View3D > Sidebar (N) > Lime Pipeline > Project Organization, Shots, Render Configs, Stage, 3D Model Organizer, Dimension Utilities, Material Manager, AI Material Renamer
- Preferencias: Edit > Preferences > Add-ons > Lime Pipeline (incluye el toggle "Enable Dimension Utilities")

## Estructura del paquete `lime_pipeline/`

- `__init__.py`: registro del add-on y bl_info
- `prefs.py`: AddonPreferences
- `props.py`: PropertyGroup persistente en WindowManager
- `core/`: nucleo comun
  - `material_naming.py`: parsing/build de materiales MAT_{TagEscena}_{Familia}_{Acabado}_{V##}
  - `naming.py`: `resolve_project_name`, normalizacion y helpers
  - `validate_scene.py`: validaciones puras de contexto de escena/SHOT
- `paths.py`: resolucion de rutas RAMV por tipo
- `scan.py`: escaneo y sugerencia de SC
- `validate.py`: validaciones y gating de acciones
- `scene/scene_utils.py`: helpers con efectos en Outliner (crear/instanciar/duplicar SHOT)
- `data/templates.py`: plantilla declarativa del arbol de SHOT y politicas
- `ops/`: operadores
  - `ops_ai_material_renamer.py`: flujo asistido por IA para proponer y aplicar nombres de materiales cumpliendo MAT_S#
  - `ops_shots.py`: New Shot / Shot Instance / Duplicate Shot
  - otros: pick root, folders, create file, backup
- `ui/`: paneles
  - `ui_ai_material_renamer.py`: Lime Toolbox / AI Material Renamer (UI simplificada con detección local y edición directa)
  - `ui_project_org.py`: Project Organization (archivos)
  - `ui_shots.py`: Shots (escena/colecciones)
  - `ui_render_configs.py`: Render Configs (siempre visible; incluye Proposal View y Renders)
  - `ui_model_organizer.py`: 3D Model Organizer (importacion STEP via sTEPper, utilidades de limpieza y medicion de dimensiones en el Viewport)
  - `ui_dimension_utilities.py`: Dimension Utilities (Dimension Checker y presets de unidades)
- `props_ai_materials.py`: propiedades para el estado del AI Material Renamer

## Instalacion local para pruebas

1. En Blender: Edit > Preferences > Add-ons > Install...
2. Selecciona el zip del proyecto (o la carpeta contenedora de `lime_pipeline`).
3. Activa "Lime Pipeline".

## Licencia

Pendiente de definir.

## Reglas canonicas y mantenimiento de docs
- El archivo canonico de reglas es: `.cursor/rules/limepipelinerules.mdc`.
- Si cambias el comportamiento visible o la arquitectura, actualiza tambien: `README.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`.
