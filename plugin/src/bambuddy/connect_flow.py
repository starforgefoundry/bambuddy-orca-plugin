"""The Bambuddy window: browser sign-in, then naming and saving printer profiles and the filaments in stock."""

import threading
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from http import HTTPStatus
from pathlib import Path
from typing import Any

from .client import BambuddyClient, BambuddyError, normalize_instance_url
from .filaments import PlannedFilament, StockedFilament, SystemFilament, plan_filaments, stocked_filaments
from .models import DEFAULT_NOZZLE
from .presets import (
    FILAMENT_DIR,
    PROCESS_DIR,
    BundleStore,
    PlannedPreset,
    PlannedProfile,
    PrinterModel,
    SkippedModel,
    name_problem,
    plan_presets,
    remove_legacy_presets,
)
from .send_flow import OpenWindow, Window
from .session import Session, SessionStore
from .shared_profiles import SharedProfile, plan_shared, shared_profile, with_shared_printers
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
    system_processes: frozenset[str]
    # Bambu printer filament ids, e.g. GFA00, to OrcaSlicer's own.
    orca_filament_ids: Mapping[str, str]
    bundle_dir: Path
    legacy_machine_dir: Path


@dataclass(frozen=True)
class FarmInventory:
    models: list[PrinterModel]
    stocked: list[StockedFilament]
    shared: list[SharedProfile]
    shared_unavailable: SkippedModel | None = None


SHARED_PROFILES_LABEL = "Bambuddy profiles"
# Local presets need settings:read, and older instances lack the endpoint; neither should block importing printers.
SHARED_PROFILES_UNAVAILABLE: dict[int | None, str] = {
    HTTPStatus.FORBIDDEN: "this account can't read Bambuddy's local presets",
    HTTPStatus.NOT_FOUND: "this Bambuddy version has no local presets",
}


def read_shared_profiles(client: BambuddyClient) -> list[SharedProfile]:
    listing = client.list_local_presets()
    ids = [preset["id"] for presets in listing.values() for preset in presets]
    profiles = (shared_profile(client.get_local_preset(preset_id)) for preset_id in ids)
    return [profile for profile in profiles if profile is not None]


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
    stocked = stocked_filaments(client.list_spools())
    try:
        shared = read_shared_profiles(client)
    except BambuddyError as error:
        reason = SHARED_PROFILES_UNAVAILABLE.get(error.status)
        if reason is None:
            raise
        return FarmInventory(models, stocked, [], SkippedModel(SHARED_PROFILES_LABEL, reason))
    return FarmInventory(models, stocked, shared)


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
        self._profiles: list[PlannedProfile] = []

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
        self._planned, self._filaments, self._profiles = [], None, []
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
        existing_names = self._bundle.existing_names()
        printers = plan_presets(farm.models, self._orca.system_printers.__contains__, existing_names)
        printer_presets = [p.inherits for p in printers.presets]
        system_presets = {
            FILAMENT_DIR: frozenset(f.name for f in self._orca.system_filaments),
            PROCESS_DIR: self._orca.system_processes,
        }
        shared = plan_shared(farm.shared, printer_presets, system_presets, self._orca.orca_filament_ids)
        stocked = [f for f in farm.stocked if not shared.covers(f)]
        filaments = plan_filaments(stocked, printer_presets, self._orca.system_filaments)
        shared_names = {p.name for p in shared.profiles if p.folder == FILAMENT_DIR}
        system_copies = [f for f in filaments.presets if f.name not in shared_names]
        skipped = printers.skipped + shared.skipped + ([farm.shared_unavailable] if farm.shared_unavailable else [])

        self._planned = with_shared_printers(printers.presets, shared.printers, existing_names)
        self._filaments = None if filaments.problem() else system_copies
        self._profiles = shared.profiles
        plan = {
            "presets": [{"name": p.name, "inherits": p.inherits, "shared": p.shared} for p in self._planned],
            "skipped": [asdict(s) for s in skipped],
            "filaments": sorted([f.name for f in system_copies] + list(shared_names)),
            "processes": [p.name for p in shared.profiles if p.folder == PROCESS_DIR],
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
        planned = {p.inherits: p for p in self._planned}
        presets = [replace(planned[p["inherits"]], name=str(p["name"])) for p in named if p.get("inherits") in planned]
        problem = self._save_problem(session, bundle_name, presets)
        if problem or session is None or self._filaments is None:
            self._post({"type": "profiles-saved", "error": problem, "restartRequired": False})
            return
        try:
            self._bundle.write(bundle_name, presets, self._filaments, self._profiles, session.instance_url)
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
