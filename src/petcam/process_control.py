"""Shared systemd command construction and execution for PetCam processes."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from typing import Any

SYSTEMCTL = "/usr/bin/systemctl"
_PROFILE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\\Z")


def systemctl_command(*arguments: str) -> list[str]:
    """Build an absolute-path systemctl invocation without a shell."""
    if not arguments or any(not isinstance(value, str) or not value for value in arguments):
        raise ValueError("systemctl arguments must be non-empty strings")
    return [SYSTEMCTL, *arguments]


def run_systemctl(*arguments: str, runner: Callable[..., Any] = subprocess.run, **options: Any) -> Any:
    """Run systemctl through an injectable process runner."""
    return runner(systemctl_command(*arguments), **options)


def stream_instance_unit(profile_id: str) -> str:
    """Return a stream worker unit only for a safe profile identifier."""
    if not isinstance(profile_id, str) or not _PROFILE_ID.fullmatch(profile_id):
        raise ValueError("Invalid camera profile identifier")
    return f"petcam-stream@{profile_id}.service"
