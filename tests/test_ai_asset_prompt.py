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


MODULE_PATH = LIME_ROOT / "core" / "ai_asset_prompt.py"
SPEC = importlib.util.spec_from_file_location(
    "lime_pipeline.core.ai_asset_prompt",
    MODULE_PATH,
    submodule_search_locations=[str(LIME_ROOT / "core")],
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
module.__package__ = "lime_pipeline.core"
sys.modules["lime_pipeline.core.ai_asset_prompt"] = module
SPEC.loader.exec_module(module)  # type: ignore[arg-type]


class AIAssetPromptTests(unittest.TestCase):
    def test_schema_json_object(self):
        self.assertEqual(module.schema_json_object(), {"type": "json_object"})

    def test_schema_assets_shape(self):
        schema = module.schema_assets()
        self.assertEqual(schema.get("type"), "json_schema")
        json_schema = schema.get("json_schema", {})
        self.assertEqual(json_schema.get("name"), "ai_asset_namer")

    def test_build_prompt_contains_rules_and_payload(self):
        prompt = module.build_prompt(
            "tag iphone",
            "summary",
            [{"id": "obj_0", "name": "Cube"}],
            [{"id": "mat_0", "name": "MAT_Plastic_Generic_V01"}],
            [{"id": "col_0", "name": "Props"}],
        )
        self.assertIn("Return ONLY JSON per schema.", prompt)
        self.assertIn("Context: tag iphone", prompt)
        self.assertIn("MaterialType must be one of:", prompt)
        self.assertIn('"scene_summary":"summary"', prompt)


if __name__ == "__main__":
    unittest.main()
