import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from petcam.infrastructure.system import supervisor, processes


class SupervisorTests(unittest.TestCase):
    def test_feature_switch_fails_closed_for_missing_or_invalid_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feature.json"
            self.assertFalse(supervisor.read_enabled(path))
            path.write_text("{", encoding="utf-8")
            self.assertFalse(supervisor.read_enabled(path))
            path.write_text(json.dumps({"enabled": "yes"}), encoding="utf-8")
            self.assertFalse(supervisor.read_enabled(path))
            path.write_text(json.dumps({"enabled": True}), encoding="utf-8")
            self.assertTrue(supervisor.read_enabled(path))
            path.write_text("MQTT_ENABLED=true\n", encoding="utf-8")
            self.assertTrue(supervisor.read_enabled(path))
            path.write_text("ENABLED=false\n", encoding="utf-8")
            self.assertFalse(supervisor.read_enabled(path))

    def test_worker_process_is_started_and_tracked(self):
        worker = supervisor.Worker("test", ("python", "-c", "pass"))
        manager = supervisor.Supervisor([worker])
        with mock.patch.object(supervisor.subprocess, "Popen") as popen:
            popen.return_value.poll.return_value = None
            popen.return_value.pid = 123
            manager.tick()
        self.assertIsNotNone(worker.process)
        self.assertEqual(worker.process.pid, 123)
        popen.assert_called_once()

    def test_disabled_worker_is_not_started(self):
        worker = supervisor.Worker("disabled", ("python", "-c", "pass"), lambda: False)
        manager = supervisor.Supervisor([worker])
        with mock.patch.object(supervisor.subprocess, "Popen") as popen:
            manager.tick()
        popen.assert_not_called()

    def test_failed_worker_uses_bounded_restart_backoff(self):
        worker = supervisor.Worker("failed", ("python", "-c", "pass"))
        manager = supervisor.Supervisor([worker], clock=lambda: 100.0)
        dead = mock.Mock()
        dead.poll.return_value = 1
        dead.returncode = 1
        worker.process = dead
        worker.started_at = 99.0
        manager.tick()
        self.assertIsNone(worker.process)
        self.assertEqual(worker.failures, 1)
        self.assertEqual(worker.next_start, 104.0)

    def test_snapshot_exposes_worker_state_without_system_manager(self):
        worker = supervisor.Worker("idle", ("python", "-c", "pass"), lambda: False)
        snapshot = supervisor.Supervisor([worker]).snapshot()
        self.assertIn("workers", snapshot)
        self.assertFalse(snapshot["workers"]["idle"]["running"])


    def test_worker_order_gates_gstreamer_and_sampler_behind_camera_capture(self):
        names = [worker.name for worker in supervisor.workers()]
        self.assertLess(names.index("camera-capture"), names.index("gstreamer-rtsp"))
        self.assertLess(names.index("gstreamer-rtsp"), names.index("rtsp-sampler"))

    def test_camera_restart_stops_rtsp_dependents_before_restarting_capture(self):
        entries = [
            supervisor.Worker("camera-capture", ("camera",)),
            supervisor.Worker("gstreamer-rtsp", ("gstreamer",)),
            supervisor.Worker("rtsp-sampler", ("sampler",)),
        ]
        for worker in entries:
            worker.process = mock.Mock()
            worker.process.poll.return_value = None
        manager = supervisor.Supervisor(entries)
        with mock.patch.object(manager, "start") as start:
            result = manager.handle_control({"action": "restart", "worker": "camera-capture"})
        self.assertTrue(result["ok"])
        entries[1].process.terminate.assert_called_once()
        entries[2].process.terminate.assert_called_once()
        start.assert_called_once_with(entries[0])

    def test_control_socket_serves_status_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory)
            manager = supervisor.Supervisor([])
            with mock.patch.object(supervisor, "RUN", run_path), \\
                    mock.patch.object(processes, "SOCKET_PATH", run_path / "supervisor.sock"):
                manager.start_control_server()
                try:
                    response = processes.request("status")
                finally:
                    manager.stop_control_server()
        self.assertTrue(response["ok"])
        self.assertIn("workers", response["snapshot"])


if __name__ == "__main__":
    unittest.main()
