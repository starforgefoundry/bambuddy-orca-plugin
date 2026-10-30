"""Minimal Bambuddy REST client built on the standard library."""

import json
import uuid
from collections.abc import Callable, Iterable, Iterator
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

API_PREFIX = "/api/v1"
HTTP_ERROR_MIN_STATUS = 400
TIMEOUT_SECONDS = 30
UPLOAD_TIMEOUT_SECONDS = 600
UPLOAD_CHUNK_BYTES = 256 * 1024


class BambuddyError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class NetworkPermissionError(BambuddyError):
    def __init__(self) -> None:
        super().__init__("OrcaSlicer blocked the request. Allow Bambuddy when OrcaSlicer asks, then try again.")


def normalize_instance_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if "://" not in url:
        url = f"https://{url}"
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise BambuddyError(f"Not a valid URL: {url}")
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"


class BambuddyClient:
    def __init__(self, instance_url: str, api_key: str | None = None):
        self.instance_url = instance_url
        self._api_key = api_key

    def auth_status(self) -> dict[str, Any]:
        return self._request("GET", "/auth/status")

    def start_device_sign_in(self, device_name: str) -> dict[str, Any]:
        return self._post_json("/connect/device", {"device_name": device_name})

    def poll_device_sign_in(self, device_code: str) -> dict[str, Any]:
        return self._post_json("/connect/device/token", {"device_code": device_code})

    def list_printers(self) -> list[dict[str, Any]]:
        return self._request("GET", "/printers/")

    def list_spools(self) -> list[dict[str, Any]]:
        return self._request("GET", "/inventory/spools")

    def printer_status(self, printer_id: int) -> dict[str, Any]:
        return self._request("GET", f"/printers/{printer_id}/status")

    def upload_file(
        self, path: Path, filename: str, on_progress: Callable[[int, int], None] | None = None
    ) -> dict[str, Any]:
        """Streams the file; on_progress(sent, total) is called with bytes of the file sent so far."""
        boundary = uuid.uuid4().hex
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        trailer = f"\r\n--{boundary}--\r\n".encode()
        total = path.stat().st_size

        def body() -> Iterator[bytes]:
            yield header
            sent = 0
            with path.open("rb") as file:
                while chunk := file.read(UPLOAD_CHUNK_BYTES):
                    sent += len(chunk)
                    yield chunk
                    if on_progress:
                        on_progress(sent, total)
            yield trailer

        return self._request(
            "POST",
            "/library/files",
            body=body(),
            content_type=f"multipart/form-data; boundary={boundary}",
            content_length=len(header) + total + len(trailer),
            timeout=UPLOAD_TIMEOUT_SECONDS,
        )

    def delete_file(self, file_id: int) -> None:
        self._request("DELETE", f"/library/files/{file_id}")

    def file_plates(self, file_id: int) -> dict[str, Any]:
        return self._request("GET", f"/library/files/{file_id}/plates")

    def filament_requirements(self, file_id: int, plate_id: int) -> dict[str, Any]:
        return self._request("GET", f"/library/files/{file_id}/filament-requirements?plate_id={plate_id}")

    def create_queue_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_json("/queue/", payload)

    def create_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_json("/queue/batches", payload)

    def _post_json(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("POST", path, body=json.dumps(payload).encode(), content_type="application/json")

    def _request(
        self,
        method: str,
        path: str,
        body: bytes | Iterable[bytes] | None = None,
        content_type: str | None = None,
        content_length: int | None = None,
        timeout: int = TIMEOUT_SECONDS,
    ) -> Any:
        url = urlsplit(self.instance_url)
        headers = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        # A streamed body needs its length up front, or it is sent chunked.
        if content_length is not None:
            headers["Content-Length"] = str(content_length)
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        # Not urllib: OrcaSlicer asks the user once per URL for urllib, but once per host for http.client.
        connection_class = HTTPSConnection if url.scheme == "https" else HTTPConnection
        connection = connection_class(url.netloc, timeout=timeout)
        try:
            connection.request(method, f"{url.path}{API_PREFIX}{path}", body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
        except PermissionError as error:
            raise NetworkPermissionError() from error
        except (HTTPException, OSError) as error:
            raise BambuddyError(f"Could not reach {self.instance_url}: {error}") from error
        finally:
            connection.close()
        if response.status >= HTTP_ERROR_MIN_STATUS:
            raise BambuddyError(_error_detail(raw, response.status), response.status)
        return json.loads(raw) if raw else None


def _error_detail(raw: bytes, status: int) -> str:
    try:
        detail = json.loads(raw).get("detail")
    except (ValueError, AttributeError):
        detail = None
    if isinstance(detail, list):
        detail = "; ".join(str(item.get("msg", item)) for item in detail)
    return str(detail or f"HTTP {status}")
