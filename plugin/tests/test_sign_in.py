import threading

import pytest

from bambuddy.client import BambuddyError
from bambuddy.session import Session
from bambuddy.sign_in import PendingSignIn, SignInCanceled, SignInFailed, sign_in

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
