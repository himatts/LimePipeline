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


MODULE_PATH = LIME_ROOT / "core" / "ai_asset_response.py"
SPEC = importlib.util.spec_from_file_location(
    "lime_pipeline.core.ai_asset_response",
    MODULE_PATH,
    submodule_search_locations=[str(LIME_ROOT / "core")],
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
module.__package__ = "lime_pipeline.core"
sys.modules["lime_pipeline.core.ai_asset_response"] = module
SPEC.loader.exec_module(module)  # type: ignore[arg-type]

parse_items_from_response = module.parse_items_from_response


class AIAssetResponseTests(unittest.TestCase):
    def test_parse_direct_items(self):
        payload = {"items": [{"id": "obj_0", "name": "Chair"}]}
        items = parse_items_from_response(payload)
        self.assertEqual(items, [{"id": "obj_0", "name": "Chair"}])

    def test_parse_category_fallback(self):
        payload = {
            "objects": [{"id": "obj_0", "name": "Chair"}],
            "materials": [{"id": "mat_0", "name": "MAT_Wood_Polished_V01"}],
            "collections": [{"id": "col_0", "name": "Props"}],
        }
        items = parse_items_from_response(payload)
        self.assertEqual(len(items or []), 3)

    def test_parse_items_with_optional_target_hint(self):
        payload = {
            "items": [
                {
                    "id": "obj_0",
                    "name": "Background",
                    "target_collection_hint": "SHOT 01/SH01_Background/Background",
                }
            ]
        }
        items = parse_items_from_response(payload)
        self.assertEqual(items, payload["items"])

    def test_parse_reject_invalid_payload(self):
        self.assertIsNone(parse_items_from_response(None))
        self.assertIsNone(parse_items_from_response({"message": "no items"}))


if __name__ == "__main__":
    unittest.main()
