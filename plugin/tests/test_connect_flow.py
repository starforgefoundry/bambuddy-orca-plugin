import json
import threading

import pytest

from bambuddy import connect_flow
from bambuddy.connect_flow import ConnectFlow, OrcaPresets
from bambuddy.filaments import SystemFilament
from bambuddy.session import Session, SessionStore

P1S = "Bambu Lab P1S 0.4 nozzle"
SYSTEM_FILAMENTS = [
    SystemFilament("Bambu PLA Basic @BBL X1C", "Bambu Lab", frozenset({P1S})),
    SystemFilament("Generic PETG @System", "Generic", frozenset()),
]
STATUS = {"nozzles": [{"nozzle_diameter": "0.4"}]}


def spool(name):
    return {"brand": "Bambu", "material": "PLA", "subtype": "Basic", "slicer_filament_name": name}


class FakeClient:
    spools: list[dict] = []

    def __init__(self, instance_url, api_key=None):
        self.instance_url = instance_url

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
    orca = OrcaPresets(frozenset({P1S}), SYSTEM_FILAMENTS, tmp_path / "bundle", legacy)
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
    assert planned["plan"]["presets"] == [{"name": "Bambuddy P1S", "inherits": P1S}]
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
