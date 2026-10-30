"""Maps the spools in Bambuddy's inventory to OrcaSlicer's built-in Bambu Lab and Generic filament presets."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

SUPPORTED_VENDORS = {"Bambu Lab", "Generic"}
QUOTED_VALUE = re.compile(r'"((?:[^"\\]|\\.)*)"')
# System presets are named "<family> @<printer variant>", e.g. "Bambu PLA Basic @BBL X1C".
VARIANT_SEPARATOR = " @"
BRAND_ALIASES = {"Bambu Lab": "Bambu"}


def config_list(value: str | None) -> list[str]:
    """Splits a serialized OrcaSlicer string-vector option such as `"a";"b"`."""
    if not value:
        return []
    quoted = QUOTED_VALUE.findall(value)
    return [v.replace('\\"', '"') for v in quoted] if quoted else [value]


@dataclass(frozen=True)
class SystemFilament:
    name: str
    vendor: str
    compatible_printers: frozenset[str]

    @property
    def family(self) -> str:
        return self.name.split(VARIANT_SEPARATOR)[0]


@dataclass(frozen=True)
class StockedFilament:
    family: str
    description: str
    filament_id: str | None = None


@dataclass(frozen=True)
class PlannedFilament:
    name: str
    # OrcaSlicer only offers a brand's color palette when the preset carries its filament id, and bundle
    # presets don't inherit it from their parent.
    filament_id: str | None


@dataclass(frozen=True)
class FilamentPlan:
    presets: list[PlannedFilament]
    unmapped: list[StockedFilament]

    def problem(self) -> str | None:
        if not self.unmapped:
            return None
        listed = ", ".join(f.description for f in self.unmapped)
        return f"These spools don't match a Bambu Lab or Generic OrcaSlicer preset: {listed}"


def stocked_filaments(spools: Iterable[dict[str, Any]]) -> list[StockedFilament]:
    """One entry per preset family in stock; colors don't matter since they are picked in OrcaSlicer."""
    stocked: dict[str, StockedFilament] = {}
    for spool in spools:
        if spool.get("archived_at"):
            continue
        brand = (spool.get("brand") or "").strip()
        parts = [BRAND_ALIASES.get(brand, brand), spool.get("material") or "", spool.get("subtype") or ""]
        derived = " ".join(p.strip() for p in parts if p and p.strip())
        family = (spool.get("slicer_filament_name") or "").strip() or derived
        filament_id = (spool.get("slicer_filament") or "").strip() or None
        known = stocked.get(family)
        if known is None or (known.filament_id is None and filament_id):
            stocked[family] = StockedFilament(family, family or "a spool with no material set", filament_id)
    return list(stocked.values())


def _variant_for(printer: str, candidates: list[SystemFilament]) -> SystemFilament | None:
    """Prefer the variant made for this printer over one that fits every printer."""
    exact = next((c for c in candidates if printer in c.compatible_printers), None)
    return exact or next((c for c in candidates if not c.compatible_printers), None)


def plan_filaments(
    stocked: Iterable[StockedFilament], printer_presets: Iterable[str], system_filaments: Iterable[SystemFilament]
) -> FilamentPlan:
    """One preset per stocked filament per printer: the system variant compatible with that printer's parent preset."""
    by_family: dict[str, list[SystemFilament]] = {}
    for filament in system_filaments:
        if filament.vendor in SUPPORTED_VENDORS:
            by_family.setdefault(filament.family, []).append(filament)

    printers = list(printer_presets)
    presets: dict[str, PlannedFilament] = {}
    unmapped: list[StockedFilament] = []
    for filament in stocked:
        candidates = by_family.get(filament.family)
        if not candidates:
            unmapped.append(filament)
            continue
        for printer in printers:
            variant = _variant_for(printer, candidates)
            if variant:
                presets[variant.name] = PlannedFilament(variant.name, filament.filament_id)
    return FilamentPlan([presets[name] for name in sorted(presets)], unmapped)
