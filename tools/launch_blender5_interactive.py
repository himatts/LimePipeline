from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_PARENT = REPO_ROOT.parent

if str(REPO_PARENT) not in sys.path:
    sys.path.insert(0, str(REPO_PARENT))

import lime_pipeline


def main() -> None:
    try:
        lime_pipeline.unregister()
    except Exception:
        pass

    lime_pipeline.register()
    print(f"[Lime Pipeline] Interactive Blender 5 session loaded from: {lime_pipeline.__file__}")


if __name__ == "__main__":
    main()
