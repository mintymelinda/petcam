"""Shared systemd command construction and execution for PetCam processes."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from typing import Any

SYSTEMCTL = "/usr/bin/systemctl"
_PROFILE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def systemctl_command(*arguments: str, sudo: bool = False) -> list[str]:
    """Build an absolute-path systemctl invocation without a shell."""
    if not arguments or any(not isinstance(value, str) or not value for value in arguments):
        raise ValueError("systemctl arguments must be non-empty strings")
    return (["sudo", "-n"] if sudo else []) + [SYSTEMCTL, *arguments]


def run_command(
    command: list[str],
    *,
    runner: Callable[..., Any] | None = None,
    **options: Any,
) -> Any:
    """Execute an argument vector through the shared infrastructure process adapter."""
    if not isinstance(command, (list, tuple)) or not command or any(
        not isinstance(value, str) or not value for value in command
    ):
        raise ValueError("process command must be a non-empty sequence of strings")
    return (runner or subprocess.run)(list(command), **options)


def run_systemctl(
    *arguments: str,
    runner: Callable[..., Any] | None = None,
    sudo: bool = False,
    **options: Any,
) -> Any:
    """Run systemctl through the shared process adapter."""
    return run_command(
        systemctl_command(*arguments, sudo=sudo),
        runner=runner,
        **options,
    )


def stream_instance_unit(profile_id: str) -> str:
    """Return a stream worker unit only for a safe profile identifier."""
    if not isinstance(profile_id, str) or not _PROFILE_ID.fullmatch(profile_id):
        raise ValueError("Invalid camera profile identifier")
    return f"petcam-stream@{profile_id}.service"
