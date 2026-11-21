import unittest

from petcam.application.camera_selection import resolve_camera_selection


class CameraSelectionTests(unittest.TestCase):
    def test_usb_selection_resolves_physical_camera_and_advertised_mode(self):
        cameras = [{
            "kind": "usb",
            "id": "usb-1",
            "device": "/dev/video2",
            "physical_path": "/sys/devices/usb1/1-1",
            "modes": [{
                "width": 1280,
                "height": 720,
                "format": "H264",
                "fps": [30],
            }],
        }]
        result = resolve_camera_selection(
            {
                "kind": "usb",
                "camera_id": "usb-1",
                "mode": {
                    "width": 1280,
                    "height": 720,
                    "format": "H264",
                    "fps": 30,
                },
            },
            discover_cameras=lambda: cameras,
            mode_supports_fps=lambda mode, fps: fps in mode["fps"],
        )
        self.assertEqual(result["SOURCE"], "usb")
        self.assertEqual(result["DEVICE"], "")
        self.assertEqual(result["USB_PHYSICAL_PATH"], "/sys/devices/usb1/1-1")
        self.assertEqual(result["RESOLUTION"], "1280x720")

    def test_csi_selection_preserves_explicit_device_path(self):
        cameras = [{
            "kind": "csi",
            "id": "csi-1",
            "camera": 0,
            "device_path": "/base/axi/pcie@120000/rp1/i2c@80000/imx708@1a",
            "modes": [{"width": 1920, "height": 1080, "fps": 30.0}],
        }]
        result = resolve_camera_selection(
            {
                "kind": "csi",
                "camera_id": "csi-1",
                "mode": {
                    "width": 1920,
                    "height": 1080,
                    "format": "CSI",
                    "fps": 30.0,
                },
            },
            discover_cameras=lambda: cameras,
            mode_supports_fps=lambda mode, fps: True,
        )
        self.assertEqual(result["SOURCE"], "csi")
        self.assertEqual(result["CAMERA"], "auto")
        self.assertEqual(result["CSI_DEVICE_PATH"], cameras[0]["device_path"])
        self.assertEqual(result["FORMAT"], "auto")

    def test_usb_selection_accepts_fractional_hardware_frame_rate(self):
        cameras = [{
            "kind": "usb",
            "id": "usb-fractional",
            "device": "/dev/video0",
            "physical_path": "",
            "modes": [{
                "width": 1920,
                "height": 1080,
                "format": "H264",
                "fps": [29.97],
            }],
        }]
        result = resolve_camera_selection(
            {
                "kind": "usb",
                "camera_id": "usb-fractional",
                "mode": {
                    "width": 1920,
                    "height": 1080,
                    "format": "H264",
                    "fps": 29.97,
                },
            },
            discover_cameras=lambda: cameras,
            mode_supports_fps=lambda mode, fps: fps in mode["fps"],
        )
        self.assertEqual(result["FPS"], "29.97")

    def test_stale_camera_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no longer available"):
            resolve_camera_selection(
                {
                    "kind": "usb",
                    "camera_id": "missing",
                    "mode": {
                        "width": 640,
                        "height": 480,
                        "format": "H264",
                        "fps": 30,
                    },
                },
                discover_cameras=lambda: [],
                mode_supports_fps=lambda mode, fps: True,
            )

    def test_unadvertised_usb_mode_is_rejected(self):
        cameras = [{
            "kind": "usb",
            "id": "usb-1",
            "device": "/dev/video0",
            "physical_path": "",
            "modes": [],
        }]
        with self.assertRaisesRegex(ValueError, "no longer advertised"):
            resolve_camera_selection(
                {
                    "kind": "usb",
                    "camera_id": "usb-1",
                    "mode": {
                        "width": 640,
                        "height": 480,
                        "format": "H264",
                        "fps": 30,
                    },
                },
                discover_cameras=lambda: cameras,
                mode_supports_fps=lambda mode, fps: True,
            )

    def test_csi_cannot_select_native_h264(self):
        with self.assertRaisesRegex(ValueError, "only for USB"):
            resolve_camera_selection(
                {
                    "kind": "csi",
                    "mode": {
                        "width": 640,
                        "height": 480,
                        "format": "H264",
                        "fps": 30,
                    },
                },
                discover_cameras=lambda: [],
                mode_supports_fps=lambda mode, fps: True,
            )


if __name__ == "__main__":
    unittest.main()
