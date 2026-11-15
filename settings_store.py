"""Persistent search/scan settings shared by the UI and cloud worker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SETTINGS_PATH = Path(__file__).resolve().parent / "settings.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "focus_region": True,
    "cities": ["רמלה", "לוד"],
    "city_keyword": "רמלה לוד",
    "use_web": True,
    "use_social": True,
    "use_yad2": False,
    "mock_mode": False,
    "include_apartments": True,
    "include_units": True,
    "ground_floor_only": False,
    "min_price": 0,
    "max_price": 3500,
    "min_rooms": 3.0,
    "max_rooms": 0,
    "min_floor": 0,
    "max_floor": 0,
    "private_only": False,
    "interval_minutes": 30,
    "enabled": True,
    "notify_enabled": True,
    "telegram_chat_id": "",
}


def load_settings() -> dict[str, Any]:
    data = dict(DEFAULT_SETTINGS)
    if SETTINGS_PATH.exists():
        try:
            loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass
    return data


def save_settings(updates: dict[str, Any]) -> dict[str, Any]:
    data = load_settings()
    data.update(updates or {})
    SETTINGS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return data
