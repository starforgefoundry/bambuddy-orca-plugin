import json

from bambuddy.send import (
    bambu_filament_ids,
    batch_payload,
    compatible_printers,
    file_filaments,
    loaded_trays,
    queue_payload,
    sent_summary,
)

OPTIONS = {"bedLevelling": True, "flowCali": False, "vibrationCali": True, "timelapse": False}
FILAMENTS = [{"slotId": 2, "type": "PLA", "color": "#FF0000", "usedGrams": 3.0, "trayInfoIdx": "GFA00"}]


def test_compatible_printers_matches_model_and_accepted_models():
    printers = [
        {"id": 1, "name": "a", "model": "X1C", "location": "Lab"},
        {"id": 2, "name": "b", "model": "P1S", "accepted_models": ["X1C"]},
        {"id": 3, "name": "c", "model": "A1"},
        {"id": 4, "name": "d", "model": "BL-P001", "is_active": False},
    ]
    assert [p["id"] for p in compatible_printers(printers, "BL-P001")] == [1, 2]


def test_loaded_trays_computes_global_ids_and_skips_empty():
    status = {
        "ams": [
            {"id": 0, "tray": [{"id": 0, "tray_type": "PLA", "tray_color": "FF0000FF"}, {"id": 1, "tray_type": ""}]},
            {"id": 1, "tray": [{"id": 2, "tray_type": "PETG", "tray_color": "00FF00FF", "state": 9}]},
            {"id": 128, "tray": [{"id": 0, "tray_type": "TPU", "tray_color": "0000FFFF"}]},
        ],
        "vt_tray": [{"id": 255, "tray_type": "PLA", "tray_color": "FFFFFFFF"}],
    }
    assert [(t["globalId"], t["label"], t["color"]) for t in loaded_trays(status)] == [
        (0, "A1", "#FF0000"),
        (128, "HT1", "#0000FF"),
        (255, "Ext", "#FFFFFF"),
    ]


def test_file_filaments_keeps_plate_slots():
    requirements = {
        "filaments": [
            {"slot_id": 1, "type": "PLA", "color": "#000000", "used_grams": 2.5, "used_in_plate": True},
            {"slot_id": 2, "type": "PLA", "color": "#FFFFFF", "used_grams": 0, "used_in_plate": False},
        ]
    }
    assert [f["slotId"] for f in file_filaments(requirements)] == [1]


def test_file_filaments_report_the_ids_bambu_printers_use():
    requirements = {
        "filaments": [
            {"slot_id": 1, "type": "PLA", "color": "#000000", "tray_info_idx": "OFoiVqVM"},
            {"slot_id": 2, "type": "PLA", "color": "#FFFFFF", "tray_info_idx": "P4d64437"},
            {"slot_id": 3, "type": "PLA", "color": "#FFFFFF", "tray_info_idx": ""},
        ]
    }
    ids = [f["trayInfoIdx"] for f in file_filaments(requirements, {"OFoiVqVM": "GFA00"})]
    assert ids == ["GFA00", "P4d64437", None]


def test_bambu_filament_ids_reads_orca_map(tmp_path):
    path = tmp_path / "bambu_filament_ids.json"
    path.write_text(json.dumps({"filaments": {"OFoiVqVM": {"bambu_id": "GFA00"}, "OFnone": {"bambu_id": ""}}}))
    assert bambu_filament_ids(path) == {"OFoiVqVM": "GFA00"}


def test_bambu_filament_ids_without_a_map_translates_nothing(tmp_path):
    (tmp_path / "broken.json").write_text("{")
    assert bambu_filament_ids(None) == {}
    assert bambu_filament_ids(tmp_path / "broken.json") == {}


def test_queue_payload_for_specific_printer():
    request = {
        "targetKind": "printer", "printerId": 7, "location": None, "dispatch": "now",
        "amsMapping": [-1, 4], "forceColorMatch": False, "options": OPTIONS,
    }
    payload = queue_payload(request, 11, 1, "X1C", FILAMENTS)
    assert payload == {
        "library_file_id": 11, "plate_id": 1, "manual_start": False, "bed_levelling": "auto",
        "flow_cali": "off", "vibration_cali": True, "timelapse": False, "printer_id": 7, "ams_mapping": [-1, 4],
    }


def test_queue_payload_for_any_printer_in_group():
    request = {
        "targetKind": "any", "printerId": None, "location": "Lab", "dispatch": "queue",
        "amsMapping": None, "forceColorMatch": True, "options": OPTIONS,
    }
    payload = queue_payload(request, 11, 2, "BL-P001", FILAMENTS)
    assert payload["target_model"] == "X1C"
    assert payload["target_location"] == "Lab"
    assert payload["manual_start"] is True
    assert "printer_id" not in payload
    assert payload["filament_overrides"] == [
        {"slot_id": 2, "type": "PLA", "color": "#FF0000", "tray_info_idx": "GFA00", "force_color_match": True}
    ]


def test_sent_summary_describes_target_and_dispatch():
    printers = [{"id": 7, "name": "Farm 3"}]
    to_printer = {"targetKind": "printer", "printerId": 7, "dispatch": "now"}
    assert sent_summary(to_printer, "Benchy.gcode.3mf", "X1C", printers) == (
        "Benchy.gcode.3mf is queued in Bambuddy and will start on Farm 3."
    )
    any_in_group = {"targetKind": "any", "printerId": None, "location": "Lab", "dispatch": "queue"}
    assert sent_summary(any_in_group, "Benchy.gcode.3mf", "X1C", printers) == (
        "Benchy.gcode.3mf is in the Bambuddy queue for the next free X1C in Lab, waiting to be started."
    )


def test_sent_summary_counts_copies():
    request = {"targetKind": "any", "printerId": None, "location": None, "dispatch": "now", "quantity": 3}
    assert sent_summary(request, "Benchy.gcode.3mf", "X1C", []) == (
        "3 copies of Benchy.gcode.3mf are queued in Bambuddy and will start on the next free X1C."
    )
    assert sent_summary(request, "Benchy.gcode.3mf", "X1C", [], plate_count=2).startswith(
        "3 copies each of 2 plates of Benchy.gcode.3mf are queued"
    )


def test_queue_payload_asks_for_copies_only_above_one():
    request = {
        "targetKind": "any", "printerId": None, "location": None, "dispatch": "now",
        "amsMapping": None, "forceColorMatch": False, "options": OPTIONS,
    }
    assert queue_payload({**request, "quantity": 4}, 11, 2, "X1C", FILAMENTS)["quantity"] == 4
    assert "quantity" not in queue_payload({**request, "quantity": 1}, 11, 2, "X1C", FILAMENTS)
    assert "quantity" not in queue_payload(request, 11, 2, "X1C", FILAMENTS)


def test_batch_payload_names_batch_after_file():
    assert batch_payload("Benchy.gcode.3mf", 11, 3) == {"name": "Benchy · 3 plates", "library_file_id": 11}


def test_queue_payload_joins_batch():
    request = {
        "targetKind": "any", "printerId": None, "location": None, "dispatch": "now",
        "amsMapping": None, "forceColorMatch": False, "options": OPTIONS,
    }
    assert queue_payload(request, 11, 2, "X1C", FILAMENTS, batch_id=5)["batch_id"] == 5
    assert "batch_id" not in queue_payload(request, 11, 2, "X1C", FILAMENTS)
