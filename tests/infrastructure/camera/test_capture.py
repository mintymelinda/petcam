import json
import signal
from unittest import mock

from petcam.infrastructure.camera import capture as MODULE


def test_usb_auto_selection_uses_first_hardware_mode_without_format_preference():
    discovery = mock.Mock(returncode=0, stdout=json.dumps({
        "usb_devices": [{"device": "/dev/video0"}], "csi_cameras": []
    }))
    first_mode = mock.Mock(returncode=0, stdout=json.dumps({
        "device": "/dev/video0", "resolution": "1920x1080", "fps": 30, "format": "H264"
    }))
    with mock.patch.object(MODULE.subprocess, "run", side_effect=[discovery, first_mode]) as run:
        source, selected = MODULE.select_backend({"SOURCE": "auto", "FORMAT": "auto"})
    assert source == "usb"
    assert selected["format"] == "H264"
    assert run.call_args_list[1].args[0][-1] == "select"


def test_usb_selection_does_not_silently_fallback_to_another_format():
    discovery = mock.Mock(returncode=0, stdout=json.dumps({
        "usb_devices": [{"device": "/dev/video0"}], "csi_cameras": []
    }))
    unsupported = mock.Mock(returncode=1, stderr="selected hardware mode is unsupported by ustreamer")
    with mock.patch.object(MODULE.subprocess, "run", side_effect=[discovery, unsupported]):
        try:
            MODULE.select_backend({"SOURCE": "auto", "FORMAT": "auto"})
        except RuntimeError as error:
            assert "selected hardware mode is unsupported" in str(error)
        else:
            raise AssertionError("Unsupported selected mode must be reported, not silently replaced")


def test_usb_mjpeg_worker_runs_ustreamer_and_removes_its_marker(tmp_path):
    marker = tmp_path / "camera-status.json"
    child = mock.Mock()
    child.poll.return_value = None
    child.wait.return_value = 0

    def spawn(command, **kwargs):
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        return child

    with mock.patch.object(MODULE, "CAMERA_STATUS", marker), \
            mock.patch.object(MODULE, "select_backend", return_value=("usb", {
                "device": "/dev/video0", "resolution": "1280x720", "fps": 30, "format": "MJPEG"
            })), \
            mock.patch.object(MODULE.subprocess, "Popen", side_effect=spawn) as popen:
        assert MODULE.run_capture({"FORMAT": "auto"}) == 0
    assert popen.call_args.args[0][0] == "ustreamer"
    assert not marker.exists()


def test_usb_native_h264_worker_cleans_marker_on_shutdown(tmp_path):
    marker = tmp_path / "camera-status.json"

    def pause():
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)

    with mock.patch.object(MODULE, "CAMERA_STATUS", marker), \
            mock.patch.object(MODULE, "select_backend", return_value=("usb", {
                "device": "/dev/video0", "resolution": "1920x1080", "fps": 30, "format": "H264"
            })), \
            mock.patch.object(MODULE.signal, "pause", side_effect=pause):
        assert MODULE.run_capture({"FORMAT": "H264"}) == 0
    assert not marker.exists()


def test_auto_selection_falls_back_to_csi_when_usb_modes_are_unsupported():
    discovery = mock.Mock(returncode=0, stdout=json.dumps({
        "usb_devices": [{"device": "/dev/video0"}], "csi_cameras": [{"index": 0}]
    }))
    unsupported_usb = mock.Mock(returncode=1, stderr="no usable USB mode")
    csi = mock.Mock(returncode=0, stdout=json.dumps({
        "camera": 0, "resolution": "1920x1080", "fps": 30
    }))
    with mock.patch.object(
        MODULE.subprocess, "run", side_effect=[discovery, unsupported_usb, csi],
    ):
        source, selected = MODULE.select_backend({"SOURCE": "auto", "FORMAT": "auto"})
    assert source == "csi"
    assert selected["camera"] == 0
    assert selected["_native_h264"] is False


def test_explicit_h264_rejects_csi_without_hardware_encoder():
    discovery = mock.Mock(returncode=0, stdout=json.dumps({
        "usb_devices": [], "csi_cameras": [{"index": 0}]
    }))
    csi = mock.Mock(returncode=0, stdout=json.dumps({
        "camera": 0, "resolution": "1920x1080", "fps": 30
    }))
    no_encoder = mock.Mock(returncode=1, stdout=json.dumps({"available": False}))
    with mock.patch.object(
        MODULE.subprocess, "run", side_effect=[discovery, csi, no_encoder]
    ):
        try:
            MODULE.select_backend({"SOURCE": "auto", "FORMAT": "H264"})
        except RuntimeError as error:
            assert "no hardware encoder" in str(error)
        else:
            raise AssertionError("Explicit H.264 selection must fail without a hardware encoder")


def test_csi_native_h264_worker_publishes_marker_and_cleans_it_on_shutdown(tmp_path):
    marker = tmp_path / "camera-status.json"
    child = mock.Mock()
    child.poll.return_value = 0
    child.wait.return_value = 0

    def spawn(command, **kwargs):
        payload = json.loads(marker.read_text(encoding="utf-8"))
        assert payload["backend"] == "csi"
        assert payload["native_h264"] is True
        assert payload["format"] == "H264"
        assert payload["pid"] > 1
        assert command[-1] == "--h264"
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        return child

    with mock.patch.object(MODULE, "CAMERA_STATUS", marker), \
            mock.patch.object(MODULE, "select_backend", return_value=("csi", {
                "camera": 0, "resolution": "1920x1080", "fps": 30, "_native_h264": True
            })), \
            mock.patch.object(MODULE.subprocess, "Popen", side_effect=spawn):
        assert MODULE.run_capture({"SOURCE": "csi", "FORMAT": "H264"}) == 0
    assert not marker.exists()
