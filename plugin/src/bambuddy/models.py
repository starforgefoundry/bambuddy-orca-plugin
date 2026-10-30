"""Bambuddy printer model names and their OrcaSlicer system presets."""

DEFAULT_NOZZLE = "0.4"

ORCA_MODEL_BY_SHORT_NAME = {
    "X1C": "Bambu Lab X1 Carbon",
    "X1": "Bambu Lab X1",
    "X1E": "Bambu Lab X1E",
    "P1S": "Bambu Lab P1S",
    "P1P": "Bambu Lab P1P",
    "P2S": "Bambu Lab P2S",
    "A1": "Bambu Lab A1",
    "A1 Mini": "Bambu Lab A1 mini",
    "H2D": "Bambu Lab H2D",
    "H2D Pro": "Bambu Lab H2D Pro",
    "H2C": "Bambu Lab H2C",
    "H2S": "Bambu Lab H2S",
    "X2D": "Bambu Lab X2D",
    "A2L": "Bambu Lab A2L",
}

# Bambuddy can report the raw SSDP model code when it has not normalised it.
SHORT_NAME_BY_ALIAS = {
    "BL-P001": "X1C",
    "BL-P002": "X1",
    "BL-P003": "X1E",
    "C13": "X1E",
    "C11": "P1P",
    "C12": "P1S",
    "N7": "P2S",
    "N6": "X2D",
    "N9": "A2L",
    "A11": "A1",
    "N2S": "A1",
    "A12": "A1 Mini",
    "N1": "A1 Mini",
    "A04": "A1 Mini",
    "A1M": "A1 Mini",
    "O1D": "H2D",
    "O1E": "H2D Pro",
    "O2D": "H2D Pro",
    "O1C": "H2C",
    "O1C2": "H2C",
    "O1S": "H2S",
}

_SHORT_NAME_BY_KEY = {
    **{short.upper(): short for short in ORCA_MODEL_BY_SHORT_NAME},
    **{orca.upper(): short for short, orca in ORCA_MODEL_BY_SHORT_NAME.items()},
    **{alias.upper(): short for alias, short in SHORT_NAME_BY_ALIAS.items()},
}


def short_name(model: str) -> str | None:
    return _SHORT_NAME_BY_KEY.get(model.strip().upper())


def orca_model(model: str) -> str | None:
    short = short_name(model)
    return ORCA_MODEL_BY_SHORT_NAME[short] if short else None


def system_preset_name(orca_model_name: str, nozzle: str) -> str:
    return f"{orca_model_name} {nozzle} nozzle"


# The `model_id` OrcaSlicer expects a device to report for each system printer model.
MODEL_ID_BY_ORCA_MODEL = {
    "Bambu Lab X1 Carbon": "BL-P001",
    "Bambu Lab X1": "BL-P002",
    "Bambu Lab X1E": "C13",
    "Bambu Lab P1P": "C11",
    "Bambu Lab P1S": "C12",
    "Bambu Lab P2S": "N7",
    "Bambu Lab A1": "N2S",
    "Bambu Lab A1 mini": "N1",
    "Bambu Lab A2L": "N9",
    "Bambu Lab H2S": "O1S",
    "Bambu Lab H2D": "O1D",
    "Bambu Lab H2D Pro": "O1E",
    "Bambu Lab H2C": "O1C2",
    "Bambu Lab X2D": "N6",
}

# OrcaSlicer's print dialog needs per-extruder device data for these, which the agent does not emulate.
DUAL_NOZZLE_ORCA_MODELS = {"Bambu Lab H2D", "Bambu Lab H2D Pro", "Bambu Lab H2C", "Bambu Lab X2D"}
