"""The Bambuddy window: browser sign-in, then naming and saving printer profiles and the filaments in stock."""

import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .client import BambuddyClient, BambuddyError, normalize_instance_url
from .filaments import PlannedFilament, StockedFilament, SystemFilament, plan_filaments, stocked_filaments
from .models import DEFAULT_NOZZLE
from .presets import BundleStore, PlannedPreset, PrinterModel, name_problem, plan_presets, remove_legacy_presets
from .send_flow import OpenWindow, Window
from .session import Session, SessionStore
from .sign_in import DeviceSignInUnavailable, PendingSignIn, SignInCanceled, SignInFailed, sign_in, sign_in_with_api_key


def printer_nozzle(status: dict[str, Any]) -> str:
    nozzles = status.get("nozzles") or []
    diameter = nozzles[0].get("nozzle_diameter") if nozzles else None
    return str(diameter) if diameter else DEFAULT_NOZZLE


@dataclass(frozen=True)
class OrcaPresets:
    """What OrcaSlicer has installed, read on the UI thread before any background work starts."""

    system_printers: frozenset[str]
    system_filaments: list[SystemFilament]
    bundle_dir: Path
    legacy_machine_dir: Path


@dataclass(frozen=True)
class FarmInventory:
    models: list[PrinterModel]
    stocked: list[StockedFilament]


def read_farm(session: Session) -> FarmInventory:
    client = BambuddyClient(session.instance_url, session.api_key)
    models = []
    for printer in client.list_printers():
        if not printer.get("is_active", True):
            continue
        try:
            status = client.printer_status(printer["id"])
        except BambuddyError:
            status = {}
        models.append(PrinterModel(printer["model"], printer_nozzle(status)))
    return FarmInventory(models, stocked_filaments(client.list_spools()))


class ConnectFlow:
    def __init__(
        self,
        sessions: SessionStore,
        orca: OrcaPresets,
        device_name: str,
        open_window: OpenWindow,
        open_browser: Callable[[str], None],
        reload_bundle: Callable[[], None],
    ):
        self._sessions = sessions
        self._orca = orca
        self._bundle = BundleStore(orca.bundle_dir)
        self._device_name = device_name
        self._open_window = open_window
        self._open_browser = open_browser
        self._reload_bundle = reload_bundle
        self._window: Window | None = None
        self._stop_sign_in = threading.Event()
        self._planned: list[PlannedPreset] = []
        self._filaments: list[PlannedFilament] | None = None

    def open(self) -> None:
        session = self._sessions.load()
        boot = {"view": "connect", "session": self._session_json(session) if session else None}
        self._window = self._open_window(boot, self._on_message, self._stop_sign_in.set)

    def close(self) -> None:
        self._stop_sign_in.set()
        if self._window is not None:
            self._window.close()

    @staticmethod
    def _session_json(session: Session) -> dict[str, Any]:
        return {"instanceUrl": session.instance_url, "username": session.username, "hasApiKey": bool(session.api_key)}

    def _post(self, data: dict[str, Any]) -> None:
        if self._window is not None:
            self._window.post(data)

    def _spawn(self, target: Callable[..., None], *args: Any) -> None:
        threading.Thread(target=target, args=args, daemon=True).start()

    def _on_message(self, data: Any) -> None:
        if not isinstance(data, dict):
            return
        kind = data.get("type")
        if kind == "sign-in":
            self._stop_sign_in.set()
            self._stop_sign_in = threading.Event()
            self._spawn(self._sign_in, str(data.get("url", "")), self._stop_sign_in)
        elif kind == "sign-in-with-api-key":
            self._spawn(self._sign_in_with_api_key, str(data.get("url", "")), str(data.get("apiKey", "")).strip())
        elif kind == "cancel-sign-in":
            self._stop_sign_in.set()
        elif kind == "plan-profiles":
            self._spawn(self._plan)
        elif kind == "save-profiles":
            self._save(str(data.get("bundleName", "")).strip(), data.get("presets") or [])
        elif kind == "disconnect":
            self._sign_out()

    def _sign_out(self) -> None:
        self._sessions.clear()
        self._planned, self._filaments = [], None
        error = None
        try:
            self._bundle.clear()
            remove_legacy_presets(self._orca.legacy_machine_dir)
            self._reload_bundle()
        except (OSError, RuntimeError) as failure:
            error = f"Signed out, but removing the Bambuddy profiles failed: {failure}"
        self._post({"type": "disconnected", "error": error})

    def _sign_in(self, url: str, stop: threading.Event) -> None:
        def on_pending(pending: PendingSignIn) -> None:
            self._post({"type": "sign-in-started", "userCode": pending.user_code, "verificationUrl": pending.verification_url})

        try:
            client = BambuddyClient(normalize_instance_url(url))
            session = sign_in(client, self._device_name, self._open_browser, on_pending, stop)
        except SignInCanceled:
            return
        except DeviceSignInUnavailable:
            self._post({"type": "api-key-required"})
            return
        except (BambuddyError, SignInFailed) as error:
            self._post({"type": "sign-in-failed", "error": str(error)})
            return
        self._signed_in(session)

    def _sign_in_with_api_key(self, url: str, api_key: str) -> None:
        if not api_key:
            self._post({"type": "sign-in-failed", "error": "Paste an API key."})
            return
        try:
            session = sign_in_with_api_key(BambuddyClient(normalize_instance_url(url), api_key))
        except (BambuddyError, SignInFailed) as error:
            self._post({"type": "sign-in-failed", "error": str(error)})
            return
        self._signed_in(session)

    def _signed_in(self, session: Session) -> None:
        self._sessions.save(session)
        self._post({"type": "signed-in", "session": self._session_json(session)})

    def _plan(self) -> None:
        session = self._sessions.load()
        if session is None:
            self._post({"type": "profiles-planned", "plan": None, "error": "Not signed in."})
            return
        try:
            farm = read_farm(session)
        except BambuddyError as error:
            self._post({"type": "profiles-planned", "plan": None, "error": str(error)})
            return
        printers = plan_presets(farm.models, self._orca.system_printers.__contains__, self._bundle.existing_names())
        filaments = plan_filaments(farm.stocked, [p.inherits for p in printers.presets], self._orca.system_filaments)
        self._planned = printers.presets
        self._filaments = None if filaments.problem() else filaments.presets
        plan = {
            "presets": [asdict(p) for p in printers.presets],
            "skipped": [asdict(s) for s in printers.skipped],
            "filaments": [f.name for f in filaments.presets],
            "bundleName": self._bundle.bundle_name(),
        }
        self._post({"type": "profiles-planned", "plan": plan, "error": filaments.problem()})

    def _save_problem(self, session: Session | None, bundle_name: str, presets: list[PlannedPreset]) -> str | None:
        if session is None:
            return "Not signed in."
        if self._filaments is None:
            return "Fix the filament problems, then refresh."
        if not bundle_name:
            return "Name the bundle."
        return name_problem(presets)

    def _save(self, bundle_name: str, named: list[dict[str, str]]) -> None:
        session = self._sessions.load()
        planned = {p.inherits for p in self._planned}
        presets = [PlannedPreset(str(p["name"]), str(p["inherits"])) for p in named if p.get("inherits") in planned]
        problem = self._save_problem(session, bundle_name, presets)
        if problem or session is None or self._filaments is None:
            self._post({"type": "profiles-saved", "error": problem, "restartRequired": False})
            return
        try:
            self._bundle.write(bundle_name, presets, self._filaments, session.instance_url)
            remove_legacy_presets(self._orca.legacy_machine_dir)
        except OSError as error:
            self._post({"type": "profiles-saved", "error": str(error), "restartRequired": False})
            return
        try:
            self._reload_bundle()
        except RuntimeError as error:
            self._post({"type": "profiles-saved", "error": f"Saved, but OrcaSlicer could not load them: {error}", "restartRequired": True})
            return
        self._post({"type": "profiles-saved", "error": None, "restartRequired": False})
