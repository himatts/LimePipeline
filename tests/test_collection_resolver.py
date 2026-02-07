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


MODULE_PATH = LIME_ROOT / "core" / "collection_resolver.py"
SPEC = importlib.util.spec_from_file_location(
    "lime_pipeline.core.collection_resolver",
    MODULE_PATH,
    submodule_search_locations=[str(LIME_ROOT / "core")],
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
module.__package__ = "lime_pipeline.core"
sys.modules["lime_pipeline.core.collection_resolver"] = module
SPEC.loader.exec_module(module)  # type: ignore[arg-type]

CollectionCandidate = module.CollectionCandidate
resolve_collection_destination = module.resolve_collection_destination
tokenize = module.tokenize


def _candidate(path: str, *, exists: bool = True):
    parts = [p for p in path.split("/") if p]
    leaf = parts[-1]
    shot_root = None
    for p in parts:
        if p.startswith("SHOT "):
            shot_root = p
            break
    return CollectionCandidate(
        path=path,
        name=leaf,
        depth=max(0, len(parts) - 1),
        shot_root_name=shot_root,
        is_shot_root=leaf.startswith("SHOT "),
        is_read_only=False,
        object_count=0,
        path_tokens=tokenize(path),
        name_tokens=tokenize(leaf),
        exists=exists,
    )


class CollectionResolverTests(unittest.TestCase):
    def test_prefers_shot_branch_when_context_exists(self):
        candidates = [
            _candidate("SHOT 01/SH01_Background/Background"),
            _candidate("SHOT 02/SH02_Background/Background"),
        ]
        result = resolve_collection_destination(
            object_name="Background_01",
            candidates=candidates,
            preferred_shot_roots=["SHOT 01"],
        )
        self.assertEqual(result.status, "AUTO")
        self.assertEqual(result.selected_path, "SHOT 01/SH01_Background/Background")

    def test_marks_ambiguous_when_scores_tie(self):
        candidates = [
            _candidate("SHOT 01/SH01_Background/Background"),
            _candidate("SHOT 02/SH02_Background/Background"),
        ]
        result = resolve_collection_destination(
            object_name="Background",
            candidates=candidates,
        )
        self.assertEqual(result.status, "AMBIGUOUS")
        self.assertEqual(len(result.candidates), 2)

    def test_selects_auto_on_clear_score_gap(self):
        candidates = [
            _candidate("Props/Chair"),
            _candidate("Props/Background"),
        ]
        result = resolve_collection_destination(
            object_name="Chair_01",
            candidates=candidates,
        )
        self.assertEqual(result.status, "AUTO")
        self.assertEqual(result.selected_path, "Props/Chair")

    def test_supports_missing_hint_path_candidate(self):
        candidates = [
            _candidate("SHOT 01/SH01_Background"),
            _candidate("SHOT 01/SH01_Props"),
        ]
        result = resolve_collection_destination(
            object_name="Background",
            candidates=candidates,
            preferred_shot_roots=["SHOT 01"],
            hint_path="SHOT 01/SH01_Background/Background",
        )
        self.assertEqual(result.status, "AUTO")
        self.assertEqual(result.selected_path, "SHOT 01/SH01_Background/Background")
        top = result.candidates[0]
        self.assertFalse(top.exists)

    def test_light_keeps_current_lights_collection_even_if_hint_points_elsewhere(self):
        light_path = "SHOT 01/SH01_00_LIGHTS/SH01_00_LIGHTS.001"
        wrong_hint = "SHOT 01/SH01_02_PROPS/Human/Annotations"
        candidates = [
            _candidate(light_path),
            _candidate(wrong_hint),
        ]
        result = resolve_collection_destination(
            object_name="TriLamp_Back",
            object_type="LIGHT",
            candidates=candidates,
            current_collection_paths=[light_path],
            preferred_shot_roots=["SHOT 01"],
            hint_path=wrong_hint,
        )
        self.assertEqual(result.status, "AUTO")
        self.assertEqual(result.selected_path, light_path)
        self.assertAlmostEqual(result.confidence, 1.0)

    def test_light_without_current_membership_prefers_lights_bucket(self):
        light_path = "SHOT 01/SH01_00_LIGHTS"
        other_path = "SHOT 01/SH01_02_PROPS"
        candidates = [
            _candidate(light_path),
            _candidate(other_path),
        ]
        result = resolve_collection_destination(
            object_name="Area_001",
            object_type="LIGHT",
            candidates=candidates,
            preferred_shot_roots=["SHOT 01"],
        )
        self.assertEqual(result.status, "AUTO")
        self.assertEqual(result.selected_path, light_path)

    def test_bg_alias_beats_current_membership_when_name_is_background(self):
        candidates = [
            _candidate("SHOT 01/SH01_90_BG/BG"),
            _candidate("SHOT 01/SH01_02_PROPS/Human/Annotations"),
        ]
        result = resolve_collection_destination(
            object_name="Background_Wall",
            candidates=candidates,
            preferred_shot_roots=["SHOT 01"],
            current_collection_paths=["SHOT 01/SH01_02_PROPS/Human/Annotations"],
        )
        self.assertEqual(result.status, "AUTO")
        self.assertEqual(result.selected_path, "SHOT 01/SH01_90_BG/BG")


if __name__ == "__main__":
    unittest.main()
