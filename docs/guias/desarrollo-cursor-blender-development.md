---
title: Desarrollo (Cursor + Blender Development)
---

# Desarrollo con Cursor + Blender Development

Este add-on se desarrolla principalmente desde el IDE **Cursor** usando un “puente” hacia Blender para probar cambios continuamente.

## Extensión recomendada
Usa la extensión **Blender Development** (Jacques Lucke) — *Tools to simplify Blender development*.

Su objetivo es reducir el “ciclo de feedback” entre editar código y probarlo en Blender.

## Qué aporta (features típicas)
- Lanzar Blender desde el IDE con un entorno de desarrollo.
- Ejecutar scripts directamente en Blender desde el editor.
- Recargar el add-on / recargar scripts sin reinstalar manualmente.
- Enviar comandos a Blender y ver salida/logs rápidamente.

## Comandos (cómo encontrarlos)
Los nombres exactos pueden variar por versión, pero normalmente aparecen en la **Command Palette** (Cursor/VS Code) buscando `Blender:`.

Comandos típicos que vas a usar a diario:
- **Start/Launch Blender**: inicia Blender desde el IDE.
- **Run Script / Run Current File**: ejecuta el archivo actual en Blender.
- **Reload Addons / Reload Addon**: recarga el add-on para reflejar cambios.
- **Open/Attach Console / View Logs**: ver logs y errores con menos fricción.

## Flujo de trabajo recomendado
1. Inicia Blender desde el IDE con Blender Development.
2. Instala/habilita Lime Pipeline una vez (si no está instalado).
3. Ciclo corto (iteración):
   - Edita código.
   - Recarga el add-on (o ejecuta el script actual) desde la Command Palette.
   - Prueba en Blender y observa la salida/errores.
4. Ciclo largo (cambios grandes):
   - Reabre el archivo `.blend` objetivo.
   - Valida flujos principales (Project Organization, Shots, Cameras, Render Configs, AI Material Renamer).

## Buenas prácticas al iterar
- Mantén la lógica reusable en `core/` y usa recargas para validar invariantes.
- Evita IO en `draw()`; los errores de UI se “sienten” inmediatamente al recargar.
- Prefiere errores claros con `self.report(...)` en operadores (feedback inmediato en Blender).

## Relación con pruebas automatizadas
En este proyecto, la validación principal durante desarrollo es **manual en Blender** usando Blender Development.
Los tests existentes (si los hay) se enfocan en lógica “core” sin Blender, pero **no se deben crear tests nuevos** salvo solicitud explícita.
