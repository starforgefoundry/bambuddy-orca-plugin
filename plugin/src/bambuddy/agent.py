"""OrcaSlicer printer agent that presents the Bambuddy server as one LAN printer and sends jobs to its queue."""

import threading
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import orca
from orca.printer_agent import AgentInfo, PrinterAgentBase

from . import __version__
from .client import BambuddyClient, BambuddyError, NetworkPermissionError
from .device import DeviceProfile, push_status, reply_to, ssdp_announcement
from .models import short_name
from .plate import sliced_model, sliced_plates
from .presets import AGENT_ID
from .runtime import SESSIONS
from .send import compatible_printers
from .send_flow import RESULT_CANCELED, SendFlow, SendJob, library_filename
from .settings import DEFAULT_SETTINGS, effective_settings, print_options
from .web import render_page, render_settings_page

T = TypeVar("T")

RESULT_FAILED = -1
CONNECT_STATUS_OK = 0
STAGE_UPLOAD = 1
DEFAULT_PLATE_ID = 1
STAGE_FINISHED = 6
QUEUE_PATH = "/queue"
PUSH_INTERVAL_SECONDS = 5
VERIFY_JOB_PROJECT = "verify_job"
SEND_WINDOW_SIZE = (640, 780)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _in_thread(work: Callable[[], T]) -> T:
    """Runs `work` on a plugin thread, where OrcaSlicer doesn't ask permission for each network call."""
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["value"] = work()
        except Exception as error:
            outcome["error"] = error

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join()
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


def notify_sent(summary: str, instance_url: str) -> None:
    """A toast in the plater, since the print job itself finishes without one."""

    def open_queue() -> bool:
        webbrowser.open(f"{instance_url}{QUEUE_PATH}")
        return True

    orca.host.ui.push_notification(
        orca.host.ui.NotificationLevel.RegularNotificationLevel, summary, "Open queue", open_queue
    )


def open_send_window(boot: dict[str, Any], on_message: Callable[[Any], None], on_close: Callable[[], None]) -> Any:
    width, height = SEND_WINDOW_SIZE
    return orca.host.ui.create_window(
        html=render_page(boot),
        title="Send to Bambuddy",
        width=width,
        height=height,
        on_message=on_message,
        on_close=on_close,
        # OrcaSlicer's print dialog is modal, so a modeless window would open behind it and ignore input.
        style=orca.host.ui.WINDOW_MODAL,
    )


class BambuddyAgent(PrinterAgentBase):
    def __init__(self) -> None:
        super().__init__()
        self._callbacks: dict[str, Callable[..., Any] | None] = {}
        self._dev_id = ""
        self._selected = ""
        self._profile: DeviceProfile | None = None
        self._printer_model = ""
        self._stop_push = threading.Event()

    def get_name(self) -> str:
        return AGENT_ID

    def get_agent_info(self) -> AgentInfo:
        return AgentInfo(AGENT_ID, "Bambuddy", __version__, "Send prints to a Bambuddy print farm queue.")

    # The send window picks the printer, so builds that support it skip OrcaSlicer's dialogs.
    def print_dialog_mode(self) -> Any:
        return orca.printer_agent.DialogMode.Takeover

    def send_dialog_mode(self) -> Any:
        return orca.printer_agent.DialogMode.Takeover

    def _emit(self, name: str, *args: Any) -> None:
        callback = self._callbacks.get(name)
        if callback is not None:
            callback(*args)

    def _reply(self, message: str) -> None:
        self._emit("local_message", self._dev_id, message)

    def _read_selected_preset(self) -> None:
        """Every Bambuddy profile points at the same server, so switching between them never reconnects."""
        preset = orca.host.preset_bundle().current_printer_preset()
        self._printer_model = preset.config_value("printer_model") or ""
        self._profile = DeviceProfile.from_preset(
            self._printer_model, preset.config_value("nozzle_diameter"), preset.config_value("nozzle_type")
        )

    def connect_printer(self, params: Any) -> int:
        self._read_selected_preset()
        self._dev_id = params.dev_id
        self._emit("local_connect", CONNECT_STATUS_OK, self._dev_id, "0")
        # Called on the UI thread, so OrcaSlicer's one-time "create a thread" prompt shows here rather than
        # failing later on the print job's worker thread.
        self._start_push_loop()
        return 0

    def disconnect_printer(self) -> int:
        self._stop_push.set()
        return 0

    def _start_push_loop(self) -> None:
        self._stop_push.set()
        stop = self._stop_push = threading.Event()

        def loop() -> None:
            while not stop.wait(PUSH_INTERVAL_SECONDS):
                if self._profile is not None:
                    self._reply(push_status(self._profile, _now_ms()))

        threading.Thread(target=loop, daemon=True).start()

    def send_message(self, dev_id: str, json_str: str, qos: int, flag: int) -> int:
        return self.send_message_to_printer(dev_id, json_str, qos, flag)

    def send_message_to_printer(self, dev_id: str, json_str: str, qos: int, flag: int) -> int:
        self._read_selected_preset()
        if self._profile is not None:
            reply = reply_to(json_str, self._profile, _now_ms())
            if reply is not None:
                self._reply(reply)
        return 0

    def start_discovery(self, start: bool, sending: bool) -> bool:
        if start and self._dev_id and self._profile is not None:
            self._emit("ssdp", ssdp_announcement(self._dev_id, self._profile))
        return True

    def get_default_config(self) -> dict[str, bool]:
        return dict(DEFAULT_SETTINGS)

    def has_config_ui(self) -> bool:
        return True

    def get_config_ui(self) -> str:
        return render_settings_page()

    def start_send_gcode_to_sdcard(self, params: Any, update_fn: Any, cancel_fn: Any, wait_fn: Any) -> int:
        if params.project_name == VERIFY_JOB_PROJECT:
            return 0
        return self._send(params, update_fn, cancel_fn)

    def start_local_print(self, params: Any, update_fn: Any, cancel_fn: Any) -> int:
        return self._send(params, update_fn, cancel_fn)

    def start_print(self, params: Any, update_fn: Any, cancel_fn: Any, wait_fn: Any) -> int:
        return self.start_local_print(params, update_fn, cancel_fn)

    def start_local_print_with_record(self, params: Any, update_fn: Any, cancel_fn: Any, wait_fn: Any) -> int:
        return self.start_local_print(params, update_fn, cancel_fn)

    def start_sdcard_print(self, params: Any, update_fn: Any, cancel_fn: Any) -> int:
        return self.start_local_print(params, update_fn, cancel_fn)

    def _send(self, params: Any, update_fn: Any, cancel_fn: Any) -> int:
        settings = effective_settings(self.get_config())
        session = SESSIONS.load()
        if session is None:
            orca.host.ui.message("Sign in to Bambuddy first: run Connect to Bambuddy from the Plugins menu.", "Bambuddy", icon="warning")
            return RESULT_CANCELED
        client = BambuddyClient(session.instance_url, session.api_key)
        preset_model = short_name(self._printer_model) or self._printer_model
        try:
            # The file says what it was sliced for, even if the selected profile changed since.
            model = _in_thread(lambda: sliced_model(Path(params.filename))) or preset_model
            # Print all exports every sliced plate into one file; a single-plate print carries just its own.
            plates = _in_thread(lambda: sliced_plates(Path(params.filename))) or [params.plate_index or DEFAULT_PLATE_ID]
            printers = _in_thread(lambda: compatible_printers(client.list_printers(), model))
        except PermissionError:
            orca.host.ui.message("Allow Bambuddy to run background tasks when OrcaSlicer asks, then try again.", "Bambuddy", icon="warning")
            return RESULT_CANCELED
        except NetworkPermissionError as error:
            orca.host.ui.message(str(error), "Bambuddy", icon="warning")
            return RESULT_CANCELED
        except BambuddyError as error:
            orca.host.ui.message(f"Could not reach Bambuddy: {error}", "Bambuddy", icon="error")
            return RESULT_FAILED
        job = SendJob(
            file_path=Path(params.filename),
            file_name=library_filename(params.project_name),
            plates=plates,
            model=model,
            printers=printers,
            options=print_options(settings),
            require_exact_colors=settings["requireExactColors"],
            group_plates=settings["groupPlates"],
        )
        started = time.monotonic()

        def report_upload(percent: int) -> None:
            if update_fn:
                update_fn(STAGE_UPLOAD, percent, f"Uploading to Bambuddy {percent}%")

        flow = SendFlow(client, job, open_send_window)
        result = flow.run(lambda: bool(cancel_fn and cancel_fn()), report_upload)
        if result == 0:
            if update_fn:
                update_fn(STAGE_FINISHED, 100, str(int(time.monotonic() - started)))
            notify_sent(flow.summary, session.instance_url)
        return result

    def bind_detect(self, dev_ip: str, sec_link: str, detect: Any) -> int:
        if self._profile is not None:
            detect.dev_id = self._dev_id
            detect.model_id = self._profile.model_id
            detect.dev_name = "Bambuddy"
            detect.connect_type = "lan"
            detect.bind_state = "free"
        return 0

    def get_user_selected_machine(self) -> str:
        return self._selected

    def set_user_selected_machine(self, dev_id: str) -> int:
        self._selected = dev_id
        return 0

    def check_cert(self) -> int:
        return 0

    def install_device_cert(self, dev_id: str, lan_only: bool) -> None:
        return None

    def ping_bind(self, ping_code: str) -> int:
        return 0

    def bind(self, *args: Any) -> int:
        return 0

    def unbind(self, dev_id: str) -> int:
        return 0

    def request_bind_ticket(self) -> tuple[int, str]:
        return 0, ""

    def get_hms_snapshot(self, dev_id: str, file_name: str, callback: Any) -> int:
        return RESULT_FAILED

    def set_server_callback(self, fn: Any) -> int:
        return 0

    def set_on_ssdp_msg_fn(self, fn: Any) -> int:
        self._callbacks["ssdp"] = fn
        return 0

    def set_on_printer_connected_fn(self, fn: Any) -> int:
        self._callbacks["printer_connected"] = fn
        return 0

    def set_on_subscribe_failure_fn(self, fn: Any) -> int:
        return 0

    def set_on_message_fn(self, fn: Any) -> int:
        self._callbacks["message"] = fn
        return 0

    def set_on_user_message_fn(self, fn: Any) -> int:
        return 0

    def set_on_local_connect_fn(self, fn: Any) -> int:
        self._callbacks["local_connect"] = fn
        return 0

    def set_on_local_message_fn(self, fn: Any) -> int:
        self._callbacks["local_message"] = fn
        return 0

    def set_queue_on_main_fn(self, fn: Any) -> int:
        return 0
