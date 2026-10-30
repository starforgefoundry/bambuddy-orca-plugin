import platform
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any

import orca

from .agent import BambuddyAgent
from .connect_flow import ConnectFlow, OrcaPresets
from .filaments import SystemFilament, config_list
from .presets import BUNDLE_ID
from .runtime import DATA_DIR, SESSIONS, SLICED_FILES_DIR
from .web import redirect_page, render_page

CONNECT_WINDOW_SIZE = (560, 760)
BAMBUDDY_WINDOW_SIZE = (1280, 860)
DEFAULT_USER_FOLDER = "default"


def _presets(collection: Any) -> list[Any]:
    return [collection.preset(i) for i in range(collection.size())]


def _user_folder(bundle: Any) -> str:
    """OrcaSlicer keeps a signed-in account's presets in user/<account id>; reuse whichever folder is live."""
    for collection in (bundle.printers, bundle.filaments, bundle.prints):
        for preset in _presets(collection):
            parts = Path(preset.file or "").parts
            if "user" in parts and parts.index("user") + 1 < len(parts):
                return parts[parts.index("user") + 1]
    return DEFAULT_USER_FOLDER


def read_orca_presets() -> OrcaPresets:
    bundle = orca.host.preset_bundle()
    filaments = [
        SystemFilament(
            name=p.name,
            vendor=next(iter(config_list(p.config_value("filament_vendor"))), ""),
            compatible_printers=frozenset(config_list(p.config_value("compatible_printers"))),
        )
        for p in _presets(bundle.filaments)
        if p.is_system
    ]
    user_dir = DATA_DIR / "user" / _user_folder(bundle)
    return OrcaPresets(
        system_printers=frozenset(p.name for p in _presets(bundle.printers) if p.is_system),
        system_filaments=filaments,
        bundle_dir=user_dir / "_local" / BUNDLE_ID,
        legacy_machine_dir=user_dir / "machine",
    )


def open_connect_window(boot: dict[str, Any], on_message: Callable[[Any], None], on_close: Callable[[], None]) -> Any:
    width, height = CONNECT_WINDOW_SIZE
    return orca.host.ui.create_window(
        html=render_page(boot),
        title="Bambuddy",
        width=width,
        height=height,
        on_message=on_message,
        on_close=on_close,
    )


class ConnectCapability(orca.script.ScriptPluginCapabilityBase):
    flow: ConnectFlow | None = None

    def get_name(self) -> str:
        return "Connect to Bambuddy"

    def execute(self) -> Any:
        if self.flow is not None:
            self.flow.close()
        self.flow = ConnectFlow(
            SESSIONS,
            read_orca_presets(),
            platform.node() or "OrcaSlicer",
            open_connect_window,
            webbrowser.open,
            lambda: orca.host.preset.bundles.reload_local(BUNDLE_ID),
        )
        self.flow.open()
        return orca.ExecutionResult.success("Bambuddy opened.")


class OpenBambuddyCapability(orca.script.ScriptPluginCapabilityBase):
    def get_name(self) -> str:
        return "Open Bambuddy"

    def execute(self) -> Any:
        session = SESSIONS.load()
        if session is None:
            orca.host.ui.message("Sign in first with Connect to Bambuddy.", "Bambuddy", icon="warning")
            return orca.ExecutionResult.skipped("Not signed in.")
        width, height = BAMBUDDY_WINDOW_SIZE
        orca.host.ui.create_window(html=redirect_page(session.instance_url), title="Bambuddy", width=width, height=height)
        return orca.ExecutionResult.success("Bambuddy opened.")


@orca.plugin
class BambuddyPlugin(orca.base):
    def register_capabilities(self) -> None:
        # Asked once at load and saved, so a send never stops on a prompt. Already-saved grants aren't asked again.
        session = SESSIONS.load()
        orca.request_permissions(
            fs_read=[str(SLICED_FILES_DIR / "*")],
            network=[session.instance_url] if session else [],
            threading=True,
        )
        orca.register_capability(BambuddyAgent)
        orca.register_capability(ConnectCapability)
        orca.register_capability(OpenBambuddyCapability)
