#!/usr/bin/env python3
"""
Script de prueba para verificar la funcionalidad de force reanalysis
"""

import bpy
import sys
import os

# Agregar el directorio del addon al path
sys.path.append(os.path.dirname(__file__))

def test_force_reanalysis():
    """Prueba la funcionalidad de force reanalysis"""

    # Crear materiales de prueba
    materials = []

    # Material correctamente nombrado (usando taxonomía básica)
    mat1 = bpy.data.materials.new("MAT_Plastic_Generic_V01")
    materials.append(mat1)

    # Material mal nombrado
    mat2 = bpy.data.materials.new("BadMaterialName")
    materials.append(mat2)

    # Material correctamente nombrado pero queremos reconsiderar
    mat3 = bpy.data.materials.new("MAT_Metal_Brushed_V01")
    materials.append(mat3)

    print(f"Materiales creados: {[m.name for m in materials]}")

    # Obtener acceso al estado de AI Material
    scene = bpy.context.scene
    if not hasattr(scene, 'lime_ai_mat'):
        print("ERROR: No se encontró lime_ai_mat en la escena")
        return False

    state = scene.lime_ai_mat

    # Probar modo normal (solo materiales mal nombrados)
    print("\n=== PRUEBA MODO NORMAL ===")
    state.force_reanalysis = False

    # Simular escaneo (en lugar de llamar al operador real)
    from lime_pipeline.ops.ops_ai_material_renamer import _write_rows

    # Datos simulados para materiales mal nombrados
    test_items_normal = [
        {
            "material_name": "BadMaterialName",
            "proposed_name": "MAT_Plastic_Generic_V02",
            "material_type": "Plastic",
            "finish": "Generic",
            "version_token": "V02",
            "read_only": False,
            "needs_rename": True,
            "confidence": 0.8,
            "is_indexed": True,
            "notes": "Improved naming"
        }
    ]

    _write_rows(scene, test_items_normal, incorrect_count=1, total_count=3)
    print(f"Filas en modo normal: {len(state.rows)}")
    print(f"Materiales seleccionados: {[r.material_name for r in state.rows if r.selected_for_apply]}")

    # Probar modo force reanalysis (todos los materiales)
    print("\n=== PRUEBA MODO FORCE REANALYSIS ===")
    state.force_reanalysis = True

    # Limpiar filas anteriores
    state.rows.clear()

    # Datos simulados para todos los materiales
    test_items_force = [
        {
            "material_name": "MAT_Plastic_Generic_V01",
            "proposed_name": "MAT_Plastic_Smooth_V01",
            "material_type": "Plastic",
            "finish": "Smooth",
            "version_token": "V01",
            "read_only": False,
            "needs_rename": False,
            "confidence": 0.9,
            "is_indexed": True,
            "notes": "Reconsidered naming"
        },
        {
            "material_name": "BadMaterialName",
            "proposed_name": "MAT_Plastic_Generic_V02",
            "material_type": "Plastic",
            "finish": "Generic",
            "version_token": "V02",
            "read_only": False,
            "needs_rename": True,
            "confidence": 0.8,
            "is_indexed": True,
            "notes": "Improved naming"
        },
        {
            "material_name": "MAT_Metal_Brushed_V01",
            "proposed_name": "MAT_Metal_Polished_V01",
            "material_type": "Metal",
            "finish": "Polished",
            "version_token": "V01",
            "read_only": False,
            "needs_rename": False,
            "confidence": 0.85,
            "is_indexed": True,
            "notes": "Better finish match"
        }
    ]

    _write_rows(scene, test_items_force, incorrect_count=3, total_count=3)
    print(f"Filas en modo force reanalysis: {len(state.rows)}")
    print(f"Materiales seleccionados: {[r.material_name for r in state.rows if r.selected_for_apply]}")

    # Verificar que todos los materiales están incluidos
    material_names = [r.material_name for r in state.rows]
    expected_names = ["MAT_Plastic_Generic_V01", "BadMaterialName", "MAT_Metal_Brushed_V01"]

    if set(material_names) == set(expected_names):
        print("✅ Todos los materiales incluidos correctamente en force reanalysis")
    else:
        print(f"❌ Error: materiales esperados {expected_names}, obtenidos {material_names}")
        return False

    # Verificar que todos están seleccionados (porque force_reanalysis=True)
    selected_count = sum(1 for r in state.rows if r.selected_for_apply)
    if selected_count == 3:
        print("✅ Todos los materiales seleccionados correctamente en force reanalysis")
    else:
        print(f"❌ Error: esperados 3 seleccionados, obtenidos {selected_count}")
        return False

    print("\n=== PRUEBA DE OPERADORES ===")

    # Probar operador Keep en material re-analizado
    from lime_pipeline.ops.ops_ai_material_renamer import LIME_TB_OT_ai_keep_proposal

    # Crear operador y probar
    keep_op = LIME_TB_OT_ai_keep_proposal()
    keep_op.material_name = "MAT_Plastic_Generic_V01"

    # Verificar estado antes
    target_row = next(r for r in state.rows if r.material_name == "MAT_Plastic_Generic_V01")
    print(f"Estado inicial - is_normalized: {target_row.is_normalized}")
    print(f"Estado inicial - proposed_name: {target_row.proposed_name}")
    print(f"Estado inicial - original_proposal: {target_row.original_proposal}")

    # Ejecutar Keep (debería mantener la propuesta actual ya que no está normalizada)
    result = keep_op.execute(bpy.context)
    print(f"Resultado de Keep: {result}")

    # Verificar estado después
    print(f"Estado después - is_normalized: {target_row.is_normalized}")
    print(f"Estado después - proposed_name: {target_row.proposed_name}")

    # Probar operador Normalize
    from lime_pipeline.ops.ops_ai_material_renamer import LIME_TB_OT_ai_normalize_to_closest

    normalize_op = LIME_TB_OT_ai_normalize_to_closest()
    normalize_op.material_name = "MAT_Plastic_Generic_V01"

    result = normalize_op.execute(bpy.context)
    print(f"Resultado de Normalize: {result}")

    # Verificar estado después de normalización
    print(f"Estado después de normalización - is_normalized: {target_row.is_normalized}")
    print(f"Estado después de normalización - proposed_name: {target_row.proposed_name}")
    print(f"Estado después de normalización - original_proposal: {target_row.original_proposal}")

    print("\n✅ Pruebas completadas exitosamente")
    return True

if __name__ == "__main__":
    success = test_force_reanalysis()
    if success:
        print("\n🎉 Todas las pruebas pasaron correctamente!")
    else:
        print("\n❌ Algunas pruebas fallaron")
        sys.exit(1)
