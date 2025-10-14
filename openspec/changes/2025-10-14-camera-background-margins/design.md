# Diseño técnico: fondos guía de márgenes para cámaras

## Arquitectura general

La implementación se basa en tres componentes principales trabajando en conjunto:

1. **Helper en `scene_utils`**: Función central que gestiona la creación/actualización de Background Images
2. **Enganches en operadores**: Integración automática en creación/duplicado de cámaras
3. **Sección UI en panel**: Controles interactivos para configuración de márgenes

## Helper `ensure_camera_margin_backgrounds`

### Firma y responsabilidades

```python
def ensure_camera_margin_backgrounds(cam: bpy.types.Object, *, set_visible: bool = True, defaults_alpha: float = 0.5) -> dict
```

**Precondiciones**:
- `cam` debe ser un objeto de tipo `CAMERA` con datos válidos
- El módulo `scene` tiene permisos para usar `bpy` según reglas de arquitectura

**Funcionamiento**:

1. **Resolución de rutas**: Calcula la ruta absoluta a `lime_pipeline/data/libraries/` usando `Path(__file__).resolve().parents[1]`

2. **Configuración de imágenes objetivo**:
   ```python
   targets = [
       ("Box Horizontal", libraries_dir / 'Box_Horizontal_Margins.png'),
       ("Box",            libraries_dir / 'Box_Margins.png'),
       ("Box Vertical",   libraries_dir / 'Box_Vertical_Margins.png'),
   ]
   ```

3. **Activación de visibilidad**: Si `set_visible=True`, activa `cam.data.show_background_images = True`

4. **Búsqueda de entradas existentes**: Construye mapa de entradas existentes por basename para evitar duplicados:
   ```python
   existing_by_basename = {}
   for entry in cam.data.background_images:
       base = Path(getattr(entry.image, 'filepath', '')).name.lower()
       existing_by_basename[base] = entry
   ```

5. **Procesamiento por imagen**:
   - Si no existe entrada → intentar añadir vía `bpy.ops.view3d.camera_background_image_add()` con override de contexto 3D
   - Si existe → reutilizar entrada existente
   - Cargar imagen con `bpy.data.images.load(path, check_existing=True)`
   - Aplicar configuración: `frame_method='CROP'`, `display_depth='FRONT'`, `alpha=defaults_alpha`

6. **Manejo de errores**: Marca `path_ok=False` si archivo no existe, sin lanzar excepciones

7. **Retorno**: Dict con estado por alias `{alias: {"found": bool, "path_ok": bool, "path": str}}`

### Estrategia de contexto 3D

Para añadir Background Images cuando no hay área 3D activa, se construye override de contexto:

```python
win = area = region = None
for w in bpy.context.window_manager.windows:
    for a in w.screen.areas:
        if a.type == 'VIEW_3D':
            r = next((rg for rg in a.regions if rg.type == 'WINDOW'), None)
            if r: win, area, region = w, a, r; break

if win and area and region:
    with bpy.context.temp_override(window=win, area=area, region=region, ...):
        bpy.ops.view3d.camera_background_image_add('EXEC_DEFAULT')
```

## Enganches en operadores

### `LIME_OT_add_camera_rig.execute`

```python
# Tras creación exitosa y aplicación de mejoras (escala, colores)
cam_coll = validate_scene.get_shot_child_by_basename(shot, C_CAM)
if cam_coll is not None:
    new_cams = [o for o in cam_coll.objects if getattr(o, "type", None) == 'CAMERA']
    for cam_obj in new_cams:
        ensure_camera_margin_backgrounds(cam_obj, set_visible=True, defaults_alpha=0.5)
```

**Ubicación**: Después de mejoras de rig pero antes de reporte final, respetando flujo existente.

### `LIME_OT_duplicate_active_camera.execute`

```python
# Tras independencia de datos y preservación de rig
for orig_obj, new_obj in original_to_copy.items():
    if getattr(orig_obj, 'type', None) == 'CAMERA':
        ensure_camera_margin_backgrounds(new_obj, set_visible=True, defaults_alpha=0.5)
```

**Ubicación**: Dentro del bloque `try` que maneja independencia de datos, respetando estructura de duplicación.

## Sección UI en panel de cámaras

### Estructura del layout

```python
# Debajo de template_list y controles principales
if scene.camera and scene.camera.type == 'CAMERA':
    layout.separator()
    layout.label(text="Márgenes / Backgrounds:")

    # Toggle de visibilidad
    row = layout.row(align=True)
    row.prop(cam_data, 'show_background_images', text="Mostrar fondos")
    if not cam_data.show_background_images:
        row.label(text="", icon='INFO')
        row.operator("lime.retry_camera_margin_backgrounds", text="Activar fondos").set_visible = True

    # Sliders por imagen
    margin_aliases = ["Box Horizontal", "Box", "Box Vertical"]
    for alias in margin_aliases:
        # Buscar entrada por basename match
        entry = find_margin_entry(cam_data.background_images, alias)
        if entry:
            layout.prop(entry, 'alpha', text=alias, slider=True)
        else:
            layout.label(text=f"{alias}:", icon='ERROR')
            layout.operator("lime.retry_camera_margin_backgrounds", text="Reintentar").alias = alias
```

### Búsqueda de entradas

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

## Operador de reintento

### Firma y comportamiento

```python
class LIME_OT_retry_camera_margin_backgrounds(Operator):
    set_visible: BoolProperty(default=True)  # Para "Activar fondos"
    alias: StringProperty(default="")        # Para reintento específico
```

**Ejecución**:
- Llama `ensure_camera_margin_backgrounds(cam, set_visible=set_visible)`
- Reporta cantidad de imágenes actualizadas
- Si `alias` especificado, mensaje incluye el alias

### Integración UI

- Botón "Activar fondos" llama con `set_visible=True`
- Botón "Reintentar" llama con `alias` específico para mensaje contextual

## Manejo de casos límite

### Rutas inválidas
- `ensure_camera_margin_backgrounds` marca `path_ok=False` sin excepciones
- UI muestra icono de error y botón "Reintentar"
- "Reintentar" vuelve a intentar cargar si archivo existe ahora

### Sin área 3D
- Usa override de contexto 3D si disponible
- Si no, deja entradas sin imagen pero con configuración aplicada

### Cámaras sin datos
- Helper devuelve error temprano sin modificar estado
- UI no se muestra si `cam.data` es None

### Backgrounds preexistentes
- No se eliminan ni modifican entradas ajenas
- Solo se añaden/actualizan las 3 objetivo por basename

## Consideraciones de rendimiento

- Búsqueda de entradas existente es O(n) pero n es pequeño (típicamente <10)
- Carga de imágenes usa `check_existing=True` para reutilizar datos
- Override de contexto se construye solo cuando necesario

## Extensibilidad futura

- Fácil añadir más imágenes objetivo modificando `targets` en helper
- Operador de reintento soporta alias específicos para granularidad
- Estructura UI soporta cualquier cantidad de imágenes objetivo

## Validación

La implementación cumple con:
- ✅ Reglas de arquitectura (módulo `scene` usa `bpy`, helper público)
- ✅ Invariantes (no altera estructura de proyecto ni nombres)
- ✅ UI nativa (usa elementos estándar de Blender)
- ✅ Internacionalización futura (textos en inglés, estructura i18n-friendly)
- ✅ Módulos separados (core/scene/ops/ui respetados)
