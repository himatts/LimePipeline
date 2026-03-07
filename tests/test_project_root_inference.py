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


MODULE_PATH = LIME_ROOT / "core" / "naming.py"
SPEC = importlib.util.spec_from_file_location(
    "lime_pipeline.core.naming",
    MODULE_PATH,
    submodule_search_locations=[str(LIME_ROOT / "core")],
)
naming = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
naming.__package__ = "lime_pipeline.core"
sys.modules["lime_pipeline.core.naming"] = naming
SPEC.loader.exec_module(naming)  # type: ignore[arg-type]


infer_project_root_from_blend_path = naming.infer_project_root_from_blend_path


class ProjectRootInferenceTests(unittest.TestCase):
    def test_infers_shared_project_root_from_ramv_path(self):
        path = pathlib.Path(
            r"C:\Projects\AB-12345 Sample\2. Graphic & Media\3. Rendering-Animation-Video\Renders\Rev A\scenes\Sample_Render_SC010_Rev_A.blend"
        )
        root = infer_project_root_from_blend_path(path)
        self.assertEqual(root, pathlib.Path(r"C:\Projects\AB-12345 Sample"))

    def test_infers_local_project_root_from_saved_local_path(self):
        path = pathlib.Path(
            r"C:\Users\Usuario\Documents\Lime Design\LocalProjects\SampleProject\Animation\Rev B\scenes\SampleProject_Anim_SC020_Rev_B.blend"
        )
        root = infer_project_root_from_blend_path(path)
        self.assertEqual(
            root,
            pathlib.Path(r"C:\Users\Usuario\Documents\Lime Design\LocalProjects\SampleProject"),
        )

    def test_returns_none_for_non_matching_filename(self):
        path = pathlib.Path(r"C:\Temp\Animation\Rev A\scenes\example.blend")
        root = infer_project_root_from_blend_path(path)
        self.assertIsNone(root)


if __name__ == "__main__":
    unittest.main()
