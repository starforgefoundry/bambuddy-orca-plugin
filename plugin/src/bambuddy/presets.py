"""Builds OrcaSlicer printer and filament presets for the printers and filaments on a Bambuddy instance."""

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from .filaments import PlannedFilament
from .models import DEFAULT_NOZZLE, DUAL_NOZZLE_ORCA_MODELS, orca_model, short_name, system_preset_name

AGENT_ID = "bambuddy"
BUNDLE_ID = "bambuddy"
DEFAULT_BUNDLE_NAME = "Bambuddy"
METADATA_FILE = "bundle_metadata.json"
MACHINE_DIR = "machine"
FILAMENT_DIR = "filament"
DEFAULT_NAME_PREFIX = "Bambuddy"
# OrcaSlicer only requires a parseable version; it re-derives it from the parent on save.
PRESET_VERSION = "2.5.0.0"
UNSAFE_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Print must go through the printer agent rather than OrcaSlicer's print-host upload.
USE_PRINT_HOST_OFF = "0"


@dataclass(frozen=True)
class PrinterModel:
    model: str
    nozzle: str = DEFAULT_NOZZLE


@dataclass(frozen=True)
class PlannedPreset:
    name: str
    inherits: str

    def to_json(self, instance_url: str) -> dict[str, str]:
        return {
            "type": "machine",
            "version": PRESET_VERSION,
            "name": self.name,
            "from": "User",
            "instantiation": "true",
            "inherits": self.inherits,
            "printer_settings_id": self.name,
            "printer_agent": AGENT_ID,
            "print_host": instance_url,
            "bbl_use_printhost": USE_PRINT_HOST_OFF,
        }


@dataclass(frozen=True)
class SkippedModel:
    model: str
    reason: str


@dataclass(frozen=True)
class PresetPlan:
    presets: list[PlannedPreset]
    skipped: list[SkippedModel]


def default_preset_name(model: str, nozzle: str) -> str:
    """Short on purpose: OrcaSlicer hides the printer picture when the selected name is too wide."""
    name = f"{DEFAULT_NAME_PREFIX} {short_name(model) or model}"
    return name if nozzle == DEFAULT_NOZZLE else f"{name} {nozzle}"


def plan_presets(
    printers: Iterable[PrinterModel],
    has_system_preset: Callable[[str], bool],
    existing_names: dict[str, str] | None = None,
) -> PresetPlan:
    existing_names = existing_names or {}
    presets: dict[str, PlannedPreset] = {}
    skipped: dict[str, SkippedModel] = {}
    for printer in printers:
        orca_name = orca_model(printer.model)
        if orca_name is None:
            skipped[printer.model] = SkippedModel(printer.model, "unknown printer model")
            continue
        if orca_name in DUAL_NOZZLE_ORCA_MODELS:
            skipped[orca_name] = SkippedModel(orca_name, "dual-nozzle printers are not supported yet")
            continue
        inherits = system_preset_name(orca_name, printer.nozzle)
        if not has_system_preset(inherits):
            skipped[inherits] = SkippedModel(inherits, "no matching OrcaSlicer system profile")
            continue
        name = existing_names.get(inherits) or default_preset_name(printer.model, printer.nozzle)
        presets[inherits] = PlannedPreset(name, inherits)
    return PresetPlan(sorted(presets.values(), key=lambda p: p.name), list(skipped.values()))


def name_problem(presets: list[PlannedPreset]) -> str | None:
    seen: set[str] = set()
    for preset in presets:
        name = preset.name
        if not name.strip():
            return f"Name the profile based on {preset.inherits}."
        if name != name.strip() or UNSAFE_NAME_CHARS.search(name):
            return f'"{name}" contains characters a profile name can\'t use.'
        if name in seen:
            return f'"{name}" is used twice.'
        seen.add(name)
    return None


class BundleStore:
    """A local preset bundle, <data_dir>/user/<folder>/_local/bambuddy, that OrcaSlicer can reload while running."""

    def __init__(self, bundle_dir: Path):
        self._dir = bundle_dir

    def existing_names(self) -> dict[str, str]:
        """Names of previously saved printer presets, by the system preset they inherit."""
        names = {}
        for path in self._files(MACHINE_DIR):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            names[data.get("inherits", "")] = data.get("name", path.stem)
        return names

    def bundle_name(self) -> str:
        try:
            return json.loads((self._dir / METADATA_FILE).read_text(encoding="utf-8"))["name"] or DEFAULT_BUNDLE_NAME
        except (OSError, ValueError, KeyError):
            return DEFAULT_BUNDLE_NAME

    def clear(self) -> None:
        self.write(self.bundle_name(), [], [], "")

    def write(
        self, bundle_name: str, printers: list[PlannedPreset], filaments: list[PlannedFilament], instance_url: str
    ) -> None:
        for path in self._files(MACHINE_DIR) + self._files(FILAMENT_DIR):
            path.unlink()
        for preset in printers:
            self._write(self._dir / MACHINE_DIR / f"{preset.name}.json", preset.to_json(instance_url))
        for filament in filaments:
            self._write(self._dir / FILAMENT_DIR / f"{filament.name}.json", filament_json(filament))
        self._write(self._dir / METADATA_FILE, {"id": BUNDLE_ID, "name": bundle_name, "version": PRESET_VERSION})

    def _write(self, path: Path, data: dict[str, str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")

    def _files(self, subdir: str) -> list[Path]:
        folder = self._dir / subdir
        return sorted(folder.glob("*.json")) if folder.is_dir() else []


def filament_json(filament: PlannedFilament) -> dict[str, str]:
    """A bundle copy of a system filament preset, so it shows in OrcaSlicer without enabling it by hand."""
    data = {
        "type": "filament",
        "name": filament.name,
        "from": "User",
        "instantiation": "true",
        "version": PRESET_VERSION,
        "inherits": filament.name,
        "filament_settings_id": filament.name,
    }
    if filament.filament_id:
        data["filament_id"] = filament.filament_id
    return data


def remove_legacy_presets(machine_dir: Path) -> None:
    """Earlier versions wrote plain user presets, which OrcaSlicer only loads at startup."""
    if not machine_dir.is_dir():
        return
    for path in machine_dir.glob("*.json"):
        try:
            owned = json.loads(path.read_text(encoding="utf-8")).get("printer_agent") == AGENT_ID
        except (OSError, ValueError):
            continue
        if owned:
            path.unlink()
            path.with_suffix(".info").unlink(missing_ok=True)
