"""Tests for application-level feature configuration use cases."""

import unittest
from unittest import mock

from petcam import feature_services


class FeatureConfigurationServiceTests(unittest.TestCase):
    def test_timelapse_update_merges_settings_and_restarts_active_consumers(self):
        current = {"enabled": False, "interval": 30}
        saved = {}
        transaction = mock.Mock(side_effect=lambda save, previous, candidate, commands, rollback: (
            saved.update(candidate) or candidate
        ))
        load_rtmp = mock.Mock(return_value={"enabled": True})

        result = feature_services.update_timelapse(
            {"enabled": True, "interval": 60},
            parse_config=lambda path: {"FORMAT": "MJPEG"},
            config_path="/etc/petcam/petcam.conf",
            load_config=lambda: current,
            save_config=lambda value: value,
            load_rtmp_config=load_rtmp,
            apply_transaction=transaction,
        )

        self.assertEqual(result, {"enabled": True, "interval": 60})
        self.assertEqual(saved, result)
        args = transaction.call_args.args
        self.assertIs(args[1], current)
        self.assertEqual(args[2], result)
        self.assertEqual(args[3], args[4])
        self.assertEqual(
            [command[0] for command in args[3]],
            [
                ["/usr/bin/systemctl", "restart", "petcam-stream.service"],
                ["/usr/bin/systemctl", "restart", "petcam-rtmp.service"],
            ],
        )

    def test_motion_update_rejects_mjpeg_only_feature_on_h264(self):
        load_config = mock.Mock()
        transaction = mock.Mock()

        with self.assertRaisesRegex(RuntimeError, "motion detection requires MJPEG frames"):
            feature_services.update_motion(
                {"enabled": True},
                parse_config=lambda path: {"FORMAT": "H264"},
                config_path="/etc/petcam/petcam.conf",
                load_config=load_config,
                save_config=mock.Mock(),
                load_rtmp_config=mock.Mock(),
                apply_transaction=transaction,
            )

        load_config.assert_not_called()
        transaction.assert_not_called()

    def test_timelapse_update_does_not_restart_obs_when_output_is_disabled(self):
        transaction = mock.Mock(return_value={"enabled": True})
        feature_services.update_timelapse(
            {"enabled": True},
            parse_config=lambda path: {"FORMAT": "MJPEG"},
            config_path="/etc/petcam/petcam.conf",
            load_config=lambda: {"enabled": False},
            save_config=mock.Mock(),
            load_rtmp_config=lambda: {"enabled": False},
            apply_transaction=transaction,
        )

        commands = transaction.call_args.args[3]
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][0], [
            "/usr/bin/systemctl", "restart", "petcam-stream.service",
        ])

    def test_light_sensor_update_delegates_persistence(self):
        save = mock.Mock(return_value={"enabled": True, "threshold": 25})
        result = feature_services.update_light_sensor(
            {"enabled": True, "threshold": 25},
            save_config=save,
        )
        save.assert_called_once_with({"enabled": True, "threshold": 25})
        self.assertEqual(result, {"enabled": True, "threshold": 25})

    def test_rtmp_update_runs_camera_and_output_transition_as_transaction(self):
        current = {"enabled": False, "url": "rtsp://old"}
        transaction = mock.Mock(
            side_effect=lambda save, previous, candidate, commands, rollback: candidate,
        )
        run = mock.Mock(return_value=mock.Mock(returncode=0))
        service_command = lambda action: ["/usr/bin/systemctl", action, "petcam-rtmp.service"]
        status = {"state": "running"}

        result = feature_services.update_rtmp_output(
            {"enabled": True, "url": "rtsp://new"},
            parse_config=lambda path: {"FORMAT": "MJPEG"},
            config_path="/etc/petcam/petcam.conf",
            load_config=lambda: current,
            save_config=mock.Mock(),
            check_runtime=mock.Mock(),
            run=run,
            service_command=service_command,
            apply_transaction=transaction,
            public_config=lambda config: {"enabled": config["enabled"], "url": config["url"]},
            status_snapshot=lambda: status,
        )

        self.assertEqual(result, {
            "config": {"enabled": True, "url": "rtsp://new"},
            "status": status,
        })
        run.assert_called_once_with(
            ["systemctl", "is-active", "--quiet", "petcam-rtmp.service"],
            check=False,
            timeout=5,
        )
        commands, rollback = transaction.call_args.args[3:5]
        self.assertEqual(commands[0][0], [
            "/usr/bin/systemctl", "restart", "petcam-stream.service",
        ])
        self.assertEqual(commands[1][0], service_command("restart"))
        self.assertEqual(rollback[1][0], service_command("disable"))

    def test_rtmp_cannot_be_disabled_while_h264_capture_is_selected(self):
        transaction = mock.Mock()

        with self.assertRaisesRegex(RuntimeError, "forced on while H.264"):
            feature_services.update_rtmp_output(
                {"enabled": False},
                parse_config=lambda path: {"FORMAT": "H264"},
                config_path="/etc/petcam/petcam.conf",
                load_config=mock.Mock(),
                save_config=mock.Mock(),
                check_runtime=mock.Mock(),
                run=mock.Mock(),
                service_command=mock.Mock(),
                apply_transaction=transaction,
                public_config=mock.Mock(),
                status_snapshot=mock.Mock(),
            )

        transaction.assert_not_called()

    def test_rtmp_runtime_validation_error_is_reported_as_runtime_error(self):
        check_runtime = mock.Mock(side_effect=ValueError("GStreamer is unavailable"))

        with self.assertRaisesRegex(RuntimeError, "GStreamer is unavailable"):
            feature_services.update_rtmp_output(
                {"enabled": True},
                parse_config=lambda path: {"FORMAT": "MJPEG"},
                config_path="/etc/petcam/petcam.conf",
                load_config=mock.Mock(),
                save_config=mock.Mock(),
                check_runtime=check_runtime,
                run=mock.Mock(),
                service_command=mock.Mock(),
                apply_transaction=mock.Mock(),
                public_config=mock.Mock(),
                status_snapshot=mock.Mock(),
            )

        check_runtime.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
