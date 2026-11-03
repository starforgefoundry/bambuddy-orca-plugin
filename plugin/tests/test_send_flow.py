import threading
from pathlib import Path

import pytest

from bambuddy.client import BambuddyError
from bambuddy.print_name import PrintName
from bambuddy.send_flow import RESULT_CANCELED, RESULT_OK, SendFlow, SendJob

BATCH_ID = 41
OPTIONS = {"bedLevelling": True, "flowCali": False, "vibrationCali": False, "timelapse": False}
JOB = SendJob(Path("plate.3mf"), PrintName("Benchy"), [2], "Bambu Lab X1 Carbon", [], OPTIONS)
REQUEST = {
    "targetKind": "any",
    "printerId": None,
    "location": None,
    "dispatch": "now",
    "plates": [{"plateId": 2, "amsMapping": None}],
    "forceColorMatch": False,
    "options": OPTIONS,
}


class FakeClient:
    instance_url = "https://b.local"

    def __init__(self, fail_queue=False, failing_plates=(), fail_batch=False, fail_rename=False):
        self.fail_queue = fail_queue
        self.failing_plates = set(failing_plates)
        self.fail_batch = fail_batch
        self.fail_rename = fail_rename
        self.uploaded_names = []
        self.renamed = []
        self.batches = []
        self.queued = []
        self.deleted = []
        self.uploaded = threading.Event()

    def file_plates(self, file_id):
        return {"plates": [{"index": 1, "name": "Left"}, {"index": 2, "name": ""}]}

    def upload_file(self, path, filename, on_progress=None):
        self.uploaded_names.append(filename)
        if on_progress:
            on_progress(50, 100)
            on_progress(100, 100)
        self.uploaded.set()
        return {"id": 9}

    def filament_requirements(self, file_id, plate_id):
        return {"filaments": [{"slot_id": 1, "type": "PLA", "color": "#FFFFFF", "used_grams": 1}]}

    def create_queue_item(self, payload):
        if self.fail_queue or payload["plate_id"] in self.failing_plates:
            raise BambuddyError("No active printers for model")
        self.queued.append(payload)

    def create_batch(self, payload):
        if self.fail_batch:
            raise BambuddyError("Forbidden")
        self.batches.append(payload)
        return {"id": BATCH_ID}

    def delete_file(self, file_id):
        self.deleted.append(file_id)

    def rename_file(self, file_id, filename):
        if self.fail_rename:
            raise BambuddyError("Invalid filename")
        self.renamed.append((file_id, filename))


class FakeWindow:
    def __init__(self, on_message, on_close):
        self.on_message = on_message
        self.on_close = on_close
        self.posts = []
        self.ready = threading.Event()

    def post(self, data):
        self.posts.append(data)
        if data["type"] == "file-ready":
            self.ready.set()
        if data["type"] == "send-result" and data["error"] is None:
            self.close()

    def close(self):
        self.on_close()


def run_flow(client, script, is_canceled=lambda: False, on_progress=None, job=JOB):
    windows = []

    def open_window(boot, on_message, on_close):
        window = FakeWindow(on_message, on_close)
        windows.append(window)
        threading.Thread(target=script, args=(window,), daemon=True).start()
        return window

    result = SendFlow(client, job, open_window).run(is_canceled, on_progress)
    return result, windows[0]


def test_upload_progress_reaches_window_and_orca():
    client = FakeClient()
    reported = []

    def script(window):
        window.ready.wait(2)
        threading.Event().wait(0.5)
        window.on_message({"type": "send", "request": REQUEST})

    _, window = run_flow(client, script, on_progress=reported.append)
    assert [p["percent"] for p in window.posts if p["type"] == "upload-progress"] == [50, 100]
    assert reported[-1] == 100


def test_send_queues_uploaded_file():
    client = FakeClient()

    def script(window):
        window.ready.wait(2)
        window.on_message({"type": "send", "request": REQUEST})

    result, window = run_flow(client, script)
    assert result == RESULT_OK
    assert client.queued[0]["library_file_id"] == 9
    assert client.queued[0]["plate_id"] == 2
    assert client.queued[0]["target_model"] == "X1C"
    ready = [p for p in window.posts if p["type"] == "file-ready"][0]
    assert ready["plates"] == [{"plateId": 2, "name": "Plate 2", "filaments": [{"slotId": 1, "type": "PLA", "color": "#FFFFFF", "usedGrams": 1, "trayInfoIdx": None}], "preview": None}]


def test_queue_error_is_shown_and_window_stays_open():
    client = FakeClient(fail_queue=True)

    def script(window):
        window.ready.wait(2)
        window.on_message({"type": "send", "request": REQUEST})
        while not any(p["type"] == "send-result" for p in window.posts):
            pass
        window.close()

    result, window = run_flow(client, script)
    assert result == RESULT_CANCELED
    assert {"type": "send-result", "error": "No active printers for model"} in window.posts
    assert eventually(lambda: client.deleted == [9])


def test_closing_window_cancels_and_deletes_upload():
    client = FakeClient()

    def script(window):
        window.ready.wait(2)
        window.close()

    result, _ = run_flow(client, script)
    assert result == RESULT_CANCELED
    assert eventually(lambda: client.deleted == [9])


def test_orca_cancel_closes_window():
    client = FakeClient()
    result, _ = run_flow(client, lambda window: None, is_canceled=lambda: client.uploaded.is_set())
    assert result == RESULT_CANCELED


def test_renamed_print_keeps_plate_suffix():
    client = FakeClient()
    job = SendJob(Path("plate.3mf"), PrintName("Benchy", "_plate_2"), [2], "X1C", [], OPTIONS)

    def script(window):
        window.ready.wait(2)
        window.on_message({"type": "send", "request": {**REQUEST, "printName": "Boat"}})

    flow = SendFlow(client, job, lambda boot, on_message, on_close: start(script, FakeWindow(on_message, on_close)))
    assert flow.run(lambda: False) == RESULT_OK
    assert client.uploaded_names == ["Benchy_plate_2.gcode.3mf"]
    assert client.renamed == [(9, "Boat_plate_2.gcode.3mf")]
    assert flow.summary.startswith("Boat_plate_2.gcode.3mf is queued")


def test_unchanged_name_is_not_renamed():
    client = FakeClient()
    send_once(client, {**REQUEST, "printName": "Benchy"}, JOB)
    assert client.renamed == []


def test_failed_rename_keeps_window_open():
    client = FakeClient(fail_rename=True)

    def script(window):
        window.ready.wait(2)
        window.on_message({"type": "send", "request": {**REQUEST, "printName": "a/b"}})
        eventually(lambda: any(p["type"] == "send-result" for p in window.posts))
        window.close()

    result, window = run_flow(client, script)
    assert result == RESULT_CANCELED
    assert {"type": "send-result", "error": "Could not rename the file: Invalid filename"} in window.posts
    assert client.queued == []


def eventually(check, timeout=2.0):
    done = threading.Event()
    deadline = threading.Timer(timeout, done.set)
    deadline.start()
    while not check() and not done.wait(0.01):
        pass
    deadline.cancel()
    return check()


def test_print_all_queues_each_selected_plate():
    client = FakeClient(failing_plates={3})
    job = SendJob(Path("plate.3mf"), PrintName("Benchy"), [1, 2, 3], "X1C", [], OPTIONS)
    request = {
        **REQUEST,
        "targetKind": "printer",
        "printerId": 7,
        "plates": [{"plateId": 1, "amsMapping": [0]}, {"plateId": 3, "amsMapping": [1]}],
    }

    def script(window):
        window.ready.wait(2)
        window.on_message({"type": "send", "request": request})

    windows = []

    def open_window(boot, on_message, on_close):
        window = FakeWindow(on_message, on_close)
        windows.append(window)
        threading.Thread(target=script, args=(window,), daemon=True).start()
        return window

    flow = SendFlow(client, job, open_window)
    assert flow.run(lambda: False) == RESULT_OK

    ready = [p for p in windows[0].posts if p["type"] == "file-ready"][0]
    assert [(p["plateId"], p["name"]) for p in ready["plates"]] == [(1, "Left"), (2, "Plate 2"), (3, "Plate 3")]
    assert [(q["plate_id"], q["ams_mapping"]) for q in client.queued] == [(1, [0])]
    assert flow.summary.startswith("Benchy.gcode.3mf is queued")
    assert "Not queued: plate 3: No active printers for model" in flow.summary


MULTI_PLATE_JOB = SendJob(Path("plate.3mf"), PrintName("Benchy"), [1, 2], "X1C", [], OPTIONS)
GROUPED_REQUEST = {
    **REQUEST,
    "groupPlates": True,
    "plates": [{"plateId": 1, "amsMapping": None}, {"plateId": 2, "amsMapping": None}],
}


def send_once(client, request, job=MULTI_PLATE_JOB):
    def script(window):
        window.ready.wait(2)
        window.on_message({"type": "send", "request": request})

    flow = SendFlow(client, job, lambda boot, on_message, on_close: start(script, FakeWindow(on_message, on_close)))
    return flow, flow.run(lambda: False)


def start(script, window):
    threading.Thread(target=script, args=(window,), daemon=True).start()
    return window


def test_grouped_plates_share_one_batch():
    client = FakeClient()
    _, result = send_once(client, GROUPED_REQUEST)
    assert result == RESULT_OK
    assert client.batches == [{"name": "Benchy · 2 plates", "library_file_id": 9}]
    assert [q["batch_id"] for q in client.queued] == [BATCH_ID, BATCH_ID]


def test_one_plate_is_never_grouped():
    client = FakeClient()
    send_once(client, {**GROUPED_REQUEST, "plates": [{"plateId": 1, "amsMapping": None}]})
    assert client.batches == []
    assert "batch_id" not in client.queued[0]


def test_failed_batch_still_queues_plates_ungrouped():
    client = FakeClient(fail_batch=True)
    flow, result = send_once(client, GROUPED_REQUEST)
    assert result == RESULT_OK
    assert [q["plate_id"] for q in client.queued] == [1, 2]
    assert flow.summary.endswith("Not grouped as a batch: Forbidden")


def test_retry_after_failed_send_reuses_batch():
    client = FakeClient(fail_queue=True)

    def script(window):
        window.ready.wait(2)
        window.on_message({"type": "send", "request": GROUPED_REQUEST})
        eventually(lambda: any(p["type"] == "send-result" for p in window.posts))
        client.fail_queue = False
        window.on_message({"type": "send", "request": GROUPED_REQUEST})

    flow = SendFlow(client, MULTI_PLATE_JOB, lambda boot, on_message, on_close: start(script, FakeWindow(on_message, on_close)))
    assert flow.run(lambda: False) == RESULT_OK
    assert len(client.batches) == 1
    assert [q["batch_id"] for q in client.queued] == [BATCH_ID, BATCH_ID]
