from types import SimpleNamespace

import pytest

from petcam.application.service_transactions import apply_config_transaction


def test_config_transaction_saves_and_runs_commands():
    saved = []
    commands = []

    def save(config):
        saved.append(config.copy())
        return config

    def run(command, **options):
        commands.append(command)
        return SimpleNamespace(returncode=0, stderr="")

    updated = apply_config_transaction(
        save, {"enabled": False}, {"enabled": True},
        [(["systemctl", "restart", "worker"], 10, "restart failed")],
        [(["systemctl", "restart", "worker"], 10, "rollback failed")],
        run,
    )
    assert updated == {"enabled": True}
    assert saved == [{"enabled": True}]
    assert commands == [["systemctl", "restart", "worker"]]


def test_config_transaction_restores_previous_config_after_service_failure():
    saved = []
    commands = []

    def save(config):
        saved.append(config.copy())
        return config

    def run(command, **options):
        commands.append(command)
        return SimpleNamespace(
            returncode=1 if len(commands) == 1 else 0,
            stderr="worker failed",
        )

    with pytest.raises(RuntimeError, match="worker failed"):
        apply_config_transaction(
            save, {"enabled": False}, {"enabled": True},
            [(["systemctl", "restart", "worker"], 10, "restart failed")],
            [(["systemctl", "restart", "worker"], 10, "rollback failed")],
            run,
        )
    assert saved == [{"enabled": True}, {"enabled": False}]
    assert len(commands) == 2
