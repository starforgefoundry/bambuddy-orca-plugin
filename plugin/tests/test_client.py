import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from bambuddy.client import BambuddyClient, BambuddyError, NetworkPermissionError, normalize_instance_url


class Handler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, *args):
        pass

    def _record(self):
        length = int(self.headers.get("Content-Length") or 0)
        Handler.requests.append(
            {"method": self.command, "path": self.path, "headers": self.headers, "body": self.rfile.read(length)}
        )

    def do_GET(self):
        self._record()
        if self.path == "/api/v1/printers/":
            self._reply(200, [{"id": 1}])
        else:
            self._reply(401, {"detail": "Authentication required"})

    def do_POST(self):
        self._record()
        self._reply(200, {"id": 5})

    def do_PUT(self):
        self._record()
        self._reply(200, {"id": 5})

    def _reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def server():
    Handler.requests = []
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_sends_api_key(server):
    assert BambuddyClient(server, "bb_x").list_printers() == [{"id": 1}]
    assert Handler.requests[0]["headers"]["X-API-Key"] == "bb_x"


def test_error_detail_is_surfaced(server):
    with pytest.raises(BambuddyError, match="Authentication required") as error:
        BambuddyClient(server).printer_status(1)
    assert error.value.status == 401


def test_upload_is_multipart_with_file_field(server, tmp_path):
    path = tmp_path / "plate.gcode.3mf"
    path.write_bytes(b"PK\x03\x04data")
    assert BambuddyClient(server).upload_file(path, "Benchy.gcode.3mf") == {"id": 5}
    request = Handler.requests[0]
    assert request["path"] == "/api/v1/library/files"
    assert request["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'name="file"; filename="Benchy.gcode.3mf"' in request["body"]
    assert b"PK\x03\x04data" in request["body"]


def test_upload_streams_with_progress(server, tmp_path, monkeypatch):
    monkeypatch.setitem(BambuddyClient.upload_file.__globals__, "UPLOAD_CHUNK_BYTES", 4)
    path = tmp_path / "plate.gcode.3mf"
    path.write_bytes(b"PK\x03\x04datadata")
    progress = []
    BambuddyClient(server).upload_file(path, "a.gcode.3mf", lambda sent, total: progress.append((sent, total)))
    assert progress == [(4, 12), (8, 12), (12, 12)]
    assert Handler.requests[0]["body"].count(b"PK\x03\x04datadata") == 1


AUDITED_EVENTS = ("urllib.Request", "http.client.connect")
audit_log: list[tuple[str, tuple]] = []
sys.addaudithook(lambda event, args: audit_log.append((event, args)) if event in AUDITED_EVENTS else None)


def test_requests_are_audited_by_host_not_url(server):
    """OrcaSlicer grants urllib.Request per URL, so every new file id would prompt again."""
    audit_log.clear()
    client = BambuddyClient(server)
    client.list_printers()
    client.create_queue_item({})
    assert [event for event, _ in audit_log] == ["http.client.connect", "http.client.connect"]
    assert {args[1] for _, args in audit_log} == {"127.0.0.1"}


def test_blocked_request_asks_to_retry(server, monkeypatch):
    def deny(*args):
        raise PermissionError("audit permission required")

    monkeypatch.setattr("http.client.HTTPConnection.connect", deny)
    with pytest.raises(NetworkPermissionError, match="try again"):
        BambuddyClient(server).list_printers()


def test_unreachable_instance():
    with pytest.raises(BambuddyError, match="Could not reach"):
        BambuddyClient("http://127.0.0.1:1").auth_status()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("bambuddy.local/", "https://bambuddy.local"), ("http://10.0.0.2:8000", "http://10.0.0.2:8000")],
)
def test_normalize_instance_url(raw, expected):
    assert normalize_instance_url(raw) == expected


def test_normalize_rejects_other_schemes():
    with pytest.raises(BambuddyError):
        normalize_instance_url("ftp://x")


def test_rename_file_puts_new_filename(server):
    BambuddyClient(server, "bb_x").rename_file(9, "Boat.gcode.3mf")
    request = Handler.requests[0]
    assert (request["method"], request["path"]) == ("PUT", "/api/v1/library/files/9")
    assert json.loads(request["body"]) == {"filename": "Boat.gcode.3mf"}
