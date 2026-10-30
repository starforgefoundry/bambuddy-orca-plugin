"""Locates OrcaSlicer's data and resource directories."""

import os
import sys
from collections.abc import Mapping
from pathlib import Path

PLUGINS_DIR_NAME = "orca_plugins"
APP_DIR_NAME = "OrcaSlicer"
BAMBU_FILAMENT_IDS_FILE = Path("printers") / "bambu_filament_ids.json"
# In wxFileName::GetTempDir's order; not tempfile.gettempdir(), which writes a probe file OrcaSlicer would ask about.
TEMP_DIR_ENV_VARS = ("TMPDIR", "TMP", "TEMP", "TEMPDIR")
FALLBACK_TEMP_DIR = "/tmp"
SLICED_MODELS_DIR_NAME = "orcaslicer_model"


def data_dir(module_file: str) -> Path:
    for parent in Path(module_file).parents:
        if parent.name == PLUGINS_DIR_NAME:
            return parent.parent
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    if sys.platform == "win32":
        return Path(os.environ["APPDATA"]) / APP_DIR_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_DIR_NAME


def sliced_files_dir(env: Mapping[str, str] = os.environ, uid: int | None = None) -> Path:
    """Where OrcaSlicer keeps the sliced project it hands the printer agent; a new subfolder every session."""
    temp_dir = Path(next((env[name] for name in TEMP_DIR_ENV_VARS if env.get(name)), FALLBACK_TEMP_DIR))
    user_temp_dir = temp_dir if uid is None else temp_dir / f"orcaslicer_{uid}"
    return user_temp_dir / SLICED_MODELS_DIR_NAME


def bambu_filament_ids_file(python_home: Path = Path(sys.prefix)) -> Path | None:
    """OrcaSlicer's bundled Python sits in MacOS/python (macOS), lib/python (Linux) or beside the exe (Windows)."""
    resource_dirs = [
        python_home.parent.parent / "Resources",
        python_home.parent.parent / "resources",
        python_home.parent / "resources",
    ]
    candidates = (d / BAMBU_FILAMENT_IDS_FILE for d in resource_dirs)
    return next((path for path in candidates if path.is_file()), None)
