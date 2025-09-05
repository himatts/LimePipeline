import re
from pathlib import Path


RE_SC = re.compile(r"_SC(\d{3})_")


def used_scene_numbers(dirpath: Path) -> set[int]:
    numbers: set[int] = set()
    if dirpath and dirpath.is_dir():
        for path in dirpath.glob("*.blend"):
            match = RE_SC.search(path.name)
            if match:
                numbers.add(int(match.group(1)))
    return numbers


def suggest_next_scene(dirpath: Path, step: int = 10) -> int:
    used = used_scene_numbers(dirpath)
    candidate = step
    while candidate <= 999 and candidate in used:
        candidate += step
    return candidate if candidate <= 999 else -1


