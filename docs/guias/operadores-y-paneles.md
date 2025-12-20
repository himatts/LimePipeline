---
title: Operadores y Paneles
---

# Operadores y Paneles

Esta guía documenta todos los operadores y paneles disponibles en Lime Pipeline, organizados por funcionalidad.

## Paneles de UI

| Panel | ID | Espacio | Categoría | Propósito |
|-------|----|---------|-----------|-----------|
| **Stage** | `LIME_PT_stage_setup` | 3D View | Lime | Configuración inicial de escena y proyecto |
| **Shots** | `LIME_PT_shots` | 3D View | Lime | Gestión de SHOT collections y organización |
| **Render Configs** | `LIME_PT_render_configs` | 3D View | Lime | Presets de render y configuraciones |
| **Project Organization** | `LIME_PT_project_org` | 3D View | Lime | Organización de archivos y carpetas |
| **Model Organizer** | `LIME_PT_model_organizer` | 3D View | Lime | Organización de modelos y grupos |
| **Animation Parameters** | `LIME_TB_PT_animation_params` | 3D View | Lime | Parámetros de animación y keyframes |
| **Alpha Manager** | `LIME_TB_PT_alpha_manager` | 3D View | Lime | Gestión de transparencias y alpha |
| **Cameras** | `LIME_PT_render_cameras` | 3D View | Lime | Gestión de cámaras y rigs |
| **Save As** | `LIME_PT_image_save_as` | Image Editor | Lime | Guardado avanzado de imágenes |
| **AI Material Renamer** | `LIME_TB_PT_ai_material_renamer` | 3D View | Lime | Renombrado inteligente de materiales |
| **Dimension Utilities** | `LIME_PT_dimension_utilities` | 3D View | Lime | Utilidades de dimensiones y unidades |
| **Noisy Movement** | `LIME_TB_PT_noisy_movement` | 3D View | Lime | Movimiento procedural con ruido |

## Operadores Principales

### Gestión de Proyecto
| Operador | ID | Archivo | Propósito |
|----------|----|---------|-----------|
| **Create File** | `lime.create_file` | `ops_create_file.py` | Crear nuevo archivo con estructura Lime |
| **Save as Template** | `lime.save_as_with_template` | `ops_save_templates.py` | Guardar con plantilla normalizada |
| **Save as RAW** | `lime.save_as_with_template_raw` | `ops_save_templates.py` | Guardar versión RAW para post-producción |
| **Create Backup** | `lime.create_backup` | `ops_backup.py` | Crear backup del archivo actual |

### Gestión de Shots
| Operador | ID | Archivo | Propósito |
|----------|----|---------|-----------|
| **New Shot** | `lime.new_shot` | `ops_shots.py` | Crear nueva colección SHOT |
| **Delete Shot** | `lime.delete_shot` | `ops_shots.py` | Eliminar SHOT seleccionado |
| **Duplicate Shot** | `lime.duplicate_shot` | `ops_shots.py` | Duplicar SHOT con estructura |
| **Activate Shot** | `lime.activate_shot` | `ops_shots.py` | Activar SHOT en viewport |

### Cámaras y Rigs
| Operador | ID | Archivo | Propósito |
|----------|----|---------|-----------|
| **Add Camera Rig** | `lime.add_camera_rig` | `ops_cameras.py` | Crear rig de cámara con márgenes |
| **Set Active Camera** | `lime.set_active_camera` | `ops_cameras.py` | Establecer cámara activa |
| **Auto Camera Background** | `lime.auto_camera_background` | `ops_auto_camera_bg.py` | Generar background automático |
| **Sync Camera List** | `lime.sync_camera_list` | `ops_cameras.py` | Sincronizar lista de cámaras |

### Materiales e IA
| Operador | ID | Archivo | Propósito |
|----------|----|---------|-----------|
| **AI Test Connection** | `lime_tb.ai_test_connection` | `ops_ai_material_renamer.py` | Verificar conexión con IA |
| **AI Scan Materials** | `lime_tb.ai_scan_materials` | `ops_ai_material_renamer.py` | Escanear materiales del proyecto |
| **AI Apply Materials** | `lime_tb.ai_apply_materials` | `ops_ai_material_renamer.py` | Aplicar renombrado inteligente |
| **AI Rename Single** | `lime_tb.ai_rename_single` | `ops_ai_material_renamer.py` | Renombrar material individual |

### Utilidades de Modelo
| Operador | ID | Archivo | Propósito |
|----------|----|---------|-----------|
| **Group Selection Empty** | `lime.group_selection_empty` | `ops_model_organizer.py` | Crear grupo vacío de selección |
| **Move Controller** | `lime.move_controller` | `ops_model_organizer.py` | Mover controlador de grupo |
| **Apply Scene Deltas** | `lime.apply_scene_deltas` | `ops_model_organizer.py` | Aplicar deltas de transformación |
| **Colorize Parent Groups** | `lime.colorize_parent_groups` | `ops_model_organizer.py` | Colorear grupos padre |

### Render y Presets
| Operador | ID | Archivo | Propósito |
|----------|----|---------|-----------|
| **Save Render Preset** | `lime.render_preset_save` | `ops_render_presets.py` | Guardar preset de render |
| **Apply Render Preset** | `lime.render_preset_apply` | `ops_render_presets.py` | Aplicar preset guardado |
| **Render Invoke** | `lime.render_invoke` | `ops_cameras.py` | Invocar render con configuración |

### Alpha y Transparencias
| Operador | ID | Archivo | Propósito |
|----------|----|---------|-----------|
| **Add Alpha Event** | `lime.tb_alpha_event_add` | `ops_alpha_manager.py` | Agregar evento de alpha |
| **Alpha Set Mode** | `lime.tb_alpha_set_mode` | `ops_alpha_manager.py` | Configurar modo de alpha |
| **Apply Object Alpha Mix** | `lime.apply_object_alpha_mix` | `ops_material_alpha_mix.py` | Aplicar mezcla de alpha |

### Movimiento y Animación
| Operador | ID | Archivo | Propósito |
|----------|----|---------|-----------|
| **Apply Keyframe Style** | `lime.tb_apply_keyframe_style` | `ops_animation_params.py` | Aplicar estilo de keyframes |
| **Add Noise Profile** | `lime.tb_noise_add_profile` | `ops_noise.py` | Agregar perfil de ruido |
| **Noise Apply to Selected** | `lime.tb_noise_apply_to_selected` | `ops_noise.py` | Aplicar ruido a selección |

### Utilidades Generales
| Operador | ID | Archivo | Propósito |
|----------|----|---------|-----------|
| **Pick Root** | `lime.pick_root` | `ops_select_root.py` | Seleccionar objeto raíz |
| **Show Text** | `lime.show_text` | `ops_tooltips.py` | Mostrar texto emergente |
| **Clean Step** | `lime.clean_step` | `ops_step_clean.py` | Limpiar paso de trabajo |
| **Dimension Envelope** | `lime.dimension_envelope` | `ops_dimensions.py` | Configurar sobre de dimensión |
| **Ensure Folders** | `lime.ensure_folders` | `ops_folders.py` | Crear estructura de carpetas |

## Listas y UI Lists

| Componente | ID | Archivo | Propósito |
|------------|----|---------|-----------|
| **Shots List** | `LIME_UL_shots` | `ui_shots.py` | Lista de SHOT collections |
| **Cameras List** | `LIME_UL_render_cameras` | `ui_cameras_manager.py` | Lista de cámaras |
| **Alpha Events List** | `LIME_TB_UL_alpha_events` | `ui_alpha_manager.py` | Lista de eventos alpha |
| **AI Materials List** | `LIME_TB_UL_ai_mat_rows` | `ui_ai_material_renamer.py` | Lista de materiales IA |
| **Noise Names List** | `LIME_TB_UL_noise_names` | `ui_noise_movement.py` | Lista de perfiles de ruido |
| **Noise Objects List** | `LIME_TB_UL_noise_objects` | `ui_noise_movement.py` | Lista de objetos con ruido |

## Convenciones de Nombres

- **Prefijo**: Todos los operadores usan `lime.` o `lime.tb.` para evitar conflictos
- **Categorización**: `.tb.` indica herramientas de toolbar, sin prefijo para operadores generales
- **Paneles**: `LIME_PT_` para paneles, `LIME_TB_PT_` para paneles de toolbar
- **Listas**: `LIME_UL_` para UI Lists
- **Operadores**: `LIME_TB_OT_` para clases (convención interna)

> **Nota**: Esta documentación se mantiene actualizada manualmente. Para regenerar automáticamente desde el código fuente, ejecutar `python tools/generate_catalog.py --full`.


