from bambuddy.filaments import PlannedFilament, StockedFilament, SystemFilament, config_list, plan_filaments, stocked_filaments

P1S = "Bambu Lab P1S 0.4 nozzle"
A1 = "Bambu Lab A1 0.4 nozzle"

SYSTEM = [
    SystemFilament("Bambu PLA Basic @BBL X1C", "Bambu Lab", frozenset({P1S, "Bambu Lab X1 Carbon 0.4 nozzle"})),
    SystemFilament("Bambu PLA Basic @BBL A1", "Bambu Lab", frozenset({A1})),
    SystemFilament("Generic TPU @System", "Generic", frozenset()),
    SystemFilament("Generic TPU @BBL A1", "Generic", frozenset({A1})),
    SystemFilament("Polymaker PLA @BBL X1C", "Polymaker", frozenset({P1S})),
]


def spool(**fields):
    return {"brand": "Bambu", "material": "PLA", "subtype": "Basic", "color_name": "Black", **fields}


def test_config_list():
    assert config_list('"Bambu Lab P1S 0.4 nozzle";"Bambu Lab A1 0.4 nozzle"') == [P1S, A1]
    assert config_list("Generic") == ["Generic"]
    assert config_list(None) == []


def test_stocked_filaments_keep_the_filament_id():
    spools = [spool(slicer_filament_name="Bambu PLA Basic"), spool(slicer_filament_name="Bambu PLA Basic", slicer_filament="GFA00")]
    assert stocked_filaments(spools) == [StockedFilament("Bambu PLA Basic", "Bambu PLA Basic", "GFA00")]


def test_stocked_filaments_collapse_colors_and_skip_archived():
    spools = [
        spool(slicer_filament_name="Bambu PLA Basic"),
        spool(slicer_filament_name="Bambu PLA Basic", color_name="Red"),
        spool(brand="Bambu Lab", material="PETG", subtype="HF", slicer_filament_name=None),
        spool(brand="Generic", material="TPU", subtype="", slicer_filament_name="Generic TPU", archived_at="2026-01-01"),
    ]
    assert [f.family for f in stocked_filaments(spools)] == ["Bambu PLA Basic", "Bambu PETG HF"]


def test_plan_picks_variant_per_printer_preferring_exact_match():
    stocked = [StockedFilament("Bambu PLA Basic", "Bambu PLA Basic", "GFA00"), StockedFilament("Generic TPU", "Generic TPU")]
    plan = plan_filaments(stocked, [P1S, A1], SYSTEM)
    assert plan.presets == [
        PlannedFilament("Bambu PLA Basic @BBL A1", "GFA00"),
        PlannedFilament("Bambu PLA Basic @BBL X1C", "GFA00"),
        PlannedFilament("Generic TPU @BBL A1", None),
        PlannedFilament("Generic TPU @System", None),
    ]
    assert plan.problem() is None


def test_plan_reports_unsupported_vendors_and_unknown_families():
    stocked = [StockedFilament("Polymaker PLA", "Polymaker PLA"), StockedFilament("eSun PLA+", "eSun PLA+")]
    plan = plan_filaments(stocked, [P1S], SYSTEM)
    assert plan.presets == []
    assert plan.problem() == "These spools don't match a Bambu Lab or Generic OrcaSlicer preset: Polymaker PLA, eSun PLA+"
