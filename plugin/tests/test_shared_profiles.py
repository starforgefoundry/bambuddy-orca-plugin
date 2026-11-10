from bambuddy.filaments import StockedFilament
from bambuddy.presets import FILAMENT_DIR, MACHINE_DIR, PROCESS_DIR, PlannedPreset, PlannedProfile
from bambuddy.shared_profiles import SharedProfile, plan_shared, shared_profile, with_shared_printers

X1C = "Bambu Lab X1 Carbon 0.4 nozzle"
P1S = "Bambu Lab P1S 0.4 nozzle"
PLA_X1C = "Bambu PLA Basic @BBL X1C"
STANDARD_X1C = "0.20mm Standard @BBL X1C"
SYSTEM = {FILAMENT_DIR: frozenset({PLA_X1C}), PROCESS_DIR: frozenset({STANDARD_X1C})}
ORCA_IDS = {"GFA00": "OFoiVqVM"}


def profile(folder, name, profile_id=1, **setting):
    return SharedProfile(profile_id, folder, name, setting)


def plan(*profiles, printers=(X1C,), existing_names=None):
    return plan_shared(profiles, printers, existing_names or {}, SYSTEM, ORCA_IDS)


def test_shared_profile_reads_bambuddy_detail():
    detail = {"id": 4, "name": "Farm PLA", "preset_type": "filament", "setting": {"inherits": PLA_X1C}}
    assert shared_profile(detail) == SharedProfile(4, FILAMENT_DIR, "Farm PLA", {"inherits": PLA_X1C})
    assert shared_profile({"id": 5, "name": "x", "preset_type": "sla", "setting": {}}) is None


def test_profile_with_local_parent_keeps_it_so_the_parent_filament_id_drives_the_color_palette():
    shared = plan(profile(FILAMENT_DIR, "Bambu PLA Basic Farm", inherits=PLA_X1C, filament_id="GFA00", setting_id="GFSA00"))
    assert shared.profiles == [
        PlannedProfile(FILAMENT_DIR, "Bambu PLA Basic Farm", PLA_X1C, {"inherits": PLA_X1C, "filament_id": "GFA00"})
    ]


def test_profile_without_local_parent_stands_alone_with_orca_filament_id():
    shared = plan(profile(FILAMENT_DIR, "Bambu PLA Basic Farm", inherits="Bambu PLA Basic @BBL Z9", filament_id="GFA00"))
    assert shared.profiles[0].inherits == ""
    assert shared.profiles[0].settings["filament_id"] == "OFoiVqVM"


def test_unknown_filament_id_is_kept():
    shared = plan(profile(FILAMENT_DIR, "Farm PLA", filament_id="P1234567"))
    assert shared.profiles[0].settings["filament_id"] == "P1234567"


def test_profiles_for_printers_not_on_bambuddy_are_skipped():
    shared = plan(
        profile(PROCESS_DIR, "Fast X1C", compatible_printers=[X1C]),
        profile(PROCESS_DIR, "Fast P1S", compatible_printers=f'"{P1S}"'),
        profile(PROCESS_DIR, "Anything"),
    )
    assert [p.name for p in shared.profiles] == ["Anything", "Fast X1C"]
    assert [s.model for s in shared.skipped] == ["Fast P1S"]


def test_unsafe_names_are_skipped():
    shared = plan(profile(PROCESS_DIR, "a/b"), profile(PROCESS_DIR, " "))
    assert shared.profiles == []
    assert len(shared.skipped) == 2


def test_printer_profiles_match_by_parent_or_model_and_nozzle():
    by_parent = profile(MACHINE_DIR, "Farm X1C", inherits=X1C)
    by_model = profile(MACHINE_DIR, "Farm P1S", 2, printer_model="Bambu Lab P1S", printer_variant="0.4")
    shared = plan(by_parent, by_model, printers=(X1C, P1S))
    assert shared.printers == {X1C: by_parent, P1S: by_model}


def test_copied_stock_printer_profile_matches_by_model_not_its_template_parent():
    stock_copy = profile(MACHINE_DIR, "Farm P1S", inherits="fdm_bbl_3dp_001_common", printer_model="Bambu Lab P1S", printer_variant="0.4")
    assert plan(stock_copy, printers=(P1S,)).printers == {P1S: stock_copy}


def test_compatible_printers_naming_bundle_printers_point_at_their_system_printer():
    shared = plan(
        profile(MACHINE_DIR, "Farm X1C", 1, inherits=X1C),
        profile(PROCESS_DIR, "Fast", 2, compatible_printers=["Farm X1C"]),
        profile(PROCESS_DIR, "Faster", 3, compatible_printers=["Saved P1S"]),
        printers=(X1C, P1S),
        existing_names={P1S: "Saved P1S"},
    )
    assert [p.settings["compatible_printers"] for p in shared.profiles] == [[X1C], [P1S]]


def test_profile_based_on_another_bambuddy_profile_gets_its_settings_and_stock_parent():
    base = profile(FILAMENT_DIR, "Farm ABS", 1, inherits=PLA_X1C, filament_type=["ABS"], nozzle_temperature=["260"])
    fast = profile(FILAMENT_DIR, "Farm ABS Fast", 2, inherits="Farm ABS", filament_max_volumetric_speed=["30"])
    planned = {p.name: p for p in plan(base, fast).profiles}
    assert planned["Farm ABS Fast"].inherits == PLA_X1C
    assert planned["Farm ABS Fast"].settings["nozzle_temperature"] == ["260"]
    assert planned["Farm ABS Fast"].settings["filament_max_volumetric_speed"] == ["30"]


def test_profile_inheriting_its_own_name_is_not_merged_with_itself():
    stock_named = profile(FILAMENT_DIR, PLA_X1C, inherits=PLA_X1C)
    assert plan(stock_named).profiles[0].inherits == PLA_X1C


def test_one_printer_profile_per_printer_model():
    shared = plan(profile(MACHINE_DIR, "A", inherits=X1C), profile(MACHINE_DIR, "B", 2, inherits=X1C), profile(MACHINE_DIR, "C", 3, inherits=P1S))
    assert list(shared.printers) == [X1C]
    assert [s.model for s in shared.skipped] == ["B", "C"]


def test_spools_set_to_a_shared_filament_map_to_its_stock_family():
    shared = plan(profile(FILAMENT_DIR, "Farm PLA @BBL X1C", 7, inherits=PLA_X1C), profile(FILAMENT_DIR, "Own @BBL X1C", 8))
    assert shared.stock_family(StockedFilament("Farm PLA @BBL X1C", "Farm PLA @BBL X1C")) == "Bambu PLA Basic"
    assert shared.stock_family(StockedFilament("Renamed", "Renamed", "7")) == "Bambu PLA Basic"
    assert shared.stock_family(StockedFilament("Own @BBL X1C", "Own @BBL X1C")) == "Own"
    assert shared.stock_family(StockedFilament("Farm PLA", "Farm PLA")) is None


def test_shared_printer_replaces_generated_preset_and_keeps_saved_names():
    shared = {X1C: profile(MACHINE_DIR, "Farm X1C", inherits=X1C, nozzle_diameter=["0.4"], base_id="GM001")}
    presets = with_shared_printers(
        [PlannedPreset("Bambuddy X1C", X1C), PlannedPreset("Renamed P1S", P1S)], shared, {P1S: "Renamed P1S"}
    )
    assert presets == [
        PlannedPreset("Farm X1C", X1C, "Farm X1C", {"inherits": X1C, "nozzle_diameter": ["0.4"]}),
        PlannedPreset("Renamed P1S", P1S),
    ]
    assert with_shared_printers([PlannedPreset("Bambuddy X1C", X1C)], shared, {X1C: "Mine"})[0].name == "Mine"
