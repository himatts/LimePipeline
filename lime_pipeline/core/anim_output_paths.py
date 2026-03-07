"""
Pure helpers for animation output path resolution.

These functions keep path rules deterministic and Blender-agnostic so shared
and local output variants can be tested outside Blender.
"""

from __future__ import annotations

from pathlib import Path

from .paths import paths_for_type


def build_pipeline_anim_output_path(
    root: str | Path,
    container_ptype: str,
    rev: str,
    sc_number: int,
    shot_idx: int,
    *,
    use_test_variant: bool,
    local_mode: bool = False,
) -> Path:
    """Build the animation output path inside the project pipeline structure."""
    root_path = Path(root)
    _ramv, folder_type, _scenes, _target, _backups = paths_for_type(
        root_path,
        container_ptype,
        rev,
        sc_number,
        local=local_mode,
    )
    shot_token = f"SC{sc_number:03d}_SH{shot_idx:02d}"
    target_dir = folder_type / shot_token
    basename = f"{shot_token}_"
    if use_test_variant:
        target_dir = target_dir / "test"
        basename = f"{shot_token}_test_"
    return target_dir / basename


def build_local_anim_output_path(
    local_base_dir: str | Path,
    project_name: str,
    sc_number: int,
    shot_idx: int,
    *,
    use_test_variant: bool,
) -> Path:
    """Build the override local animation output path outside the shared tree."""
    base = Path(local_base_dir)
    shot_token = f"SC{sc_number:03d}_SH{shot_idx:02d}"
    target_dir = base / project_name / shot_token
    basename = f"{shot_token}_"
    if use_test_variant:
        target_dir = target_dir / "test"
        basename = f"{shot_token}_test_"
    return target_dir / basename


__all__ = [
    "build_pipeline_anim_output_path",
    "build_local_anim_output_path",
]
