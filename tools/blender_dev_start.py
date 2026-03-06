from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def _find_default_blender_exe() -> str:
    candidates = [
        Path(r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"),
        Path(r"C:\Program Files\Blender Foundation\Blender 5.0.1\blender.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "blender"


def _find_blender_development_launch_py(explicit: str | None) -> Path:
    if explicit:
        launch = Path(explicit).expanduser().resolve()
        if not launch.is_file():
            raise FileNotFoundError(f"launch.py not found: {launch}")
        return launch

    ext_root = Path.home() / ".vscode" / "extensions"
    candidates = sorted(ext_root.glob("jacqueslucke.blender-development-*/pythonFiles/launch.py"))
    if not candidates:
        raise FileNotFoundError("Could not locate Blender Development launch.py under ~/.vscode/extensions.")
    return candidates[-1]


def _build_parser(repo_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Blender in terminal with a Start flow equivalent for Blender 5.0."
    )
    parser.add_argument(
        "--mode",
        choices=("direct", "blender-development"),
        default="direct",
        help="direct: register addon from repo script. blender-development: execute extension launch.py contract.",
    )
    parser.add_argument("--blender-exe", default=_find_default_blender_exe(), help="Path to blender.exe.")
    parser.add_argument(
        "--addon-dir",
        default=str((repo_root / "lime_pipeline").resolve()),
        help="Absolute addon package directory.",
    )
    parser.add_argument("--module-name", default="lime_pipeline", help="Addon module name.")
    parser.add_argument(
        "--launch-py",
        default=None,
        help="Optional explicit path to Blender Development pythonFiles/launch.py.",
    )
    parser.add_argument(
        "--editor-port",
        type=int,
        default=17342,
        help="Editor server port for blender-development mode.",
    )
    return parser


def _run_command(command: list[str], env: dict[str, str] | None = None) -> int:
    printable = " ".join(f"\"{arg}\"" if " " in arg else arg for arg in command)
    print(f"[blender_dev_start] Running: {printable}")
    process = subprocess.run(command, env=env)
    return process.returncode


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = _build_parser(repo_root)
    args, blender_args = parser.parse_known_args()
    if blender_args and blender_args[0] == "--":
        blender_args = blender_args[1:]

    blender_exe = str(Path(args.blender_exe).expanduser())
    addon_dir = str(Path(args.addon_dir).expanduser().resolve())

    if args.mode == "direct":
        launcher = repo_root / "tools" / "launch_blender5_interactive.py"
        command = [blender_exe, "--python", str(launcher), *blender_args]
        return _run_command(command)

    launch_py = _find_blender_development_launch_py(args.launch_py)
    env = dict(os.environ)
    env["ADDONS_TO_LOAD"] = json.dumps(
        [{"load_dir": addon_dir, "module_name": args.module_name}],
        ensure_ascii=False,
    )
    env["EDITOR_PORT"] = str(args.editor_port)
    command = [blender_exe, "--python", str(launch_py), *blender_args]
    return _run_command(command, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
