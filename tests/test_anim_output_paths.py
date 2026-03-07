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


MODULE_PATH = LIME_ROOT / "core" / "anim_output_paths.py"
SPEC = importlib.util.spec_from_file_location(
    "lime_pipeline.core.anim_output_paths",
    MODULE_PATH,
    submodule_search_locations=[str(LIME_ROOT / "core")],
)
anim_output_paths = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
anim_output_paths.__package__ = "lime_pipeline.core"
sys.modules["lime_pipeline.core.anim_output_paths"] = anim_output_paths
SPEC.loader.exec_module(anim_output_paths)  # type: ignore[arg-type]


build_local_anim_output_path = anim_output_paths.build_local_anim_output_path
build_pipeline_anim_output_path = anim_output_paths.build_pipeline_anim_output_path


class AnimOutputPathsTests(unittest.TestCase):
    def test_pipeline_animation_path_uses_ramv_structure(self):
        root = pathlib.Path(r"C:\Projects\AB-12345 Sample")
        output = build_pipeline_anim_output_path(
            root,
            "ANIM",
            "C",
            10,
            3,
            use_test_variant=False,
        )
        expected = root / "2. Graphic & Media" / "3. Rendering-Animation-Video" / "Animation" / "Rev C" / "SC010_SH03" / "SC010_SH03_"
        self.assertEqual(output, expected)

    def test_pipeline_render_container_path_uses_renders_folder(self):
        root = pathlib.Path(r"C:\Projects\AB-12345 Sample")
        output = build_pipeline_anim_output_path(
            root,
            "REND",
            "B",
            20,
            7,
            use_test_variant=True,
        )
        expected = root / "2. Graphic & Media" / "3. Rendering-Animation-Video" / "Renders" / "Rev B" / "SC020_SH07" / "test" / "SC020_SH07_test_"
        self.assertEqual(output, expected)

    def test_local_output_path_uses_project_name_root(self):
        base = pathlib.Path(r"C:\Users\Usuario\Desktop")
        output = build_local_anim_output_path(
            base,
            "MyProject",
            30,
            12,
            use_test_variant=False,
        )
        expected = base / "MyProject" / "SC030_SH12" / "SC030_SH12_"
        self.assertEqual(output, expected)

    def test_local_output_test_variant_uses_test_subfolder(self):
        base = pathlib.Path(r"C:\Users\Usuario\Desktop")
        output = build_local_anim_output_path(
            base,
            "MyProject",
            40,
            1,
            use_test_variant=True,
        )
        expected = base / "MyProject" / "SC040_SH01" / "test" / "SC040_SH01_test_"
        self.assertEqual(output, expected)


if __name__ == "__main__":
    unittest.main()
