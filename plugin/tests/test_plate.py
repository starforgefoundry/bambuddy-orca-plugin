import json
import zipfile

import base64

from bambuddy.plate import plate_labels, plate_previews, sliced_model, sliced_plates

SLICE_INFO = '<config><plate><metadata key="index" value="1"/><metadata key="printer_model_id" value="O1S"/></plate></config>'


def make_3mf(tmp_path, **entries):
    path = tmp_path / "plate.gcode.3mf"
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return path


def test_reads_model_id_from_slice_info(tmp_path):
    path = make_3mf(tmp_path, **{"Metadata/slice_info.config": SLICE_INFO})
    assert sliced_model(path) == "H2S"


def test_falls_back_to_project_settings(tmp_path):
    settings = json.dumps({"printer_model": "Bambu Lab P1S"})
    path = make_3mf(tmp_path, **{"Metadata/project_settings.config": settings})
    assert sliced_model(path) == "P1S"


def test_unreadable_file(tmp_path):
    path = tmp_path / "broken.gcode.3mf"
    path.write_bytes(b"not a zip")
    assert sliced_model(path) is None
    assert sliced_model(tmp_path / "missing.gcode.3mf") is None


def test_sliced_plates_lists_plates_with_gcode(tmp_path):
    path = make_3mf(
        tmp_path,
        **{
            "Metadata/plate_3.gcode": "G1",
            "Metadata/plate_1.gcode": "G1",
            "Metadata/plate_1.gcode.md5": "x",
            "Metadata/plate_2.png": "png",
        },
    )
    assert sliced_plates(path) == [1, 3]


def test_sliced_plates_of_unreadable_file(tmp_path):
    assert sliced_plates(tmp_path / "missing.gcode.3mf") == []


def test_plate_previews_prefer_the_small_render(tmp_path):
    path = make_3mf(
        tmp_path,
        **{"Metadata/plate_1.png": b"big", "Metadata/plate_1_small.png": b"small", "Metadata/plate_2.png": b"two"},
    )
    previews = plate_previews(path, [1, 2, 3])
    assert previews == {
        1: "data:image/png;base64," + base64.b64encode(b"small").decode(),
        2: "data:image/png;base64," + base64.b64encode(b"two").decode(),
    }
    assert plate_previews(tmp_path / "missing.gcode.3mf", [1]) == {}


MODEL_SETTINGS = (
    "<config>"
    '<plate><metadata key="plater_id" value="1"/><metadata key="plater_name" value="Left"/>'
    '<model_instance><metadata key="object_id" value="2"/></model_instance></plate>'
    '<plate><metadata key="plater_id" value="2"/><metadata key="plater_name" value=""/></plate>'
    "</config>"
)


def test_plate_labels_skip_unnamed_plates(tmp_path):
    path = make_3mf(tmp_path, **{"Metadata/model_settings.config": MODEL_SETTINGS})
    assert plate_labels(path) == {1: "Left"}


def test_plate_labels_without_model_settings(tmp_path):
    assert plate_labels(make_3mf(tmp_path, **{"Metadata/slice_info.config": SLICE_INFO})) == {}
