import json

import pytest

from bambuddy.device import DeviceProfile, device_id, push_status, reply_to, ssdp_announcement

PROFILE = DeviceProfile.from_preset("Bambu Lab X1 Carbon", "0.6,0.6", "stainless_steel")


def test_profile_from_preset_values():
    assert PROFILE == DeviceProfile("BL-P001", "0.6", "stainless_steel")


@pytest.mark.parametrize(
    ("host", "expected"),
    [("https://b.example.com", "b.example.com"), ("http://host:8000/sub", "host:8000"), ("10.0.0.2:80", "10.0.0.2:80")],
)
def test_device_id_matches_orca(host, expected):
    assert device_id(host) == expected


def test_push_status_reports_ready_idle_printer():
    status = json.loads(push_status(PROFILE, 5))["print"]
    assert status["printer_type"] == "BL-P001"
    assert status["sdcard"] is True
    assert status["gcode_state"] == "IDLE"
    assert status["nozzle_diameter"] == "0.6"
    assert "home_flag" not in status


def test_ssdp_fields_are_strings():
    payload = json.loads(ssdp_announcement("b.example.com", PROFILE))
    assert payload["dev_ip"] == payload["dev_id"] == "b.example.com"
    assert all(isinstance(v, str) for v in payload.values())


def test_replies():
    version = json.loads(reply_to('{"info":{"command":"get_version","sequence_id":"7"}}', PROFILE, 0))
    assert version["info"]["sequence_id"] == "7"
    assert version["info"]["module"][0]["name"] == "ota"
    assert json.loads(reply_to('{"pushing":{"command":"pushall"}}', PROFILE, 0))["print"]["command"] == "push_status"
    assert "access_code" in json.loads(reply_to('{"system":{"command":"get_access_code"}}', PROFILE, 0))["system"]
    assert reply_to('{"print":{"command":"pause"}}', PROFILE, 0) is None
    assert reply_to("not json", PROFILE, 0) is None
