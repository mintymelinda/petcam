from pathlib import Path
from urllib.error import URLError

from petcam.application.capture_coordinator import live_status


def test_capture_status_returns_empty_when_no_backend_is_reachable(tmp_path):
    def fail(*args, **kwargs):
        raise URLError("offline")

    result = live_status(
        tmp_path / "missing.conf",
        parse_config=lambda path: {"PORT": "8081"},
        urlopen=fail,
        kill=lambda pid, signal: None,
        path_factory=lambda path: tmp_path / Path(path).name,
    )
    assert result == {}
