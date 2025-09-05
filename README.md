# Lime Pipeline (Blender 4.5 LTS add-on)

Organización de proyectos, normalización de nombres y helpers para primer guardado y backups.

- Target: Blender 4.5 LTS
- Panel: View3D > Sidebar (N) > Lime Pipeline > Project Organization
- Preferencias: Edit > Preferences > Add-ons > Lime Pipeline

## Estructura del paquete `lime_pipeline/`

- `__init__.py`: registro del add-on y bl_info
- `prefs.py`: AddonPreferences
- `props.py`: PropertyGroup persistente en WindowManager
- `naming.py`: normalización y helpers de nombres
- `paths.py`: resolución de rutas RAMV por tipo
- `scan.py`: escaneo y sugerencia de SC
- `validate.py`: validaciones y gating de acciones
- `ops_*.py`: operadores (pick root, folders, create file, backup)
- `ui.py`: panel principal

## Instalación local para pruebas

1. En Blender: Edit > Preferences > Add-ons > Install...
2. Selecciona el zip del proyecto (o la carpeta contenedora de `lime_pipeline`).
3. Activa "Lime Pipeline".

## Licencia

Pendiente de definir.
