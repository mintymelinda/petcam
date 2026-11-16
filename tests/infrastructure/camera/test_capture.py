import json
import signal
from unittest import mock

from petcam.infrastructure.camera import capture as MODULE


def test_usb_camera_selection_prefers_native_h264_when_auto_is_requested():
    discovery = mock.Mock(returncode=0, stdout=json.dumps({
        "usb_devices": [{"device": "/dev/video0"}], "csi_cameras": []
    }))
    h264 = mock.Mock(returncode=0, stdout=json.dumps({
        "device": "/dev/video0", "resolution": "1920x1080", "fps": 30, "format": "H264"
    }))
    with mock.patch.object(MODULE.subprocess, "run", side_effect=[discovery, h264]) as run:
        source, selected = MODULE.select_backend({"SOURCE": "auto", "FORMAT": "auto"})
    assert source == "usb"
    assert selected["format"] == "H264"
    assert run.call_args_list[1].args[0][-1] == "select-h264"


def test_usb_selection_falls_back_to_mjpeg_and_then_csi():
    discovery = mock.Mock(returncode=0, stdout=json.dumps({
        "usb_devices": [{"device": "/dev/video0"}], "csi_cameras": [{"index": 0}]
    }))
    no_h264 = mock.Mock(returncode=1, stderr="no H264")
    mjpeg = mock.Mock(returncode=0, stdout=json.dumps({
        "device": "/dev/video0", "resolution": "1280x720", "fps": 30, "format": "MJPEG"
    }))
    with mock.patch.object(MODULE.subprocess, "run", side_effect=[discovery, no_h264, mjpeg]):
        source, selected = MODULE.select_backend({"SOURCE": "auto", "FORMAT": "auto"})
    assert source == "usb"
    assert selected["format"] == "MJPEG"


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
