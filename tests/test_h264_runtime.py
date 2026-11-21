from __future__ import annotations

import unittest

from petcam.cli import (
    camera_modes,
    inventory_signature,
    parse_short_config,
)
from petcam.configuration import ConfigurationError, validate_config
from petcam.domain.camera.capabilities import parse_csi_cameras, parse_v4l2_modes
from petcam.infrastructure.camera.csi import H264TCPBridge
from petcam.infrastructure.streaming.gstreamer import (
    GStreamerError,
    build_rtsp_launch,
    build_source_launch,
)


class ShortConfigurationTests(unittest.TestCase):
    def test_parses_usb_shortcut(self):
        self.assertEqual(
            parse_short_config("USB;1920x1080;30"),
            ("USB", "1920x1080", 30.0),
        )

    def test_parses_csi_shortcut_case_insensitively(self):
        self.assertEqual(
            parse_short_config("csi;1280x720;29.97"),
            ("CSI", "1280x720", 29.97),
        )

    def test_rejects_invalid_shortcut(self):
        for value in ("USB;1920x1080", "MJPEG;1280x720;30", "USB;1280x720;0"):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                parse_short_config(value)

    def test_configuration_has_only_camera_stream_parameters(self):
        config = validate_config({
            "source": "USB",
            "device": "/dev/video2",
            "physical_path": "/sys/devices/usb1/1-1",
            "resolution": "1280x720",
            "fps": 30,
        })
        self.assertEqual(
            set(config),
            {"source", "device", "physical_path", "resolution", "fps"},
        )


class CameraModeTests(unittest.TestCase):
    def test_v4l2_modes_are_parsed_with_format_and_rate(self):
        output = """[0]: 'H264' (H.264, compressed)
    Size: Discrete 1920x1080
        Interval: Discrete 0.033s (30.000 fps)
        Interval: Discrete 0.017s (60.000 fps)
[1]: 'MJPG' (Motion-JPEG, compressed)
    Size: Discrete 1280x720
        Interval: Discrete 0.033s (30.000 fps)
"""
        modes = parse_v4l2_modes(output)
        self.assertEqual([mode["format"] for mode in modes], ["H264", "MJPG"])
        self.assertEqual(modes[0]["fps"], [60.0, 30.0])

    def test_usb_mode_selector_excludes_non_h264_modes(self):
        camera = {"modes": [
            {"format": "MJPG", "width": 1280, "height": 720, "fps": [30]},
            {"format": "H264", "width": 1920, "height": 1080, "fps": [30]},
        ]}
        self.assertEqual(
            camera_modes("USB", camera),
            [{"resolution": "1920x1080", "fps": 30.0, "format": "H264"}],
        )

    def test_csi_modes_parse_from_sensor_mode_listing(self):
        output = """Available cameras
-----------------
0 : imx219 [3280x2464] (/base/soc/i2c0/imx219@10)
    Modes: 'SRGGB10_CSI2P' : 1920x1080 [30.00 fps (0, 0)/3280x2464 crop]
"""
        cameras = parse_csi_cameras(output)
        self.assertEqual(len(cameras), 1)
        self.assertEqual(
            cameras[0]["modes"],
            [{"width": 1920, "height": 1080, "fps": 30.0}],
        )

    def test_inventory_signature_changes_when_camera_list_changes(self):
        first = [{"device": "/dev/video0", "physical_path": "usb-a", "modes": []}]
        second = first + [{"device": "/dev/video2", "physical_path": "usb-b", "modes": []}]
        self.assertNotEqual(
            inventory_signature("USB", first),
            inventory_signature("USB", second),
        )


class H264PipelineTests(unittest.TestCase):
    def test_usb_source_is_native_h264_without_decoder(self):
        launch = build_source_launch({
            "native_h264": True,
            "backend": "usb",
            "device": "/dev/video0",
            "resolution": "1920x1080",
            "fps": 30,
        })
        self.assertIn("v4l2src", launch)
        self.assertIn("video/x-h264", launch)
        self.assertIn("h264parse", launch)
        self.assertNotIn("jpeg", launch.lower())
        self.assertNotIn("decode", launch.lower())
        self.assertNotIn("videoconvert", launch.lower())

    def test_usb_source_preserves_fractional_advertised_frame_rate(self):
        launch = build_source_launch({
            "native_h264": True,
            "backend": "usb",
            "device": "/dev/video0",
            "resolution": "1920x1080",
            "fps": 29.97,
        })
        self.assertIn("framerate=2997/100", launch)

    def test_csi_source_is_native_h264_without_decoder(self):
        launch = build_source_launch({
            "native_h264": True,
            "backend": "csi",
            "tcp_port": 8556,
            "resolution": "1280x720",
            "fps": 30,
        })
        self.assertIn("tcpclientsrc", launch)
        self.assertIn("h264parse", launch)
        self.assertNotIn("decode", launch.lower())

    def test_rtsp_factory_only_packetizes_h264(self):
        launch = build_rtsp_launch()
        self.assertIn("appsrc", launch)
        self.assertIn("h264parse", launch)
        self.assertIn("rtph264pay", launch)
        self.assertNotIn("rtpjpegpay", launch)
        self.assertNotIn("decode", launch.lower())

    def test_non_native_camera_source_is_rejected(self):
        with self.assertRaises(GStreamerError):
            build_source_launch({"native_h264": False, "backend": "usb"})


class CsiBridgeTests(unittest.TestCase):
    def test_encoder_waits_for_rtsp_source_connection_and_forwards_bytes(self):
        bridge = H264TCPBridge(port=0)
        bridge.start()
        client = None
        try:
            self.assertFalse(bridge.wait_for_client(timeout=0.01))
            port = bridge.listener.getsockname()[1]
            client = __import__("socket").create_connection(("127.0.0.1", port), timeout=1)
            self.assertTrue(bridge.wait_for_client(timeout=1))
            bridge.publish(b"\\x00\\x00\\x00\\x01\\x67H264")
            self.assertEqual(client.recv(9), b"\\x00\\x00\\x00\\x01\\x67H264")
        finally:
            if client is not None:
                client.close()
            bridge.stop()


if __name__ == "__main__":
    unittest.main()
