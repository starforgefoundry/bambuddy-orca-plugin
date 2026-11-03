"""Runs one "send to Bambuddy" job: uploads the sliced file while the send window collects the target."""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .client import BambuddyClient, BambuddyError
from .paths import bambu_filament_ids_file
from .plate import plate_previews
from .print_name import PrintName
from .send import bambu_filament_ids, batch_payload, file_filaments, loaded_trays, queue_payload, sent_summary

RESULT_OK = 0
RESULT_CANCELED = -18
CANCEL_POLL_SECONDS = 0.2


class Window(Protocol):
    def post(self, data: Any) -> None: ...
    def close(self) -> None: ...


OpenWindow = Callable[[dict[str, Any], Callable[[Any], None], Callable[[], None]], Window]


@dataclass(frozen=True)
class SendJob:
    file_path: Path
    name: PrintName
    plates: list[int]
    model: str
    printers: list[dict[str, Any]]
    options: dict[str, bool]
    require_exact_colors: bool = False
    group_plates: bool = False


def plate_names(plates_response: dict[str, Any]) -> dict[int, str]:
    return {p["index"]: p["name"] for p in plates_response.get("plates") or [] if p.get("name")}


class SendFlow:
    def __init__(self, client: BambuddyClient, job: SendJob, open_window: OpenWindow):
        self._client = client
        self._job = job
        self._open_window = open_window
        self._name = job.name
        self._lock = threading.Lock()
        self._finished = threading.Event()
        self._result = RESULT_CANCELED
        self._file_id: int | None = None
        self._batch_id: int | None = None
        self._filaments: dict[int, list[dict[str, Any]]] = {}
        self._canceled = False
        self._submitted = False
        self._window: Window | None = None
        self._upload_percent = 0
        self.summary = ""

    def run(self, is_canceled: Callable[[], bool], on_progress: Callable[[int], None] | None = None) -> int:
        """on_progress(percent) is called from this thread, the one OrcaSlicer's progress callback must use."""
        self._window = self._open_window(self._boot(), self._on_message, self._on_close)
        self._spawn(self._upload)
        reported = -1
        while not self._finished.wait(CANCEL_POLL_SECONDS):
            if is_canceled():
                self._cancel()
                self._window.close()
                return RESULT_CANCELED
            if on_progress and self._upload_percent != reported:
                reported = self._upload_percent
                on_progress(reported)
        return self._result

    def _boot(self) -> dict[str, Any]:
        return {
            "view": "send",
            "instanceUrl": self._client.instance_url,
            "printName": self._job.name.base,
            "nameSuffix": self._job.name.suffix,
            "model": self._job.model,
            "printers": self._job.printers,
            "options": self._job.options,
            "requireExactColors": self._job.require_exact_colors,
            "groupPlates": self._job.group_plates,
        }

    def _spawn(self, target: Callable[..., None], *args: Any) -> None:
        threading.Thread(target=target, args=args, daemon=True).start()

    def _post(self, data: dict[str, Any]) -> None:
        if self._window is not None:
            self._window.post(data)

    def _report_upload(self, sent: int, total: int) -> None:
        percent = sent * 100 // total if total else 100
        if percent != self._upload_percent:
            self._upload_percent = percent
            self._post({"type": "upload-progress", "percent": percent})

    def _upload(self) -> None:
        try:
            uploaded = self._client.upload_file(self._job.file_path, self._job.name.file_name, self._report_upload)
            with self._lock:
                self._file_id = uploaded["id"]
                canceled = self._canceled
            if canceled:
                self._delete_upload()
                return
            try:
                names = plate_names(self._client.file_plates(uploaded["id"]))
            except BambuddyError:
                names = {}
            previews = plate_previews(self._job.file_path, self._job.plates)
            bambu_ids = bambu_filament_ids(bambu_filament_ids_file())
            plates = []
            for plate_id in self._job.plates:
                requirements = self._client.filament_requirements(uploaded["id"], plate_id)
                self._filaments[plate_id] = file_filaments(requirements, bambu_ids)
                plates.append(
                    {
                        "plateId": plate_id,
                        "name": names.get(plate_id, f"Plate {plate_id}"),
                        "filaments": self._filaments[plate_id],
                        "preview": previews.get(plate_id),
                    }
                )
            self._post({"type": "file-ready", "plates": plates})
        except BambuddyError as error:
            self._post({"type": "upload-failed", "error": str(error)})

    def _load_trays(self, printer_id: int) -> None:
        try:
            trays = loaded_trays(self._client.printer_status(printer_id))
            self._post({"type": "trays-loaded", "printerId": printer_id, "trays": trays, "error": None})
        except BambuddyError as error:
            self._post({"type": "trays-loaded", "printerId": printer_id, "trays": [], "error": str(error)})

    def _submit(self, request: dict[str, Any]) -> None:
        with self._lock:
            file_id = self._file_id
        if file_id is None:
            self._post({"type": "send-result", "error": "The file has not finished uploading."})
            return
        try:
            self._rename(file_id, self._name.renamed(str(request.get("printName") or self._name.base)))
        except BambuddyError as error:
            self._post({"type": "send-result", "error": f"Could not rename the file: {error}"})
            return
        queued, failures = [], []
        batch_id, batch_error = None, None
        if request.get("groupPlates") and len(request["plates"]) > 1:
            try:
                batch_id = self._batch(file_id, len(request["plates"]))
            except BambuddyError as error:
                batch_error = str(error)
        for plate in request["plates"]:
            plate_id = int(plate["plateId"])
            plate_request = {**request, "amsMapping": plate.get("amsMapping")}
            filaments = self._filaments.get(plate_id, [])
            try:
                payload = queue_payload(plate_request, file_id, plate_id, self._job.model, filaments, batch_id)
                self._client.create_queue_item(payload)
                queued.append(plate_id)
            except BambuddyError as error:
                failures.append(f"plate {plate_id}: {error}" if len(request["plates"]) > 1 else str(error))
        if not queued:
            self._post({"type": "send-result", "error": "; ".join(failures) or "No plates selected."})
            return
        with self._lock:
            self._submitted = True
        self.summary = sent_summary(request, self._name.file_name, self._job.model, self._job.printers, len(queued))
        if failures:
            self.summary += " Not queued: " + "; ".join(failures)
        if batch_error:
            self.summary += f" Not grouped as a batch: {batch_error}"
        self._result = RESULT_OK
        self._post({"type": "send-result", "error": None})
        self._finished.set()

    def _batch(self, file_id: int, plate_count: int) -> int:
        """One batch per send window, so a retry after a failed send reuses it instead of leaving an empty one."""
        if self._batch_id is None:
            self._batch_id = self._client.create_batch(batch_payload(self._name.file_name, file_id, plate_count))["id"]
        return self._batch_id

    def _rename(self, file_id: int, name: PrintName) -> None:
        if name.file_name != self._name.file_name:
            self._client.rename_file(file_id, name.file_name)
        self._name = name

    def _on_message(self, data: Any) -> None:
        if not isinstance(data, dict):
            return
        if data.get("type") == "load-trays":
            self._spawn(self._load_trays, int(data["printerId"]))
        elif data.get("type") == "send":
            self._spawn(self._submit, data["request"])

    def _on_close(self) -> None:
        with self._lock:
            submitted = self._submitted
        if not submitted:
            self._cancel()
        self._finished.set()

    def _cancel(self) -> None:
        with self._lock:
            if self._canceled or self._submitted:
                return
            self._canceled = True
            uploaded = self._file_id is not None
        if uploaded:
            self._spawn(self._delete_upload)

    def _delete_upload(self) -> None:
        try:
            if self._file_id is not None:
                self._client.delete_file(self._file_id)
        except BambuddyError:
            pass
