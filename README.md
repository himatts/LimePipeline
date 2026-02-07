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
- Incluye un AI Asset Organizer v2 para sugerir y aplicar nombres de objetos/materiales/colecciones (OpenRouter), con preview unificado, resolución jerárquica de destinos y organización opcional de colecciones.
- AI Asset Organizer v2 usa PascalCase por segmentos separados con guion bajo para objetos y colecciones (ejemplo: `SciFiCrate_Large_02`).
- AI Asset Organizer v2 muestra rutas completas de destino, maneja ambigüedad con confirmación por fila y permite filtros de Apply Scope (All / Only Objects / Only Materials / Only Collections).
- Permite re-rutear manualmente en lote el destino de colección para objetos seleccionados en la lista antes de aplicar cambios.
- Cuando una reorganización requiere crear nuevas colecciones, AI Asset Organizer v2 las muestra como filas editables de “planned collections” para ajustar nombres antes de aplicar, manteniendo sincronía con destinos de objetos.
- AI Asset Organizer v2 puede abrirse en una ventana emergente enfocada (`Open in Window`) para revisar nombrado/organización (objetos, materiales, colecciones) sin mezclar el bloque de texturas.
- AI Asset Organizer v2 prioriza destinos de colecciones activas por defecto y ofrece reportes de debug (materiales y colecciones) para auditar decisiones IA/heurísticas.
- AI Material Renamer fue retirado de la UI y del runtime; usa AI Asset Organizer como flujo único.
- Los controles de debug y reroute masivo se mantienen como herramientas internas y no se muestran en la UI principal para reducir ruido.
- Cuando no existen destinos activos, AI Asset Organizer puede usar un hint de IA válido como destino virtual (p. ej. `Props`) para crearlo durante `Organize collections on apply`, sin reactivar colecciones existentes desactivadas.
- AI Asset Organizer v2 incorpora señales jerárquicas (padre/hijo/raíz y rol de empties) para mejorar sugerencias de naming y organización sin depender únicamente de contexto manual.
- La resolución de colecciones aplica guardrails para roles jerárquicos (`ROOT_CONTROLLER`/`CONTROLLER`) y evita clasificar controladores raíz en subcategorías técnicas (como `Electronics`) salvo evidencia fuerte.
- Incluye herramientas de Textures (Scan/Adopt) dentro de AI Asset Organizer para centralizar texturas en `rsc/Textures`.
- Incluye un AI Render Converter para convertir renders a storyboard/sketch con Krea y OpenRouter.
- Mejora la gestión visual del AI Render Converter con miniaturas, vista grande y filtros por sección.
- Incluye opciones de limpieza de imágenes generadas (eliminación individual y batch con confirmación).
- Permite abrir la carpeta de outputs de la IA y limpiar manifests generados.
- Añade utilidades prácticas de escena (por ejemplo, checks de dimensiones y ayudas de cámara).
- El panel de Cameras permite agregar Camera Rigs o Simple Cameras dentro del SHOT activo.
- El panel 3D Model Organizer (Lime Toolbox) incluye acciones de Linked Collections (convertir a local manteniendo meshes linkeados).

## Requisitos
- Blender 4.5 LTS (objetivo actual del add-on).

## Instalación local (rápida)
1. Blender > Edit > Preferences > Add-ons > Install...
2. Selecciona el `.zip` del proyecto (o la carpeta que contiene `lime_pipeline`).
3. Activa “Lime Pipeline”.

## API keys (.env)
- Las API keys de OpenRouter y Krea ya no se guardan en preferencias de Blender.
- Se cargan desde un archivo `.env` local en la raíz del repositorio.
- Variables soportadas:
  - `LIME_OPENROUTER_API_KEY` (o `OPENROUTER_API_KEY`)
  - `LIME_KREA_API_KEY` (o `KREA_API_KEY`)
- Puedes usar `.env.example` como plantilla.
