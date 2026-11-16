"""Transactional helpers for configuration changes that restart system services."""


def run_service_commands(commands, run):
    for command, timeout, failure_message in commands:
        result = run(command, capture_output=True, text=True, timeout=timeout, check=False)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or failure_message)


def apply_config_transaction(save, previous, candidate, commands, rollback_commands, run):
    """Persist a feature config only when its dependent services transition successfully."""
    updated = save(candidate)
    try:
        run_service_commands(commands, run)
    except Exception as apply_error:
        try:
            save(previous)
        except Exception as restore_error:
            raise RuntimeError(
                f"Applying the new settings failed ({apply_error}); restoring the previous settings also failed ({restore_error})."
            ) from apply_error
        try:
            run_service_commands(rollback_commands, run)
        except Exception as rollback_error:
            raise RuntimeError(
                f"New settings failed ({apply_error}); previous settings were restored, but service recovery failed ({rollback_error})."
            ) from apply_error
        raise
    return updated
