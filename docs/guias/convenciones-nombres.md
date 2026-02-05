---
title: Convenciones de nombres
---

# Convenciones de nombres en Lime Pipeline

Esta guia resume las convenciones de nombres vigentes en el codigo para proyectos, archivos, SHOTs, materiales y outputs.

## Estructura general de proyectos

### Raiz de proyecto
- Formato de carpeta: `^[A-Z]{2}-\d{5}\s+(.+)$`
- Ejemplos: `AB-00001 Mi Proyecto`, `CD-12345 Animacion Corporativa`

### ProjectName normalizado (para nombres de archivo)
- Se elimina el prefijo `XX-#####`.
- Se quitan diacriticos y caracteres reservados de Windows.
- Se colapsan espacios y se concatena en CamelCase.
- Ejemplo: carpeta `AB-00001 Mi Proyecto` -> `MiProyecto`.

### Revisiones
- Formato: una sola letra mayuscula `A-Z`.

## Nombres de archivo

### Archivos .blend
- Con SC: `{ProjectName}_{Token}_SC{###}_Rev_{Letter}.blend`
- Sin SC (solo BASE y TMP): `{ProjectName}_{Token}_Rev_{Letter}.blend`

### Tokens por tipo
| Tipo | Token en filename | Requiere SC |
|------|-------------------|-------------|
| BASE | BaseModel         | No          |
| PV   | PV                | Si          |
| REND | Render            | Si          |
| SB   | SB                | Si          |
| ANIM | Anim              | Si          |
| TMP  | Tmp               | No          |

### Ejemplos .blend
```
MiProyecto_PV_SC001_Rev_A.blend
MiProyecto_Render_SC010_Rev_B.blend
MiProyecto_Anim_SC020_Rev_A.blend
MiProyecto_BaseModel_Rev_A.blend
MiProyecto_Tmp_Rev_C.blend
```

## Estructura de escenas

### Numeracion de escenas
- Formato: `SC{###}` donde `###` es 001-999.
- Regla: si `free_scene_numbering` es false, SC debe ser multiplo de `scene_step`.

## Nombres de materiales

### Sistema MAT
- Formato: `MAT_{SceneTag?}_{MaterialType}_{Finish}_{V##}`
- `SceneTag` es opcional.
- `MaterialType` permitido:
  `Plastic, Metal, Glass, Rubber, Silicone, Background, Paint, Wood, Fabric, Ceramic, Emissive, Stone, Concrete, Paper, Leather, Liquid, Organic, Tissue, Tooth, Text`
- `Finish` es alfanumerico CamelCase (sin espacios ni caracteres especiales).
- Maximo 64 caracteres y sin sufijos `.001`.

### Ejemplos
```
MAT_SC001_Metal_Rusty_V01
MAT_Intro_Plastic_Matte_V02
MAT_Wood_Polished_V01
```

## Estructura de colecciones (SHOT system)

### SHOT root
- Formato: `SHOT 01` o `SHOT 001` (2-3 digitos).

### Arbol estandar
```
SHOT 01
|-- SH01_00_CAM
|-- SH01_00_LIGHTS
|-- SH01_01_{ProjectName}_MAIN
|-- SH01_02_PROPS
`-- SH01_90_BG
```

### Colecciones de assets (AI Asset Organizer v2)
- Formato recomendado: CamelCase alfanumerico (sin espacios, guiones, puntos ni guion bajo).
- Evitar prefijos de SHOT para colecciones de assets reutilizables.
- Nombres de categoria sugeridos por reglas seguras:
  - `Lights`
  - `Cameras`
- Agrupaciones automaticas de assets usan la clave inicial CamelCase del nombre de objeto (ejemplo: `CarBody`, `CarWheel` -> `Car`).

## Camaras y rigs

- Camara: `SHOT_##_CAMERA_{N}`
- Camera Data: `SHOT_##_CAMERA_{N}.Data`
- Rig Armature: `CAM_RIG_SH##_{N}` (o `CAM_RIG_SH###_{N}` si SHOT >= 100)

## Nombres de texturas (AI Asset Organizer v2)

- Formato objetivo al copiar/relinkear texturas afectadas:
  - `TX_{MaterialStem}_{MapType}_{NN}.{ext}`
- `MaterialStem`: nombre de material final sin prefijo `MAT_` ni sufijo `_V##`.
- `MapType`: inferido por nodos/sockets (por ejemplo `BaseColor`, `Normal`, `Roughness`, `Metallic`, `Alpha`, `Height`, `Emission`, `AO`, `Generic`).
- El sistema evita duplicar copias para el mismo archivo origen y relinkea rutas relativas cuando es posible.

## Outputs de render

### Save Templates (imagenes)
- REND: `Project_Render_SC###_SH##C{cam}_Rev_{rev}.png`
- PV: `Project_PV_SC###_SH##C{cam}_Rev_{rev}.png`
- SB: `Project_SB_SC###_Rev_{rev}.png`
- TMP: `Project_TMP_SC###_Rev_{rev}.png`
- Sufijos opcionales antes de `Rev`: `V##` y/o `{Descriptor}` (descriptor normalizado).

Ejemplo con sufijos:
```
MiProyecto_Render_SC005_SH02C1_V02_Test_Rev_B.png
```

### RAW
- Prefijo `RAW_` y carpeta `editables/RAW/`.
- Ejemplos:
```
RAW_MiProyecto_Render_SC005_SH02C1_Rev_B.png
RAW_MiProyecto_PV_SC005_SH02C1_Rev_B.png
RAW_MiProyecto_SB_SC005_Rev_B.png
```
- Render RAW desde marcadores usa este orden:
  `RAW_{Project}_Render_SH##C{cam}_SC{sc}_Rev_{rev}.png`

### AI Render Converter
- Source: `Project_Render_SC###_SH##C{cam}_F####_Rev_{rev}.png`
- Output stem: `Project_SB_SC###_SH##C{cam}_F####_{ModeToken}`
- Output file: `..._Rev_{rev}.png` o `..._V##_Rev_{rev}.png`
- Si hay multiples outputs: `..._Rev_{rev}_NN.png`
- Manifest: `..._AI_manifest.json`

### Animacion
- Carpeta RAMV: `Animation/Rev X/SC###_SH##/`
- Si el contenedor es REND: `Renders/Rev X/SC###_SH##/`
- Test: subcarpeta `test/`
- Prefijo de salida: `SC###_SH##_` o `SC###_SH##_test_` (Blender agrega `####`)
- Local: `Desktop/<ProjectName>/SC###_SH##/` (mismo esquema)

## Backups

- Nombre: `Backup_XX_{filename}` en la carpeta `backups/` del tipo y revision.

## Validacion automatica

Lime Pipeline valida:
- Raiz de proyecto con el formato `XX-##### Nombre`.
- Revision con una letra `A-Z`.
- SC en rango 001-999 y multiplo de `scene_step` cuando aplica.
- Existencia de directorios criticos y colisiones de nombre.
- Longitud maxima de ruta segun preferencias.

## Casos de uso comunes

### 1. Nuevo proyecto
```
1. Crear directorio: AB-00001 Mi Proyecto/
2. Archivo inicial: MiProyecto_SB_SC001_Rev_A.blend
3. Primera escena: SHOT 01
4. Material inicial: MAT_SC001_Plastic_Generic_V01
```

### 2. Iteracion de revision
```
Archivo anterior: MiProyecto_SB_SC001_Rev_A.blend
Nueva revision:    MiProyecto_SB_SC001_Rev_B.blend
```

### 3. Multiples escenas
```
SC001 - Opening
SC005 - Dialogue Scene A
SC010 - Action Sequence
SC015 - Closing
```

## Troubleshooting de nombres

### Errores comunes
- Proyecto sin formato valido: usar `XX-##### Nombre`.
- SC no multiplo: revisar `scene_step` o activar `free_scene_numbering`.
- Revision invalida: una sola letra `A-Z`.
- Material mal formado: `MAT_{SceneTag?}_{MaterialType}_{Finish}_{V##}`.
- ProjectName distinto a la carpeta: es normal por la normalizacion.

### Validacion manual
Usa el panel de Project Organization / Stage Setup para ejecutar validaciones antes de guardar o renderizar.
