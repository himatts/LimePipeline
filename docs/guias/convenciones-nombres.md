---
title: Convenciones de nombres
---

# Convenciones de Nombres en Lime Pipeline

Esta guía detalla las convenciones de nomenclatura utilizadas en Lime Pipeline para mantener consistencia en proyectos, archivos y elementos de escena.

## Estructura General de Proyectos

### Nombres de Proyecto
- **Formato**: `^[A-Z]{2}-\d{5}\s+(.+)$`
- **Ejemplos**:
  - `AB-00001 Mi Proyecto`
  - `CD-12345 Animación Corporativa`
  - `EF-99999 Video Publicitario`

### Revisiones
- **Formato**: Una sola letra mayúscula `A–Z`
- **Propósito**: Control de versiones del proyecto
- **Ejemplos**:
  - `Rev A`: Versión inicial
  - `Rev B`: Primera revisión
  - `Rev Z`: Última revisión posible

## Nombres de Archivo

### Archivos de Blender
- **Formato**: `{ProjectName}_{Type}_SC{###}_Rev_{Letter}.blend`
- **Componentes**:
  - `ProjectName`: Nombre del proyecto (ej: `AB-00001 Mi Proyecto`)
  - `Type`: Tipo de archivo (PV, SB, TMP, RAW, ANIM, etc.)
  - `SC{###}`: Número de escena (001-999)
  - `Rev_{Letter}`: Letra de revisión

#### Ejemplos de Nombres de Archivo
```
AB-00001 Mi Proyecto_PV_SC001_Rev_A.blend
AB-00001 Mi Proyecto_SB_SC001_Rev_A.blend
AB-00001 Mi Proyecto_TMP_SC015_Rev_B.blend
AB-00001 Mi Proyecto_RAW_SC030_Rev_C.blend
AB-00001 Mi Proyecto_ANIM_SC045_Rev_A.blend
```

### Tipos de Archivo Comunes

| Tipo | Descripción | Uso |
|------|-------------|-----|
| **PV** | Previsualización | Renders rápidos para revisión |
| **SB** |Storyboard | Bocetos y planificación visual |
| **TMP** | Temporal | Archivos temporales de trabajo |
| **RAW** | Crudo | Archivos sin post-producción |
| **ANIM** | Animación | Archivos con animación completa |
| **REND** | Render Final | Archivos renderizados finales |

## Estructura de Escenas

### Numeración de Escenas
- **Formato**: `SC{###}` donde `###` es 001-999
- **Regla**: Los números de escena deben ser múltiplos de `scene_step` (configurable)
- **Excepción**: Se puede desactivar con `free_scene_numbering`

### Ejemplos de Escenas
```
SC001 - Introducción
SC005 - Desarrollo
SC010 - Clímax
SC015 - Conclusión
```

## Nombres de Materiales

### Sistema MAT (Materiales)
- **Formato**: `MAT_{TagEscena}_{Familia}_{Acabado}_{Version}`
- **Componentes**:
  - `TagEscena`: Identificador de escena (ej: SC001, INTRO)
  - `Familia`: Tipo de material (METAL, PLASTIC, WOOD, etc.)
  - `Acabado`: Acabado específico (MATTE, GLOSSY, RUSTY, etc.)
  - `Version`: Número de versión (V01, V02, etc.)

#### Ejemplos de Materiales
```
MAT_SC001_METAL_RUSTY_V01
MAT_INTRO_PLASTIC_MATTE_V02
MAT_CLIMAX_WOOD_POLISHED_V01
MAT_SC010_FABRIC_DENIM_V03
```

## Estructura de Colecciones (SHOT System)

### SHOT Collections
- **Formato**: `SHOT ###` donde `###` es 001-999
- **Propósito**: Organizar elementos por escena/shot
- **Jerarquía**:
  ```
  SHOT 001
  ├── CAMERAS
  ├── LIGHTS
  ├── PROPS
  └── CHARACTERS
  ```

### Colecciones de Sistema
- **CAMERAS**: Todas las cámaras del shot
- **LIGHTS**: Iluminación específica del shot
- **PROPS**: Objetos y elementos decorativos
- **CHARACTERS**: Personajes y elementos animados

## Nombres de Objetos y Assets

### Cámaras
- **Formato**: `{ShotName}_CAM_{Purpose}_{Index}`
- **Ejemplos**:
  - `SHOT001_CAM_MAIN_01`
  - `SHOT001_CAM_CLOSEUP_01`
  - `SHOT001_CAM_WIDE_02`

### Luces
- **Formato**: `{ShotName}_LIGHT_{Type}_{Purpose}_{Index}`
- **Ejemplos**:
  - `SHOT001_LIGHT_KEY_MAIN_01`
  - `SHOT001_LIGHT_FILL_CHARACTER_01`
  - `SHOT001_LIGHT_RIM_BACKGROUND_02`

### Objetos
- **Formato**: `{AssetName}_{Variant}_{Purpose}_{Index}`
- **Ejemplos**:
  - `Chair_Wood_Dining_01`
  - `Table_Glass_Modern_02`
  - `Character_Hero_Idle_01`

## Convenciones de Render

### Nombres de Output
- **Formato**: `{Project}_{Type}_{SC###}_{Camera}_{Frame}_{Rev}`
- **Ejemplos**:
  - `AB-00001_PV_SC001_Cam01_0001_A.exr`
  - `AB-00001_SB_SC005_Cam02_0120_B.png`
  - `AB-00001_REND_SC010_CamMain_0500_A.exr`

### Layers de Render
- **Base**: Capa principal con iluminación completa
- **Shadow**: Solo sombras
- **AO**: Ambient Occlusion
- **Normal**: Normal map para compositing
- **Depth**: Z-depth para efectos de profundidad

## Configuración y Personalización

### Variables de Configuración
- `scene_step`: Incremento entre números de escena (default: 5)
- `free_scene_numbering`: Permitir numeración libre de escenas
- `project_root_detection`: Detección automática de raíz de proyecto

### Validación Automática
Lime Pipeline valida automáticamente:
- ✅ Formato de nombres de proyecto
- ✅ Numeración de escenas (si no es free)
- ✅ Existencia de directorios requeridos
- ✅ Consistencia de revisiones

## Casos de Uso Comunes

### 1. Nuevo Proyecto
```
1. Crear directorio: AB-00001 Mi Proyecto/
2. Archivo inicial: AB-00001 Mi Proyecto_SB_SC001_Rev_A.blend
3. Primera escena: SHOT 001
4. Material inicial: MAT_SC001_BASIC_DEFAULT_V01
```

### 2. Iteración de Revisión
```
Archivo anterior: Project_SB_SC001_Rev_A.blend
Nueva revisión: Project_SB_SC001_Rev_B.blend
(Incrementar letra de revisión)
```

### 3. Multiples Escenas
```
SC001 - Opening
SC005 - Dialogue Scene A
SC010 - Action Sequence
SC015 - Closing
```

## Troubleshooting de Nombres

### Errores Comunes
- **Proyecto sin formato válido**: Asegurarse de formato `XX-##### Nombre`
- **Escena no múltiplo**: Verificar configuración de `scene_step`
- **Revisión inválida**: Solo letras A-Z mayúsculas
- **Material mal formado**: Seguir esquema `MAT_{Tag}_{Familia}_{Acabado}_{V##}`

### Validación Manual
Usar las herramientas de validación en el panel de **Stage Setup** para verificar conformidad con las convenciones.
