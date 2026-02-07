---
title: Troubleshooting
---

# Guía de Troubleshooting - Lime Pipeline

Esta guía proporciona soluciones detalladas para los problemas más comunes en Lime Pipeline, organizados por categoría.

## Problemas de Instalación y Configuración

### El Addon No Aparece en Blender
**Síntomas:**
- No se ven paneles de Lime Pipeline en la UI
- Error al cargar Blender: "addon not found"

**Soluciones:**
1. **Verificar instalación:**
   - Ir a `Edit > Preferences > Add-ons`
   - Buscar "Lime Pipeline"
   - Asegurarse de que esté habilitado (✓)

2. **Reinstalar addon:**
   - Deshabilitar addon actual
   - Reiniciar Blender
   - Remover carpeta `lime_pipeline` de addons
   - Copiar versión nueva
   - Habilitar nuevamente

3. **Verificar compatibilidad:**
   - Confirmar versión de Blender soportada
   - Revisar `README.md` para requisitos

### Error de Importación de Módulos
**Error típico:** `ModuleNotFoundError` o `ImportError`

**Causas comunes:**
- Dependencias faltantes (requests, numpy, etc.)
- Conflicto de versiones
- Archivos corruptos

**Soluciones:**
**Soluciones:**
- Verifica que el add-on est? instalado y habilitado.
- Para funciones de IA, revisa la API key y la conectividad.
- Si el error persiste, reinstala el add-on.

## Problemas con Paneles y UI

### Paneles No Aparecen en el Viewport
**Causa:** Contextos incorrectos o espacios no soportados

**Verificación:**
- **Paneles 3D View:** Solo aparecen en `3D Viewport > Sidebar (N) > Lime`
- **Paneles Image Editor:** Solo en `Image Editor > Sidebar > Lime`
- **Toolbar Panels:** Solo en `3D Viewport > Tool > Active Tool` (con objeto seleccionado)

**Solución:**
1. Cambiar al espacio correcto (3D View, Image Editor, etc.)
2. Abrir sidebar con `N` o desde menú
3. Seleccionar pestaña "Lime"

### Paneles Aparecen pero sin Contenido
**Causa:** Estado de escena corrupto o configuración faltante

**Soluciones:**
1. **Restablecer configuración:**
   - Deshabilita y vuelve a habilitar el add-on.
   - Abre un archivo nuevo para descartar estado corrupto.

2. **Validar escena:**
   - Usar "Add Missing Collections" en Project Organization
   - Verificar estructura de shots

3. **Limpiar escena:**
   - Ejecutar "Clean Step" para eliminar elementos problemáticos
   - Crear nueva escena y migrar assets

## Problemas con Cámaras y Márgenes

### Márgenes de Cámara No se Crean
**Síntomas:**
- Background plane no aparece
- Error: "No camera found" o "Margin creation failed"

**Diagnóstico:**
1. Verificar que hay una cámara activa
2. Confirmar que la cámara está en una collection SHOT
3. Revisar constraints de la cámara

**Soluciones:**
1. **Crear rig manualmente:**
   - Seleccionar cámara
   - Ejecutar "Add Camera Rig" en Cameras Manager

2. **Reparar márgenes existentes:**
   - Usar "Retry Camera Margin Backgrounds"
   - Verificar resolución en Dimension Utilities

3. **Limpiar y recrear:**
   - Ejecutar "Clean Step"
   - Remover rig existente
   - Crear nuevo rig

### Backgrounds No se Actualizan
**Causa:** Sistema de constraints roto o rutas inválidas

**Soluciones:**
1. **Forzar actualización:**
   - Botón "Refresh" en Auto Camera Background
   - Cambiar frame y volver

2. **Verificar constraints:**
   - Seleccionar background plane
   - Revisar `Properties > Object Constraints`
   - Debe tener "Follow Path" o "Track To"

3. **Recrear backgrounds:**
   - Usar "Cleanup" para remover existentes
   - Ejecutar "Auto Camera Background" nuevamente

## Problemas de Materiales y Texturas

### Materiales No se Renombran Correctamente
**Causa:** Nodos shader no detectados o formato inválido

**Verificación:**
- Solo materiales con nodos Principled BSDF son compatibles
- Nombres deben seguir formato `MAT_{Tag}_{Familia}_{Acabado}_{V##}`

**Soluciones:**
1. **Convertir nodos:**
   - Cambiar a Principled BSDF
   - Reconectar texturas manualmente

2. **Renombrado manual:**
   - Usar AI Asset Organizer con Apply Scope = Only Materials
   - Aplicar cambios uno por uno

3. **Verificar taxonomía:**
   - Revisar `core/material_taxonomy.py`
   - Ajustar t?rminos si es necesario

### Alpha Manager No Funciona
**Problemas comunes:**
- Transparencias no se aplican
- Eventos alpha no se guardan
- Modos no cambian correctamente

**Soluciones:**
1. **Verificar materiales:**
   - Deben usar nodos Alpha
   - Configurar blend mode apropiado

2. **Reset eventos:**
   - Limpiar lista de eventos
   - Recrear desde cero

3. **Verificar keyframes:**
   - Revisar timeline para eventos alpha
   - Confirmar interpolación correcta

## Problemas de Render y Presets

### Presets de Render No se Aplican
**Causa:** Configuración corrupta o presets faltantes

**Soluciones:**
1. **Restaurar defaults:**
   - Botón "Restore Defaults" en Render Configs
   - Reset all settings

2. **Verificar presets:**
   - Archivo `render_presets.json` debe existir
   - Presets deben tener estructura válida

3. **Aplicar manualmente:**
   - Configurar parámetros uno por uno
   - Guardar como nuevo preset

### Renders Fallan o Son Lentos
**Síntomas:**
- Blender se congela durante render
- Memoria insuficiente
- Renders incompletos

**Optimizaciones:**
1. **Reducir resolución:**
   - Usar Dimension Utilities para presets más pequeños
   - Configurar render regions

2. **Optimizar escena:**
   - Usar "Clean Step" para eliminar elementos innecesarios
   - Reducir subdivisiones y modificadores

3. **Configurar denoising:**
   - Habilitar denoising en Render Presets
   - Ajustar calidad vs velocidad

## Problemas de Organización y SHOT System

### Collections SHOT No se Crean
**Causa:** Estructura de escena incompatible

**Soluciones:**
1. **Crear manualmente:**
   - `Scene Collection > New Collection`
   - Nombrar como "SHOT ###"

2. **Usar herramienta automática:**
   - "New Shot" en Shots Manager
   - "Add Missing Collections" para estructura completa

3. **Verificar jerarquía:**
   ```
   Scene Collection
   ├── SHOT 001
   │   ├── CAMERAS
   │   ├── LIGHTS
   │   ├── PROPS
   │   └── CHARACTERS
   ```

### Shots No se Sincronizan
**Problema:** Cambios en un shot no afectan a otros

**Soluciones:**
1. **Sync manual:**
   - Botón "Sync Shot List" en Shots Manager
   - Aplicar cambios a shots seleccionados

2. **Verificar aislamiento:**
   - Modo "Isolate Active Shot" puede estar activado
   - Desactivar para ver todos los shots

3. **Reset collections:**
   - Limpiar y recrear estructura de shots
   - Migrar assets a collections correctas

## Problemas de Rendimiento y Memoria

### Blender se Congela o se Cierra
**Causas comunes:**
- Memoria insuficiente para escenas complejas
- Loops infinitos en scripts
- Drivers o constraints corruptos

**Soluciones:**
1. **Liberar memoria:**
   - Cerrar otros programas
   - Aumentar memoria virtual
   - Usar `File > New` para escenas más pequeñas

2. **Debug scripts:**
   - Ejecutar desde terminal: `blender --background --python script.py`
   - Revisar console output para errores

3. **Limpiar escena:**
   - "Clean Step" para eliminar elementos problemáticos
   - Remover modificadores complejos temporalmente

### Archivos .blend Muy Grandes
**Causa:** Assets embebidos o historial largo

**Soluciones:**
1. **Limpiar historial:**
   - `File > Clean Up > Recursive Unused Data Blocks`
   - `File > Clean Up > Unused Data Blocks`

2. **Externalizar assets:**
   - Mover texturas fuera del .blend
   - Usar linked libraries para assets compartidos

3. **Optimizar:**
   - Reducir resolución de texturas
   - Usar proxies para geometría compleja

## Problemas de Versionado y Backup

### Sistema de Revisiones No Funciona
**Problema:** Archivos no se nombran correctamente

**Verificación:**
- Formato debe ser `Rev_{Letter}` (A-Z)
- Solo una letra por revisión

**Soluciones:**
1. **Corregir nombres:**
   - Renombrar archivos manualmente
   - Usar "Save as Template" con nombre correcto

2. **Reset contador:**
   - Configurar revisión inicial en Scene Properties
   - Asegurar consistencia entre archivos

### Backups No se Crean
**Causa:** Permisos de directorio o rutas inválidas

**Soluciones:**
1. **Verificar permisos:**
   - Directorio debe ser escribible
   - Espacio suficiente en disco

2. **Configurar ruta:**
   - Establecer `backup_path` en preferences
   - Usar ruta absoluta

3. **Backup manual:**
   - `File > Save As...` con nombre de backup
   - Mantener convención de nombres

## Problemas de IA y Conectividad

### AI Tools No Conectan
**Error típico:** "Connection failed" o "API timeout"

**Diagnóstico:**
1. Verificar conexión a internet
2. Confirmar API key válida
3. Revisar configuración de endpoint

**Soluciones:**
1. **Test conexión:**
   - Botón "Test Connection" en preferencias del add-on
   - Verificar respuesta en consola

2. **Configurar proxy:**
   - Si hay firewall corporativo
   - Configurar variables de entorno HTTP_PROXY

3. **Modo offline:**
   - Usar renombrado manual sin IA
   - Aplicar taxonomía local

## Errores Comunes y Sus Soluciones Rápidas

| Problema | Solución Rápida | Herramienta |
|----------|-----------------|-------------|
| Paneles faltantes | Cambiar espacio de trabajo | N/A |
| Márgenes rotos | "Retry Camera Margin Backgrounds" | Cameras Manager |
| Materiales mal nombrados | "Suggest Names (AI)" + "Apply Selected" (Only Materials) | AI Asset Organizer |
| Shots desincronizados | "Sync Shot List" | Shots Manager |
| Renders lentos | "Clean Step" + reducir resolución | Render Configs |
| Memoria insuficiente | "Clean Step" + externalizar assets | Model Organizer |

## Obteniendo Ayuda Adicional

### Logs y Debug
- Revisar `Console` de Blender para errores
- Habilitar debug mode en preferences
- Guardar logs para reportar issues

### Reportar Problemas
- Documentar pasos para reproducir
- Incluir versión de Blender y Lime Pipeline
- Adjuntar archivos .blend minimales que reproduzcan el problema

### Recursos Adicionales
- Revisar `docs/guias/` para workflows específicos
- Ver `ARCHITECTURE.md` para diseño del sistema
- Consultar `CHANGELOG.md` para cambios recientes
