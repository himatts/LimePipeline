# Especificaciones: panel UI para fondos guía de márgenes

## Visión general

Esta especificación define los requisitos para la interfaz de usuario que permite controlar las imágenes-guía de márgenes en cámaras dentro del panel "Cameras".

## Panel afectado

### LIME_PT_render_cameras

#### ADDED Requirements

**R001 - Sección Márgenes / Backgrounds**
- **Escenario**: Panel de cámaras con cámara seleccionada
  - **Dado que** hay una cámara activa (`scene.camera`) de tipo `CAMERA`
  - **Y** la cámara tiene datos válidos (`cam.data`)
  - **Entonces** debe mostrar sección "Márgenes / Backgrounds:" debajo de la lista de cámaras
  - **Y** solo mostrar esta sección cuando se cumplen las condiciones anteriores

**R002 - Toggle de visibilidad**
- **Escenario**: Control de `show_background_images`
  - **Dado que** la sección está visible
  - **Entonces** debe mostrar `layout.prop(cam_data, 'show_background_images', text="Mostrar fondos")`
  - **Y** si `show_background_images` es `False`, mostrar icono de información
  - **Y** mostrar botón "Activar fondos" que llame a `retry_camera_margin_backgrounds` con `set_visible=True`

**R003 - Sliders de opacidad por imagen**
- **Escenario**: Controles individuales para cada imagen de márgenes
  - **Dado que** las imágenes objetivo son: "Box Horizontal", "Box", "Box Vertical"
  - **Entonces** debe mostrar un slider por cada imagen objetivo en orden fijo
  - **Y** cada slider debe ser `layout.prop(entry, 'alpha', text=alias, slider=True)`
  - **Y** los sliders deben permanecer siempre activos e interactivos
  - **Y** buscar entrada correspondiente por basename en `cam_data.background_images`
  - **Y** mostrar solo sliders para entradas encontradas

**R004 - Indicadores de estado por imagen**
- **Escenario**: Estados de imágenes faltantes o con error
  - **Dado que** una imagen objetivo no tiene entrada correspondiente
  - **Entonces** mostrar etiqueta con icono de error: `layout.label(text=f"{alias}:", icon='ERROR')`
  - **Y** mostrar botón "Reintentar" que llame a `retry_camera_margin_backgrounds` con `alias` específico
  - **Y** el botón debe usar el alias para mensaje contextual

**R005 - Indicadores visuales para alpha cero**
- **Escenario**: Cuando el alpha de una imagen está en 0
  - **Dado que** una imagen tiene entrada pero `alpha == 0`
  - **Entonces** mostrar indicador visual con ícono `HIDE_OFF`
  - **Y** mostrar botón rápido "0.5" que llame a `reset_margin_alpha` con `target_alpha=0.5`
  - **Y** mantener el slider siempre activo e interactivo
  - **Y** no desactivar ningún control cuando alpha llega a 0

## Comportamiento de la interfaz

### Layout y organización

**L001 - Ubicación en panel**
- La sección se coloca debajo del `template_list` y controles principales
- Se separa visualmente con `layout.separator()`
- Usa etiqueta clara: `layout.label(text="Márgenes / Backgrounds:")`

**L002 - Organización de controles**
- Toggle de visibilidad en primera fila con botón de activación si es necesario
- Cada imagen objetivo en su propia fila con slider o controles de error
- Alineación consistente usando `align=True` donde aplica

### Estados visuales

**V001 - Estados de imagen**
- **Imagen encontrada**: mostrar slider de opacidad con valor actual
- **Imagen faltante**: mostrar etiqueta de error + botón de reintento
- **Imagen con alpha=0**: mostrar slider activo + indicador visual (ícono HIDE_OFF) + botón rápido "0.5"

**V002 - Estados de toggle**
- **Activado**: controles normales, sin mensaje adicional
- **Desactivado**: controles presentes pero con indicador visual + botón de activación

### Interacciones

**I001 - Respuesta inmediata**
- Cambios en sliders se reflejan inmediatamente en `entry.alpha`
- Cambios en toggle se reflejan inmediatamente en `cam_data.show_background_images`
- No hay operaciones asíncronas; todo es inmediato

**I002 - Mensajes contextuales**
- Botón "Activar fondos" incluye mensaje: "Reintentado márgenes: X/3 imágenes actualizadas"
- Botón "Reintentar" incluye alias: "Reintentado 'Box Horizontal': X/3 imágenes actualizadas"

## Dependencias técnicas

### Búsqueda de entradas

**D001 - Algoritmo de matching**
```python
def find_margin_entry(background_images, alias):
    target_base = alias.lower().replace(' ', '_') + '_margins.png'
    for bg_entry in background_images:
        img = getattr(bg_entry, 'image', None)
        fp = getattr(img, 'filepath', '') if img else ''
        name = getattr(img, 'name', '') if img else ''
        base = (Path(fp).name if fp else (name or '')).lower()
        if target_base in base:
            return bg_entry
    return None
```

**D002 - Orden de imágenes**
- Procesar en orden fijo: ["Box Horizontal", "Box", "Box Vertical"]
- No depender de orden interno de `background_images`

### Manejo de errores

**E001 - Cámaras inválidas**
- Si `scene.camera` es None o no es CAMERA → no mostrar sección
- Si `cam.data` es None → no mostrar sección

**E002 - Entradas faltantes**
- No lanzar excepciones si no se encuentran entradas
- Mostrar controles de error en su lugar

## Casos de uso

### UC001 - Cámara nueva con márgenes
**Actor**: Usuario del addon
**Precondiciones**: Cámara creada automáticamente con márgenes aplicados
**Flujo principal**:
1. Usuario selecciona cámara en lista
2. Panel muestra sección Márgenes / Backgrounds
3. Toggle "Mostrar fondos" está activado
4. Tres sliders muestran alpha=0.5 cada uno
5. Usuario puede ajustar opacidad individualmente
**Postcondiciones**: Configuración se guarda automáticamente

### UC002 - Cámara con márgenes desactivados
**Actor**: Usuario del addon
**Precondiciones**: Cámara con márgenes pero `show_background_images=False`
**Flujo principal**:
1. Usuario selecciona cámara en lista
2. Panel muestra sección Márgenes / Backgrounds
3. Toggle "Mostrar fondos" está desactivado
4. Aparece icono de información y botón "Activar fondos"
5. Sliders siguen visibles pero indican estado desactivado
**Postcondiciones**: Usuario puede reactivar fondos fácilmente

### UC003 - Cámara con imágenes faltantes
**Actor**: Usuario del addon
**Precondiciones**: Cámara con entradas de márgenes pero rutas inválidas
**Flujo principal**:
1. Usuario selecciona cámara en lista
2. Panel muestra sección Márgenes / Backgrounds
3. Para imágenes faltantes: mostrar etiqueta de error + botón "Reintentar"
4. Usuario hace clic en "Reintentar"
5. Sistema recarga imágenes válidas
**Postcondiciones**: Imágenes válidas se cargan correctamente

## Validación

### Criterios de aceptación

- ✅ Sección aparece solo para cámaras válidas seleccionadas
- ✅ Toggle controla correctamente `show_background_images`
- ✅ Sliders reflejan y modifican `alpha` de cada imagen
- ✅ Controles de error aparecen para imágenes faltantes
- ✅ Botón "Reintentar" funciona correctamente con mensajes contextuales
- ✅ Layout es claro y consistente con resto del panel

### Casos de prueba

**TP001 - Cámara nueva**
- Crear cámara nueva → seleccionar → verificar sección visible con 3 sliders

**TP002 - Toggle desactivado**
- Desactivar toggle → verificar icono info y botón "Activar fondos"

**TP003 - Imagen faltante**
- Invalidar ruta de imagen → verificar etiqueta error + botón reintentar

**TP004 - Reintento exitoso**
- Ejecutar reintento → verificar que imagen se carga correctamente

**TP005 - Sin cámara seleccionada**
- Deseleccionar cámara → verificar que sección desaparece

## Consideraciones de accesibilidad

- **Textos en inglés**: Preparado para futura internacionalización
- **Iconos estándar**: Usa iconos nativos de Blender para consistencia
- **Layout responsivo**: Se adapta a diferentes anchos de panel
- **Estados visuales claros**: Iconos y colores indican claramente el estado

## Mantenimiento

- **Extensibilidad**: Fácil añadir más imágenes objetivo modificando `margin_aliases`
- **Consistencia**: Mantiene estilo y patrones del resto del panel de cámaras
- **Separación de responsabilidades**: Lógica de búsqueda y controles claramente separados
