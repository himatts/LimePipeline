import importlib.util
import pathlib
import sys
import types
import unittest
from types import SimpleNamespace


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


MODULE_PATH = LIME_ROOT / "core" / "ai_asset_collection_paths.py"
SPEC = importlib.util.spec_from_file_location(
    "lime_pipeline.core.ai_asset_collection_paths",
    MODULE_PATH,
    submodule_search_locations=[str(LIME_ROOT / "core")],
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
module.__package__ = "lime_pipeline.core"
sys.modules["lime_pipeline.core.ai_asset_collection_paths"] = module
SPEC.loader.exec_module(module)  # type: ignore[arg-type]


class AIAssetCollectionPathsTests(unittest.TestCase):
    def test_missing_segments(self):
        missing = module.build_missing_path_segments(
            ["Props/Chairs/Metal", "Props/Tables"],
            ["Props"],
        )
        self.assertEqual(missing, ["Props/Tables", "Props/Chairs", "Props/Chairs/Metal"])

    def test_normalize_collection_path_value(self):
        value = module.normalize_collection_path_value("SHOT 01/SH01_Props/My Props")
        self.assertEqual(value, "SHOT_01/SH_01_Props/My_Props")

    def test_replace_prefix(self):
        self.assertEqual(
            module.replace_path_prefix("Props/Old/Item", "Props/Old", "Props/New"),
            "Props/New/Item",
        )

    def test_canonical_collection_keys(self):
        self.assertEqual(module.canonical_collection_name_key("my props"), "my_props")
        self.assertEqual(
            module.canonical_collection_path_key("SHOT 01/SH01_Props/My Props"),
            "shot_01/sh_01_props/my_props",
        )

    def test_serialize_parse_candidates(self):
        serialized = module.serialize_ranked_candidates(
            [
                SimpleNamespace(path="Props/Chairs", score=1.25, exists=True),
                SimpleNamespace(path="Props/Tables", score=0.75, exists=False),
            ]
        )
        parsed = module.parse_target_candidates_json(serialized)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["path"], "Props/Chairs")
        self.assertTrue(parsed[0]["exists"])


if __name__ == "__main__":
    unittest.main()
