"""Browser sign-in: Bambuddy shows a consent page in the system browser while the plugin polls for the key.

Instances older than browser sign-in take an API key the user pastes in instead.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from .client import BambuddyClient, BambuddyError
from .session import Session

HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_METHOD_NOT_ALLOWED = 405
DEVICE_SIGN_IN_MISSING = (HTTP_NOT_FOUND, HTTP_METHOD_NOT_ALLOWED)
KEY_REJECTED = (HTTP_UNAUTHORIZED, HTTP_FORBIDDEN)


class SignInCanceled(Exception):
    pass


class SignInFailed(Exception):
    pass


class DeviceSignInUnavailable(Exception):
    pass


@dataclass(frozen=True)
class PendingSignIn:
    user_code: str
    verification_url: str


def sign_in(
    client: BambuddyClient,
    device_name: str,
    open_browser: Callable[[str], None],
    on_pending: Callable[[PendingSignIn], None],
    stop: threading.Event,
) -> Session:
    if not client.auth_status().get("auth_enabled"):
        return Session(client.instance_url, None, None)

    try:
        grant = client.start_device_sign_in(device_name)
    except BambuddyError as error:
        if error.status in DEVICE_SIGN_IN_MISSING:
            raise DeviceSignInUnavailable() from error
        raise
    pending = PendingSignIn(grant["user_code"], client.instance_url + grant["verification_path"])
    on_pending(pending)
    open_browser(pending.verification_url)

    deadline = time.monotonic() + grant["expires_in"]
    while not stop.wait(grant["interval"]):
        if time.monotonic() > deadline:
            raise SignInFailed("The sign-in request expired. Try again.")
        try:
            result = client.poll_device_sign_in(grant["device_code"])
        except BambuddyError as error:
            if error.status == HTTP_NOT_FOUND:
                raise SignInFailed("Sign-in was denied or expired.") from error
            raise
        if result["status"] == "approved":
            return Session(client.instance_url, result["key"], result["username"])
    raise SignInCanceled()


def sign_in_with_api_key(client: BambuddyClient) -> Session:
    try:
        client.list_printers()
    except BambuddyError as error:
        if error.status in KEY_REJECTED:
            raise SignInFailed(f"Bambuddy rejected the API key: {error}") from error
        raise
    try:
        username = client.current_user().get("username")
    except BambuddyError:
        username = None
    return Session(client.instance_url, client.api_key, username)
