import importlib.util
import pathlib
import sys
import types
import unittest
from unittest import mock


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

if "lime_pipeline.ops" not in sys.modules:
    ops_package = types.ModuleType("lime_pipeline.ops")
    ops_package.__path__ = [str(LIME_ROOT / "ops")]
    sys.modules["lime_pipeline.ops"] = ops_package

if "lime_pipeline.ops.ai_asset_organizer" not in sys.modules:
    organizer_package = types.ModuleType("lime_pipeline.ops.ai_asset_organizer")
    organizer_package.__path__ = [str(LIME_ROOT / "ops" / "ai_asset_organizer")]
    sys.modules["lime_pipeline.ops.ai_asset_organizer"] = organizer_package


MODULE_PATH = LIME_ROOT / "ops" / "ai_asset_organizer" / "openrouter_client.py"
SPEC = importlib.util.spec_from_file_location(
    "lime_pipeline.ops.ai_asset_organizer.openrouter_client",
    MODULE_PATH,
    submodule_search_locations=[str(LIME_ROOT / "ops" / "ai_asset_organizer")],
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
module.__package__ = "lime_pipeline.ops.ai_asset_organizer"
sys.modules["lime_pipeline.ops.ai_asset_organizer.openrouter_client"] = module
SPEC.loader.exec_module(module)  # type: ignore[arg-type]


def _chat_result(content: str, finish_reason: str = "stop"):
    return {
        "choices": [
            {
                "finish_reason": finish_reason,
                "message": {"content": content},
            }
        ]
    }


class OpenRouterClientTests(unittest.TestCase):
    def test_repair_pass_recovers_non_json_output(self):
        responses = [
            _chat_result("I think this is fine without JSON"),
            _chat_result("still not json"),
            _chat_result('{"items":[{"id":"obj_0","name":"Chair"}]}'),
        ]
        with mock.patch.object(module, "http_post_json", side_effect=responses) as post:
            items, err, finish_reason = module.openrouter_suggest(
                headers={},
                model="model",
                prompt="prompt",
                expected_ids=["obj_0"],
            )
        self.assertIsNone(err)
        self.assertEqual(finish_reason, "stop")
        self.assertEqual(items, [{"id": "obj_0", "name": "Chair"}])
        self.assertEqual(post.call_count, 3)

    def test_error_includes_preview_when_repair_fails(self):
        responses = [
            _chat_result("plain text response", finish_reason="stop"),
            _chat_result("second plain response", finish_reason="stop"),
            _chat_result("third plain response", finish_reason="stop"),
        ]
        with mock.patch.object(module, "http_post_json", side_effect=responses):
            items, err, finish_reason = module.openrouter_suggest(
                headers={},
                model="model",
                prompt="prompt",
                expected_ids=["obj_0"],
            )
        self.assertIsNone(items)
        self.assertEqual(finish_reason, "stop")
        self.assertIn("did not contain a JSON object", str(err))
        self.assertIn("Raw preview:", str(err))


if __name__ == "__main__":
    unittest.main()
