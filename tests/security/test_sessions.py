from petcam.security import sessions


def test_password_storage_and_session_invalidation(tmp_path, monkeypatch):
    monkeypatch.setattr(sessions, "AUTH_FILE", tmp_path / "auth.json")
    with sessions._lock:
        sessions._sessions.clear()
    sessions.save_password("correct horse battery staple")
    assert sessions.is_configured()
    assert sessions.verify_password("correct horse battery staple")
    assert not sessions.verify_password("incorrect password")
    token, csrf = sessions.new_session()
    assert sessions.get_session(token)["csrf"] == csrf
    sessions.invalidate_session(token)
    assert sessions.get_session(token) is None
