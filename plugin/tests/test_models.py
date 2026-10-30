import pytest

from bambuddy.models import orca_model, short_name, system_preset_name


@pytest.mark.parametrize(
    ("reported", "expected"),
    [
        ("X1C", "Bambu Lab X1 Carbon"),
        ("BL-P001", "Bambu Lab X1 Carbon"),
        ("a1 mini", "Bambu Lab A1 mini"),
        ("N1", "Bambu Lab A1 mini"),
        ("Bambu Lab H2D Pro", "Bambu Lab H2D Pro"),
        ("C12", "Bambu Lab P1S"),
    ],
)
def test_orca_model_resolves_names_and_codes(reported, expected):
    assert orca_model(reported) == expected


def test_unknown_model():
    assert orca_model("Ender 3") is None
    assert short_name("Ender 3") is None


def test_system_preset_name():
    assert system_preset_name("Bambu Lab P1S", "0.6") == "Bambu Lab P1S 0.6 nozzle"
