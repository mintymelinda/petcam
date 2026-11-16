from types import SimpleNamespace

import pytest

from petcam.application.output_coordinator import restart_gstreamer_service


def test_rtsp_restart_uses_the_service_command_adapter():
    calls = []
    restart_gstreamer_service(
        systemctl_command=lambda *args: ["systemctl", *args],
        run_command=lambda command, **options: calls.append((command, options)) or SimpleNamespace(returncode=0, stderr=""),
    )
    assert calls[0][0] == ["systemctl", "restart", "petcam-g-streamer-rtsp.service"]
    assert calls[0][1]["timeout"] == 30


def test_rtsp_restart_surfaces_service_failure():
    with pytest.raises(RuntimeError, match="cannot restart"):
        restart_gstreamer_service(
            systemctl_command=lambda *args: list(args),
            run_command=lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="cannot restart"),
        )
