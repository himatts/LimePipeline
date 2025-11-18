"""
Project Path and Directory Structure Utilities

This module defines the canonical directory structure for Lime Pipeline projects
following the RAMV (Rendering-Animation-Media-Video) organizational standard.
It provides utilities for constructing project paths based on project type, revision,
and scene requirements.

The RAMV structure organizes projects hierarchically:
- Project Root (XX-##### format)
  - 2. Graphic & Media/
    - 3. Rendering-Animation-Video/
      - 3D Base Model/Rev X/
      - Proposal Views/Rev X/scenes/
      - Renders/Rev X/scenes/
      - Storyboard/Rev X/scenes/
      - Animation/Rev X/scenes/
      - tmp/Rev X/

Key Features:
- Canonical RAMV directory path construction
- Project type-based directory mapping (BASE, PV, REND, SB, ANIM, TMP)
- Automatic scenes directory creation for applicable project types
- Backups directory management per revision
- Integration with Lime Pipeline naming conventions
- Path validation and error handling for missing directories
"""

from pathlib import Path

# Canonical RAMV directory segments under a project root
RAMV_DIR_1 = r"2. Graphic & Media"
RAMV_DIR_2 = r"3. Rendering-Animation-Video"


def get_ramv_dir(root: Path) -> Path:
    """Return the base RAMV directory for a given project root."""
    return root / RAMV_DIR_1 / RAMV_DIR_2


def paths_for_type(root: Path, ptype: str, rev: str, sc: int | None, *, local: bool = False):
    """Return tuple: (ramv, folder_type, scenes, target_dir, backups).

    - ramv: Base directory used for type folders (root in local mode, RAMV dir otherwise)
    - folder_type: Directory for project type and revision
    - scenes: Scenes directory if applicable, else None
    - target_dir: Directory where .blend should be placed
    - backups: Directory for backups under folder_type
    """
    ramv = root if local else get_ramv_dir(root)

    if ptype == 'BASE':
        folder_type = ramv / "3D Base Model" / f"Rev {rev}"
        scenes = None
    elif ptype == 'PV':
        folder_type = ramv / "Proposal Views" / f"Rev {rev}"
        scenes = folder_type / "scenes"
    elif ptype == 'REND':
        folder_type = ramv / "Renders" / f"Rev {rev}"
        scenes = folder_type / "scenes"
    elif ptype == 'SB':
        folder_type = ramv / "Storyboard" / f"Rev {rev}"
        scenes = folder_type / "scenes"
    elif ptype == 'ANIM':
        folder_type = ramv / "Animation" / f"Rev {rev}"
        scenes = folder_type / "scenes"
    elif ptype == 'TMP':
        folder_type = ramv / "tmp" / f"Rev {rev}"
        scenes = None
    else:
        raise ValueError("Unknown project type")

    target_dir = scenes if scenes else folder_type
    backups = folder_type / "backups"
    return ramv, folder_type, scenes, target_dir, backups


