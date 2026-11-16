"""System service state and lifecycle operations."""

import subprocess

from .processes import run_command, systemctl_command


def is_active(unit, run=run_command):
    """Return whether a systemd unit is active without raising for inactive units."""
    try:
        return run(
            systemctl_command("is-active", "--quiet", unit),
            check=False,
            timeout=1,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def restart(unit, *, timeout=30, run=run_command):
    """Restart one systemd unit and raise a useful error on failure."""
    result = run(
        systemctl_command("restart", unit),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"Unable to restart {unit}.")
