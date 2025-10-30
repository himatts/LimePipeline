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


def _load_module(module_name: str, module_path: pathlib.Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        module_name,
        module_path,
        submodule_search_locations=[str(LIME_ROOT / "core")],
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "lime_pipeline.core"
    loader = spec.loader
    assert loader is not None
    sys.modules[module_name] = module
    loader.exec_module(module)  # type: ignore[arg-type]
    return module


material_naming = _load_module(
    "lime_pipeline.core.material_naming",
    LIME_ROOT / "core" / "material_naming.py",
)
material_taxonomy = _load_module(
    "lime_pipeline.core.material_taxonomy",
    LIME_ROOT / "core" / "material_taxonomy.py",
)


class MaterialTaxonomyTests(unittest.TestCase):
    def test_allowed_types_include_silicone(self) -> None:
        allowed = material_taxonomy.get_allowed_material_types()
        self.assertIn("Silicone", allowed)
        self.assertIn("Background", allowed)
        self.assertIn("Silicone", material_naming.ALLOWED_MATERIAL_TYPES)
        self.assertIn("Background", material_naming.ALLOWED_MATERIAL_TYPES)
        self.assertEqual(material_naming.normalize_material_type("silicone"), "Silicone")
        self.assertEqual(material_naming.normalize_material_type("background"), "Background")

    def test_infer_prefers_silicone_when_token_present(self) -> None:
        material_type, finishes = material_taxonomy.infer_material_type_and_finishes(
            "Silicone Gasket",
            ["silicone_color", "gasket_ao"],
            ["seal"],
            ["hardware"],
            {"roughness": 0.65, "metallic": 0.0},
        )
        self.assertEqual(material_type, "Silicone")
        self.assertTrue(finishes)

    def test_infer_rubber_without_silicone_hint(self) -> None:
        material_type, _ = material_taxonomy.infer_material_type_and_finishes(
            "Industrial Rubber Mat",
            ["floor_rubber_diffuse"],
            [],
            [],
            {"roughness": 0.7, "metallic": 0.0},
        )
        self.assertEqual(material_type, "Rubber")

    def test_infer_background_from_hints(self) -> None:
        material_type, _ = material_taxonomy.infer_material_type_and_finishes(
            "Sky Dome",
            [],
            ["BG_Sky"],
            ["Environment"],
            {"emission_strength": 1.2},
        )
        self.assertEqual(material_type, "Background")


if __name__ == "__main__":
    unittest.main()

