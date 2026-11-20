import contextlib
import tempfile
from petcam.infrastructure.persistence import configuration as CONFIG_MODULE
import unittest
from pathlib import Path
from unittest import mock

from petcam.infrastructure.system import health as MODULE


class HealthMonitorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.state_file = Path(self.directory.name) / "health.json"
        self.config_file = Path(self.directory.name) / "petcam.conf"
        self.config_guard_patch = mock.patch.object(
            MODULE, "config_transaction_guard",
            side_effect=lambda: CONFIG_MODULE.config_transaction_guard(self.config_file),
        )
        self.config_guard_patch.start()
        self.state_patch = mock.patch.object(MODULE, "STATE_FILE", self.state_file)
        self.state_patch.start()
        self.active = {"state": "active", "active_age": 120.0}
        self.services = mock.patch.object(
            MODULE, "service_snapshot", side_effect=lambda name: self.active
        )
        self.services.start()
        self.rtsp_ready_patch = mock.patch.object(
            MODULE, "rtsp_service_ready", return_value=True
        )
        self.rtsp_ready_patch.start()

    def tearDown(self):
        self.rtsp_ready_patch.stop()
        self.services.stop()
        self.state_patch.stop()
        self.config_guard_patch.stop()
        self.directory.cleanup()

    def test_gstreamer_restart_uses_supervisor_worker_control(self):
        with mock.patch.object(MODULE.process_control, "restart_worker") as restart:
            self.assertEqual(MODULE.restart_service("gstreamer-rtsp"), (True, ""))
        restart.assert_called_once_with("gstreamer-rtsp")

    def test_restart_service_rejects_unknown_service_names(self):
        with mock.patch.object(MODULE.subprocess, "run") as run:
            succeeded, error = MODULE.restart_service("unknown-worker")
        self.assertFalse(succeeded)
        self.assertIn("unsupported", error.lower())
        run.assert_not_called()

    def test_healthy_backend_and_public_proxy_clear_failure_streak(self):
        MODULE.save_state({"consecutive_failures": 3, "recovery_count": 4, "next_recovery_at": 900})
        with mock.patch.object(MODULE, "probe_stream", side_effect=[True, True]):
            report = MODULE.check_health(now=1000)
        self.assertEqual(report["state"], "healthy")
        self.assertTrue(report["backend_stream_ready"])
        self.assertTrue(report["public_stream_ready"])
        self.assertEqual(report["consecutive_failures"], 0)
        self.assertEqual(report["recovery_count"], 4)
        self.assertEqual(report["next_recovery_at"], 0)


    def test_csi_native_h264_rtsp_status_is_accepted_as_ready(self):
        status_file = Path(self.directory.name) / "rtsp-status.json"
        status_file.write_text(__import__("json").dumps({
            "source": "native_h264_csi", "state": "publishing", "active": True, "updated_at": 1000,
        }))
        with mock.patch.object(MODULE, "RTSP_STATUS_FILE", status_file):
            self.assertTrue(MODULE.rtsp_service_ready(now=1000))

    def test_mjpeg_rtsp_idle_state_is_ready_without_a_connected_client(self):
        status_file = Path(self.directory.name) / "rtsp-status.json"
        status_file.write_text(__import__("json").dumps({
            "source": "mjpeg_copy", "state": "ready", "active": False, "updated_at": 1000,
        }))
        with mock.patch.object(MODULE, "RTSP_STATUS_FILE", status_file):
            self.assertTrue(MODULE.rtsp_service_ready(now=1000))

    def test_mjpeg_health_restarts_gstreamer_when_its_heartbeat_is_stale(self):
        with mock.patch.object(MODULE, "parse_config", return_value={"FORMAT": "MJPEG"}), \
                mock.patch.object(MODULE, "native_h264_capture_active", return_value=False), \
                mock.patch.object(MODULE, "rtsp_service_ready", return_value=False), \
                mock.patch.object(MODULE, "probe_stream", return_value=True), \
                mock.patch.object(MODULE, "service_snapshot", side_effect=lambda _name: self.active), \
                mock.patch.object(MODULE, "restart_service", return_value=(True, "")) as restart:
            report = MODULE.check_health(now=1000)
        self.assertEqual(report["state"], "recovering")
        self.assertFalse(report["rtsp_output_ready"])
        self.assertEqual(report["recovery_target"], "gstreamer-rtsp")
        restart.assert_called_once_with("gstreamer-rtsp")

    def test_native_h264_health_uses_rtsp_not_mjpeg_probes(self):
        with mock.patch.object(MODULE, "parse_config", return_value={"FORMAT": "H264"}), \
                mock.patch.object(MODULE, "native_h264_capture_active", return_value=True), \
                mock.patch.object(MODULE, "rtsp_service_ready", return_value=True), \
                mock.patch.object(MODULE, "probe_stream") as probe, \
                mock.patch.object(MODULE, "service_snapshot", side_effect=lambda name: self.active), \
                mock.patch.object(MODULE, "restart_service") as restart:
            report = MODULE.check_health(now=1000)
        self.assertEqual(report["state"], "healthy")
        self.assertEqual(report["capture_mode"], "native_h264")
        self.assertTrue(report["backend_stream_ready"])
        self.assertTrue(report["rtsp_output_ready"])
        self.assertIsNone(report["public_stream_ready"])
        probe.assert_not_called()
        restart.assert_not_called()

    def test_native_h264_idle_ready_heartbeat_does_not_trigger_recovery(self):
        status_file = Path(self.directory.name) / "rtsp-status.json"
        status_file.write_text(__import__("json").dumps({
            "source": "native_h264",
            "state": "ready",
            "active": False,
            "updated_at": 1000,
        }), encoding="utf-8")

        self.rtsp_ready_patch.stop()
        try:
            with (
                mock.patch.object(MODULE, "parse_config", return_value={"FORMAT": "H264"}),
                mock.patch.object(MODULE, "native_h264_capture_active", return_value=True),
                mock.patch.object(MODULE, "RTSP_STATUS_FILE", status_file),
                mock.patch.object(MODULE, "probe_stream") as probe,
                mock.patch.object(MODULE, "service_snapshot", side_effect=lambda _name: self.active),
                mock.patch.object(MODULE, "restart_service") as restart,
            ):
                report = MODULE.check_health(now=1000)
            self.assertEqual(report["state"], "healthy")
            self.assertTrue(report["rtsp_output_ready"])
            self.assertIsNone(report["public_stream_ready"])
            probe.assert_not_called()
            restart.assert_not_called()
        finally:
            self.rtsp_ready_patch.start()

    def test_native_h264_rtsp_failure_restarts_only_publisher(self):
        with mock.patch.object(MODULE, "parse_config", return_value={"FORMAT": "H264"}), \
                mock.patch.object(MODULE, "native_h264_capture_active", return_value=True), \
                mock.patch.object(MODULE, "rtsp_service_ready", return_value=False), \
                mock.patch.object(MODULE, "service_snapshot", side_effect=lambda name: self.active), \
                mock.patch.object(MODULE, "restart_service", return_value=(True, "")) as restart:
            report = MODULE.check_health(now=1000)
        self.assertEqual(report["state"], "recovering")
        self.assertEqual(report["recovery_target"], "gstreamer-rtsp")
        restart.assert_called_once_with("gstreamer-rtsp")

    def test_health_recovery_pauses_during_config_transaction(self):
        with mock.patch.object(MODULE, "config_transaction_guard", return_value=contextlib.nullcontext(False)), \
                mock.patch.object(MODULE, "service_snapshot") as snapshot, \
                mock.patch.object(MODULE, "restart_service") as restart:
            report = MODULE.check_health(now=1000)
        self.assertEqual(report["state"], "configuring")
        snapshot.assert_not_called()
        restart.assert_not_called()

    def test_unknown_supervisor_state_does_not_trigger_recovery(self):
        with mock.patch.object(MODULE, "service_snapshot", return_value={"state": "unknown", "active_age": None}), \
                mock.patch.object(MODULE, "restart_service") as restart:
            report = MODULE.check_health(now=1000)
        self.assertEqual(report["state"], "service_state_unknown")
        restart.assert_not_called()

    def test_startup_grace_does_not_probe_or_restart(self):
        self.active = {"state": "active", "active_age": 5.0}
        with mock.patch.object(MODULE, "probe_stream") as probe, \
                mock.patch.object(MODULE, "restart_service") as restart:
            report = MODULE.check_health(now=1000)
        self.assertEqual(report["state"], "starting")
        probe.assert_not_called()
        restart.assert_not_called()

    def test_disconnected_camera_is_reported_without_restarting_service(self):
        with mock.patch.object(MODULE, "probe_stream", return_value=False), \
                mock.patch.object(MODULE, "camera_present", return_value=False), \
                mock.patch.object(MODULE, "restart_service") as restart:
            report = MODULE.check_health(now=1000)
        self.assertEqual(report["state"], "camera_disconnected")
        self.assertFalse(report["camera_connected"])
        restart.assert_not_called()

    def test_dead_capture_process_is_distinguished_from_stalled_stream(self):
        def snapshot(service):
            if service == "camera-capture":
                return {"state": "inactive", "active_age": None}
            return self.active
        with mock.patch.object(MODULE, "service_snapshot", side_effect=snapshot), \
                mock.patch.object(MODULE, "camera_present", return_value=True), \
                mock.patch.object(MODULE, "probe_stream") as probe, \
                mock.patch.object(MODULE, "restart_service", return_value=(True, "")) as restart:
            report = MODULE.check_health(now=1000)
        self.assertEqual(report["state"], "recovering")
        self.assertEqual(report["reason"], "Capture service is not active.")
        probe.assert_not_called()
        restart.assert_called_once_with("camera-capture")

    def test_live_but_stalled_backend_is_restarted(self):
        with mock.patch.object(MODULE, "probe_stream", return_value=False), \
                mock.patch.object(MODULE, "camera_present", return_value=True), \
                mock.patch.object(MODULE, "restart_service", return_value=(True, "")) as restart:
            report = MODULE.check_health(now=1000)
        self.assertEqual(report["state"], "recovering")
        self.assertEqual(report["recovery_target"], "camera-capture")
        self.assertEqual(report["recovery_count"], 1)
        restart.assert_called_once_with("camera-capture")

    def test_recovered_backend_and_public_stream_return_to_healthy(self):
        with mock.patch.object(MODULE, "probe_stream", side_effect=[False, True, True]), \
                mock.patch.object(MODULE, "camera_present", return_value=True), \
                mock.patch.object(MODULE, "restart_service", return_value=(True, "")):
            recovering = MODULE.check_health(now=1000)
            healthy = MODULE.check_health(now=1060)
        self.assertEqual(recovering["state"], "recovering")
        self.assertEqual(healthy["state"], "healthy")
        self.assertEqual(healthy["recovery_count"], 1)
        self.assertEqual(healthy["consecutive_failures"], 0)

    def test_healthy_backend_with_broken_public_proxy_restarts_only_web_service(self):
        with mock.patch.object(MODULE, "probe_stream", side_effect=[True, False]), \
                mock.patch.object(MODULE, "restart_service", return_value=(True, "")) as restart:
            report = MODULE.check_health(now=1000)
        self.assertEqual(report["state"], "recovering")
        self.assertEqual(report["recovery_target"], "web-ui")
        restart.assert_called_once_with("web-ui")

    def test_camera_discovery_failure_does_not_trigger_restart(self):
        with mock.patch.object(MODULE, "probe_stream", return_value=False), \
                mock.patch.object(MODULE, "camera_present", return_value=None), \
                mock.patch.object(MODULE, "restart_service") as restart:
            report = MODULE.check_health(now=1000)
        self.assertEqual(report["state"], "camera_detection_failed")
        restart.assert_not_called()

    def test_repeated_failures_observe_bounded_backoff(self):
        MODULE.save_state({
            "consecutive_failures": 2,
            "recovery_count": 2,
            "next_recovery_at": 2000,
        })
        with mock.patch.object(MODULE, "probe_stream", return_value=False), \
                mock.patch.object(MODULE, "camera_present", return_value=True), \
                mock.patch.object(MODULE, "restart_service") as restart:
            report = MODULE.check_health(now=1500)
        self.assertEqual(report["state"], "recovery_backoff")
        self.assertEqual(report["next_recovery_at"], 2000)
        self.assertEqual(report["consecutive_failures"], 3)
        restart.assert_not_called()


if __name__ == "__main__":
    unittest.main()
