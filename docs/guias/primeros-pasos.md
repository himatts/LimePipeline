---
title: Primeros Pasos
---

# Primeros Pasos con Lime Pipeline

Lime Pipeline es un add-on para Blender orientado a estandarizar estructura y naming. Esta guía te ayuda a instalarlo y crear tu primer archivo con las convenciones del pipeline.

## Requisitos
- **Blender 4.5 LTS**.
- Conexión a internet solo si usarás funciones de IA.

## Instalación
1. En Blender: `Edit > Preferences > Add-ons > Install...`.
2. Selecciona el ZIP del proyecto (o la carpeta que contiene `lime_pipeline`).
3. Activa “Lime Pipeline”.

## Configuración inicial (primer archivo)
1. Abre Blender y ve a `View3D > Sidebar (N) > Lime Pipeline`.
2. En el panel **Project Organization** configura root, tipo, revisión y escena.
3. En el panel **Stage** crea el archivo con “Create File”.
4. En el panel **Shots** crea tu primer SHOT.

## Estructura esperada
Después de crear un SHOT verás una jerarquía similar a:
```
Scene Collection
└─ SHOT 001
   ├─ CAMERAS
   ├─ LIGHTS
   ├─ PROPS
   └─ CHARACTERS
```

## Cámaras y márgenes
1. Ve al panel **Cameras**.
2. Usa “Add Camera Rig” para crear una cámara con márgenes automáticos.
3. Ajusta opacidad/guías en el mismo panel.

## Render básico
1. Ve a **Render Configs** y aplica un preset.
2. Usa “Render” desde el panel de cámaras si necesitas un output rápido.

## Materiales con IA (opcional)
1. Configura la API key en preferencias.
2. En **AI Asset Organizer** usa `Suggest Names (AI)`.
3. Ajusta `Apply Scope` a **Only Materials** y luego usa `Apply Selected`.
4. Usa `Test Connection` desde preferencias para validar OpenRouter en el flujo de AI Asset Organizer.

## Próximos pasos
- Revisa **Convenciones de nombres** para reglas de naming.
- Explora **Flujos típicos** para procesos completos.
- Si vas a contribuir, revisa `CONTRIBUTING.md` en la raiz del repositorio.
