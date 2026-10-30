import stat

from bambuddy.session import Session, SessionStore


def test_round_trip_and_private_file(tmp_path):
    store = SessionStore(tmp_path / "nested" / "session.json")
    assert store.load() is None

    session = Session("https://b.local", "bb_key", "alice")
    store.save(session)
    assert store.load() == session
    assert stat.S_IMODE((tmp_path / "nested" / "session.json").stat().st_mode) == 0o600

    store.clear()
    assert store.load() is None
