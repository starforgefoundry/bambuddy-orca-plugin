import json

from bambuddy.filaments import PlannedFilament
from bambuddy.presets import (
    AGENT_ID,
    PROCESS_DIR,
    BundleStore,
    PlannedPreset,
    PlannedProfile,
    PrinterModel,
    default_preset_name,
    name_problem,
    plan_presets,
    remove_legacy_presets,
)


def known(name: str) -> bool:
    return name != "Bambu Lab X1 Carbon 0.8 nozzle"


def test_plan_dedupes_models_and_nozzles():
    plan = plan_presets(
        [PrinterModel("X1C"), PrinterModel("BL-P001"), PrinterModel("X1C", "0.6"), PrinterModel("P1S")], known
    )
    assert [(p.name, p.inherits) for p in plan.presets] == [
        ("Bambuddy P1S", "Bambu Lab P1S 0.4 nozzle"),
        ("Bambuddy X1C", "Bambu Lab X1 Carbon 0.4 nozzle"),
        ("Bambuddy X1C 0.6", "Bambu Lab X1 Carbon 0.6 nozzle"),
    ]
    assert plan.skipped == []


def test_plan_keeps_names_from_previous_save():
    plan = plan_presets([PrinterModel("P1S")], known, {"Bambu Lab P1S 0.4 nozzle": "Farm P1S"})
    assert plan.presets == [PlannedPreset("Farm P1S", "Bambu Lab P1S 0.4 nozzle")]


def test_plan_skips_unknown_models_and_missing_system_presets():
    plan = plan_presets([PrinterModel("Ender 3"), PrinterModel("X1C", "0.8")], known)
    assert plan.presets == []
    assert [s.reason for s in plan.skipped] == ["unknown printer model", "no matching OrcaSlicer system profile"]


def test_plan_skips_dual_nozzle_models():
    plan = plan_presets([PrinterModel("H2D")], known)
    assert plan.presets == []
    assert plan.skipped[0].reason == "dual-nozzle printers are not supported yet"


def test_default_name_is_short():
    assert default_preset_name("Bambu Lab A1 mini", "0.4") == "Bambuddy A1 Mini"
    assert default_preset_name("C12", "0.2") == "Bambuddy P1S 0.2"


def test_name_problem():
    a = PlannedPreset("Farm P1S", "Bambu Lab P1S 0.4 nozzle")
    assert name_problem([a]) is None
    assert "twice" in name_problem([a, PlannedPreset("Farm P1S", "Bambu Lab A1 0.4 nozzle")])
    assert "characters" in name_problem([PlannedPreset("a/b", "x")])
    assert "Name the profile" in name_problem([PlannedPreset(" ", "x")])


def test_bundle_writes_printers_filaments_and_metadata(tmp_path):
    store = BundleStore(tmp_path)
    store.write(
        "Starforge",
        [PlannedPreset("Farm P1S", "Bambu Lab P1S 0.4 nozzle")],
        [PlannedFilament("Bambu PLA Basic @BBL X1C", "GFA00"), PlannedFilament("Generic TPU @System", None)],
        [],
        "https://b.local",
    )

    printer = json.loads((tmp_path / "machine" / "Farm P1S.json").read_text())
    assert printer["inherits"] == "Bambu Lab P1S 0.4 nozzle"
    assert printer["printer_agent"] == AGENT_ID
    assert printer["print_host"] == "https://b.local"
    assert printer["bbl_use_printhost"] == "0"
    assert printer["type"] == "machine"

    filament = json.loads((tmp_path / "filament" / "Bambu PLA Basic @BBL X1C.json").read_text())
    assert filament["inherits"] == "Bambu PLA Basic @BBL X1C"
    assert filament["type"] == "filament"
    assert filament["filament_id"] == "GFA00"
    assert "filament_id" not in json.loads((tmp_path / "filament" / "Generic TPU @System.json").read_text())

    assert json.loads((tmp_path / "bundle_metadata.json").read_text()) == {
        "id": "bambuddy",
        "name": "Starforge",
        "version": "2.5.0.0",
    }
    assert store.bundle_name() == "Starforge"
    assert store.existing_names() == {"Bambu Lab P1S 0.4 nozzle": "Farm P1S"}


def test_bundle_name_defaults_and_survives_clear(tmp_path):
    store = BundleStore(tmp_path)
    assert store.bundle_name() == "Bambuddy"
    store.write("Starforge", [], [], [], "")
    store.clear()
    assert store.bundle_name() == "Starforge"


def test_bundle_write_replaces_previous_contents(tmp_path):
    store = BundleStore(tmp_path)
    store.write(
        "B",
        [PlannedPreset("Old", "Bambu Lab P1S 0.4 nozzle")],
        [PlannedFilament("Generic PLA @base", None)],
        [PlannedProfile(PROCESS_DIR, "Fast", "", {})],
        "https://a",
    )
    store.write("B", [PlannedPreset("New", "Bambu Lab A1 0.4 nozzle")], [], [], "https://a")
    assert [p.name for p in (tmp_path / "machine").glob("*.json")] == ["New.json"]
    assert list((tmp_path / "filament").glob("*.json")) == []
    assert list((tmp_path / "process").glob("*.json")) == []


def test_shared_settings_never_override_what_the_bundle_needs(tmp_path):
    shared = {"name": "Theirs", "printer_agent": "bbl", "print_host": "x", "nozzle_diameter": ["0.4"], "from": "system"}
    printer = PlannedPreset("Farm X1C", "Bambu Lab X1 Carbon 0.4 nozzle", "Theirs", shared).to_json("https://b.local")
    assert printer["nozzle_diameter"] == ["0.4"]
    assert (printer["name"], printer["printer_settings_id"], printer["from"]) == ("Farm X1C", "Farm X1C", "User")
    assert (printer["printer_agent"], printer["print_host"]) == (AGENT_ID, "https://b.local")


def test_bundle_writes_profiles_to_their_folder(tmp_path):
    BundleStore(tmp_path).write(
        "B", [], [], [PlannedProfile(PROCESS_DIR, "Fast", "0.20mm Standard @BBL X1C", {"layer_height": "0.3"})], ""
    )
    assert json.loads((tmp_path / "process" / "Fast.json").read_text()) == {
        "layer_height": "0.3",
        "type": "process",
        "version": "2.5.0.0",
        "name": "Fast",
        "from": "User",
        "instantiation": "true",
        "inherits": "0.20mm Standard @BBL X1C",
        "print_settings_id": "Fast",
    }


def test_remove_legacy_presets_only_touches_ours(tmp_path):
    (tmp_path / "Mine.json").write_text(json.dumps({"printer_agent": AGENT_ID}))
    (tmp_path / "Mine.info").write_text("sync_info =")
    (tmp_path / "Other.json").write_text(json.dumps({"printer_agent": "bbl"}))
    remove_legacy_presets(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Other.json"]
