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


MODULE_PATH = LIME_ROOT / "core" / "asset_naming.py"
SPEC = importlib.util.spec_from_file_location(
    "lime_pipeline.core.asset_naming",
    MODULE_PATH,
    submodule_search_locations=[str(LIME_ROOT / "core")],
)
asset_naming = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
asset_naming.__package__ = "lime_pipeline.core"
sys.modules["lime_pipeline.core.asset_naming"] = asset_naming
SPEC.loader.exec_module(asset_naming)  # type: ignore[arg-type]


normalize_object_name = asset_naming.normalize_object_name
ensure_unique_object_name = asset_naming.ensure_unique_object_name
is_valid_object_name = asset_naming.is_valid_object_name
build_material_name_with_scene_tag = asset_naming.build_material_name_with_scene_tag
bump_material_version_until_unique = asset_naming.bump_material_version_until_unique


class AssetNamingTests(unittest.TestCase):
    def test_normalize_object_name_camel_case(self):
        self.assertEqual(normalize_object_name("wheel mount"), "WheelMount")
        self.assertEqual(normalize_object_name("Cube.001"), "Cube001")

    def test_normalize_object_name_strips_diacritics(self):
        self.assertEqual(normalize_object_name("silla de ruedas"), "SillaDeRuedas")

    def test_object_name_validation(self):
        self.assertTrue(is_valid_object_name("WheelMount01"))
        self.assertFalse(is_valid_object_name("Wheel_Mount"))
        self.assertFalse(is_valid_object_name("1Wheel"))

    def test_ensure_unique_object_name(self):
        existing = {"WheelMount", "WheelMount2"}
        self.assertEqual(ensure_unique_object_name("WheelMount", existing), "WheelMount3")

    def test_material_name_build_and_bump_version(self):
        name = build_material_name_with_scene_tag("Wheelchair", "Metal", "Glossy", 1)
        self.assertTrue(name.startswith("MAT_Wheelchair_Metal_Glossy_V"))
        bumped = bump_material_version_until_unique({name}, name)
        self.assertNotEqual(bumped, name)


if __name__ == "__main__":
    unittest.main()

