# Lime Pipeline (Blender add-on)

## �Qu� es?
Un add-on para Blender que re�ne herramientas y convenciones para mantener orden y consistencia durante la producci�n (nombres, rutas, guardados y utilidades de escena).

## �Cu�l es su prop�sito?
Estandarizar el trabajo para reducir fricci�n y errores humanos: archivos mal nombrados, guardados en rutas incorrectas, falta de backups, materiales desordenados y escenas dif�ciles de mantener.

## �C�mo ayuda a solucionar el problema?
- Centraliza la configuraci�n del proyecto y genera nombres/rutas consistentes.
- Asiste en el primer guardado y crea backups numerados.
- Facilita la creaci�n/duplicado/instanciado de �shots� con reglas claras.
- Ayuda a mantener materiales bajo una nomenclatura consistente (manual y, opcionalmente, asistido por IA).
- Incluye un AI Asset Organizer v2 para sugerir y aplicar nombres de objetos/materiales/colecciones (OpenRouter), con preview unificado, resoluci�n jer�rquica de destinos y organizaci�n opcional de colecciones.
- AI Asset Organizer v2 usa PascalCase por segmentos separados con guion bajo para objetos y colecciones (ejemplo: `SciFiCrate_Large_02`).
- AI Asset Organizer v2 muestra rutas completas de destino, maneja ambig�edad con confirmaci�n por fila y permite filtros de Apply Scope (All / Only Objects / Only Materials / Only Collections).
- Permite re-rutear manualmente en lote el destino de colecci�n para objetos seleccionados en la lista antes de aplicar cambios.
- Cuando una reorganizaci�n requiere crear nuevas colecciones, AI Asset Organizer v2 las muestra como filas editables de �planned collections� para ajustar nombres antes de aplicar, manteniendo sincron�a con destinos de objetos.
- AI Asset Organizer v2 puede abrirse en una ventana emergente enfocada (`Open in Window`) para revisar nombrado/organizacion (objetos, materiales, colecciones).
- AI Asset Organizer v2 valida estrictamente la respuesta JSON de IA (IDs completos, unicos y sin omisiones); si la respuesta es parcial o invalida, bloquea el flujo y pide reintento.
- AI Asset Organizer v2 usa un cap dinamico por presupuesto de prompt (ya no limite fijo de 60 por categoria) y mantiene orden estable para resultados reproducibles.
- AI Asset Organizer v2 evita versiones innecesarias de materiales: reutiliza nombres existentes, aplica relink en Apply y limpia huerfanos locales cuando quedan sin usuarios.
- AI Asset Organizer v2 aplica fallback neutral determinista para subpartes ambiguas (por ejemplo Mesh_001) para evitar nombres creativos sin evidencia.
- AI Asset Organizer v2 reconcilia paths de coleccion con matching canonico (normalizado + case-insensitive) para prevenir duplicados por variaciones de nombre.
- El contexto del AI Asset Organizer se usa como gu�a creativa; para materiales, tambi�n puedes pedir simplemente "agrega un tag" y el sistema intentar� inferirlo del objeto (adem�s de soportar override expl�cito como `force tag: Phone` o `fixed tag: Phone`).
- Internamente, AI Asset Organizer v2 est� modularizado en `ops/ai_asset_organizer/*` y usa helpers Blender-agnostic en `core/` para facilitar mantenimiento y testing.
- AI Material Renamer fue retirado de la UI y del runtime; usa AI Asset Organizer como flujo �nico.
- Los controles de debug y reroute masivo se mantienen como herramientas internas y no se muestran en la UI principal para reducir ruido.
- Cuando no existen destinos activos, AI Asset Organizer puede usar un hint de IA v�lido como destino virtual (p. ej. `Props`) para crearlo durante `Organize collections on apply`, sin reactivar colecciones existentes desactivadas.
- AI Asset Organizer v2 incorpora se�ales jer�rquicas (padre/hijo/ra�z y rol de empties) para mejorar sugerencias de naming y organizaci�n sin depender �nicamente de contexto manual.
- La resoluci�n de colecciones aplica guardrails para roles jer�rquicos (`ROOT_CONTROLLER`/`CONTROLLER`) y evita clasificar controladores ra�z en subcategor�as t�cnicas (como `Electronics`) salvo evidencia fuerte.
- Incluye un panel independiente **AI Textures Organizer** con flujo por fases (**Analyze -> Refine -> Apply**) para centralizar texturas en `rsc/Textures`, respetando rutas protegidas externas (Asset Libraries y `XPBR`) y usando `rsc/Textures` en la raiz del proyecto cuando el modo local esta activo.
- Incluye un AI Render Converter para convertir renders a storyboard/sketch con Krea y OpenRouter.
- Mejora la gesti�n visual del AI Render Converter con miniaturas, vista grande y filtros por secci�n.
- Incluye opciones de limpieza de im�genes generadas (eliminaci�n individual y batch con confirmaci�n).
- Permite abrir la carpeta de outputs de la IA y limpiar manifests generados.
- A�ade utilidades pr�cticas de escena (por ejemplo, checks de dimensiones y ayudas de c�mara).
- El panel de Cameras permite agregar Camera Rigs o Simple Cameras dentro del SHOT activo.
- El panel 3D Model Organizer (Lime Toolbox) incluye acciones de Linked Collections (prioriza objetos seleccionados; si no hay candidatos, usa la colección activa de forma recursiva para convertir linked/override a local preservando jerarquías y manteniendo mallas linkeadas).
- La sección Linked Data Localization muestra diagnóstico previo (scope, candidatos y estimaciones) y pide confirmación automática en operaciones grandes.
- La sección Linked Data Localization agrega **Resync Object Materials** para recargar librerías usadas por la selección y volver a sincronizar materiales desde DATA hacia slots en OBJECT (manteniendo edición por instancia).
- En 3D Model Organizer, **Apply Deltas** y el aviso de offsets de locaci�n operan solo sobre objetos seleccionados.

## Requisitos
- Blender 4.5 LTS (objetivo actual del add-on).

## Instalaci�n local (r�pida)
1. Blender > Edit > Preferences > Add-ons > Install...
2. Selecciona el `.zip` del proyecto (o la carpeta que contiene `lime_pipeline`).
3. Activa �Lime Pipeline�.

## API keys (.env)
- Las API keys de OpenRouter y Krea ya no se guardan en preferencias de Blender.
- Se cargan desde un archivo `.env` local en la ra�z del repositorio.
- Variables soportadas:
  - `LIME_OPENROUTER_API_KEY` (o `OPENROUTER_API_KEY`)
  - `LIME_KREA_API_KEY` (o `KREA_API_KEY`)
- Puedes usar `.env.example` como plantilla.

