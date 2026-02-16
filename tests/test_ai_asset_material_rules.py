import importlib.util
import pathlib
import sys
import types
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LIME_ROOT = REPO_ROOT / "lime_pipeline"

if "lime_pipeline" not in sys.modules:
    package = types.ModuleType("lime_pipeline")
    package.__path__ = [str(LIME_ROOT)]
    sys.modules["lime_pipeline"] = package

if "lime_pipeline.core" not in sys.modules:
    core_package = types.ModuleType("lime_pipeline.core")
    core_package.__path__ = [str(LIME_ROOT / "core")]
    sys.modules["lime_pipeline.core"] = core_package


MODULE_PATH = LIME_ROOT / "core" / "ai_asset_material_rules.py"
SPEC = importlib.util.spec_from_file_location(
    "lime_pipeline.core.ai_asset_material_rules",
    MODULE_PATH,
    submodule_search_locations=[str(LIME_ROOT / "core")],
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
module.__package__ = "lime_pipeline.core"
sys.modules["lime_pipeline.core.ai_asset_material_rules"] = module
SPEC.loader.exec_module(module)  # type: ignore[arg-type]


class AIAssetMaterialRulesTests(unittest.TestCase):
    def test_normalize_tag_and_fold(self):
        self.assertEqual(module.normalize_tag_token("iphone 15 pro"), "Iphone15Pro")
        self.assertEqual(module.fold_text_for_match("iPhone-15 Pro"), "iphone15pro")

    def test_extract_context_directive(self):
        tag, obj_filter = module.extract_context_material_tag_directive(
            'Please force tag "Iphone" for object "phone" materials'
        )
        self.assertEqual(tag, "Iphone")
        self.assertEqual(obj_filter, "")

    def test_extract_context_directive_explicit_force(self):
        tag, obj_filter = module.extract_context_material_tag_directive(
            "Please force tag: PhonePro materials for object phone"
        )
        self.assertEqual(tag, "Phonepro")
        self.assertEqual(obj_filter, "Phone")

    def test_extract_context_directive_plain_tag_mention_does_not_force(self):
        tag, obj_filter = module.extract_context_material_tag_directive(
            'Please use tag "Iphone" for object "phone" materials'
        )
        self.assertEqual(tag, "")
        self.assertEqual(obj_filter, "")

    def test_context_requests_material_tag(self):
        self.assertTrue(
            module.context_requests_material_tag(
                "este es un Tools Cart, dale a los materiales un tag relacionado con este objeto"
            )
        )
        self.assertTrue(module.context_requests_material_tag("force tag: ToolsCart"))
        self.assertFalse(module.context_requests_material_tag("sin tag en los materiales"))

    def test_force_material_tag(self):
        tagged = module.force_material_name_tag("MAT_Metal_Brushed_V01", "Iphone")
        self.assertEqual(tagged, "MAT_Iphone_Metal_Brushed_V01")

    def test_normalize_material_name_for_organizer(self):
        profile = {
            "metallic": 0.0,
            "roughness": 0.8,
            "transmission": 0.0,
            "emission_strength": 0.0,
            "emission_luma": 0.0,
            "has_metallic_input": False,
            "has_emission_input": False,
        }
        notes = []
        out = module.normalize_material_name_for_organizer(
            "plastic_metalpolished_v01",
            profile=profile,
            source_name="plastic_metalpolished_v01",
            trace=notes,
        )
        self.assertTrue(out.startswith("MAT_"))
        self.assertTrue(out.endswith("_V01"))
        self.assertTrue(len(notes) >= 1)

    def test_normalize_material_name_keeps_existing_tag(self):
        out = module.normalize_material_name_for_organizer(
            "MAT_ToolCart_Rubber_Matte_V01",
            source_name="MAT_Rubber_Matte_V01",
        )
        self.assertEqual(out, "MAT_ToolCart_Rubber_Matte_V01")

    def test_material_status_from_trace(self):
        self.assertEqual(
            module.material_status_from_trace("A", "B", ["Applied shader-profile guardrails"]),
            "NORMALIZED_SEMANTIC",
        )
        self.assertEqual(module.material_status_from_trace("A", "B", []), "NORMALIZED_STRUCTURAL")
        self.assertEqual(module.material_status_from_trace("A", "A", []), "AI_EXACT")


if __name__ == "__main__":
    unittest.main()
