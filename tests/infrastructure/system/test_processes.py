import unittest
from unittest import mock

from petcam.infrastructure.system import processes as MODULE


class ProcessControlTests(unittest.TestCase):
    def test_supervisor_command_builds_worker_restart_request(self):
        self.assertEqual(MODULE.supervisor_command("restart", "gstreamer-rtsp"),
                         ["@supervisor", "restart", "gstreamer-rtsp"])

    def test_supervisor_command_rejects_unknown_actions(self):
        with self.assertRaises(ValueError):
            MODULE.supervisor_command("shell", "gstreamer-rtsp")

    def test_run_command_uses_supervisor_ipc_and_returns_process_result(self):
        with mock.patch.object(MODULE, "request", return_value={"ok": True}) as request:
            result = MODULE.run_command(["@supervisor", "restart", "camera-capture"])
        request.assert_called_once_with("restart", "camera-capture")
        self.assertEqual(result.returncode, 0)

    def test_run_command_rejects_external_process_commands(self):
        for command in ([], ["systemctl", "restart"], ["/usr/bin/example"]):
            with self.subTest(command=command), self.assertRaises(ValueError):
                MODULE.run_command(command)

    def test_worker_snapshot_reads_named_worker_from_supervisor_status(self):
        snapshot = {"workers": {"motion": {"running": True, "started_at": 10}}}
        with mock.patch.object(MODULE, "request", return_value={"ok": True, "snapshot": snapshot}):
            self.assertEqual(MODULE.worker_snapshot("motion"), snapshot["workers"]["motion"])

    def test_request_rejects_unknown_action_and_invalid_worker(self):
        with self.assertRaises(ValueError):
            MODULE.request("exec")
        with self.assertRaises(ValueError):
            MODULE.request("restart", "../unsafe")


if __name__ == "__main__":
    unittest.main()
