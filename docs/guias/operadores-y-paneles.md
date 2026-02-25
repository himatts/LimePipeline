---
title: Operadores y Paneles
---

# Operadores y Paneles

Esta gu�a documenta todos los operadores y paneles disponibles en Lime Pipeline, organizados por funcionalidad.

## Paneles de UI

| Panel | ID | Espacio | Categor�a | Prop�sito |
|-------|----|---------|-----------|-----------|
| **Stage** | `LIME_PT_stage_setup` | 3D View | Lime | Configuraci�n inicial de escena y proyecto |
| **Shots** | `LIME_PT_shots` | 3D View | Lime | Gesti�n de SHOT collections y organizaci�n |
| **Render Configs** | `LIME_PT_render_configs` | 3D View | Lime | Presets de render y configuraciones |
| **Project Organization** | `LIME_PT_project_org` | 3D View | Lime | Organizaci�n de archivos y carpetas |
| **Model Organizer** | `LIME_PT_model_organizer` | 3D View | Lime | Organizaci�n de modelos y grupos |
| **Animation Parameters** | `LIME_TB_PT_animation_params` | 3D View | Lime | Par�metros de animaci�n y keyframes |
| **Alpha Manager** | `LIME_TB_PT_alpha_manager` | 3D View | Lime | Gesti�n de transparencias y alpha |
| **Cameras** | `LIME_PT_render_cameras` | 3D View | Lime | Gesti�n de c�maras y rigs |
| **Save As** | `LIME_PT_image_save_as` | Image Editor | Lime | Guardado avanzado de im�genes |
| **AI Asset Organizer** | `LIME_TB_PT_ai_asset_organizer` | 3D View | Lime | Nombres IA para objetos/materiales/colecciones |
| **AI Textures Organizer** | `LIME_TB_PT_ai_textures_organizer` | 3D View | Lime | Flujo por fases para analisis/refine/apply de texturas |
| **Dimension Utilities** | `LIME_PT_dimension_utilities` | 3D View | Lime | Utilidades de dimensiones y unidades |
| **Noisy Movement** | `LIME_TB_PT_noisy_movement` | 3D View | Lime | Movimiento procedural con ruido |

## Operadores Principales

### Gesti�n de Proyecto
| Operador | ID | Archivo | Prop�sito |
|----------|----|---------|-----------|
| **Create File** | `lime.create_file` | `ops_create_file.py` | Crear nuevo archivo con estructura Lime |
| **Save as Template** | `lime.save_as_with_template` | `ops_save_templates.py` | Guardar con plantilla normalizada |
| **Save as RAW** | `lime.save_as_with_template_raw` | `ops_save_templates.py` | Guardar versi�n RAW para post-producci�n |
| **Create Backup** | `lime.create_backup` | `ops_backup.py` | Crear backup del archivo actual |

### Gesti�n de Shots
| Operador | ID | Archivo | Prop�sito |
|----------|----|---------|-----------|
| **New Shot** | `lime.new_shot` | `ops_shots.py` | Crear nueva colecci�n SHOT |
| **Delete Shot** | `lime.delete_shot` | `ops_shots.py` | Eliminar SHOT seleccionado |
| **Duplicate Shot** | `lime.duplicate_shot` | `ops_shots.py` | Duplicar SHOT con estructura |
| **Activate Shot** | `lime.activate_shot` | `ops_shots.py` | Activar SHOT en viewport |

### C�maras y Rigs
| Operador | ID | Archivo | Prop�sito |
|----------|----|---------|-----------|
| **Add Camera Rig** | `lime.add_camera_rig` | `ops_cameras.py` | Crear rig de c�mara con m�rgenes |
| **Duplicate Camera** | `lime.duplicate_active_camera` | `ops_cameras.py` | Duplicar c�mara/rig activo y asignar nuevo �ndice al final |
| **Reorganize Camera Names** | `lime.rename_shot_cameras` | `ops_cameras.py` | Renombrar c�maras seg�n el orden actual de la lista en el panel |
| **Move Camera List Item** | `lime.move_camera_list_item` | `ops_cameras.py` | Subir o bajar la c�mara seleccionada en la lista del panel |
| **Set Active Camera** | `lime.set_active_camera` | `ops_cameras.py` | Establecer c�mara activa |
| **Auto Camera Background** | `lime.auto_camera_background` | `ops_auto_camera_bg.py` | Generar background autom�tico |
| **Sync Camera List** | `lime.sync_camera_list` | `ops_cameras.py` | Refrescar lista sin renombrar autom�ticamente |

Nota de uso (solo panel Cameras): `Ctrl+Click` sobre el nombre de una c�mara en la lista activa la c�mara y, si tiene marcador de timeline asignado, salta al frame de ese marcador.

### Materiales e IA
| Operador | ID | Archivo | Prop�sito |
|----------|----|---------|-----------|
| **AI Asset Suggest Names** | `lime_tb.ai_asset_suggest_names` | `ops_ai_asset_organizer.py` | Sugerir nombres para la selecci�n |
| **AI Asset Apply Names** | `lime_tb.ai_asset_apply_names` | `ops_ai_asset_organizer.py` | Aplicar cambios seleccionados |
| **AI Test Connection** | `lime_tb.ai_asset_test_connection` | `ops_ai_asset_organizer.py` | Test OpenRouter para flujos IA |

### Utilidades de Modelo
| Operador | ID | Archivo | Prop�sito |
|----------|----|---------|-----------|
| **Group Selection Empty** | `lime.group_selection_empty` | `ops_model_organizer.py` | Crear grupo vac�o de selecci�n |
| **Move Controller** | `lime.move_controller` | `ops_model_organizer.py` | Mover controlador de grupo |
| **Apply Scene Deltas** | `lime.apply_scene_deltas` | `ops_model_organizer.py` | Aplicar deltas de transformaci�n solo sobre la selecci�n |
| **Colorize Parent Groups** | `lime.colorize_parent_groups` | `ops_model_organizer.py` | Colorear grupos padre |
| **Resync Object Materials** | `lime.resync_object_materials_from_data` | `ops_linked_collections.py` | Recargar librerias usadas y resincronizar materiales DATA->OBJECT en seleccion elegible |
### Render y Presets
| Operador | ID | Archivo | Prop�sito |
|----------|----|---------|-----------|
| **Save Render Preset** | `lime.render_preset_save` | `ops_render_presets.py` | Guardar preset de render |
| **Apply Render Preset** | `lime.render_preset_apply` | `ops_render_presets.py` | Aplicar preset guardado |
| **Render Invoke** | `lime.render_invoke` | `ops_cameras.py` | Invocar render con configuraci�n |

### Alpha y Transparencias
| Operador | ID | Archivo | Prop�sito |
|----------|----|---------|-----------|
| **Add Alpha Event** | `lime.tb_alpha_event_add` | `ops_alpha_manager.py` | Agregar evento de alpha |
| **Alpha Set Mode** | `lime.tb_alpha_set_mode` | `ops_alpha_manager.py` | Configurar modo de alpha |
| **Apply Object Alpha Mix** | `lime.apply_object_alpha_mix` | `ops_material_alpha_mix.py` | Aplicar mezcla de alpha |

### Movimiento y Animaci�n
| Operador | ID | Archivo | Prop�sito |
|----------|----|---------|-----------|
| **Apply Keyframe Style** | `lime.tb_apply_keyframe_style` | `ops_animation_params.py` | Aplicar estilo de keyframes |
| **Add Noise Profile** | `lime.tb_noise_add_profile` | `ops_noise.py` | Agregar perfil de ruido |
| **Noise Apply to Selected** | `lime.tb_noise_apply_to_selected` | `ops_noise.py` | Aplicar ruido a selecci�n |

### Utilidades Generales
| Operador | ID | Archivo | Prop�sito |
|----------|----|---------|-----------|
| **Pick Root** | `lime.pick_root` | `ops_select_root.py` | Seleccionar objeto ra�z |
| **Show Text** | `lime.show_text` | `ops_tooltips.py` | Mostrar texto emergente |
| **Clean Step** | `lime.clean_step` | `ops_step_clean.py` | Limpiar paso de trabajo |
| **Dimension Envelope** | `lime.dimension_envelope` | `ops_dimensions.py` | Configurar sobre de dimensi�n |
| **Ensure Folders** | `lime.ensure_folders` | `ops_folders.py` | Crear estructura de carpetas |

## Listas y UI Lists

| Componente | ID | Archivo | Prop�sito |
|------------|----|---------|-----------|
| **Shots List** | `LIME_UL_shots` | `ui_shots.py` | Lista de SHOT collections |
| **Cameras List** | `LIME_UL_render_cameras` | `ui_cameras_manager.py` | Lista de c�maras |
| **Alpha Events List** | `LIME_TB_UL_alpha_events` | `ui_alpha_manager.py` | Lista de eventos alpha |
| **AI Asset Items List** | `LIME_TB_UL_ai_asset_items` | `ui_ai_asset_organizer.py` | Lista unificada de propuestas IA |
| **Noise Names List** | `LIME_TB_UL_noise_names` | `ui_noise_movement.py` | Lista de perfiles de ruido |
| **Noise Objects List** | `LIME_TB_UL_noise_objects` | `ui_noise_movement.py` | Lista de objetos con ruido |

## Convenciones de Nombres

- **Prefijo**: Todos los operadores usan `lime.` o `lime.tb.` para evitar conflictos
- **Categorizaci�n**: `.tb.` indica herramientas de toolbar, sin prefijo para operadores generales
- **Paneles**: `LIME_PT_` para paneles, `LIME_TB_PT_` para paneles de toolbar
- **Listas**: `LIME_UL_` para UI Lists
- **Operadores**: `LIME_TB_OT_` para clases (convenci�n interna)

> **Nota**: Esta documentaci�n se mantiene actualizada manualmente. Para regenerar autom�ticamente desde el c�digo fuente, ejecutar `python tools/generate_catalog.py --full`.




