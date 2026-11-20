import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from petcam.infrastructure.streaming import gstreamer as MODULE
from petcam.infrastructure.system.supervisor import workers


class GStreamerOutputTests(unittest.TestCase):
    def test_rtsp_server_binds_dual_stack_ipv6_address(self):
        class FakeServer:
            def __init__(self):
                self.address = None
                self.service = None

            def set_address(self, address):
                self.address = address

            def set_service(self, service):
                self.service = service

        server = FakeServer()
        MODULE.configure_rtsp_server(server)
        self.assertEqual(server.address, "::")
        self.assertEqual(server.service, "8554")

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

    def test_native_h264_pipeline_preserves_fractional_advertised_frame_rates(self):
        pipeline = MODULE.build_native_capture_launch({
            "native_h264": True,
            "device": "/dev/video0",
            "resolution": "1280x720",
            "fps": "29.97",
        })
        self.assertIn("framerate=2997/100", pipeline)

    def test_native_h264_pipeline_rejects_invalid_camera_metadata(self):
        with self.assertRaisesRegex(MODULE.GStreamerError, "device path is invalid"):
            MODULE.build_gstreamer_launch({
                "native_h264": True,
                "device": "/tmp/not-a-camera",
                "resolution": "1280x720",
                "fps": "30",
            })

    def test_mjpeg_rtsp_pipeline_can_be_packetized_without_decoding(self):
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


    def test_idle_server_heartbeat_keeps_ready_state_across_intervals(self):
        with tempfile.TemporaryDirectory() as directory:
            status_file = Path(directory) / "gstreamer-status.json"
            current_state = {"value": "starting"}

            MODULE._set_status_state(current_state, "ready", "native_h264", status_file)
            for _ in range(3):
                self.assertTrue(MODULE._write_heartbeat(current_state, "native_h264", status_file))
                status = json.loads(status_file.read_text(encoding="utf-8"))
                self.assertEqual(status["state"], "ready")
                self.assertFalse(status["active"])
                self.assertEqual(status["source"], "native_h264")

            MODULE._set_status_state(current_state, "publishing", "native_h264", status_file)
            self.assertEqual(json.loads(status_file.read_text(encoding="utf-8"))["state"], "publishing")

            MODULE._set_status_state(current_state, "ready", "native_h264", status_file)
            self.assertEqual(json.loads(status_file.read_text(encoding="utf-8"))["state"], "ready")

    def test_status_reports_measured_frame_rate(self):
        with tempfile.TemporaryDirectory() as directory:
            status_file = Path(directory) / "gstreamer-status.json"
            MODULE._write_status("publishing", "native_h264", status_file, 29.97)
            status = json.loads(status_file.read_text(encoding="utf-8"))
            self.assertEqual(status["fps"], 29.97)
            self.assertTrue(status["active"])

    def test_supervisor_owns_streaming_workers_without_unit_files(self):
        names = {worker.name for worker in workers()}
        self.assertTrue({"gstreamer-rtsp", "rtsp-sampler", "setup-portal"}.issubset(names))
        self.assertFalse((Path(__file__).parents[3] / "deploy" / "systemd").exists())
    def test_rtsp_client_tracking_logs_connections_and_removes_closed_clients(self):
        class FakeClient:
            def __init__(self):
                self.closed_callback = None

            def connect(self, signal, callback):
                self.assert_signal = signal
                self.closed_callback = callback

        clients = []
        client = FakeClient()
        with self.assertLogs(level="INFO") as logs:
            MODULE.track_rtsp_client(clients, client)
            self.assertEqual(clients, [client])
            self.assertEqual(client.assert_signal, "closed")
            client.closed_callback(client)
            self.assertEqual(clients, [])
        self.assertIn("RTSP client connected (1 active)", logs.output[0])
        self.assertIn("RTSP client disconnected (0 active)", logs.output[1])

    def test_camera_capture_restart_retains_existing_rtsp_sessions(self):
        class FakeClient:
            def __init__(self):
                self.close_calls = 0

            def close(self):
                self.close_calls += 1

        clients = [FakeClient(), FakeClient()]
        with self.assertLogs(level="INFO") as logs:
            retained = MODULE.retain_rtsp_clients(clients, "camera mode change")
        self.assertEqual(retained, 2)
        self.assertEqual([client.close_calls for client in clients], [0, 0])
        self.assertIn("Retaining 2 RTSP client session(s)", logs.output[0])

    def test_camera_mode_recovery_closes_existing_rtsp_clients(self):
        class FakeClient:
            def __init__(self):
                self.close_calls = 0

            def close(self):
                self.close_calls += 1

        clients = [FakeClient(), FakeClient()]
        original_clients = tuple(clients)
        closed = MODULE.close_rtsp_clients(clients, "camera mode changed")
        self.assertEqual(closed, 2)
        self.assertEqual([client.close_calls for client in original_clients], [1, 1])
        self.assertEqual(clients, [])

    def test_rtsp_client_close_failures_do_not_block_other_clients(self):
        class FakeClient:
            def __init__(self, fail=False):
                self.fail = fail
                self.close_calls = 0

            def close(self):
                self.close_calls += 1
                if self.fail:
                    raise RuntimeError("close failed")

        clients = [FakeClient(fail=True), FakeClient()]
        original_clients = tuple(clients)
        with self.assertLogs(level="ERROR"):
            closed = MODULE.close_rtsp_clients(clients, "test")
        self.assertEqual(closed, 2)
        self.assertEqual([client.close_calls for client in original_clients], [1, 1])
        self.assertEqual(clients, [])

    def test_camera_status_signature_changes_when_resolution_or_capture_pid_changes(self):
        original = {
            "pid": 100,
            "backend": "usb",
            "device": "/dev/video0",
            "resolution": "1280x720",
            "fps": "30",
            "native_h264": True,
        }
        changed_resolution = {**original, "resolution": "640x480"}
        changed_pid = {**original, "pid": 101}
        self.assertNotEqual(
            MODULE.camera_status_signature(original),
            MODULE.camera_status_signature(changed_resolution),
        )
        self.assertNotEqual(
            MODULE.camera_status_signature(original),
            MODULE.camera_status_signature(changed_pid),
        )
        self.assertEqual(
            MODULE.camera_status_signature(original),
            MODULE.camera_status_signature(dict(original)),
        )

    def test_native_v4l2_caps_verification_rejects_driver_mode_mismatch(self):
        class Structure:
            def get_name(self): return "video/x-h264"
            def get_value(self, key): return {"width": 1920, "height": 1080}[key]
            def get_fraction(self, _key): return (True, 30, 1)
        class Caps:
            def is_empty(self): return False
            def get_structure(self, _index): return Structure()
        class Pad:
            def get_current_caps(self): return Caps()
        class Source:
            def get_static_pad(self, _name): return Pad()
        class Pipeline:
            def get_by_name(self, _name): return Source()
        with self.assertRaisesRegex(MODULE.GStreamerError, "negotiated video/x-h264 1920x1080"):
            MODULE.verify_native_h264_v4l2_caps(Pipeline(), {"resolution": "1280x720", "fps": "30"})

    def test_native_v4l2_caps_verification_accepts_matching_driver_mode(self):
        class Structure:
            def get_name(self): return "video/x-h264"
            def get_value(self, key): return {"width": 1280, "height": 720}[key]
            def get_fraction(self, _key): return (True, 30, 1)
        class Caps:
            def is_empty(self): return False
            def get_structure(self, _index): return Structure()
        class Pad:
            def get_current_caps(self): return Caps()
        class Source:
            def get_static_pad(self, _name): return Pad()
        class Pipeline:
            def get_by_name(self, _name): return Source()
        MODULE.verify_native_h264_v4l2_caps(Pipeline(), {"resolution": "1280x720", "fps": "30"})

    def test_native_h264_capture_pipeline_tees_compressed_video_before_decode(self):
        pipeline = MODULE.build_native_capture_launch({
            "native_h264": True,
            "device": "/dev/video0",
            "resolution": "1280x720",
            "fps": "30",
        })
        self.assertIn("v4l2src name=camera_source", pipeline)
        self.assertIn("tee name=source_tee", pipeline)
        self.assertIn("appsink name=rtsp_sink", pipeline)
        self.assertIn(
            f"queue max-size-buffers=0 max-size-bytes={MODULE.RTSP_QUEUE_MAX_BYTES} "
            "max-size-time=0 leaky=downstream",
            pipeline,
        )
        self.assertEqual(MODULE.RTSP_QUEUE_MAX_BYTES, 100 * 1024 * 1024)
        self.assertIn("valve name=frame_valve drop=true", pipeline)
        self.assertIn("videorate drop-only=true max-rate=1", pipeline)
        self.assertIn("appsink name=frame_sink", pipeline)
        self.assertLess(pipeline.index("tee name=source_tee"), pipeline.index("avdec_h264"))
        self.assertLess(pipeline.index("valve name=frame_valve"), pipeline.rindex("h264parse"))
        for forbidden in ("rtph264pay", "udpsink", "rtspsrc", "x264enc", "avenc_h264", "ffmpeg"):
            self.assertNotIn(forbidden, pipeline)

    def test_native_h264_rtsp_factory_uses_direct_appsrc_without_udp_round_trip(self):
        pipeline = MODULE.build_native_rtsp_launch()
        self.assertIn("appsrc name=rtsp_source", pipeline)
        self.assertIn("do-timestamp=true min-latency=0", pipeline)
        self.assertIn("caps=video/x-h264,stream-format=byte-stream,alignment=au", pipeline)
        self.assertIn("rtph264pay name=pay0", pipeline)
        for forbidden in ("udpsrc", "udpsink", "rtpjitterbuffer", "rtph264depay",
                          "v4l2src", "tcpclientsrc", "avdec_h264"):
            self.assertNotIn(forbidden, pipeline)

    def test_native_capture_pipeline_and_rtsp_factory_share_encoded_access_units(self):
        capture = MODULE.build_native_capture_launch({
            "native_h264": True, "device": "/dev/video0",
            "resolution": "1280x720", "fps": "30",
        })
        rtsp = MODULE.build_native_rtsp_launch()
        self.assertIn("appsink name=rtsp_sink", capture)
        self.assertIn("appsrc name=rtsp_source", rtsp)
        self.assertNotIn("udpsink", capture + rtsp)
        self.assertNotIn("udpsrc", capture + rtsp)

    def test_native_h264_frame_branch_validates_decoder_and_csi_source(self):
        pipeline = MODULE.build_native_capture_launch({
            "native_h264": True,
            "backend": "csi",
            "tcp_port": 8556,
            "resolution": "1920x1080",
            "fps": 30,
        }, "v4l2h264dec")
        self.assertIn("tcpclientsrc host=127.0.0.1 port=8556", pipeline)
        self.assertIn("valve name=frame_valve", pipeline)
        self.assertIn("v4l2h264dec", pipeline)

    def test_native_h264_frame_branch_rejects_invalid_decoder(self):
        with self.assertRaisesRegex(MODULE.GStreamerError, "Unsupported H.264 decoder"):
            MODULE.build_native_capture_launch({
                "device": "/dev/video0",
                "resolution": "1280x720",
                "fps": "30",
            }, "bad-decoder")

    def test_frame_consumers_are_detected_from_feature_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "motion").mkdir()
            (root / "timelapse").mkdir()
            (root / "motion" / "config.json").write_text('{"enabled": false}', encoding="utf-8")
            (root / "timelapse" / "config.json").write_text('{"enabled": true}', encoding="utf-8")
            self.assertTrue(MODULE.frame_consumers_enabled(root))
            (root / "timelapse" / "config.json").write_text('{"enabled": false}', encoding="utf-8")
            self.assertFalse(MODULE.frame_consumers_enabled(root))


if __name__ == "__main__":
    unittest.main()
