# Lime Pipeline (Blender 4.5 LTS add-on)

Lime Pipeline es un add-on de Blender orientado a estudios y equipos que buscan orden y consistencia en la producción. Su propósito es estandarizar la organización de proyectos y escenas para reducir fricción operativa y errores humanos.

De forma práctica, el add-on:
- Centraliza la configuración del proyecto (raíz, tipo, revisión y escena) y genera nombres limpios y consistentes.
- Asiste en el primer guardado, rutas objetivo y backups numerados.
- Crea y gestiona estructuras de SHOT dentro de la escena, incluyendo instanciado y duplicado de shots con políticas claras.
- Presenta paneles en el Sidebar para flujo de archivos y preparación interna de la escena.
- Permite medir selecciones con un cubo envolvente y longitudes nativas en el Viewport.

- Target: Blender 4.5 LTS
- Paneles: View3D > Sidebar (N) > Lime Pipeline > Project Organization, Shots, Render Configs, Stage, 3D Model Organizer
- Preferencias: Edit > Preferences > Add-ons > Lime Pipeline

## Estructura del paquete `lime_pipeline/`

- `__init__.py`: registro del add-on y bl_info
- `prefs.py`: AddonPreferences
- `props.py`: PropertyGroup persistente en WindowManager
- `core/`: núcleo común
  - `naming.py`: `resolve_project_name`, normalización y helpers
  - `validate_scene.py`: validaciones puras de contexto de escena/SHOT
- `paths.py`: resolución de rutas RAMV por tipo
- `scan.py`: escaneo y sugerencia de SC
- `validate.py`: validaciones y gating de acciones
- `scene/scene_utils.py`: helpers con efectos en Outliner (crear/instanciar/duplicar SHOT)
- `data/templates.py`: plantilla declarativa del árbol de SHOT y políticas
- `ops/`: operadores
  - `ops_shots.py`: New Shot / Shot Instance / Duplicate Shot
  - otros: pick root, folders, create file, backup
- `ui/`: paneles
  - `ui_project_org.py`: Project Organization (archivos)
  - `ui_shots.py`: Shots (escena/colecciones)
  - `ui_render_configs.py`: Render Configs (siempre visible; incluye Proposal View y Renders)
  - `ui_model_organizer.py`: 3D Model Organizer (importacion STEP via sTEPper, utilidades de limpieza y medicion de dimensiones en el Viewport)

## Instalación local para pruebas

1. En Blender: Edit > Preferences > Add-ons > Install...
2. Selecciona el zip del proyecto (o la carpeta contenedora de `lime_pipeline`).
3. Activa "Lime Pipeline".

## Licencia

Pendiente de definir.

## Reglas canónicas y mantenimiento de docs
- El archivo canónico de reglas es: `.cursor/rules/limepipelinerules.mdc`.
- Si cambias el comportamiento visible o la arquitectura, actualiza también: `README.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`.
