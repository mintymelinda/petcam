import json
from types import SimpleNamespace

from petcam.infrastructure.streaming.status import snapshot


def test_status_combines_systemd_state_with_fresh_heartbeat(tmp_path):
    status_file = tmp_path / "status.json"
    status_file.write_text(json.dumps({
        "state": "publishing", "updated_at": 99, "fps": 25, "source": "native_h264",
    }))
    result = snapshot(
        status_file,
        run=lambda *args, **kwargs: SimpleNamespace(returncode=0),
        clock=lambda: 100,
    )
    assert result["service_active"] is True
    assert result["active"] is True
    assert result["fps"] == 25
