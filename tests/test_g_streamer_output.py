import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from petcam import g_streamer_output as MODULE


class GStreamerOutputTests(unittest.TestCase):
    def test_native_h264_pipeline_uses_v4l2_and_rtp_packetization_only(self):
        pipeline = MODULE.build_gstreamer_launch({
            "native_h264": True,
            "device": "/dev/v4l/by-id/usb-Alpha_Imaging_Tech._Corp._Razer_Kiyo-video-index0",
            "resolution": "1280x720",
            "fps": "30",
        })
        self.assertIn("v4l2src", pipeline)
        self.assertIn("video/x-h264,width=1280,height=720,framerate=30/1", pipeline)
        self.assertIn("h264parse", pipeline)
        self.assertIn("rtph264pay name=pay0 pt=96", pipeline)
        for forbidden in ("avdec_h264", "decodebin", "x264enc", "avenc_h264", "ffmpeg", "mpegts", "udp://"):
            self.assertNotIn(forbidden, pipeline)

    def test_csi_hardware_h264_pipeline_reads_local_compressed_stream(self):
        pipeline = MODULE.build_gstreamer_launch({
            "native_h264": True, "backend": "csi", "tcp_port": 8556,
            "resolution": "1920x1080", "fps": 30,
        })
        self.assertIn("tcpclientsrc host=127.0.0.1 port=8556", pipeline)
        self.assertIn("h264parse config-interval=-1", pipeline)
        self.assertIn("rtph264pay name=pay0 pt=96", pipeline)
        for forbidden in ("v4l2src", "avdec_h264", "x264enc", "avenc_h264", "ffmpeg"):
            self.assertNotIn(forbidden, pipeline)

    def test_csi_h264_pipeline_rejects_invalid_bridge_port(self):
        with self.assertRaisesRegex(MODULE.GStreamerError, "bridge port"):
            MODULE.build_gstreamer_launch({
                "native_h264": True, "backend": "csi", "tcp_port": 70000,
                "resolution": "1280x720", "fps": 30,
            })

    def test_native_h264_pipeline_rejects_invalid_camera_metadata(self):
        with self.assertRaisesRegex(MODULE.GStreamerError, "device path is invalid"):
            MODULE.build_gstreamer_launch({
                "native_h264": True,
                "device": "/tmp/not-a-camera",
                "resolution": "1280x720",
                "fps": "30",
            })

    def test_mjpeg_browser_stream_can_be_packetized_without_decoding(self):
        pipeline = MODULE.build_gstreamer_launch({"native_h264": False})
        self.assertIn("souphttpsrc", pipeline)
        self.assertIn("multipartdemux", pipeline)
        self.assertIn("jpegparse", pipeline)
        self.assertIn("rtpjpegpay", pipeline)
        self.assertNotIn("ffmpeg", pipeline)

    def test_runtime_check_requires_all_gstreamer_plugins(self):
        class Factory:
            @staticmethod
            def find(name):
                return object() if name != "h264parse" else None

        fake_gst = type("FakeGst", (), {"ElementFactory": Factory})
        with patch.object(MODULE, "_load_gstreamer", return_value=(None, fake_gst, None)):
            with self.assertRaisesRegex(MODULE.GStreamerError, "h264parse"):
                MODULE.check_gstreamer_runtime()

    def test_camera_marker_requires_a_live_capture_service_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "camera-status.json"
            marker.write_text(json.dumps({
                "pid": os.getpid(),
                "native_h264": True,
                "device": "/dev/video0",
                "resolution": "1280x720",
                "fps": "30",
            }), encoding="utf-8")
            self.assertTrue(MODULE.native_h264_available(marker_path=marker))
            marker.write_text(json.dumps({"pid": 99999999, "native_h264": True, "device": "/dev/video0"}))
            self.assertFalse(MODULE.native_h264_available(marker_path=marker))




if __name__ == "__main__":
    unittest.main()
