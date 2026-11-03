"""Reads what a sliced .gcode.3mf contains: the printer it was made for and the plates it carries G-code for."""

import base64
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from .models import short_name

SLICE_INFO = "Metadata/slice_info.config"
PROJECT_SETTINGS = "Metadata/project_settings.config"
MODEL_SETTINGS = "Metadata/model_settings.config"
PLATE_ID_KEY = "plater_id"
PLATE_NAME_KEY = "plater_name"
PLATE_GCODE = re.compile(r"^Metadata/plate_(\d+)\.gcode$")
PNG_DATA_URI = "data:image/png;base64,"


def preview_names(plate: int) -> tuple[str, str]:
    return f"Metadata/plate_{plate}_small.png", f"Metadata/plate_{plate}.png"


def plate_previews(path: Path, plates: list[int]) -> dict[int, str]:
    """Each plate's preview from the file as a data URI, preferring the small render."""
    previews: dict[int, str] = {}
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            for plate in plates:
                name = next((n for n in preview_names(plate) if n in names), None)
                if name:
                    previews[plate] = PNG_DATA_URI + base64.b64encode(archive.read(name)).decode()
    except (OSError, zipfile.BadZipFile):
        return {}
    return previews


def sliced_plates(path: Path) -> list[int]:
    """1-based numbers of the plates with G-code, in order. Print all exports every sliced plate."""
    try:
        with zipfile.ZipFile(path) as archive:
            numbers = {int(match.group(1)) for name in archive.namelist() if (match := PLATE_GCODE.match(name))}
    except (OSError, zipfile.BadZipFile):
        return []
    return sorted(numbers)


def plate_labels(path: Path) -> dict[int, str]:
    """The names given to plates in OrcaSlicer, by 1-based plate number."""
    try:
        with zipfile.ZipFile(path) as archive:
            root = ElementTree.fromstring(archive.read(MODEL_SETTINGS))
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError):
        return {}
    labels: dict[int, str] = {}
    for plate in root.iter("plate"):
        meta = {m.get("key"): m.get("value") or "" for m in plate.findall("metadata")}
        if meta.get(PLATE_ID_KEY, "").isdigit() and meta.get(PLATE_NAME_KEY):
            labels[int(meta[PLATE_ID_KEY])] = meta[PLATE_NAME_KEY]
    return labels


def sliced_model(path: Path) -> str | None:
    """The short model name (e.g. "H2S"), or None when the file doesn't say or can't be read."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if SLICE_INFO in names:
                for meta in ElementTree.fromstring(archive.read(SLICE_INFO)).iter("metadata"):
                    if meta.get("key") == "printer_model_id" and (model := short_name(meta.get("value") or "")):
                        return model
            if PROJECT_SETTINGS in names:
                return short_name(json.loads(archive.read(PROJECT_SETTINGS)).get("printer_model") or "")
    except (OSError, zipfile.BadZipFile, ElementTree.ParseError, ValueError):
        return None
    return None
