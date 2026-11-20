import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from petcam.bootstrap import setup_portal


class SetupPortalStreamStatusTests(unittest.TestCase):
    def test_snapshot_reports_configured_mode_active_camera_and_rtsp_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                "/etc/petcam/petcam.conf": root / "petcam.conf",
                "/var/lib/petcam/camera-status.json": root / "camera-status.json",
                "/run/petcam/g-streamer-status.json": root / "g-streamer-status.json",
                "/run/petcam/supervisor-status.json": root / "supervisor-status.json",
            }
            files["/etc/petcam/petcam.conf"].write_text(
                "FORMAT=H264\nRESOLUTION=1280x720\nFPS=30\n",
                encoding="utf-8",
            )
            files["/var/lib/petcam/camera-status.json"].write_text(json.dumps({
                "pid": os.getpid(), "backend": "usb", "format": "H264",
                "resolution": "1280x720", "fps": "30",
            }), encoding="utf-8")
            files["/run/petcam/g-streamer-status.json"].write_text(json.dumps({
                "state": "publishing", "fps": 29.9, "updated_at": 1000.0,
            }), encoding="utf-8")
            files["/run/petcam/supervisor-status.json"].write_text(json.dumps({
                "workers": {"gstreamer-rtsp": {"running": True}},
            }), encoding="utf-8")

            real_path = Path
            def mapped_path(value):
                return real_path(files.get(str(value), value))

            with (
                patch.object(setup_portal, "Path", side_effect=mapped_path),
                patch.object(setup_portal.time, "time", return_value=1000.0),
            ):
                result = setup_portal.stream_status_snapshot()

        self.assertEqual(result["configured"], {
            "format": "H264", "resolution": "1280x720", "fps": "30",
        })
        self.assertEqual(result["active_camera"]["resolution"], "1280x720")
        self.assertEqual(result["rtsp"]["state"], "publishing")
        self.assertEqual(result["rtsp"]["fps"], 29.9)

    def test_snapshot_marks_stale_rtsp_status_as_stalled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                "/etc/petcam/petcam.conf": root / "petcam.conf",
                "/var/lib/petcam/camera-status.json": root / "camera-status.json",
                "/run/petcam/g-streamer-status.json": root / "g-streamer-status.json",
                "/run/petcam/supervisor-status.json": root / "supervisor-status.json",
            }
            files["/etc/petcam/petcam.conf"].write_text("", encoding="utf-8")
            files["/var/lib/petcam/camera-status.json"].write_text("", encoding="utf-8")
            files["/run/petcam/g-streamer-status.json"].write_text(
                json.dumps({"state": "publishing", "updated_at": 980.0}),
                encoding="utf-8",
            )
            files["/run/petcam/supervisor-status.json"].write_text(json.dumps({
                "workers": {"gstreamer-rtsp": {"running": True}},
            }), encoding="utf-8")

            real_path = Path
            def mapped_path(value):
                return real_path(files.get(str(value), value))

            with (
                patch.object(setup_portal, "Path", side_effect=mapped_path),
                patch.object(setup_portal.time, "time", return_value=1000.0),
            ):
                result = setup_portal.stream_status_snapshot()

        self.assertEqual(result["rtsp"]["state"], "stalled")
        self.assertIsNone(result["rtsp"]["fps"])


if __name__ == "__main__":
    unittest.main()
