"""Printer, filament and process profiles saved in Bambuddy's local presets, planned for the bundle."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from .filaments import VARIANT_SEPARATOR, StockedFilament, config_list
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
INHERITS_KEY = "inherits"
COMPATIBLE_PRINTERS_KEY = "compatible_printers"


@dataclass(frozen=True)
class SharedProfile:
    id: int
    folder: str
    name: str
    setting: Mapping[str, Any]

    @property
    def parent(self) -> str:
        return str(self.setting.get(INHERITS_KEY) or "")

    @property
    def compatible_printers(self) -> list[str]:
        value = self.setting.get(COMPATIBLE_PRINTERS_KEY)
        return [str(v) for v in value] if isinstance(value, list) else config_list(value)

    @property
    def stock_family(self) -> str:
        return (self.parent or self.name).split(VARIANT_SEPARATOR)[0]

    def system_printer(self, printers_in_farm: set[str]) -> str:
        """A copy of a stock printer profile inherits a shared template, so its model and nozzle name the printer."""
        if self.parent in printers_in_farm:
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


def merge_shared_parents(profiles: Iterable[SharedProfile]) -> list[SharedProfile]:
    """Bambuddy can only fill in stock parents, so a profile based on another Bambuddy profile arrives with just its
    own changes. Merging the chain leaves each profile with a stock parent or none."""
    profiles = list(profiles)
    by_name = {(p.folder, p.name): p for p in profiles}

    def merged(profile: SharedProfile) -> SharedProfile:
        setting, seen = dict(profile.setting), {profile.name}
        parent = by_name.get((profile.folder, profile.parent))
        while parent is not None and parent.name not in seen:
            seen.add(parent.name)
            setting = {**parent.setting, **setting, INHERITS_KEY: parent.parent}
            parent = by_name.get((profile.folder, parent.parent))
        return replace(profile, setting=setting)

    return [merged(p) for p in profiles]


@dataclass(frozen=True)
class SharedPlan:
    printers: dict[str, SharedProfile]
    profiles: list[PlannedProfile]
    skipped: list[SkippedModel]
    # A spool set to a Bambuddy profile stores the profile's id and full name.
    stock_families_by_reference: Mapping[str, str]

    def stock_family(self, filament: StockedFilament) -> str | None:
        """The stock family behind the Bambuddy profile a spool is set to, so printers the profile doesn't cover
        still get stock presets."""
        references = self.stock_families_by_reference
        return references.get(filament.filament_id or "") or references.get(filament.family)


def plan_shared(
    profiles: Iterable[SharedProfile],
    printer_presets: Iterable[str],
    existing_names: Mapping[str, str],
    system_presets: Mapping[str, frozenset[str]],
    orca_filament_ids: Mapping[str, str],
) -> SharedPlan:
    """printer_presets are the system printers being imported, existing_names the names they were saved under, and
    orca_filament_ids maps Bambu filament ids to OrcaSlicer's."""
    printers_in_farm = set(printer_presets)
    printers: dict[str, SharedProfile] = {}
    others: list[SharedProfile] = []
    skipped: list[SkippedModel] = []
    for profile in sorted(merge_shared_parents(profiles), key=lambda p: p.name):
        if not profile.name.strip() or UNSAFE_NAME_CHARS.search(profile.name):
            skipped.append(SkippedModel(profile.name, "the name has characters a profile name can't use"))
        elif profile.folder != MACHINE_DIR:
            others.append(profile)
        elif (printer := profile.system_printer(printers_in_farm)) not in printers_in_farm:
            skipped.append(SkippedModel(profile.name, f"no {printer} printer on Bambuddy"))
        elif printer in printers:
            skipped.append(SkippedModel(profile.name, f"{printers[printer].name} is already used for {printer}"))
        else:
            printers[printer] = profile

    # Bundle printers load under a bundle-prefixed name, so OrcaSlicer only matches them through their system parent.
    system_printer_by_name = {name: printer for printer, name in existing_names.items()}
    system_printer_by_name.update({profile.name: printer for printer, profile in printers.items()})
    planned: list[PlannedProfile] = []
    references: dict[str, str] = {}
    for profile in others:
        compatible = [system_printer_by_name.get(name, name) for name in profile.compatible_printers]
        if compatible and printers_in_farm.isdisjoint(compatible):
            skipped.append(SkippedModel(profile.name, "not compatible with the printers on Bambuddy"))
            continue
        settings = profile.settings
        if compatible:
            settings[COMPATIBLE_PRINTERS_KEY] = compatible
        planned.append(_bundle_profile(profile, settings, system_presets.get(profile.folder, frozenset()), orca_filament_ids))
        if profile.folder == FILAMENT_DIR:
            references.update({str(profile.id): profile.stock_family, profile.name: profile.stock_family})
    return SharedPlan(printers, planned, skipped, references)


def _bundle_profile(
    profile: SharedProfile, settings: dict[str, Any], system_presets: frozenset[str], orca_filament_ids: Mapping[str, str]
) -> PlannedProfile:
    """OrcaSlicer gives a preset with a parent the parent's filament id, and the Bambu color palette is looked up by
    that id. A preset without a parent keeps its own, so it gets OrcaSlicer's form of a Bambu id."""
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
