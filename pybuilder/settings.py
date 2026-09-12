"""Persistance : dernière configuration, fichiers récents et préférences d'affichage."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings

from . import APP_NAME
from .models import BuildConfig

ORGANISATION = "PyBuilder"
MAX_RECENT = 10


def _settings() -> QSettings:
    return QSettings(ORGANISATION, APP_NAME)


def save_config(config: BuildConfig) -> None:
    _settings().setValue("config", json.dumps(config.to_dict(), ensure_ascii=False))


def load_config() -> BuildConfig:
    raw = _settings().value("config", "")
    if not raw:
        return BuildConfig()
    try:
        return BuildConfig.from_dict(json.loads(raw))
    except (ValueError, TypeError):
        return BuildConfig()


def recent_scripts() -> list[str]:
    raw = _settings().value("recent", [])
    if isinstance(raw, str):
        raw = [raw] if raw else []
    return [item for item in list(raw) if Path(item).is_file()]


def push_recent(path: str) -> list[str]:
    items = [path] + [item for item in recent_scripts() if item != path]
    items = items[:MAX_RECENT]
    _settings().setValue("recent", items)
    return items


def save_theme(name: str) -> None:
    _settings().setValue("theme", name)


def load_theme(default: str = "dark") -> str:
    return str(_settings().value("theme", default))


def save_geometry(data) -> None:
    _settings().setValue("geometry", data)


def load_geometry():
    return _settings().value("geometry")
