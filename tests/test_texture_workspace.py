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


MODULE_PATH = LIME_ROOT / "core" / "texture_workspace.py"
SPEC = importlib.util.spec_from_file_location(
    "lime_pipeline.core.texture_workspace",
    MODULE_PATH,
    submodule_search_locations=[str(LIME_ROOT / "core")],
)
texture_workspace = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
texture_workspace.__package__ = "lime_pipeline.core"
sys.modules["lime_pipeline.core.texture_workspace"] = texture_workspace
SPEC.loader.exec_module(texture_workspace)  # type: ignore[arg-type]


deduce_texture_project_root = texture_workspace.deduce_texture_project_root
deduce_texture_project_workspace = texture_workspace.deduce_texture_project_workspace
extra_protected_texture_roots = texture_workspace.extra_protected_texture_roots
infer_local_project_root_from_blend_path = texture_workspace.infer_local_project_root_from_blend_path
resolve_texture_root = texture_workspace.resolve_texture_root


class TextureWorkspaceTests(unittest.TestCase):
    def test_extra_protected_roots_contains_xpbr(self):
        roots = extra_protected_texture_roots()
        expected = pathlib.Path.home() / "Documents" / "Blender Addons" / "XPBR"
        self.assertIn(str(expected.resolve()), {str(p) for p in roots})

    def test_infer_local_root_from_render_scene_path(self):
        blend = pathlib.Path(
            "C:/LocalProjects/CarViz/Renders/Rev A/scenes/CarViz_Render_SC010_Rev_A.blend"
        )
        root = infer_local_project_root_from_blend_path(blend)
        self.assertEqual(root, pathlib.Path("C:/LocalProjects/CarViz"))

    def test_infer_local_root_from_base_model_path(self):
        blend = pathlib.Path(
            "C:/LocalProjects/CarViz/3D Base Model/Rev B/CarViz_BaseModel_Rev_B.blend"
        )
        root = infer_local_project_root_from_blend_path(blend)
        self.assertEqual(root, pathlib.Path("C:/LocalProjects/CarViz"))

    def test_deduce_local_root_uses_state_even_if_missing(self):
        root = deduce_texture_project_root(
            state_project_root="C:/LocalProjects/NewProject",
            use_local_project=True,
            blend_path="",
        )
        self.assertEqual(root, pathlib.Path("C:/LocalProjects/NewProject"))

    def test_deduce_local_root_falls_back_to_blend_path(self):
        root = deduce_texture_project_root(
            state_project_root="",
            use_local_project=True,
            blend_path="C:/LocalProjects/Chair/Storyboard/Rev C/scenes/Chair_SB_SC020_Rev_C.blend",
        )
        self.assertEqual(root, pathlib.Path("C:/LocalProjects/Chair"))

    def test_workspace_falls_back_to_local_mode_from_local_blend(self):
        root, local_mode = deduce_texture_project_workspace(
            state_project_root="",
            use_local_project=False,
            blend_path="C:/LocalProjects/LimeDesignEpicEnergies/Animation/Rev A/scenes/LimeDesignEpicEnergies_Anim_SC010_Rev_A.blend",
        )
        self.assertEqual(root, pathlib.Path("C:/LocalProjects/LimeDesignEpicEnergies"))
        self.assertTrue(local_mode)

    def test_workspace_detects_shared_root_when_state_points_inside_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            shared_root = pathlib.Path(tmp) / "AA-12345 Test"
            nested = shared_root / "2. Graphic & Media" / "3. Rendering-Animation-Video" / "Animation" / "Rev A" / "scenes"
            nested.mkdir(parents=True, exist_ok=True)
            root, local_mode = deduce_texture_project_workspace(
                state_project_root=str(nested),
                use_local_project=False,
                blend_path="",
            )
            self.assertEqual(root, shared_root.resolve())
            self.assertFalse(local_mode)

    def test_resolve_texture_root_local_and_cloud(self):
        project_root = pathlib.Path("C:/Projects/AA-12345 Test")
        blend_dir = pathlib.Path("C:/tmp")

        local_texture_root = resolve_texture_root(project_root, local_mode=True, blend_dir=blend_dir)
        cloud_texture_root = resolve_texture_root(project_root, local_mode=False, blend_dir=blend_dir)

        self.assertEqual(local_texture_root, project_root / "rsc" / "Textures")
        self.assertEqual(
            cloud_texture_root,
            project_root / "2. Graphic & Media" / "3. Rendering-Animation-Video" / "rsc" / "Textures",
        )


if __name__ == "__main__":
    unittest.main()
