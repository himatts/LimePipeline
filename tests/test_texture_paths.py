import importlib.util
import pathlib
import tempfile
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


MODULE_PATH = LIME_ROOT / "core" / "texture_paths.py"
SPEC = importlib.util.spec_from_file_location(
    "lime_pipeline.core.texture_paths",
    MODULE_PATH,
    submodule_search_locations=[str(LIME_ROOT / "core")],
)
texture_paths = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
texture_paths.__package__ = "lime_pipeline.core"
sys.modules["lime_pipeline.core.texture_paths"] = texture_paths
SPEC.loader.exec_module(texture_paths)  # type: ignore[arg-type]


is_subpath = texture_paths.is_subpath
classify_path = texture_paths.classify_path


class TexturePathsTests(unittest.TestCase):
    def test_is_subpath(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp).resolve()
            inside = (root / "a" / "b").resolve()
            outside = (root.parent / "elsewhere").resolve()
            self.assertTrue(is_subpath(inside, root))
            self.assertFalse(is_subpath(outside, root))

    def test_classify_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = pathlib.Path(tmp).resolve()
            protected_root = (project_root / "AssetsLib").resolve()
            protected_root.mkdir(parents=True, exist_ok=True)

            protected_file = (protected_root / "tx.png").resolve()
            in_project_file = (project_root / "foo" / "bar.png").resolve()
            external_file = (project_root.parent / "external.png").resolve()

            c1 = classify_path(protected_file, project_root=project_root, protected_roots=(protected_root,))
            self.assertEqual(c1.kind, "PROTECTED_ROOT")

            c2 = classify_path(in_project_file, project_root=project_root, protected_roots=(protected_root,))
            self.assertEqual(c2.kind, "IN_PROJECT")

            c3 = classify_path(external_file, project_root=project_root, protected_roots=(protected_root,))
            self.assertEqual(c3.kind, "EXTERNAL")

            c4 = classify_path(None, project_root=project_root)
            self.assertEqual(c4.kind, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()

