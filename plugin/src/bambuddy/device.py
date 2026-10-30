"""Bambu LAN protocol replies that make OrcaSlicer treat the Bambuddy server as an idle, ready printer."""

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .models import MODEL_ID_BY_ORCA_MODEL

DEVICE_NAME = "Bambuddy"
DEVICE_SERIAL = "BAMBUDDY0001"
DEFAULT_NOZZLE_TYPE = "hardened_steel"
# OrcaSlicer only enables "Send" for firmware at or above 01.01.01.00.
FIRMWARE_VERSION = "01.09.00.00"
# The network library's placeholder LAN access code.
ACCESS_CODE = "88888888"


@dataclass(frozen=True)
class DeviceProfile:
    model_id: str
    nozzle_diameter: str
    nozzle_type: str

    @classmethod
    def from_preset(cls, printer_model: str | None, nozzle_diameter: str | None, nozzle_type: str | None) -> "DeviceProfile":
        return cls(
            model_id=MODEL_ID_BY_ORCA_MODEL.get(printer_model or "", printer_model or ""),
            nozzle_diameter=(nozzle_diameter or "0.4").split(",")[0],
            nozzle_type=(nozzle_type or DEFAULT_NOZZLE_TYPE).split(",")[0],
        )


def device_id(print_host: str) -> str:
    """Mirrors OrcaSlicer's dev_id_from_address: host[:port], no scheme or path."""
    return urlsplit(print_host if "://" in print_host else f"//{print_host}").netloc


def ssdp_announcement(dev_id: str, profile: DeviceProfile) -> str:
    return json.dumps(
        {
            "dev_name": DEVICE_NAME,
            "dev_id": dev_id,
            "dev_ip": dev_id,
            "dev_type": profile.model_id,
            "dev_signal": "0",
            "connect_type": "lan",
            "bind_state": "free",
            "sec_link": "secure",
            "ssdp_version": "v1",
        }
    )


def push_status(profile: DeviceProfile, now_ms: int) -> str:
    # Never include home_flag: OrcaSlicer parses it after "sdcard" and it overrides the storage state.
    return json.dumps(
        {
            "print": {
                "command": "push_status",
                "msg": 0,
                "sequence_id": "0",
                "printer_type": profile.model_id,
                "gcode_state": "IDLE",
                "mc_print_stage": 0,
                "mc_percent": 0,
                "mc_remaining_time": 0,
                "mc_print_error_code": 0,
                "print_error": 0,
                "sdcard": True,
                "nozzle_type": profile.nozzle_type,
                "nozzle_diameter": profile.nozzle_diameter,
                "nozzle_temper": 0.0,
                "nozzle_target_temper": 0.0,
                "bed_temper": 0.0,
                "bed_target_temper": 0.0,
                "support_send_to_sd": True,
                "support_mqtt_alive": True,
                "ipcam": {"ipcam_dev": "0"},
            },
            "t_utc": now_ms,
        }
    )


def reply_to(message: str, profile: DeviceProfile, now_ms: int) -> str | None:
    """The device's reply to a command OrcaSlicer sends it, if any."""
    try:
        request: dict[str, Any] = json.loads(message)
    except ValueError:
        return None
    if "pushing" in request:
        return push_status(profile, now_ms)
    info = request.get("info") or {}
    if info.get("command") == "get_version":
        return json.dumps(
            {
                "info": {
                    "command": "get_version",
                    "sequence_id": info.get("sequence_id", "0"),
                    "result": "success",
                    "module": [
                        {"name": "ota", "sw_ver": FIRMWARE_VERSION, "product_name": DEVICE_NAME, "sn": DEVICE_SERIAL}
                    ],
                }
            }
        )
    if (request.get("system") or {}).get("command") == "get_access_code":
        return json.dumps({"system": {"command": "get_access_code", "access_code": ACCESS_CODE}})
    return None
