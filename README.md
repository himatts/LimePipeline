# Lime Pipeline (Blender add-on)

## ¿Qué es?
Un add-on para Blender que reúne herramientas y convenciones para mantener orden y consistencia durante la producción (nombres, rutas, guardados y utilidades de escena).

## ¿Cuál es su propósito?
Estandarizar el trabajo para reducir fricción y errores humanos: archivos mal nombrados, guardados en rutas incorrectas, falta de backups, materiales desordenados y escenas difíciles de mantener.

## ¿Cómo ayuda a solucionar el problema?
- Centraliza la configuración del proyecto y genera nombres/rutas consistentes.
- Asiste en el primer guardado y crea backups numerados.
- Facilita la creación/duplicado/instanciado de “shots” con reglas claras.
- Ayuda a mantener materiales bajo una nomenclatura consistente (manual y, opcionalmente, asistido por IA).
- Incluye un AI Asset Organizer v2 para sugerir y aplicar nombres de objetos/materiales/colecciones (OpenRouter), con preview de cambios y organización opcional de colecciones.
- Incluye herramientas de Textures (Scan/Adopt) dentro de AI Asset Organizer para centralizar texturas en `rsc/Textures`.
- Incluye un AI Render Converter para convertir renders a storyboard/sketch con Krea y OpenRouter.
- Mejora la gestión visual del AI Render Converter con miniaturas, vista grande y filtros por sección.
- Incluye opciones de limpieza de imágenes generadas (eliminación individual y batch con confirmación).
- Permite abrir la carpeta de outputs de la IA y limpiar manifests generados.
- Añade utilidades prácticas de escena (por ejemplo, checks de dimensiones y ayudas de cámara).
- El panel 3D Model Organizer (Lime Toolbox) incluye acciones de Linked Collections (convertir a local manteniendo meshes linkeados).

## Requisitos
- Blender 4.5 LTS (objetivo actual del add-on).

## Instalación local (rápida)
1. Blender > Edit > Preferences > Add-ons > Install...
2. Selecciona el `.zip` del proyecto (o la carpeta que contiene `lime_pipeline`).
3. Activa “Lime Pipeline”.
