---
title: Flujos típicos
---

# Flujos de Trabajo Típicos en Lime Pipeline

Esta guía describe los workflows más comunes en Lime Pipeline, organizados por tipo de tarea y complejidad.

## 1. Configuración Inicial de Proyecto

### Nuevo Proyecto desde Cero
```
1. Crear directorio del proyecto (formato: XX-##### Nombre Proyecto)
2. Ejecutar "Create File" desde Lime Pipeline
3. Configurar unidades en Dimension Utilities
4. Establecer estructura de shots inicial (SHOT 001)
5. Crear rig de cámara principal con márgenes
6. Configurar presets de render básicos
7. Guardar como SB_SC001_Rev_A
```

### Proyecto Existente - Migración
```
1. Abrir archivo existente
2. Ejecutar "Add Missing Collections" para crear estructura faltante
3. Renombrar colecciones al formato SHOT ###
4. Configurar márgenes de cámara para shots existentes
5. Aplicar presets de render estándar
6. Validar nomenclatura con herramientas de Stage Setup
```

## 2. Workflows de Animación

### Storyboard y Previsualización
```
1. Crear shots para cada escena (SHOT 001, 005, 010...)
2. Configurar cámaras principales por shot
3. Añadir backgrounds automáticos con "Auto Camera Background"
4. Crear animática básica con placeholders
5. Render previews con preset PV (previsualización)
6. Revisar timing y composición
```

### Animación Detallada
```
1. Importar assets desde librería
2. Configurar rigs de personajes en collections apropiadas
3. Aplicar Animation Parameters para keyframes consistentes
4. Usar Noisy Movement para elementos procedurales
5. Configurar Alpha Manager para transparencias
6. Render test shots con preset TMP
```

### Post-Animación y Lighting
```
1. Ajustar iluminación por shot en collections LIGHTS
2. Configurar render layers (Base, Shadow, AO, Normal, Depth)
3. Aplicar Render Presets optimizados
4. Test render con denoising
5. Ajustar márgenes de cámara si es necesario
6. Render final con preset REND
```

## 3. Workflows de Materiales

### Materiales Estándar
```
1. Crear materiales siguiendo convención MAT_{Tag}_{Familia}_{Acabado}_{V##}
2. Usar Alpha Manager para transparencias complejas
3. Aplicar Object Alpha Mix para objetos con múltiples materiales
4. Configurar presets de render con materiales específicos
5. Test render con iluminación variada
```

### Renombrado Inteligente con IA
```
1. Ejecutar "AI Test Connection" para verificar conectividad
2. Usar "AI Scan Materials" para analizar materiales existentes
3. Revisar sugerencias de renombrado en AI Material Renamer
4. Aplicar cambios con "AI Apply Materials"
5. Verificar consistencia con convenciones MAT_*
6. Ajustar manualmente casos especiales si es necesario
```

## 4. Workflows de Producción

### Pipeline de Renders Sociales
```
1. Configurar dimensiones (panel Dimension Utilities)
2. Crear rigs de cámara con márgenes específicos para redes sociales
3. Configurar shots optimizados para formato vertical/horizontal
4. Aplicar Render Presets con compresión optimizada
5. Usar "Save as Template" para mantener consistencia
6. Render secuencia completa con nombres normalizados
```

### Producción Multi-Shot
```
1. Crear estructura de shots numerada (001, 005, 010...)
2. Configurar cameras independientes por shot
3. Organizar assets en collections apropiadas
4. Aplicar iluminación consistente usando "Sync Shot List"
5. Render shots individuales con "Render Invoke"
6. Gestionar versiones con sistema de revisiones
```

### Backup y Versionado
```
1. Usar "Create Backup" regularmente durante producción
2. Mantener versiones TMP para trabajo diario
3. Crear versiones RAW para post-producción
4. Usar sistema de revisiones (A, B, C...) para hitos importantes
5. Archivar versiones finales como REND o ANIM
```

## 5. Workflows de Post-Producción

### Compositing y Efectos
```
1. Render layers separados (Base, Shadow, AO, etc.)
2. Exportar con nombres consistentes por frame
3. Usar "Save as RAW" para archivos sin compresión
4. Mantener estructura de directorios organizada
5. Preparar para integración con software de compositing
```

### Optimización Final
```
1. Revisar tamaños de archivo y rendimiento
2. Aplicar presets de render finales optimizados
3. Verificar consistencia de colores entre shots
4. Crear versiones alternativas con diferentes calidades
5. Archivar proyecto completo con estructura organizada
```

## 6. Workflows de Mantenimiento

### Limpieza de Escena
```
1. Ejecutar "Clean Step" para eliminar elementos temporales
2. Verificar integridad de collections con "Add Missing Collections"
3. Optimizar estructura de shots con herramientas de Model Organizer
4. Limpiar materiales no utilizados
5. Compactar archivo y crear backup final
```

### Migración entre Versiones
```
1. Abrir archivo en nueva versión de Blender
2. Ejecutar validación completa con Stage Setup
3. Actualizar presets de render si es necesario
4. Verificar compatibilidad de materiales y nodos
5. Test render completo antes de continuar producción
```

## Consejos Generales para Todos los Workflows

### Organización
- Mantener estructura de carpetas consistente
- Usar nombres descriptivos pero concisos
- Documentar decisiones importantes en comentarios

### Rendimiento
- Usar proxies y placeholders durante desarrollo
- Configurar render regions para tests rápidos
- Optimizar escenas antes de renders finales

### Versionado
- Crear backups antes de cambios importantes
- Usar sistema de revisiones para controlar versiones
- Mantener historial de cambios significativo

### Colaboración
- Sincronizar convenciones de nombres con el equipo
- Documentar workflows personalizados
- Compartir presets y templates útiles

## Troubleshooting en Workflows

### Problemas Comunes
- **Collections faltantes**: Usar "Add Missing Collections"
- **Cámaras sin márgenes**: Ejecutar "Auto Camera Background"
- **Materiales inconsistentes**: Revisar con AI Material Renamer
- **Rendimiento lento**: Optimizar con "Clean Step"

### Recuperación de Errores
- Mantener backups regulares
- Usar "Save as Template" para estados estables
- Documentar problemas y soluciones para referencia futura
