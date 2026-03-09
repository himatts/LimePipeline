import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
LIME_ROOT = REPO_ROOT / "lime_pipeline"
MODULE_NAME = "lime_pipeline.core.env_config"
MODULE_PATH = LIME_ROOT / "core" / "env_config.py"
CORE_PATH = LIME_ROOT / "core"


if "lime_pipeline" not in sys.modules:
    package = types.ModuleType("lime_pipeline")
    package.__path__ = [str(LIME_ROOT)]
    sys.modules["lime_pipeline"] = package

if "lime_pipeline.core" not in sys.modules:
    core_package = types.ModuleType("lime_pipeline.core")
    core_package.__path__ = [str(CORE_PATH)]
    sys.modules["lime_pipeline.core"] = core_package


class EnvConfigTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            MODULE_NAME,
            MODULE_PATH,
            submodule_search_locations=[str(CORE_PATH)],
        )
        self.module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        self.module.__package__ = "lime_pipeline.core"
        sys.modules[MODULE_NAME] = self.module
        spec.loader.exec_module(self.module)  # type: ignore[arg-type]

    def tearDown(self):
        self.module._CACHE_PATH = None
        self.module._CACHE_MTIME = None
        self.module._CACHE_VALUES = {}
        sys.modules.pop(MODULE_NAME, None)

    def test_override_env_file_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            override = root / "custom.env"
            override.write_text("LIME_OPENROUTER_API_KEY=test\n", encoding="utf-8")
            fake_module_file = root / "addon" / "lime_pipeline" / "core" / "env_config.py"
            fake_module_file.parent.mkdir(parents=True, exist_ok=True)
            fake_module_file.write_text("# placeholder\n", encoding="utf-8")

            with patch.object(self.module, "__file__", str(fake_module_file)):
                with patch.dict("os.environ", {"LIME_PIPELINE_ENV_FILE": str(override)}, clear=False):
                    self.assertEqual(self.module.env_file_path(), override.resolve())

    def test_package_env_file_is_preferred(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_root = root / "addon"
            fake_module_file = package_root / "lime_pipeline" / "core" / "env_config.py"
            fake_module_file.parent.mkdir(parents=True, exist_ok=True)
            fake_module_file.write_text("# placeholder\n", encoding="utf-8")
            package_env = package_root / ".env"
            package_env.write_text("LIME_OPENROUTER_API_KEY=test\n", encoding="utf-8")
            cwd = root / "workspace"
            cwd.mkdir()
            (cwd / ".env").write_text("LIME_OPENROUTER_API_KEY=wrong\n", encoding="utf-8")

            with patch.object(self.module, "__file__", str(fake_module_file)):
                with patch.dict("os.environ", {}, clear=True):
                    with patch("pathlib.Path.cwd", return_value=cwd):
                        self.assertEqual(self.module.env_file_path(), package_env.resolve())

    def test_cwd_ancestor_env_file_is_used_when_package_env_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_module_file = root / "installed_addon" / "lime_pipeline" / "core" / "env_config.py"
            fake_module_file.parent.mkdir(parents=True, exist_ok=True)
            fake_module_file.write_text("# placeholder\n", encoding="utf-8")
            workspace = root / "repo" / "subdir" / "nested"
            workspace.mkdir(parents=True)
            repo_env = root / "repo" / ".env"
            repo_env.write_text("LIME_OPENROUTER_API_KEY=test\n", encoding="utf-8")

            with patch.object(self.module, "__file__", str(fake_module_file)):
                with patch.dict("os.environ", {}, clear=True):
                    with patch("pathlib.Path.cwd", return_value=workspace):
                        self.assertEqual(self.module.env_file_path(), repo_env.resolve())

    def test_fallback_returns_package_env_path_when_nothing_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_module_file = root / "installed_addon" / "lime_pipeline" / "core" / "env_config.py"
            fake_module_file.parent.mkdir(parents=True, exist_ok=True)
            fake_module_file.write_text("# placeholder\n", encoding="utf-8")
            workspace = root / "repo" / "subdir"
            workspace.mkdir(parents=True)
            expected = root / "installed_addon" / ".env"

            with patch.object(self.module, "__file__", str(fake_module_file)):
                with patch.dict("os.environ", {}, clear=True):
                    with patch("pathlib.Path.cwd", return_value=workspace):
                        self.assertEqual(self.module.env_file_path(), expected.resolve())


if __name__ == "__main__":
    unittest.main()
