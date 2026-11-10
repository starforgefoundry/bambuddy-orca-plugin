"""Printer, filament and process profiles saved in Bambuddy's local presets, planned for the bundle."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from .filaments import StockedFilament, config_list
from .models import system_preset_name
from .presets import (
    FILAMENT_DIR,
    MACHINE_DIR,
    PROCESS_DIR,
    UNSAFE_NAME_CHARS,
    PlannedPreset,
    PlannedProfile,
    SkippedModel,
)

FOLDER_BY_PRESET_TYPE = {"printer": MACHINE_DIR, "filament": FILAMENT_DIR, "process": PROCESS_DIR}
# They name the system or cloud preset Bambuddy resolved the settings from, not the bundle copy.
SOURCE_KEYS = frozenset({"setting_id", "base_id", "is_custom_defined"})
FILAMENT_ID_KEY = "filament_id"


@dataclass(frozen=True)
class SharedProfile:
    id: int
    folder: str
    name: str
    setting: Mapping[str, Any]

    @property
    def parent(self) -> str:
        return str(self.setting.get("inherits") or "")

    @property
    def compatible_printers(self) -> list[str]:
        value = self.setting.get("compatible_printers")
        return [str(v) for v in value] if isinstance(value, list) else config_list(value)

    @property
    def system_printer(self) -> str:
        if self.parent:
            return self.parent
        return system_preset_name(str(self.setting.get("printer_model", "")), str(self.setting.get("printer_variant", "")))

    @property
    def settings(self) -> dict[str, Any]:
        return {key: value for key, value in self.setting.items() if key not in SOURCE_KEYS}


def shared_profile(detail: Mapping[str, Any]) -> SharedProfile | None:
    folder = FOLDER_BY_PRESET_TYPE.get(str(detail.get("preset_type")))
    if folder is None:
        return None
    return SharedProfile(int(detail["id"]), folder, str(detail.get("name", "")), detail.get("setting") or {})


@dataclass(frozen=True)
class SharedPlan:
    printers: dict[str, SharedProfile]
    profiles: list[PlannedProfile]
    skipped: list[SkippedModel]
    spool_references: frozenset[str]

    def covers(self, filament: StockedFilament) -> bool:
        """A spool set to a Bambuddy profile stores the profile's id and full name."""
        return filament.family in self.spool_references or filament.filament_id in self.spool_references


def plan_shared(
    profiles: Iterable[SharedProfile],
    printer_presets: Iterable[str],
    system_presets: Mapping[str, frozenset[str]],
    orca_filament_ids: Mapping[str, str],
) -> SharedPlan:
    """printer_presets are the system printers being imported; orca_filament_ids maps Bambu ids to OrcaSlicer's."""
    printers_in_farm = set(printer_presets)
    printers: dict[str, SharedProfile] = {}
    planned: list[PlannedProfile] = []
    skipped: list[SkippedModel] = []
    references: set[str] = set()
    for profile in sorted(profiles, key=lambda p: p.name):
        if not profile.name.strip() or UNSAFE_NAME_CHARS.search(profile.name):
            skipped.append(SkippedModel(profile.name, "the name has characters a profile name can't use"))
            continue
        if profile.folder == MACHINE_DIR:
            printer = profile.system_printer
            if printer not in printers_in_farm:
                skipped.append(SkippedModel(profile.name, f"no {printer} printer on Bambuddy"))
            elif printer in printers:
                skipped.append(SkippedModel(profile.name, f"{printers[printer].name} is already used for {printer}"))
            else:
                printers[printer] = profile
            continue
        compatible = profile.compatible_printers
        if compatible and printers_in_farm.isdisjoint(compatible):
            skipped.append(SkippedModel(profile.name, "not compatible with the printers on Bambuddy"))
            continue
        planned.append(_bundle_profile(profile, system_presets.get(profile.folder, frozenset()), orca_filament_ids))
        if profile.folder == FILAMENT_DIR:
            references.update({str(profile.id), profile.name})
    return SharedPlan(printers, planned, skipped, frozenset(references))


def _bundle_profile(
    profile: SharedProfile, system_presets: frozenset[str], orca_filament_ids: Mapping[str, str]
) -> PlannedProfile:
    """OrcaSlicer gives a preset with a parent the parent's filament id, and the Bambu color palette is looked up by
    that id. A preset without a parent keeps its own, so it gets OrcaSlicer's form of a Bambu id."""
    settings = profile.settings
    if profile.parent in system_presets:
        return PlannedProfile(profile.folder, profile.name, profile.parent, settings)
    filament_id = settings.get(FILAMENT_ID_KEY)
    if isinstance(filament_id, str):
        settings[FILAMENT_ID_KEY] = orca_filament_ids.get(filament_id, filament_id)
    return PlannedProfile(profile.folder, profile.name, "", settings)


def with_shared_printers(
    presets: Iterable[PlannedPreset], shared: Mapping[str, SharedProfile], existing_names: Mapping[str, str]
) -> list[PlannedPreset]:
    def apply(preset: PlannedPreset) -> PlannedPreset:
        profile = shared.get(preset.inherits)
        if profile is None:
            return preset
        name = existing_names.get(preset.inherits) or profile.name
        return replace(preset, name=name, shared=profile.name, settings=profile.settings)

    return sorted((apply(p) for p in presets), key=lambda p: p.name)
