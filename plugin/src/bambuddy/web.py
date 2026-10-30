import json
from importlib.resources import files
from typing import Any

BOOT_PLACEHOLDER = "__BAMBUDDY_BOOT__"
DOCTYPE = "<!doctype html>"


def render_page(boot: dict[str, Any]) -> str:
    template = files(__package__).joinpath("web/index.html").read_text(encoding="utf-8")
    # The boot JSON sits inside a <script> element, so "</" must not appear verbatim.
    return template.replace(BOOT_PLACEHOLDER, json.dumps(boot).replace("</", "<\\/"), 1)


def render_settings_page() -> str:
    # OrcaSlicer puts its config bridge in front of the page, and a doctype after it would be ignored.
    return render_page({"view": "settings"}).replace(DOCTYPE, "", 1)


def redirect_page(url: str) -> str:
    return f"<!doctype html><script>location.replace({json.dumps(url)})</script>"
