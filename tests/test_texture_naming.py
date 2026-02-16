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


MODULE_PATH = LIME_ROOT / "core" / "texture_naming.py"
SPEC = importlib.util.spec_from_file_location(
    "lime_pipeline.core.texture_naming",
    MODULE_PATH,
    submodule_search_locations=[str(LIME_ROOT / "core")],
)
texture_naming = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
texture_naming.__package__ = "lime_pipeline.core"
sys.modules["lime_pipeline.core.texture_naming"] = texture_naming
SPEC.loader.exec_module(texture_naming)  # type: ignore[arg-type]


sanitize_token = texture_naming.sanitize_token
sanitize_filename_stem = texture_naming.sanitize_filename_stem
canonicalize_texture_stem = texture_naming.canonicalize_texture_stem
material_stem = texture_naming.material_stem
map_type_from_text = texture_naming.map_type_from_text
map_type_from_socket_links = texture_naming.map_type_from_socket_links
short_hash = texture_naming.short_hash
TextureNameHints = texture_naming.TextureNameHints
propose_texture_filename = texture_naming.propose_texture_filename


class TextureNamingTests(unittest.TestCase):
    def test_sanitize_token(self):
        self.assertEqual(sanitize_token("base color", "X"), "BaseColor")
        self.assertEqual(sanitize_token("  ", "Fallback"), "Fallback")

    def test_sanitize_filename_stem(self):
        self.assertEqual(sanitize_filename_stem("ReticleTrainerApp_Texture_01"), "ReticleTrainerApp_Texture_01")
        self.assertEqual(sanitize_filename_stem("My tex.name-01"), "My_tex_name_01")
        self.assertEqual(sanitize_filename_stem(""), "")

    def test_canonicalize_texture_stem(self):
        self.assertEqual(
            canonicalize_texture_stem(project_token="ReticleTrainer", stem="ReticleTrainerApp_Texture_01", map_type="Alpha"),
            "ReticleTrainer_App_Texture_Alpha_01",
        )
        self.assertEqual(
            canonicalize_texture_stem(project_token="ReticleTrainer", stem="Display", map_type="Alpha"),
            "ReticleTrainer_Display_Alpha_01",
        )
        self.assertEqual(
            canonicalize_texture_stem(project_token="ReticleTrainer", stem="ReticleTrainer_Target", map_type="Alpha"),
            "ReticleTrainer_Target_Alpha_01",
        )

    def test_material_stem(self):
        self.assertEqual(material_stem("MAT_Wheel_V03"), "Wheel")
        self.assertEqual(material_stem("MAT__V01"), "Material")
        self.assertEqual(material_stem("SomeMaterial"), "SomeMaterial")

    def test_map_type_from_text(self):
        self.assertEqual(map_type_from_text("my_normal_map.png"), "Normal")
        self.assertEqual(map_type_from_text("roughness"), "Roughness")
        self.assertEqual(map_type_from_text("baseColor"), "BaseColor")
        self.assertEqual(map_type_from_text("something else"), "Generic")

    def test_map_type_from_socket_links_single_role(self):
        self.assertEqual(map_type_from_socket_links(["Alpha"], fallback_text=""), "Alpha")
        self.assertEqual(map_type_from_socket_links(["Base Color"], fallback_text=""), "BaseColor")
        self.assertEqual(map_type_from_socket_links(["Normal"], fallback_text=""), "Normal")

    def test_map_type_from_socket_links_multi_role_returns_generic(self):
        self.assertEqual(
            map_type_from_socket_links(["Base Color", "Roughness"], fallback_text="alpha mask"),
            "Generic",
        )

    def test_map_type_from_socket_links_fallback(self):
        self.assertEqual(map_type_from_socket_links([], fallback_text="opacity_mask"), "Alpha")

    def test_short_hash_length(self):
        self.assertEqual(len(short_hash("abc", length=8)), 8)
        self.assertEqual(len(short_hash("abc", length=4)), 4)

    def test_propose_texture_filename(self):
        name = propose_texture_filename(
            TextureNameHints(material_name="MAT_Wheel_V01", map_type="Normal", source_path="C:/tmp/nrm.png"),
            ext=".png",
            hash_length=8,
        )
        self.assertTrue(name.startswith("TX_"))
        self.assertTrue(name.endswith(".png"))
        self.assertIn("_Normal_", name)


if __name__ == "__main__":
    unittest.main()
