from types import SimpleNamespace

import pytest

from petcam.application.service_transactions import (
    apply_config_transaction,
    run_service_commands,
)


def test_run_service_commands_reports_command_failure():
    with pytest.raises(RuntimeError, match="Restart failed"):
        run_service_commands(
            [(["systemctl", "restart", "petcam-stream.service"], 45, "Restart failed")],
            lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stderr=""),
        )


def test_transaction_restores_previous_config_and_services_on_failure():
    saved = []
    calls = []
    results = iter([
        SimpleNamespace(returncode=1, stderr="new service config failed"),
        SimpleNamespace(returncode=0, stderr=""),
    ])

    def run(command, **_kwargs):
        calls.append(command)
        return next(results)

    with pytest.raises(RuntimeError, match="new service config failed"):
        apply_config_transaction(
            lambda config: saved.append(config) or config,
            {"enabled": False},
            {"enabled": True},
            [(["systemctl", "restart", "new.service"], 20, "apply failed")],
            [(["systemctl", "restart", "old.service"], 20, "rollback failed")],
            run,
        )
    assert saved == [{"enabled": True}, {"enabled": False}]
    assert calls == [["systemctl", "restart", "new.service"], ["systemctl", "restart", "old.service"]]


def test_transaction_raises_original_error_after_successful_rollback():
    saved = []
    results = iter([
        SimpleNamespace(returncode=1, stderr="primary failure"),
        SimpleNamespace(returncode=1, stderr="rollback failure"),
    ])

    def run(_command, **_kwargs):
        return next(results)

    with pytest.raises(RuntimeError, match="previous settings were restored"):
        apply_config_transaction(
            lambda config: saved.append(config) or config,
            {"enabled": False},
            {"enabled": True},
            [(["apply"], 1, "apply failed")],
            [(["rollback"], 1, "rollback failed")],
            run,
        )

    assert saved == [{"enabled": True}, {"enabled": False}]
