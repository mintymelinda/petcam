import pytest

from petcam.infrastructure.system.processes import run_command, stream_instance_unit, systemctl_command


def test_systemctl_command_uses_absolute_executable_and_no_shell():
    assert systemctl_command("restart", "petcam-stream.service") == [
        "/usr/bin/systemctl", "restart", "petcam-stream.service",
    ]
    assert systemctl_command("status", "petcam-stream.service", sudo=True)[:2] == ["sudo", "-n"]


def test_process_runner_rejects_shell_strings_and_preserves_arguments():
    with pytest.raises(ValueError, match="process command"):
        run_command("systemctl restart petcam-stream.service")
    called = []
    result = run_command(["echo", "ok"], runner=lambda command, **options: called.append(command) or "done")
    assert result == "done"
    assert called == [["echo", "ok"]]


def test_stream_unit_name_requires_safe_profile_identifier():
    assert stream_instance_unit("usb-camera") == "petcam-stream@usb-camera.service"
    with pytest.raises(ValueError):
        stream_instance_unit("../unexpected")
