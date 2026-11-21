from __future__ import annotations

import unittest

from petcam.cli import camera_modes, inventory_signature, parse_short_config
from petcam.configuration import ConfigurationError, validate_config
from petcam.domain.camera.capabilities import parse_csi_cameras, parse_v4l2_modes
from petcam.infrastructure.camera.h264 import (
    AnnexBNalFramer,
    H264AccessUnitFramer,
    inspect_h264_access_unit,
)
from petcam.infrastructure.streaming.live555 import (
    H264Publisher,
    Live555Error,
    build_capture_command,
)


class ShortConfigurationTests(unittest.TestCase):
    def test_parses_usb_shortcut(self):
        self.assertEqual(parse_short_config("USB;1920x1080;30"), ("USB", "1920x1080", 30.0))

    def test_parses_csi_shortcut_case_insensitively(self):
        self.assertEqual(parse_short_config("csi;1280x720;29.97"), ("CSI", "1280x720", 29.97))

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
        self.assertEqual(set(config), {"source", "device", "physical_path", "resolution", "fps"})


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
        self.assertEqual(cameras[0]["modes"], [{"width": 1920, "height": 1080, "fps": 30.0}])

    def test_inventory_signature_changes_when_camera_list_changes(self):
        first = [{"device": "/dev/video0", "physical_path": "usb-a", "modes": []}]
        second = first + [{"device": "/dev/video2", "physical_path": "usb-b", "modes": []}]
        self.assertNotEqual(inventory_signature("USB", first), inventory_signature("USB", second))


class NativeCaptureTests(unittest.TestCase):
    def setUp(self):
        self.usb = {
            "native_h264": True, "backend": "usb", "device": "/dev/video0",
            "resolution": "1920x1080", "fps": 29.97,
        }

    def test_usb_capture_uses_v4l2_direct_h264_streaming(self):
        command = build_capture_command(self.usb)
        self.assertEqual(command[0], "v4l2-ctl")
        self.assertIn("--stream-mmap=3", command)
        self.assertIn("--stream-to=-", command)
        self.assertIn("--set-fmt-video=width=1920,height=1080,pixelformat=H264", command)
        self.assertFalse(any("gst" in part.lower() for part in command))

    def test_non_native_source_is_rejected(self):
        with self.assertRaises(Live555Error):
            build_capture_command({**self.usb, "native_h264": False})

    def test_invalid_backend_is_rejected(self):
        with self.assertRaisesRegex(Live555Error, "backend"):
            build_capture_command({**self.usb, "backend": "network"})

    def test_publisher_caches_parameter_sets_and_marks_idr_boundary(self):
        class FakeServer:
            def __init__(self):
                self.nals = []
            def push_nal(self, nal, keyframe=False):
                self.nals.append((nal, keyframe))

        server = FakeServer()
        publisher = H264Publisher(server)
        prefix = b"\\x00\\x00\\x00\\x01"
        publisher.publish(prefix + b"\\x67\\x42\\x00\\x1e")
        publisher.publish(prefix + b"\\x68\\xce\\x06")
        publisher.publish(prefix + b"\\x65\\x88")
        publisher.publish(prefix + b"\\x41\\x9a")
        self.assertEqual(server.nals, [
            (b"\\x67\\x42\\x00\\x1e", True),
            (b"\\x68\\xce\\x06", False),
            (b"\\x65\\x88", False),
            (b"\\x41\\x9a", False),
        ])

    def test_publisher_rejects_idr_without_parameter_sets(self):
        class FakeServer:
            def push_nal(self, nal, keyframe=False):
                raise AssertionError("Must not publish without SPS/PPS")
        with self.assertRaisesRegex(Live555Error, "SPS and PPS"):
            H264Publisher(FakeServer()).publish(b"\\x00\\x00\\x00\\x01\\x65\\x88")


class H264AccessUnitFramingTests(unittest.TestCase):
    @staticmethod
    def nal(header: int, payload: bytes = b"\x80") -> bytes:
        return b"\x00\x00\x00\x01" + bytes([header]) + payload

    def test_annex_b_framer_handles_split_start_codes_and_final_nal(self):
        sps = self.nal(0x67, b"\x42\x00\x1e")
        pps = self.nal(0x68, b"\xce\x06")
        framer = AnnexBNalFramer()
        stream = sps + pps
        output = []
        output.extend(framer.feed(stream[:7]))
        output.extend(framer.feed(stream[7:13]))
        output.extend(framer.feed(stream[13:]))
        output.extend(framer.flush())
        self.assertEqual(output, [sps, pps])


    def test_access_unit_metadata_retains_codec_config_for_late_rtsp_clients(self):
        sps = self.nal(0x67, b"\\x42\\x00\\x1e")
        pps = self.nal(0x68, b"\\xce\\x06")
        aud = self.nal(0x09, b"\\xf0")
        idr = self.nal(0x65)
        metadata = inspect_h264_access_unit(sps + pps + aud + idr)
        self.assertEqual(metadata["sps"], sps)
        self.assertEqual(metadata["pps"], pps)
        self.assertTrue(metadata["has_sps"])
        self.assertTrue(metadata["has_pps"])
        self.assertTrue(metadata["has_idr"])

    def test_access_units_split_at_first_slice_and_keep_parameter_sets(self):
        sps = self.nal(0x67, b"\x42\x00\x1e")
        pps = self.nal(0x68, b"\xce\x06")
        aud = self.nal(0x09, b"\xf0")
        idr = self.nal(0x65)
        first_p = self.nal(0x41)
        second_p = self.nal(0x41)
        framer = H264AccessUnitFramer()
        stream = sps + pps + aud + idr + first_p + second_p
        output = []
        for offset in range(0, len(stream), 5):
            output.extend(framer.feed(stream[offset:offset + 5]))
        output.extend(framer.flush())
        self.assertEqual(output, [sps + pps + aud + idr, first_p, second_p])


if __name__ == "__main__":
    unittest.main()
