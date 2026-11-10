"""Send defaults, edited on the Bambuddy agent's page in OrcaSlicer's plugin settings."""

import json
from typing import Any

DEFAULT_SETTINGS: dict[str, bool] = {
    "requireExactColors": True,
    "groupPlates": False,
    "bedLevelling": True,
    "flowCali": False,
    "vibrationCali": False,
    "timelapse": False,
}
PRINT_OPTION_KEYS = ("bedLevelling", "flowCali", "vibrationCali", "timelapse")


def effective_settings(config_json: str | None) -> dict[str, bool]:
    """The stored settings over the defaults; anything missing or of the wrong type falls back."""
    try:
        stored: Any = json.loads(config_json) if config_json else {}
    except ValueError:
        stored = {}
    if not isinstance(stored, dict):
        stored = {}
    return {key: stored[key] if isinstance(stored.get(key), bool) else default for key, default in DEFAULT_SETTINGS.items()}


def print_options(settings: dict[str, bool]) -> dict[str, bool]:
    return {key: settings[key] for key in PRINT_OPTION_KEYS}
