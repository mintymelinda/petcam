from types import SimpleNamespace

from petcam.infrastructure.system.services import is_active, restart


def test_service_state_distinguishes_active_and_inactive_units():
    assert is_active("petcam-stream.service", run=lambda *a, **k: SimpleNamespace(returncode=0))
    assert not is_active("petcam-stream.service", run=lambda *a, **k: SimpleNamespace(returncode=3))


def test_service_restart_surfaces_command_error():
    try:
        restart(
            "petcam-stream.service",
            run=lambda *a, **k: SimpleNamespace(returncode=1, stderr="systemd failed"),
        )
    except RuntimeError as error:
        assert "systemd failed" in str(error)
    else:
        raise AssertionError("restart should fail when systemd reports an error")
