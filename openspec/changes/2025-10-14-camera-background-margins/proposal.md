# Implementación: fondos guía de márgenes para cámaras

## Propósito y contexto

Se requiere añadir funcionalidad para automatizar la aplicación de imágenes-guía de márgenes como fondos de cámara en el proyecto Lime Pipeline. Estas imágenes facilitan la composición visual al mostrar las márgenes deseadas para distintos formatos directamente en la vista de cámara.

## Alcance definido

- **Imágenes objetivo**: Trabajar con 3 imágenes de márgenes (excluyendo "Instagram" según decisión del usuario):
  - `Box_Horizontal_Margins.png`
  - `Box_Margins.png`
  - `Box_Vertical_Margins.png`

- **Comportamiento automático**: Al crear o duplicar cámaras mediante los operadores propios del proyecto (`lime.add_camera_rig` y `lime.duplicate_active_camera`), el sistema debe:
  - Añadir/actualizar automáticamente las imágenes como Background Images
  - Aplicar configuración uniforme: `frame_method='CROP'`, `display_depth='FRONT'`, `alpha=0.5`
  - Evitar duplicados reutilizando entradas existentes
  - Activar `show_background_images=True` para visualización inmediata

- **Interfaz de usuario**: En el panel "Cameras" añadir sección "Márgenes / Backgrounds" que:
  - Muestre toggle de `show_background_images` con mensaje de estado
  - Proporcione sliders de opacidad (0-1) para cada imagen de márgenes
  - Incluya botón "Reintentar" para recargar rutas faltantes
  - Solo se muestra cuando hay una cámara seleccionada

- **Resolución de rutas**: Las imágenes se buscan en `lime_pipeline/data/libraries/` usando resolución relativa al addon.

## Decisiones tomadas

1. **Exclusión de operadores externos**: Solo se aplica la funcionalidad cuando se usan los operadores internos (`lime.add_camera_rig` y `lime.duplicate_active_camera`), no para cámaras creadas vía Shift+A u otros medios.

2. **Exclusión de imagen "Instagram"**: Según decisión del usuario, trabajar únicamente con las 3 imágenes Box (Horizontal, regular, Vertical).

3. **Ubicación del helper**: El helper `ensure_camera_margin_backgrounds` se coloca en `scene/scene_utils.py` respetando las reglas de arquitectura (módulo `scene` puede usar `bpy`).

4. **Manejo de rutas inválidas**: Si faltan archivos, se marca `path_ok=False` en el estado devuelto sin lanzar excepciones. La UI muestra botón "Reintentar" para recargar.

## Criterios de aceptación

- ✅ Crear cámaras con `lime.add_camera_rig` añade automáticamente las 3 imágenes con configuración correcta
- ✅ Duplicar cámaras con `lime.duplicate_active_camera` actualiza fondos sin duplicados
- ✅ Panel "Cameras" muestra sección "Márgenes / Backgrounds" con controles de opacidad
- ✅ Toggle `show_background_images` controla visibilidad sin perder configuración
- ✅ Sliders reflejan inmediatamente cambios en `alpha` de cada imagen
- ✅ Rutas se resuelven desde `lime_pipeline/data/libraries/` con fallback
- ✅ Funcionalidad coexiste sin conflictos con utilidades existentes de cámaras

## Archivos afectados

- `lime_pipeline/scene/scene_utils.py`: Nuevo helper público `ensure_camera_margin_backgrounds`
- `lime_pipeline/ops/ops_cameras.py`: Enganches en operadores de creación/duplicado + operador `retry_camera_margin_backgrounds`
- `lime_pipeline/ui/ui_cameras_manager.py`: Sección UI con controles de márgenes

## Documentación

- Actualizar `README.md` con breve nota sobre funcionalidad de márgenes
- Actualizar `ARCHITECTURE.md` mencionando el helper en `scene` y enganches en operadores

## Estado

Implementación completa y lista para revisión.
