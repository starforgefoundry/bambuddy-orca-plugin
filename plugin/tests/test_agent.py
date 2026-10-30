import importlib
import json
import sys
import types

import pytest

from orca_stub import Bundle, Preset, install

CURRENT = Preset(
    "Bambuddy - Bambu Lab P1S 0.4 nozzle",
    {"printer_model": "Bambu Lab P1S", "nozzle_diameter": "0.4", "nozzle_type": "stainless_steel"},
)


@pytest.fixture
def plugin(monkeypatch, tmp_path):
    orca = install(Bundle(CURRENT, [Preset("Bambu Lab P1S 0.4 nozzle", is_system=True)]))
    for name in [m for m in sys.modules if m == "bambuddy" or m.startswith("bambuddy.")]:
        del sys.modules[name]
    package = importlib.import_module("bambuddy")
    runtime = importlib.import_module("bambuddy.runtime")
    monkeypatch.setattr(runtime.SESSIONS, "_path", tmp_path / "session.json")
    yield orca, package
    for name in ("orca", "orca.printer_agent"):
        sys.modules.pop(name, None)


def connected_agent(plugin_module):
    from bambuddy.agent import BambuddyAgent

    agent = BambuddyAgent()
    events = []
    agent.set_on_local_connect_fn(lambda *args: events.append(("connect", args)))
    agent.set_on_local_message_fn(lambda dev_id, msg: events.append(("message", json.loads(msg))))
    params = types.SimpleNamespace(dev_id="b.local", host="b.local", port="", password="88888888")
    assert agent.connect_printer(params) == 0
    return agent, events


def test_registers_agent_and_scripts(plugin):
    orca, package = plugin
    package.BambuddyPlugin().register_capabilities()
    assert [cls.__name__ for cls in orca.registered] == ["BambuddyAgent", "ConnectCapability", "OpenBambuddyCapability"]


def test_requests_sliced_files_and_instance_at_load(plugin):
    orca, package = plugin
    from bambuddy.runtime import SESSIONS, SLICED_FILES_DIR
    from bambuddy.session import Session

    SESSIONS.save(Session("https://bambuddy.local", "bb_x", None))
    package.BambuddyPlugin().register_capabilities()
    assert orca.permission_requests == [
        {"fs_read": [f"{SLICED_FILES_DIR}/*"], "network": ["https://bambuddy.local"], "threading": True}
    ]


def test_signed_out_load_requests_no_network(plugin):
    orca, package = plugin
    package.BambuddyPlugin().register_capabilities()
    assert orca.permission_requests[0]["network"] == []


def test_connect_reports_ok_and_answers_version(plugin):
    agent, events = connected_agent(plugin)
    assert events[0] == ("connect", (0, "b.local", "0"))
    agent.send_message_to_printer("b.local", '{"info":{"command":"get_version","sequence_id":"1"}}', 0, 0)
    assert events[1][1]["info"]["module"][0]["sw_ver"]
    agent.send_message_to_printer("b.local", '{"pushing":{"command":"pushall"}}', 0, 0)
    assert events[2][1]["print"]["printer_type"] == "C12"
    agent.disconnect_printer()


def test_verify_job_is_accepted_without_upload(plugin):
    agent, _ = connected_agent(plugin)
    params = types.SimpleNamespace(project_name="verify_job")
    assert agent.start_send_gcode_to_sdcard(params, None, None, None) == 0
    agent.disconnect_printer()


def test_send_without_session_asks_to_sign_in(plugin):
    orca, _ = plugin
    agent, _ = connected_agent(plugin)
    params = types.SimpleNamespace(project_name="Benchy", filename="x.3mf", plate_index=1)
    assert agent.start_send_gcode_to_sdcard(params, None, None, None) == -18
    assert "Sign in" in orca.host.ui.messages[0]
    agent.disconnect_printer()


def test_connect_window_lists_session_state(plugin):
    orca, package = plugin
    from bambuddy.plugin import ConnectCapability

    assert ConnectCapability().execute()[0] == "success"
    html = orca.host.ui.windows[0]["html"]
    assert '"view": "connect"' in html


def test_agent_takes_over_orca_dialogs(plugin):
    orca, _ = plugin
    from bambuddy.agent import BambuddyAgent

    agent = BambuddyAgent()
    assert agent.print_dialog_mode() == orca.printer_agent.DialogMode.Takeover
    assert agent.send_dialog_mode() == orca.printer_agent.DialogMode.Takeover


def test_notify_sent_links_to_queue(plugin, monkeypatch):
    orca, _ = plugin
    from bambuddy import agent

    opened = []
    monkeypatch.setattr(agent.webbrowser, "open", opened.append)
    agent.notify_sent("Benchy is queued.", "https://b.local")
    _, text, link, on_click = orca.host.ui.notifications[0]
    assert (text, link) == ("Benchy is queued.", "Open queue")
    assert on_click() is True
    assert opened == ["https://b.local/queue"]


def test_switching_bambuddy_profiles_updates_the_device(plugin):
    orca, _ = plugin
    agent, events = connected_agent(plugin)
    orca.host.preset_bundle()._current = Preset(
        "Bambuddy H2S", {"printer_model": "Bambu Lab H2S", "nozzle_diameter": "0.4", "nozzle_type": "hardened_steel"}
    )
    agent.send_message_to_printer("b.local", '{"pushing":{"command":"pushall"}}', 0, 0)
    assert events[-1][1]["print"]["printer_type"] == "O1S"
    agent.disconnect_printer()


def test_settings_page_and_defaults(plugin):
    from bambuddy.agent import BambuddyAgent

    agent = BambuddyAgent()
    assert agent.has_config_ui() is True
    assert agent.get_default_config()["requireExactColors"] is False
    page = agent.get_config_ui()
    assert '"view": "settings"' in page
    assert not page.lstrip().lower().startswith("<!doctype")
