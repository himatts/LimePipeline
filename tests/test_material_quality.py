import importlib.util
import pathlib
import types
import sys
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

MODULE_PATH = LIME_ROOT / "core" / "material_quality.py"
SPEC = importlib.util.spec_from_file_location(
    "lime_pipeline.core.material_quality",
    MODULE_PATH,
    submodule_search_locations=[str(LIME_ROOT / "core")],
)
material_quality = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
material_quality.__package__ = "lime_pipeline.core"
sys.modules["lime_pipeline.core.material_quality"] = material_quality
SPEC.loader.exec_module(material_quality)  # type: ignore[arg-type]

evaluate_material_name = material_quality.evaluate_material_name


class MaterialQualityTests(unittest.TestCase):
    def test_excellent_name_has_high_score(self):
        result = evaluate_material_name("MAT_Metal_Brushed_V02")
        self.assertEqual(result.label, "excellent")
        self.assertGreaterEqual(result.score, 0.85)

    def test_invalid_name_detected(self):
        result = evaluate_material_name("Material001")
        self.assertEqual(result.label, "invalid")
        self.assertLess(result.score, 0.2)


if __name__ == "__main__":
    unittest.main()
