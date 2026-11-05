"""Translates between Bambuddy API payloads and the send window's data shapes."""

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .models import short_name

AMS_HT_MIN_ID = 128
TRAYS_PER_AMS = 4
EXTERNAL_SPOOL_LABELS = {254: "Ext-L", 255: "Ext"}
TRAY_STATE_EMPTY = 9

DISPATCH_QUEUE = "queue"
TARGET_PRINTER = "printer"
TRISTATE_ON = "auto"
TRISTATE_OFF = "off"


def _hex_color(value: str | None) -> str:
    return f"#{(value or '')[:6] or '808080'}"


def compatible_printers(printers: list[dict[str, Any]], model: str) -> list[dict[str, Any]]:
    """Printers that accept jobs sliced for `model`, by model or by opting in through accepted_models."""
    wanted = short_name(model)
    return [
        {"id": p["id"], "name": p["name"], "model": p["model"], "location": p.get("location") or None}
        for p in printers
        if p.get("is_active", True)
        and (short_name(p["model"]) == wanted or wanted in {short_name(m) for m in p.get("accepted_models") or []})
    ]


def _tray(global_id: int, label: str, raw: dict[str, Any]) -> dict[str, Any] | None:
    if not raw.get("tray_type") or raw.get("state") == TRAY_STATE_EMPTY:
        return None
    return {
        "globalId": global_id,
        "label": label,
        "type": raw["tray_type"],
        "color": _hex_color(raw.get("tray_color")),
        "subBrand": raw.get("tray_sub_brands") or None,
        "trayInfoIdx": raw.get("tray_info_idx") or None,
    }


def tray_label(ams_id: int, tray_id: int) -> str:
    if ams_id >= AMS_HT_MIN_ID:
        return f"HT{ams_id - AMS_HT_MIN_ID + 1}"
    return f"{chr(ord('A') + ams_id)}{tray_id + 1}"


def global_tray_id(ams_id: int, tray_id: int) -> int:
    return ams_id if ams_id >= AMS_HT_MIN_ID else ams_id * TRAYS_PER_AMS + tray_id


def loaded_trays(status: dict[str, Any]) -> list[dict[str, Any]]:
    trays: list[dict[str, Any] | None] = []
    for unit in status.get("ams") or []:
        for raw in unit.get("tray") or []:
            trays.append(_tray(global_tray_id(unit["id"], raw["id"]), tray_label(unit["id"], raw["id"]), raw))
    for raw in status.get("vt_tray") or []:
        trays.append(_tray(raw["id"], EXTERNAL_SPOOL_LABELS.get(raw["id"], "Ext"), raw))
    return [tray for tray in trays if tray]


def bambu_filament_ids(path: Path | None) -> dict[str, str]:
    """OrcaSlicer's own filament ids mapped to the ones Bambu printers report, e.g. OFoiVqVM -> GFA00."""
    if path is None:
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))["filaments"]
        return {orca_id: row["bambu_id"] for orca_id, row in rows.items() if row.get("bambu_id")}
    except (OSError, ValueError, KeyError, AttributeError):
        return {}


def _bambu_id(tray_info_idx: str | None, bambu_ids: Mapping[str, str]) -> str | None:
    return bambu_ids.get(tray_info_idx, tray_info_idx) if tray_info_idx else None


def file_filaments(requirements: dict[str, Any], bambu_ids: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    return [
        {
            "slotId": f["slot_id"],
            "type": f.get("type") or "?",
            "color": f.get("color") or "#808080",
            "usedGrams": f.get("used_grams") or 0,
            "trayInfoIdx": _bambu_id(f.get("tray_info_idx"), bambu_ids or {}),
        }
        for f in requirements.get("filaments") or []
        if f.get("used_in_plate", True)
    ]


def batch_payload(file_name: str, library_file_id: int, plate_count: int) -> dict[str, Any]:
    """Named the way Bambuddy names the batches its own print dialog makes."""
    base = re.sub(r"(\.gcode)?\.3mf$", "", file_name, flags=re.IGNORECASE) or "Batch"
    return {"name": f"{base} · {plate_count} plates", "library_file_id": library_file_id}


def request_quantity(request: dict[str, Any]) -> int:
    return max(1, int(request.get("quantity") or 1))


def queue_payload(
    request: dict[str, Any],
    library_file_id: int,
    plate_id: int,
    model: str,
    filaments: list[dict[str, Any]],
    batch_id: int | None = None,
) -> dict[str, Any]:
    options = request["options"]
    payload: dict[str, Any] = {
        "library_file_id": library_file_id,
        "plate_id": plate_id,
        "manual_start": request["dispatch"] == DISPATCH_QUEUE,
        "bed_levelling": TRISTATE_ON if options["bedLevelling"] else TRISTATE_OFF,
        "flow_cali": TRISTATE_ON if options["flowCali"] else TRISTATE_OFF,
        "vibration_cali": options["vibrationCali"],
        "timelapse": options["timelapse"],
    }
    if request_quantity(request) > 1:
        payload["quantity"] = request_quantity(request)
    if batch_id is not None:
        payload["batch_id"] = batch_id
    if request["targetKind"] == TARGET_PRINTER:
        payload["printer_id"] = request["printerId"]
        payload["ams_mapping"] = request["amsMapping"]
        return payload
    payload["target_model"] = short_name(model) or model
    if request.get("location"):
        payload["target_location"] = request["location"]
    if request.get("forceColorMatch"):
        payload["filament_overrides"] = [
            {
                "slot_id": f["slotId"],
                "type": f["type"],
                "color": f["color"],
                "tray_info_idx": f["trayInfoIdx"],
                "force_color_match": True,
            }
            for f in filaments
        ]
    return payload


def sent_summary(
    request: dict[str, Any], file_name: str, model: str, printers: list[dict[str, Any]], plate_count: int = 1
) -> str:
    """What the confirmation toast in OrcaSlicer says happened."""
    quantity = request_quantity(request)
    subject = file_name if plate_count == 1 else f"{plate_count} plates of {file_name}"
    if quantity > 1:
        subject = f"{quantity} copies of {subject}" if plate_count == 1 else f"{quantity} copies each of {subject}"
    verb = "is" if plate_count == 1 and quantity == 1 else "are"
    if request["targetKind"] == TARGET_PRINTER:
        where = next((p["name"] for p in printers if p["id"] == request["printerId"]), "the printer")
    else:
        where = f"the next free {model}"
        if request.get("location"):
            where += f" in {request['location']}"
    if request["dispatch"] == DISPATCH_QUEUE:
        return f"{subject} {verb} in the Bambuddy queue for {where}, waiting to be started."
    return f"{subject} {verb} queued in Bambuddy and will start on {where}."
