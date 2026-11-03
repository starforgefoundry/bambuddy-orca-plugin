import threading

import pytest

from bambuddy.client import BambuddyError
from bambuddy.session import Session
from bambuddy.sign_in import (
    DeviceSignInUnavailable,
    PendingSignIn,
    SignInCanceled,
    SignInFailed,
    sign_in,
    sign_in_with_api_key,
)

GRANT = {
    "device_code": "dc",
    "user_code": "ABCD-EFGH",
    "verification_path": "/connect",
    "expires_in": 600,
    "interval": 0,
}


class FakeClient:
    instance_url = "https://b.local"

    def __init__(self, polls, auth_enabled=True):
        self._polls = iter(polls)
        self._auth_enabled = auth_enabled
        self.device_names = []

    def auth_status(self):
        return {"auth_enabled": self._auth_enabled}

    def start_device_sign_in(self, device_name):
        self.device_names.append(device_name)
        return GRANT

    def poll_device_sign_in(self, device_code):
        assert device_code == "dc"
        result = next(self._polls)
        if isinstance(result, Exception):
            raise result
        return result


def run(client, stop=None):
    opened, pending = [], []
    session = sign_in(client, "studio-mac", opened.append, pending.append, stop or threading.Event())
    return session, opened, pending


def test_approved_after_pending():
    client = FakeClient([{"status": "pending"}, {"status": "approved", "key": "bb_k", "username": "alice"}])
    session, opened, pending = run(client)
    assert session == Session("https://b.local", "bb_k", "alice")
    assert opened == ["https://b.local/connect"]
    assert pending == [PendingSignIn("ABCD-EFGH", opened[0])]
    assert client.device_names == ["studio-mac"]


def test_auth_disabled_skips_browser():
    session, opened, _ = run(FakeClient([], auth_enabled=False))
    assert session == Session("https://b.local", None, None)
    assert opened == []


def test_denied():
    with pytest.raises(SignInFailed, match="denied or expired"):
        run(FakeClient([BambuddyError("expired_or_denied", 404)]))


def test_server_errors_propagate():
    with pytest.raises(BambuddyError):
        run(FakeClient([BambuddyError("boom", 500)]))


def test_cancel():
    stop = threading.Event()
    stop.set()
    with pytest.raises(SignInCanceled):
        run(FakeClient([]), stop)


@pytest.mark.parametrize("status", [404, 405])
def test_instance_without_device_sign_in_needs_api_key(status):
    client = FakeClient([])

    def missing(device_name):
        raise BambuddyError("Not Found", status)

    client.start_device_sign_in = missing
    with pytest.raises(DeviceSignInUnavailable):
        run(client)


class KeyClient:
    instance_url = "https://b.local"
    api_key = "bb_k"

    def __init__(self, printers_error=None, me=None):
        self._printers_error = printers_error
        self._me = me

    def list_printers(self):
        if self._printers_error:
            raise self._printers_error
        return []

    def current_user(self):
        if isinstance(self._me, Exception):
            raise self._me
        return self._me


def test_api_key_session_uses_key_owner():
    assert sign_in_with_api_key(KeyClient(me={"username": "alice"})) == Session("https://b.local", "bb_k", "alice")


def test_api_key_without_user_lookup():
    session = sign_in_with_api_key(KeyClient(me=BambuddyError("Not Found", 404)))
    assert session == Session("https://b.local", "bb_k", None)


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_api_key(status):
    with pytest.raises(SignInFailed, match="rejected the API key"):
        sign_in_with_api_key(KeyClient(printers_error=BambuddyError("Invalid API key", status)))


def test_api_key_server_errors_propagate():
    with pytest.raises(BambuddyError):
        sign_in_with_api_key(KeyClient(printers_error=BambuddyError("boom", 500)))
