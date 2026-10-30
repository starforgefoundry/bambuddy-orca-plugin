import stat
import sys

import pytest

from bambuddy.session import Session, SessionStore


def test_round_trip(tmp_path):
    store = SessionStore(tmp_path / "nested" / "session.json")
    assert store.load() is None

    session = Session("https://b.local", "bb_key", "alice")
    store.save(session)
    assert store.load() == session

    store.clear()
    assert store.load() is None


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no POSIX file modes")
def test_session_file_is_private(tmp_path):
    path = tmp_path / "session.json"
    SessionStore(path).save(Session("https://b.local", "bb_key", "alice"))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
