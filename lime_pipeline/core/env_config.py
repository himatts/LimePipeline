"""Environment configuration helpers for local secrets and API credentials."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict


_CACHE_PATH: Path | None = None
_CACHE_MTIME: float | None = None
_CACHE_VALUES: Dict[str, str] = {}


def _resolve_env_file() -> Path:
    """Return the .env path, allowing override via LIME_PIPELINE_ENV_FILE."""
    override = (os.getenv("LIME_PIPELINE_ENV_FILE") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    # Repository root when developing from source.
    return Path(__file__).resolve().parents[2] / ".env"


def env_file_path() -> Path:
    return _resolve_env_file()


def _parse_env(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return values

    for line in lines:
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith("export "):
            raw = raw[7:].strip()
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        values[key] = value
    return values


def _values() -> Dict[str, str]:
    global _CACHE_PATH, _CACHE_MTIME, _CACHE_VALUES

    path = _resolve_env_file()
    mtime: float | None
    try:
        mtime = path.stat().st_mtime
    except Exception:
        mtime = None

    if _CACHE_PATH == path and _CACHE_MTIME == mtime:
        return _CACHE_VALUES

    _CACHE_PATH = path
    _CACHE_MTIME = mtime
    _CACHE_VALUES = _parse_env(path) if mtime is not None else {}
    return _CACHE_VALUES


def get_env(name: str, default: str = "") -> str:
    value = (_values().get(name) or "").strip()
    return value or default


def get_openrouter_api_key() -> str:
    return get_env("LIME_OPENROUTER_API_KEY") or get_env("OPENROUTER_API_KEY")


def get_krea_api_key() -> str:
    return get_env("LIME_KREA_API_KEY") or get_env("KREA_API_KEY")


def has_openrouter_api_key() -> bool:
    return bool(get_openrouter_api_key())


def has_krea_api_key() -> bool:
    return bool(get_krea_api_key())

