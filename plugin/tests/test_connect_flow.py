import json
import threading

import pytest

from bambuddy import connect_flow
from bambuddy.client import BambuddyError
from bambuddy.connect_flow import ConnectFlow, OrcaPresets
from bambuddy.filaments import SystemFilament
from bambuddy.session import Session, SessionStore

P1S = "Bambu Lab P1S 0.4 nozzle"
SYSTEM_FILAMENTS = [
    SystemFilament("Bambu PLA Basic @BBL X1C", "Bambu Lab", frozenset({P1S})),
    SystemFilament("Generic PETG @System", "Generic", frozenset()),
]
STATUS = {"nozzles": [{"nozzle_diameter": "0.4"}]}
STANDARD = "0.20mm Standard @BBL P1S"
ORCA_IDS = {"GFA00": "OFoiVqVM"}


def spool(name):
    return {"brand": "Bambu", "material": "PLA", "subtype": "Basic", "slicer_filament_name": name}


class FakeClient:
    spools: list[dict] = []
    local_presets: list[dict] = []
    local_presets_error: BambuddyError | None = None

    def __init__(self, instance_url, api_key=None):
        self.instance_url = instance_url

    def list_local_presets(self):
        if self.local_presets_error:
            raise self.local_presets_error
        listing = {"filament": [], "printer": [], "process": []}
        for preset in self.local_presets:
            listing[preset["preset_type"]].append({key: value for key, value in preset.items() if key != "setting"})
        return listing

    def get_local_preset(self, preset_id):
        return next(p for p in self.local_presets if p["id"] == preset_id)

    def list_printers(self):
        return [{"id": 1, "name": "Farm 1", "model": "P1S"}, {"id": 2, "name": "Farm 2", "model": "C12"}]

    def printer_status(self, printer_id):
        return STATUS

    def list_spools(self):
        return self.spools


class FakeWindow:
    def __init__(self):
        self.posts = []
        self.event = threading.Event()

    def post(self, data):
        self.posts.append(data)
        self.event.set()

    def close(self):
        pass

    def wait_for(self, kind):
        while not any(p["type"] == kind for p in self.posts):
            self.event.clear()
            assert self.event.wait(2), f"no {kind} message"
        return next(p for p in self.posts if p["type"] == kind)


@pytest.fixture
def flow(tmp_path, monkeypatch):
    monkeypatch.setattr(connect_flow, "BambuddyClient", FakeClient)
    sessions = SessionStore(tmp_path / "session.json")
    sessions.save(Session("https://b.local", "bb_k", "alice"))
    legacy = tmp_path / "user" / "default" / "machine"
    legacy.mkdir(parents=True)
    (legacy / "Bambuddy - Bambu Lab P1S 0.4 nozzle.json").write_text(json.dumps({"printer_agent": "bambuddy"}))
    FakeClient.local_presets, FakeClient.local_presets_error = [], None
    orca = OrcaPresets(frozenset({P1S}), SYSTEM_FILAMENTS, frozenset({STANDARD}), ORCA_IDS, tmp_path / "bundle", legacy)
    window = FakeWindow()
    reloads = []
    flow = ConnectFlow(sessions, orca, "studio", lambda boot, on_message, on_close: window, print, lambda: reloads.append(1))
    flow.open()
    return flow, window, reloads, tmp_path


def test_plan_then_save_writes_bundle_and_reloads(flow):
    flow, window, reloads, tmp_path = flow
    FakeClient.spools = [spool("Bambu PLA Basic"), spool("Generic PETG"), spool("Bambu PLA Basic")]

    flow._on_message({"type": "plan-profiles"})
    planned = window.wait_for("profiles-planned")
    assert planned["error"] is None
    assert planned["plan"]["bundleName"] == "Bambuddy"
    assert planned["plan"]["presets"] == [{"name": "Bambuddy P1S", "inherits": P1S, "shared": None}]
    assert planned["plan"]["filaments"] == ["Bambu PLA Basic @BBL X1C", "Generic PETG @System"]

    flow._on_message({"type": "save-profiles", "bundleName": "Starforge", "presets": [{"name": "Farm P1S", "inherits": P1S}]})
    assert window.wait_for("profiles-saved") == {"type": "profiles-saved", "error": None, "restartRequired": False}
    assert reloads == [1]
    assert json.loads((tmp_path / "bundle" / "bundle_metadata.json").read_text())["name"] == "Starforge"
    assert (tmp_path / "bundle" / "machine" / "Farm P1S.json").exists()
    assert sorted(p.name for p in (tmp_path / "bundle" / "filament").iterdir()) == [
        "Bambu PLA Basic @BBL X1C.json",
        "Generic PETG @System.json",
    ]
    assert list((tmp_path / "user" / "default" / "machine").iterdir()) == []


def test_bambuddy_profiles_are_planned_and_saved(flow):
    flow, window, reloads, tmp_path = flow
    FakeClient.spools = [spool("Farm PLA @BBL X1C"), spool("Bambu PLA Basic")]
    FakeClient.local_presets = [
        {"id": 1, "name": "Farm P1S", "preset_type": "printer", "setting": {"inherits": P1S, "retraction_length": ["0.6"]}},
        {"id": 2, "name": "Farm PLA @BBL X1C", "preset_type": "filament", "setting": {"filament_id": "GFA00"}},
        {"id": 3, "name": "Fast", "preset_type": "process", "setting": {"inherits": STANDARD, "compatible_printers": [P1S]}},
        {"id": 4, "name": "Fast A1", "preset_type": "process", "setting": {"compatible_printers": ["Bambu Lab A1 0.4 nozzle"]}},
    ]

    flow._on_message({"type": "plan-profiles"})
    plan = window.wait_for("profiles-planned")["plan"]
    assert plan["presets"] == [{"name": "Farm P1S", "inherits": P1S, "shared": "Farm P1S"}]
    assert plan["filaments"] == ["Bambu PLA Basic @BBL X1C", "Farm PLA @BBL X1C"]
    assert plan["processes"] == ["Fast"]
    assert plan["skipped"] == [{"model": "Fast A1", "reason": "not compatible with the printers on Bambuddy"}]

    flow._on_message({"type": "save-profiles", "bundleName": "Starforge", "presets": plan["presets"]})
    assert window.wait_for("profiles-saved")["error"] is None
    printer = json.loads((tmp_path / "bundle" / "machine" / "Farm P1S.json").read_text())
    assert (printer["retraction_length"], printer["printer_agent"]) == (["0.6"], "bambuddy")
    filament = json.loads((tmp_path / "bundle" / "filament" / "Farm PLA @BBL X1C.json").read_text())
    assert (filament["inherits"], filament["filament_id"]) == ("", "OFoiVqVM")
    assert json.loads((tmp_path / "bundle" / "process" / "Fast.json").read_text())["inherits"] == STANDARD


def test_unreadable_bambuddy_profiles_are_skipped(flow):
    flow, window, _, _ = flow
    FakeClient.spools = []
    FakeClient.local_presets_error = BambuddyError("Forbidden", 403)

    flow._on_message({"type": "plan-profiles"})
    planned = window.wait_for("profiles-planned")
    assert planned["error"] is None
    assert planned["plan"]["skipped"] == [
        {"model": "Bambuddy profiles", "reason": "this account can't read Bambuddy's local presets"}
    ]


def test_unmapped_filament_blocks_save(flow):
    flow, window, reloads, tmp_path = flow
    FakeClient.spools = [spool("Polymaker PLA")]

    flow._on_message({"type": "plan-profiles"})
    assert "Polymaker PLA" in window.wait_for("profiles-planned")["error"]

    flow._on_message({"type": "save-profiles", "bundleName": "Starforge", "presets": [{"name": "Farm P1S", "inherits": P1S}]})
    assert window.wait_for("profiles-saved")["error"] == "Fix the filament problems, then refresh."
    assert reloads == []
    assert not (tmp_path / "bundle").exists()


def test_reload_failure_asks_for_restart(tmp_path, monkeypatch, flow):
    flow, window, _, _ = flow
    FakeClient.spools = []

    def fail():
        raise RuntimeError("preset is modified")

    flow._reload_bundle = fail
    flow._on_message({"type": "plan-profiles"})
    window.wait_for("profiles-planned")
    flow._on_message({"type": "save-profiles", "bundleName": "Starforge", "presets": [{"name": "Farm P1S", "inherits": P1S}]})
    saved = window.wait_for("profiles-saved")
    assert saved["restartRequired"] is True
    assert "preset is modified" in saved["error"]


def test_sign_out_clears_session_and_profiles(flow):
    flow, window, reloads, tmp_path = flow
    FakeClient.spools = [spool("Bambu PLA Basic")]
    flow._on_message({"type": "plan-profiles"})
    window.wait_for("profiles-planned")
    flow._on_message({"type": "save-profiles", "bundleName": "Starforge", "presets": [{"name": "Farm P1S", "inherits": P1S}]})
    window.wait_for("profiles-saved")

    flow._on_message({"type": "disconnect"})
    assert window.wait_for("disconnected") == {"type": "disconnected", "error": None}
    assert flow._sessions.load() is None
    assert list((tmp_path / "bundle" / "machine").glob("*.json")) == []
    assert list((tmp_path / "bundle" / "filament").glob("*.json")) == []
    assert reloads == [1, 1]


def test_api_key_sign_in_saves_session(flow, monkeypatch):
    flow, window, _, tmp_path = flow
    monkeypatch.setattr(connect_flow, "sign_in_with_api_key", lambda client: Session(client.instance_url, "bb_new", None))

    flow._on_message({"type": "sign-in-with-api-key", "url": "b2.local", "apiKey": " bb_new "})
    signed_in = window.wait_for("signed-in")
    assert signed_in["session"] == {"instanceUrl": "https://b2.local", "username": None, "hasApiKey": True}
    assert SessionStore(tmp_path / "session.json").load() == Session("https://b2.local", "bb_new", None)


def test_blank_api_key_is_refused(flow):
    flow, window, _, _ = flow
    flow._on_message({"type": "sign-in-with-api-key", "url": "b.local", "apiKey": "  "})
    assert window.wait_for("sign-in-failed")["error"] == "Paste an API key."


def test_missing_device_sign_in_asks_for_api_key(flow, monkeypatch):
    flow, window, _, _ = flow

    def unavailable(*args):
        raise connect_flow.DeviceSignInUnavailable()

    monkeypatch.setattr(connect_flow, "sign_in", unavailable)
    flow._on_message({"type": "sign-in", "url": "b.local"})
    assert window.wait_for("api-key-required") == {"type": "api-key-required"}
