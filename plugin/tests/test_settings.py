from bambuddy.settings import DEFAULT_SETTINGS, effective_settings, print_options


def test_defaults_when_nothing_stored():
    assert effective_settings(None) == DEFAULT_SETTINGS
    assert effective_settings("not json") == DEFAULT_SETTINGS
    assert effective_settings("[]") == DEFAULT_SETTINGS


def test_stored_values_override_and_bad_types_fall_back():
    settings = effective_settings('{"requireExactColors": true, "timelapse": "yes", "unknown": 1}')
    assert settings["requireExactColors"] is True
    assert settings["timelapse"] is False
    assert "unknown" not in settings


def test_print_options():
    assert print_options(DEFAULT_SETTINGS) == {
        "bedLevelling": True,
        "flowCali": False,
        "vibrationCali": False,
        "timelapse": False,
    }
