from pathlib import Path

import pytest

from bambuddy.paths import bambu_filament_ids_file, data_dir, sliced_files_dir


def test_data_dir_from_installed_plugin():
    module = "/data/OrcaSlicer/orca_plugins/bambuddy.whl/x.whl/bambuddy/__init__.py"
    assert data_dir(module) == Path("/data/OrcaSlicer")


@pytest.mark.parametrize(
    ("python_home", "resources"),
    [
        ("OrcaSlicer.app/Contents/MacOS/python", "OrcaSlicer.app/Contents/Resources"),
        ("orca/lib/python", "orca/resources"),
        ("Program Files/OrcaSlicer/python", "Program Files/OrcaSlicer/resources"),
    ],
)
def test_bambu_filament_ids_file_next_to_bundled_python(tmp_path, python_home, resources):
    expected = tmp_path / resources / "printers" / "bambu_filament_ids.json"
    expected.parent.mkdir(parents=True)
    expected.write_text("{}")
    assert bambu_filament_ids_file(tmp_path / python_home).samefile(expected)


@pytest.mark.parametrize(
    ("env", "uid", "expected"),
    [
        ({"TMPDIR": "/var/folders/x/T", "TMP": "/other"}, 501, "/var/folders/x/T/orcaslicer_501/orcaslicer_model"),
        ({"TEMP": "C:/Users/a/Temp"}, None, "C:/Users/a/Temp/orcaslicer_model"),
        ({}, 1000, "/tmp/orcaslicer_1000/orcaslicer_model"),
    ],
)
def test_sliced_files_dir_matches_orcaslicer_temp_layout(env, uid, expected):
    assert sliced_files_dir(env, uid) == Path(expected)


def test_bambu_filament_ids_file_missing(tmp_path):
    assert bambu_filament_ids_file(tmp_path / "lib" / "python") is None
