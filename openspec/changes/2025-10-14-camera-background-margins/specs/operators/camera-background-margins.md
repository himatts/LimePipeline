# Especificaciones: operadores para fondos guía de márgenes

## Visión general

Esta especificación define los requisitos para la integración automática de imágenes-guía de márgenes en operadores de creación y duplicado de cámaras.

## Operadores afectados

### LIME_OT_add_camera_rig

#### ADDED Requirements

**R001 - Auto-aplicación de márgenes en creación**
- **Escenario**: Cuando se ejecuta `lime.add_camera_rig` exitosamente
  - **Dado que** se crea una o más cámaras nuevas en la colección CAM del SHOT activo
  - **Cuando** la creación es exitosa y se aplican mejoras de rig
  - **Entonces** debe llamar a `ensure_camera_margin_backgrounds(cam)` para cada cámara creada
  - **Y** aplicar configuración por defecto: `set_visible=True`, `defaults_alpha=0.5`

**R002 - Ubicación del enganche**
- **Escenario**: Integración en flujo de creación
  - **Dado que** el operador tiene estructura: creación → mejoras → reporte
  - **Entonces** el enganche debe ubicarse después de mejoras de rig pero antes del reporte final
  - **Y** respetar el flujo existente sin alterar lógica de creación o naming

### LIME_OT_duplicate_active_camera

#### ADDED Requirements

**R003 - Auto-aplicación de márgenes en duplicado**
- **Escenario**: Cuando se ejecuta `lime.duplicate_active_camera` exitosamente
  - **Dado que** se duplican cámara(s) y sus rigs asociados
  - **Cuando** se establece independencia de datos de cámara
  - **Entonces** debe llamar a `ensure_camera_margin_backgrounds(new_obj)` para cada cámara duplicada
  - **Y** aplicar configuración por defecto: `set_visible=True`, `defaults_alpha=0.5`

**R004 - Ubicación del enganche**
- **Escenario**: Integración en flujo de duplicado
  - **Dado que** el operador tiene estructura: duplicado → independencia de datos → reporte
  - **Entonces** el enganche debe ubicarse dentro del bloque de independencia de datos
  - **Y** procesar todas las cámaras en `original_to_copy` que tengan `type=='CAMERA'`

### LIME_OT_retry_camera_margin_backgrounds

#### ADDED Requirements

**R005 - Operador de reintento**
- **Escenario**: Reintentar carga de imágenes de márgenes faltantes
  - **Dado que** hay una cámara activa seleccionada
  - **Cuando** se ejecuta el operador
  - **Entonces** debe llamar a `ensure_camera_margin_backgrounds(cam, set_visible=set_visible)`
  - **Y** reportar cantidad de imágenes actualizadas exitosamente
  - **Y** incluir alias en mensaje si se especifica

**R006 - Propiedades del operador**
- **Escenario**: Parámetros de configuración
  - **Dado que** el operador necesita flexibilidad para diferentes casos de uso
  - **Entonces** debe tener propiedad `set_visible: BoolProperty(default=True)`
  - **Y** propiedad `alias: StringProperty(default="")` para mensajes específicos
  - **Y** usar estos parámetros al llamar al helper

## Comportamiento general

### Invariantes

**I001 - No alterar operadores existentes**
- Los operadores afectados mantienen toda su funcionalidad existente
- La nueva funcionalidad es puramente aditiva
- No se modifican nombres, estructuras o flujos existentes

**I002 - Manejo de errores graceful**
- Si falla la aplicación de márgenes, no debe afectar el resultado principal del operador
- Errores se manejan con excepciones internas sin alterar estado del usuario
- Reportes informativos indican éxito/parcial/falla de la aplicación de márgenes

### Dependencias

**D001 - Dependencia del helper**
- Todos los operadores requieren que `ensure_camera_margin_backgrounds` esté disponible
- Se importa desde `..scene.scene_utils`

## Casos de uso

### UC001 - Creación de cámara nueva
**Actor**: Usuario del addon
**Precondiciones**: SHOT activo con colección CAM
**Flujo principal**:
1. Usuario ejecuta `lime.add_camera_rig`
2. Sistema crea cámara(s) nueva(s)
3. Sistema aplica mejoras de rig (escala, colores)
4. Sistema aplica márgenes automáticamente
5. Sistema reporta creación exitosa
**Postcondiciones**: Cámara tiene 3 imágenes de márgenes configuradas con alpha=0.5

### UC002 - Duplicado de cámara existente
**Actor**: Usuario del addon
**Precondiciones**: Cámara activa seleccionada
**Flujo principal**:
1. Usuario ejecuta `lime.duplicate_active_camera`
2. Sistema duplica cámara y rig asociado
3. Sistema establece independencia de datos
4. Sistema aplica márgenes a cámara duplicada
5. Sistema reporta duplicado exitoso
**Postcondiciones**: Cámara duplicada tiene márgenes configurados, originales preservados

### UC003 - Reintento de márgenes
**Actor**: Usuario del addon
**Precondiciones**: Cámara activa con márgenes faltantes o rutas inválidas
**Flujo principal**:
1. Usuario ejecuta `lime.retry_camera_margin_backgrounds`
2. Sistema intenta recargar imágenes de márgenes
3. Sistema reporta resultado con conteo de actualizaciones
**Postcondiciones**: Imágenes válidas se cargan, estado se actualiza

## Validación

### Criterios de aceptación

- ✅ Operadores principales ejecutan correctamente con márgenes aplicados
- ✅ No hay regresiones en funcionalidad existente de operadores
- ✅ Reportes informativos indican estado de aplicación de márgenes
- ✅ Manejo graceful de errores sin alterar flujo principal

### Casos de prueba

**TP001 - Creación exitosa**
- Crear cámara nueva → verificar que tiene 3 fondos de márgenes

**TP002 - Duplicado exitoso**
- Duplicar cámara existente → verificar que duplicada tiene márgenes, original preservado

**TP003 - Reintento exitoso**
- Forzar rutas inválidas → ejecutar reintento → verificar que carga imágenes válidas

**TP004 - Error en márgenes**
- Simular error en helper → verificar que operador principal sigue funcionando
