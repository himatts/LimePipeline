from pathlib import Path


def paths_for_type(root: Path, ptype: str, rev: str, sc: int | None):
    """Return tuple: (ramv, folder_type, scenes, target_dir, backups).

    - ramv: Base RAMV directory under project root
    - folder_type: Directory for project type and revision
    - scenes: Scenes directory if applicable, else None
    - target_dir: Directory where .blend should be placed
    - backups: Directory for backups under folder_type
    """
    ramv = root / r"2. Graphic & Media" / r"3. Rendering-Animation-Video"

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


