import pytest

from bambuddy.print_name import PrintName, plate_suffixes


@pytest.mark.parametrize(
    ("project", "suffixes", "expected"),
    [
        ("Benchy", [], PrintName("Benchy")),
        ("Benchy.gcode.3mf", [], PrintName("Benchy")),
        ("Benchy_plate_2", ["_plate_2"], PrintName("Benchy", "_plate_2")),
        ("Benchy_plate_2.gcode.3mf", ["_plate_2"], PrintName("Benchy", "_plate_2")),
        ("Benchy_Left", ["_plate_2", "_Left"], PrintName("Benchy", "_Left")),
        ("_plate_2", ["_plate_2"], PrintName("_plate_2")),
    ],
)
def test_from_project(project, suffixes, expected):
    assert PrintName.from_project(project, suffixes) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (PrintName("Benchy"), "Benchy.gcode.3mf"),
        (PrintName("a/b:c", "_plate_1"), "a_b_c_plate_1.gcode.3mf"),
        (PrintName("  ", "_plate_1"), "OrcaSlicer_plate_1.gcode.3mf"),
    ],
)
def test_file_name(name, expected):
    assert name.file_name == expected


def test_renamed_keeps_suffix():
    assert PrintName("Benchy", "_plate_2").renamed("Boat").file_name == "Boat_plate_2.gcode.3mf"


def test_plate_suffixes_prefer_labels():
    assert plate_suffixes([1, 2], {1: "Left"}) == ["_Left", "_plate_2"]
