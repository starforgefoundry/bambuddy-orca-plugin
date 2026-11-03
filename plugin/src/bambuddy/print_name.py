"""The name a print gets in the Bambuddy library: a base the user can edit, then OrcaSlicer's plate suffix."""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace

GCODE_3MF_SUFFIX = ".gcode.3mf"
FALLBACK_BASE = "OrcaSlicer"
PROJECT_EXTENSION = re.compile(r"(\.gcode)?\.3mf$", re.IGNORECASE)
UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe(text: str) -> str:
    return UNSAFE_FILENAME_CHARS.sub("_", text.strip())


def plate_suffixes(plates: Iterable[int], labels: Mapping[int, str]) -> list[str]:
    """What OrcaSlicer appends to the project name for each plate: its label, or its number when unlabeled."""
    return [f"_{labels[plate]}" if labels.get(plate) else f"_plate_{plate}" for plate in plates]


@dataclass(frozen=True)
class PrintName:
    base: str
    suffix: str = ""

    @classmethod
    def from_project(cls, project_name: str, suffixes: Iterable[str] = ()) -> "PrintName":
        stem = PROJECT_EXTENSION.sub("", project_name.strip())
        suffix = next((s for s in suffixes if len(stem) > len(s) and stem.endswith(s)), "")
        return cls(stem.removesuffix(suffix), suffix)

    def renamed(self, base: str) -> "PrintName":
        return replace(self, base=base)

    @property
    def file_name(self) -> str:
        return (_safe(self.base) or FALLBACK_BASE) + _safe(self.suffix) + GCODE_3MF_SUFFIX
