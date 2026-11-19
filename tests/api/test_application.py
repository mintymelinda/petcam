import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from petcam.api import application as MODULE
from petcam.api import auth_routes, management_routes, system_routes

DASHBOARD_SCRIPTS = ("dashboard-api.js", "dashboard-core.js", "dashboard-camera.js", "dashboard-features.js", "dashboard.js")
DASHBOARD_JS = "\\n".join(
    Path("src/petcam/static", name).read_text(encoding="utf-8")
    for name in DASHBOARD_SCRIPTS
)
PAGE_AND_JS = MODULE.PAGE + DASHBOARD_JS

class WebManagerTests(unittest.TestCase):

    def test_full_ui_setting_is_saved_through_authenticated_system_route(self):
        class Handler:
            path = "/api/web-ui"

            def send_json(self, status, payload):
                self.status = status
                self.payload = payload

        handler = Handler()
        services = mock.Mock()
        self.assertTrue(system_routes.handle_post(handler, services, {"enabled": False}))
        services.set_web_ui_enabled.assert_called_once_with(False)
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.payload, {"ok": True, "enabled": False, "setup_path": "/setup"})

    def test_full_ui_setting_rejects_non_boolean_values(self):
        class Handler:
            path = "/api/web-ui"

            def send_json(self, status, payload):
                self.status = status
                self.payload = payload

        handler = Handler()
        services = mock.Mock()
        with self.assertRaisesRegex(ValueError, "enabled must be a boolean"):
            system_routes.handle_post(handler, services, {"enabled": "false"})
        services.set_web_ui_enabled.assert_not_called()

    def test_system_tab_exposes_full_ui_shutdown_and_recovery_controls(self):
        self.assertIn('id="disable-full-ui"', PAGE_AND_JS)
        self.assertIn('id="save-full-ui"', PAGE_AND_JS)
        self.assertIn('window.location.assign("/setup")', PAGE_AND_JS)
        self.assertIn("data.web_ui_enabled", PAGE_AND_JS)

    def test_feature_config_transaction_restores_config_and_services_on_failure(self):
        previous = {"enabled": False, "interval_seconds": 300}
        candidate = {"enabled": True, "interval_seconds": 120}
        saved = []
        save = lambda value: saved.append(dict(value)) or dict(value)
        commands = [
            (["@supervisor", "restart", "camera-capture"], 45, "capture restart failed"),
            (["@supervisor", "restart", "gstreamer-rtsp"], 30, "publisher restart failed"),
        ]
        rollback_commands = [
            (["@supervisor", "restart", "camera-capture"], 45, "capture rollback failed"),
            (["@supervisor", "restart", "gstreamer-rtsp"], 30, "publisher rollback failed"),
        ]
        results = [
            mock.Mock(returncode=0, stderr=""),
            mock.Mock(returncode=1, stderr="publisher failed"),
            mock.Mock(returncode=0, stderr=""),
            mock.Mock(returncode=0, stderr=""),
        ]
        with mock.patch.object(MODULE.process_control, "run_command", side_effect=results) as run:
            with self.assertRaisesRegex(RuntimeError, "publisher failed"):
                MODULE.apply_service_config_transaction(
                    save, previous, candidate, commands, rollback_commands,
                )
        self.assertEqual(saved, [candidate, previous])
        self.assertEqual(run.call_count, 4)

    def test_manager_page_uses_configured_device_hostname_for_rtsp_endpoint(self):
        class Request:
            path = "/"

            def __init__(self):
                self.headers = {}
                self.wfile = io.BytesIO()
                self.headers_sent = []

            def send_response(self, status):
                self.status = status

            def send_header(self, name, value):
                self.headers_sent.append((name, value))

            def end_headers(self):
                pass

        request = Request()
        with mock.patch.object(MODULE.socket, "gethostname", return_value="kittycam"):
            MODULE.Handler.do_GET(request)
        page = request.wfile.getvalue().decode()
        self.assertEqual(request.status, 200)
        self.assertNotIn(":8080/", page)
        self.assertIn("rtsp://kittycam.local:8554/petcam", page)
        self.assertNotIn("petcam.local", page)
        self.assertNotIn("__PETCAM_HOST__", page)

    def test_device_mdns_hostname_preserves_configured_domain(self):
        with mock.patch.object(MODULE.socket, "gethostname", return_value="kittycam"):
            self.assertEqual(MODULE.device_mdns_hostname(), "kittycam.local")
        with mock.patch.object(MODULE.socket, "gethostname", return_value="kittycam.example.net"):
            self.assertEqual(MODULE.device_mdns_hostname(), "kittycam.example.net")
    def test_management_page_uses_the_four_tab_layout(self):
        self.assertIn("Refresh", PAGE_AND_JS)
        self.assertNotIn("Browser Source", PAGE_AND_JS)
        self.assertIn('role="tablist"', PAGE_AND_JS)
        tab_order = [PAGE_AND_JS.index('data-tab="camera"'), PAGE_AND_JS.index('data-tab="timelapse"'),
                     PAGE_AND_JS.index('data-tab="motion"'), PAGE_AND_JS.index('data-tab="system"')]
        self.assertEqual(tab_order, sorted(tab_order))
        self.assertIn('id="logout" type="button" class="sign-out">Sign out</button>', PAGE_AND_JS)
        self.assertNotIn(">OBS</button>", PAGE_AND_JS)
        self.assertNotIn(">Streams</button>", PAGE_AND_JS)
        self.assertNotIn("copy-media-source", PAGE_AND_JS)
        self.assertIn('id="panel-camera"', PAGE_AND_JS)
        self.assertIn('id="panel-timelapse"', PAGE_AND_JS)
        self.assertIn('id="panel-motion"', PAGE_AND_JS)
        self.assertIn('id="panel-system"', PAGE_AND_JS)
        self.assertIn('id="advanced-camera-dialog"', PAGE_AND_JS)
        self.assertIn('setInterval(() => {', PAGE_AND_JS)
        self.assertIn('pendingCameraControlChanges.size === 0', PAGE_AND_JS)
        self.assertIn('refreshCameraControls()', PAGE_AND_JS)
        self.assertIn('advancedApplyHandle = setTimeout(() => {', PAGE_AND_JS)
        self.assertIn('if (pendingCameraControlChanges.size) applyCameraControlChanges();', PAGE_AND_JS)
        self.assertIn('id="camera-controls-list"', PAGE_AND_JS)
        self.assertIn('id="apply-camera-controls" type="button" hidden disabled', PAGE_AND_JS)
        self.assertIn('grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr))', PAGE_AND_JS)
        self.assertIn('id="system-info"', PAGE_AND_JS)
        self.assertNotIn("Software updates", PAGE_AND_JS)
        self.assertNotIn("/api/update/", PAGE_AND_JS)
        self.assertIn('GStreamer RTSP FPS', PAGE_AND_JS)
        self.assertIn("gStreamer.service_active", PAGE_AND_JS)
        self.assertIn("gStreamer.state", PAGE_AND_JS)
        self.assertIn('id="g-streamer-service"', PAGE_AND_JS)
        self.assertIn("RTSP endpoint", PAGE_AND_JS)
        self.assertIn("RTSP service will attempt to use this hardware mode", PAGE_AND_JS)
        self.assertNotIn("rtmp://", PAGE_AND_JS)
        self.assertNotIn("stream_key", PAGE_AND_JS)
        self.assertNotIn("rtmp-server-url", PAGE_AND_JS)
        self.assertNotIn("rtmp-stream-key", PAGE_AND_JS)
        self.assertIn('id="g-streamer-url"', PAGE_AND_JS)
        self.assertIn('id="g-streamer-url" type="text"', PAGE_AND_JS)
        self.assertIn('Network Up / Down', PAGE_AND_JS)
        self.assertIn('Wi-Fi signal', PAGE_AND_JS)
        self.assertIn("signal >= -50", PAGE_AND_JS)
        self.assertIn("signal >= -75", PAGE_AND_JS)
        self.assertIn('"▮".repeat(bars) + "▯".repeat(4 - bars)', PAGE_AND_JS)
        self.assertIn("Network diagnostics", PAGE_AND_JS)
        self.assertIn('/api/diagnostics', PAGE_AND_JS)
        self.assertIn('/api/support-bundle', PAGE_AND_JS)
        self.assertNotIn('/api/streams', PAGE_AND_JS)
        self.assertNotIn('change-password', PAGE_AND_JS)
        self.assertNotIn('/api/password', PAGE_AND_JS)

    def test_dashboard_tab_activation_updates_selection_and_panel_visibility(self):
        core = Path("src/petcam/static/dashboard-core.js").read_text(encoding="utf-8")
        self.assertIn("function activateTab(tabName, focus = false)", core)
        self.assertIn('button.setAttribute("aria-selected", String(selected))', core)
        self.assertIn("button.tabIndex = selected ? 0 : -1", core)
        self.assertIn('document.querySelectorAll(\'[role="tabpanel"]\')', core)
        self.assertIn("panel.hidden = !selected", core)
        self.assertIn('panel.classList.toggle("active", selected)', core)
        self.assertIn("if (focus) selectedButton.focus()", core)
        self.assertIn('activateTab("camera")', PAGE_AND_JS)
        self.assertIn("activateTab(tabButtons[next].dataset.tab, true)", PAGE_AND_JS)

    def test_live_capture_status_reports_csi_hardware_h264_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "camera-status.json"
            marker.write_text(json.dumps({
                "pid": __import__("os").getpid(), "native_h264": True, "backend": "csi",
                "resolution": "1920x1080", "fps": 30, "encoder": "bcm2835-codec-encode",
            }))
            real_path = MODULE.Path
            def mapped_path(value):
                if str(value) == "/var/lib/petcam/camera-status.json":
                    return marker
                return real_path(value)
            with mock.patch.object(MODULE, "Path", side_effect=mapped_path), \
                    mock.patch.object(MODULE, "parse_config", return_value={"PORT": 8081, "RESOLUTION": "auto", "FPS": "auto"}):
                status = MODULE.live_capture_status()
        self.assertEqual(status["active_capture_format"], "H264")
        self.assertEqual(status["active_resolution"], "1920x1080")
        self.assertEqual(status["capture_mode"], "native_h264_csi")

    def test_dashboard_javascript_modules_are_external_and_served_without_authentication(self):
        for name in ("dashboard-core.js", "dashboard-camera.js", "dashboard-features.js", "dashboard.js"):
            with self.subTest(asset=name):
                self.assertIn(f'<script src="/static/{name}" defer></script>', MODULE.PAGE)
                class Request:
                    path = f"/static/{name}"
                    def __init__(self):
                        self.headers = {}
                        self.wfile = io.BytesIO()
                        self.response_headers = []
                    def send_response(self, status):
                        self.status = status
                    def send_header(self, key, value):
                        self.response_headers.append((key, value))
                    def end_headers(self):
                        pass
                    def send_error(self, status, message=None):
                        self.status = status
                request = Request()
                MODULE.Handler.do_GET(request)
                self.assertEqual(request.status, 200)
                self.assertIn(("Content-Type", "application/javascript; charset=utf-8"), request.response_headers)
                expected = Path("src/petcam/static", name).read_text(encoding="utf-8")
                self.assertEqual(request.wfile.getvalue().decode(), expected)

        self.assertNotRegex(MODULE.PAGE, r"<script(?:\s[^>]*)?>\s*[^<]")

    def test_browser_http_stream_pipeline_is_removed_and_rtsp_remains(self):
        self.assertFalse(hasattr(MODULE, "StreamHandler"))
        self.assertFalse(hasattr(MODULE, "proxy_stream"))
        source = Path(MODULE.__file__).read_text(encoding="utf-8")
        self.assertNotIn("streaming_routes", source)
        self.assertNotIn("browser-source", MODULE.STATIC_ASSETS)
        dashboard = Path("src/petcam/static/dashboard.html").read_text(encoding="utf-8")
        self.assertNotIn("data-browser-feed-link", dashboard)
        self.assertIn("g-streamer-url", dashboard)


    def test_g_streamer_status_without_supervisor_snapshot_is_stopped(self):
        with mock.patch.object(MODULE, "SUPERVISOR_STATUS_FILE", Path("/missing/supervisor.json")):
            status = MODULE.g_streamer_status_snapshot()
        self.assertFalse(status["active"])
        self.assertFalse(status["service_active"])
        self.assertEqual(status["state"], "stopped")

    def test_g_streamer_status_reports_publishing_state_from_runtime_file(self):
        with tempfile.TemporaryDirectory() as directory:
            status_file = Path(directory) / "g-streamer-status.json"
            status_file.write_text(json.dumps({
                "state": "publishing", "active": True, "fps": 29.8, "updated_at": MODULE.time.time()
            }))
            supervisor_file = Path(directory) / "supervisor-status.json"
            supervisor_file.write_text(json.dumps({"workers": {"gstreamer-rtsp": {"running": True}}}))
            with mock.patch.object(MODULE, "G_STREAMER_STATUS_FILE", status_file), \
                    mock.patch.object(MODULE, "SUPERVISOR_STATUS_FILE", supervisor_file):
                status = MODULE.g_streamer_status_snapshot()
        self.assertTrue(status["active"])
        self.assertTrue(status["service_active"])
        self.assertEqual(status["state"], "publishing")
        self.assertEqual(status["fps"], 29.8)

    def test_admin_reauthentication_uses_masked_password_dialog_not_prompt(self):
        self.assertIn('<dialog id="login-dialog"', PAGE_AND_JS)
        self.assertIn('id="login-password" type="password"', PAGE_AND_JS)
        self.assertIn('autocomplete="current-password"', PAGE_AND_JS)
        self.assertIn('dialog.showModal()', PAGE_AND_JS)
        self.assertNotIn('window.prompt("Enter your PetCam manager password")', PAGE_AND_JS)

    def test_first_run_admin_setup_is_available_in_the_browser(self):
        self.assertIn('id="first-run-form"', PAGE_AND_JS)
        self.assertIn('id="setup-password"', PAGE_AND_JS)
        self.assertIn("/api/setup/status", PAGE_AND_JS)
        self.assertIn("/api/setup", PAGE_AND_JS)
        self.assertIn("SSH is not required", PAGE_AND_JS)
        self.assertIn("handle_public_post", management_routes.handle_post.__code__.co_names)
        self.assertIn("initialize_password", auth_routes.handle_public_post.__code__.co_names)
        self.assertIn("handle_get", management_routes.handle_get.__code__.co_names)
        self.assertIn("is_configured", auth_routes.handle_get.__code__.co_names)

    def test_first_run_setup_endpoint_creates_session_and_cookie(self):
        payload = json.dumps({
            "password": "a sufficiently long password",
            "password_confirmation": "a sufficiently long password",
        }).encode()
        class Request:
            path = "/api/setup"
            headers = {
                "Origin": "https://petcam.local:8443",
                "Host": "petcam.local:8443",
                "Content-Length": str(len(payload)),
            }
            rfile = io.BytesIO(payload)
            response = None

            def send_json(self, status, body, headers=None):
                self.response = (status, body, headers or {})

        request = Request()
        with mock.patch.object(MODULE, "is_configured", return_value=False), \
                mock.patch.object(MODULE, "initialize_password") as initialize, \
                mock.patch.object(MODULE, "new_session", return_value=("session-token", "csrf-token")):
            MODULE.Handler.do_POST(request)
        initialize.assert_called_once_with("a sufficiently long password")
        self.assertEqual(request.response[0], 201)
        self.assertEqual(request.response[1]["csrf_token"], "csrf-token")
        self.assertIn("HttpOnly; Secure; SameSite=Strict", request.response[2]["Set-Cookie"])

    def test_first_run_setup_endpoint_rejects_non_same_origin_request(self):
        class Request:
            path = "/api/setup"
            headers = {"Origin": "http://attacker.example", "Host": "petcam.local:8443"}
            response = None

            def send_json(self, status, body, headers=None):
                self.response = (status, body, headers or {})

        request = Request()
        with mock.patch.object(MODULE, "is_configured", return_value=False), \
                mock.patch.object(MODULE, "initialize_password") as initialize:
            MODULE.Handler.do_POST(request)
        self.assertEqual(request.response[0], 403)
        initialize.assert_not_called()

    def test_first_run_setup_endpoint_cannot_reconfigure_existing_device(self):
        class Request:
            path = "/api/setup"
            headers = {}
            response = None

            def send_json(self, status, body, headers=None):
                self.response = (status, body, headers or {})

        request = Request()
        with mock.patch.object(MODULE, "is_configured", return_value=True), \
                mock.patch.object(MODULE, "initialize_password") as initialize:
            MODULE.Handler.do_POST(request)
        self.assertEqual(request.response[0], 409)
        initialize.assert_not_called()

    def test_api_application_has_no_sudo_privilege_handoffs(self):
        source = Path(MODULE.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"sudo"', source)

    def test_camera_inventory_uses_shared_discovery_and_exposes_h264_modes(self):
        usb_devices = [{
            "device": "/dev/video0",
            "physical_path": "/sys/devices/usb1/1-1",
            "modes": [
                {"format": "MJPG", "width": 1280, "height": 720, "fps": [30]},
                {"format": "H264", "width": 1920, "height": 1080, "fps": [30]},
            ],
        }]
        with mock.patch.object(MODULE, "discover_devices", return_value=usb_devices) as discover_usb:
            with mock.patch.object(MODULE, "discover_csi_cameras", return_value=[]) as discover_csi:
                cameras = MODULE.camera_inventory()
        discover_usb.assert_called_once_with()
        discover_csi.assert_called_once_with()
        self.assertEqual({mode["format"] for mode in cameras[0]["modes"]}, {"MJPG", "H264"})

    def test_h264_selection_uses_transactional_camera_config_apply(self):
        camera = {
            "kind": "usb", "id": "usb-kiyo", "device": "/dev/video0",
            "physical_path": "/sys/devices/usb1/1-1",
            "modes": [{"format": "H264", "width": 1920, "height": 1080, "fps": [30]}],
        }
        previous_camera = {**MODULE.parse_config(), "SOURCE": "usb", "FORMAT": "MJPG",
                           "RESOLUTION": "1280x720", "FPS": "30"}
        with mock.patch.object(MODULE, "camera_inventory", return_value=[camera]), \
                mock.patch.object(MODULE, "parse_config", return_value=previous_camera), \
                mock.patch.object(MODULE, "load_timelapse_config", return_value={"enabled": False}), \
                mock.patch.object(MODULE, "load_motion_config", return_value={"enabled": False}), \
                mock.patch.object(MODULE, "apply_config") as apply:
            MODULE.save_selection({
                "kind": "usb", "camera_id": "usb-kiyo",
                "mode": {"format": "H264", "width": 1920, "height": 1080, "fps": 30},
            })
        apply.assert_called_once()
        self.assertEqual(apply.call_args.args[0]["FORMAT"], "H264")

    def test_h264_mode_is_selectable_without_application_feature_policy(self):
        camera = {
            "kind": "usb", "id": "usb-kiyo", "device": "/dev/video0",
            "modes": [{"format": "H264", "width": 1920, "height": 1080, "fps": [30]}],
        }
        with (
            mock.patch.object(MODULE, "camera_inventory", return_value=[camera]),
            mock.patch.object(MODULE, "parse_config", return_value=MODULE.parse_config()),
            mock.patch.object(MODULE, "load_timelapse_config", return_value={"enabled": True}),
            mock.patch.object(MODULE, "load_motion_config", return_value={"enabled": False}),
            mock.patch.object(MODULE, "apply_config") as apply,
        ):
            MODULE.save_selection({
                "kind": "usb", "camera_id": "usb-kiyo",
                "mode": {"format": "H264", "width": 1920, "height": 1080, "fps": 30},
            })
        self.assertEqual(apply.call_args.args[0]["FORMAT"], "H264")

    def test_valid_selection_uses_transactional_config_apply(self):
        original = MODULE.camera_inventory
        MODULE.camera_inventory = lambda: [{
            "kind": "usb",
            "device": "/dev/video0",
            "modes": [{"width": 640, "height": 480, "fps": [30], "format": "MJPG"}],
        }]
        try:
            with mock.patch.object(MODULE, "apply_config") as apply:
                MODULE.save_selection({
                    "kind": "usb",
                    "device": "/dev/video0",
                    "mode": {"width": 640, "height": 480, "fps": 30, "format": "MJPG"},
                })
            apply.assert_called_once_with({
                "SOURCE": "usb", "DEVICE": "/dev/video0",
                "USB_PHYSICAL_PATH": "", "CSI_DEVICE_PATH": "", "CAMERA": "auto",
                "FORMAT": "MJPG", "RESOLUTION": "640x480", "FPS": "30",
            })
        finally:
            MODULE.camera_inventory = original

    def test_high_demand_hardware_mode_is_saved_without_performance_override(self):
        camera = {
            "kind": "usb", "id": "usb-fast", "device": "/dev/video0",
            "modes": [{"width": 3840, "height": 2160, "fps": [60], "format": "YUYV"}],
        }
        with (
            mock.patch.object(MODULE, "camera_inventory", return_value=[camera]),
            mock.patch.object(MODULE, "apply_config") as apply,
        ):
            MODULE.save_selection({
                "kind": "usb", "camera_id": "usb-fast",
                "mode": {"width": 3840, "height": 2160, "fps": 60, "format": "YUYV"},
            })
        self.assertEqual(apply.call_args.args[0]["FPS"], "60")
        self.assertEqual(apply.call_args.args[0]["FORMAT"], "YUYV")

    def test_primary_usb_selection_persists_physical_topology(self):
        physical_path = "/sys/devices/platform/soc/usb1/1-1/1-1.2"
        camera = {
            "kind": "usb",
            "id": "usb-stable",
            "device": "/dev/video4",
            "physical_path": physical_path,
            "modes": [{"width": 640, "height": 480, "fps": [30], "format": "MJPG"}],
        }
        with mock.patch.object(MODULE, "camera_inventory", return_value=[camera]), \
                mock.patch.object(MODULE, "apply_config") as apply:
            MODULE.save_selection({
                "kind": "usb",
                "camera_id": "usb-stable",
                "device": "/dev/video0",
                "physical_path": physical_path,
                "mode": {"width": 640, "height": 480, "fps": 30, "format": "MJPG"},
            })
        values = apply.call_args.args[0]
        self.assertEqual(values["DEVICE"], "")
        self.assertEqual(values["USB_PHYSICAL_PATH"], physical_path)

    def test_primary_csi_selection_persists_device_tree_path(self):
        device_path = "/base/soc/i2c0mux/i2c@1/imx708@1a"
        camera = {
            "kind": "csi",
            "id": "csi-stable",
            "camera": 1,
            "sensor": "imx708",
            "device_path": device_path,
            "modes": [{"width": 640, "height": 480, "fps": 30}],
        }
        with mock.patch.object(MODULE, "camera_inventory", return_value=[camera]), \
                mock.patch.object(MODULE, "apply_config") as apply:
            MODULE.save_selection({
                "kind": "csi",
                "camera_id": "csi-stable",
                "camera": 0,
                "device_path": device_path,
                "mode": {"width": 640, "height": 480, "fps": 30},
            })
        values = apply.call_args.args[0]
        self.assertEqual(values["CAMERA"], "auto")
        self.assertEqual(values["CSI_DEVICE_PATH"], device_path)

    def test_usb_selection_rejects_unadvertised_device(self):
        original = MODULE.camera_inventory
        MODULE.camera_inventory = lambda: []
        try:
            with self.assertRaisesRegex(ValueError, "no longer available"):
                MODULE.save_selection({
                    "kind": "usb", "device": "/dev/video0",
                    "mode": {"width": 640, "height": 480, "fps": 30, "format": "MJPG"},
                })
        finally:
            MODULE.camera_inventory = original

    def test_camera_inventory_cache_reuses_recent_discovery_and_returns_copies(self):
        camera = {"kind": "usb", "device": "/dev/video0", "modes": []}
        MODULE._camera_inventory_cache = None
        MODULE._camera_inventory_cache_at = 0.0
        try:
            with mock.patch.object(MODULE, "camera_inventory", return_value=[camera]) as discover:
                first = MODULE.cached_camera_inventory()
                first[0]["device"] = "/dev/changed"
                second = MODULE.cached_camera_inventory()
            discover.assert_called_once_with()
            self.assertEqual(second[0]["device"], "/dev/video0")
        finally:
            MODULE._camera_inventory_cache = None
            MODULE._camera_inventory_cache_at = 0.0

    def test_camera_inventory_exposes_stable_identity_metadata(self):
        with mock.patch.object(
            MODULE, "discover_devices",
            return_value=[{"device": "/dev/v4l/by-id/usb-camera", "modes": []}],
        ), mock.patch.object(
            MODULE, "discover_csi_cameras",
            return_value=[{"index": 0, "sensor": "imx708", "modes": []}],
        ):
            cameras = MODULE.camera_inventory()
        self.assertEqual(len(cameras), 2)
        self.assertTrue(cameras[0]["stable_identity"])
        self.assertEqual(cameras[1]["id"], "csi-imx708-0")
        self.assertNotIn("hardware_tier", cameras[0])
        self.assertNotIn("hardware_budget_pixels_per_second", cameras[0])

    def test_camera_page_restores_saved_camera_and_mode_and_refreshes_preview(self):
        self.assertIn("activeCameraMatches", PAGE_AND_JS)
        self.assertIn("activeConfig", PAGE_AND_JS)
        self.assertNotIn("refreshLivePreview", PAGE_AND_JS)
        self.assertNotIn("dashboard-preview", PAGE_AND_JS)
        self.assertIn("GStreamer RTSP FPS", PAGE_AND_JS)
        self.assertIn("gStreamer.service_active", PAGE_AND_JS)
        self.assertIn("gStreamer.state", PAGE_AND_JS)
        self.assertIn('id="g-streamer-service"', PAGE_AND_JS)
        self.assertIn('id="g-streamer-url"', PAGE_AND_JS)
        self.assertIn('id="g-streamer-url" type="text"', PAGE_AND_JS)
        self.assertNotIn('id="live-preview"', PAGE_AND_JS)
        self.assertNotIn('rtmp-encoder', PAGE_AND_JS)
        self.assertIn("Hardware-advertised modes are available for selection", PAGE_AND_JS)

    def test_camera_page_displays_measured_capture_rate_separately_from_configured_fps(self):
        self.assertIn("Actual captured rate:", PAGE_AND_JS)
        self.assertIn("latest_captured_fps", PAGE_AND_JS)
        self.assertIn("configured:", PAGE_AND_JS)
        self.assertIn("actual ", PAGE_AND_JS)
        self.assertIn("setInterval(refreshLiveStatus, 5000)", PAGE_AND_JS)
        self.assertIn("Capture status refreshes every 5 seconds", PAGE_AND_JS)
        self.assertIn('id="capture-status-freshness"', PAGE_AND_JS)

    def test_system_tab_displays_the_installed_application_version_without_dead_telemetry_nodes(self):
        self.assertIn('id="installed-version"', PAGE_AND_JS)
        self.assertIn('id="system-health-grid"', PAGE_AND_JS)
        self.assertIn('id="statistics-updated"', PAGE_AND_JS)
        self.assertNotIn('id="frame-statistics"', PAGE_AND_JS)
        self.assertNotIn('id="viewer-statistics"', PAGE_AND_JS)
        self.assertNotIn('id="network-statistics"', PAGE_AND_JS)
        self.assertIn("refreshStatistics", PAGE_AND_JS)
        self.assertIn("/api/live-status", PAGE_AND_JS)
        self.assertIn("/api/system", PAGE_AND_JS)
        with tempfile.TemporaryDirectory() as directory:
            version_file = Path(directory) / "VERSION"
            version_file.write_text("9.8.7\n", encoding="utf-8")
            lib_directory = Path(directory) / "lib"
            lib_directory.mkdir()
            with mock.patch.object(MODULE, "__file__", str(lib_directory / "application.py")):
                self.assertEqual(MODULE.installed_version(), "9.8.7")

    def test_system_resource_metrics_reports_procfs_memory_and_cpu(self):
        metrics = MODULE.system_resource_metrics()
        self.assertIn("cpu_percent", metrics)
        self.assertIn("memory_used_mb", metrics)
        self.assertIn("memory_total_mb", metrics)
        if metrics["cpu_percent"] is not None:
            self.assertGreaterEqual(metrics["cpu_percent"], 0)
            self.assertLessEqual(metrics["cpu_percent"], 100)
        if metrics["memory_total_mb"] is not None:
            self.assertGreater(metrics["memory_total_mb"], 0)
            self.assertGreaterEqual(metrics["memory_used_mb"], 0)
            self.assertLessEqual(metrics["memory_used_mb"], metrics["memory_total_mb"])

    def test_camera_ui_does_not_apply_performance_budget_filtering(self):
        self.assertNotIn("projectedPixelRate", PAGE_AND_JS)
        self.assertNotIn("exceeds_performance_budget", PAGE_AND_JS)
        self.assertNotIn("performance_budget_pixels_per_second", PAGE_AND_JS)
        self.assertIn("Hardware-advertised mode selected", PAGE_AND_JS)

    def test_active_camera_config_returns_only_selection_fields(self):
        config = {
            "SOURCE": "usb", "DEVICE": "", "USB_PHYSICAL_PATH": "/sys/devices/usb1/1-1",
            "CSI_DEVICE_PATH": "", "CAMERA": "auto", "FORMAT": "MJPG",
            "RESOLUTION": "1280x720", "FPS": "30", "PORT": "8081", "CSI_QUALITY": "70",
        }
        with mock.patch.object(MODULE, "parse_config", return_value=config):
            active = MODULE.active_camera_config()
        self.assertEqual(active["RESOLUTION"], "1280x720")
        self.assertEqual(active["FPS"], "30")
        self.assertNotIn("PORT", active)
        self.assertNotIn("CSI_QUALITY", active)

    def test_live_capture_status_reads_ustreamer_metrics_directly(self):
        payload = {
            "ok": True,
            "result": {
                "source": {
                    "captured_fps": 15,
                    "resolution": {"width": 1280, "height": 720},
                },
                "encoder": {"type": "HW"},
            },
        }

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(payload).encode()

        with mock.patch.object(MODULE, "parse_config", return_value={"PORT": "8081"}), \
                mock.patch.object(MODULE.urllib.request, "urlopen", return_value=Response()) as open_url, \
                mock.patch.object(MODULE.subprocess, "run") as run:
            actual = MODULE.live_capture_status()

        open_url.assert_called_once_with("http://127.0.0.1:8081/state", timeout=2)
        run.assert_not_called()
        self.assertEqual(actual, {
            "latest_captured_fps": 15,
            "active_resolution": "1280x720",
            "active_capture_format": "MJPEG",
        })

    def test_live_capture_status_falls_back_to_csi_metrics(self):
        payload = {
            "backend": "csi",
            "captured_fps_average": 29.5,
        }

        class Response:
            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(self.body).encode()

        with mock.patch.object(MODULE, "parse_config", return_value={"PORT": "8081", "RESOLUTION": "1920x1080"}), \
                mock.patch.object(
                    MODULE.urllib.request,
                    "urlopen",
                    side_effect=[Response({"ok": False}), Response(payload)],
                ) as open_url:
            actual = MODULE.live_capture_status()

        self.assertEqual(open_url.call_count, 2)
        self.assertEqual(actual, {
            "latest_captured_fps": 29.5,
            "active_resolution": "1920x1080",
            "active_capture_format": "MJPEG",
        })

    def test_live_capture_status_returns_empty_when_backend_metrics_are_unavailable(self):
        with mock.patch.object(MODULE, "parse_config", return_value={"PORT": "8081"}), \
                mock.patch.object(MODULE.urllib.request, "urlopen", side_effect=OSError("offline")):
            self.assertEqual(MODULE.live_capture_status(), {})

    def test_invalid_capture_values_are_rejected(self):
        for mode in (
            {"width": 0, "height": 480, "fps": 30},
            {"width": 640, "height": 480, "fps": 0},
        ):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                MODULE.save_selection({"kind": "csi", "camera": 0, "mode": mode})

class CameraControlTests(unittest.TestCase):
    SAMPLE_CONTROLS = """brightness 0x00980900 (int) : min=0 max=255 step=1 default=128 value=128 flags=has-min-max
white_balance_automatic 0x0098090c (bool) : default=1 value=1
power_line_frequency 0x00980918 (menu) : min=0 max=2 default=2 value=2 (60 Hz)
        0: Disabled
        1: 50 Hz
        2: 60 Hz
auto_exposure 0x009a0901 (menu) : min=0 max=3 default=0 value=3 (Aperture Priority Mode)
        1: Manual Mode
        3: Aperture Priority Mode
exposure_time_absolute 0x009a0902 (int) : min=3 max=2047 step=1 default=250 value=250 flags=inactive, has-min-max
exposure_dynamic_framerate 0x009a0903 (bool) : default=0 value=1
"""

    def test_parser_discovers_integer_boolean_and_menu_controls(self):
        controls = MODULE.parse_v4l2_controls(self.SAMPLE_CONTROLS)
        by_name = {control["name"]: control for control in controls}
        self.assertEqual(by_name["brightness"]["min"], 0)
        self.assertEqual(by_name["brightness"]["max"], 255)
        self.assertTrue(by_name["brightness"]["writable"])
        self.assertEqual(by_name["white_balance_automatic"]["type"], "bool")
        self.assertEqual(by_name["power_line_frequency"]["menu"], [
            {"value": 0, "label": "Disabled"},
            {"value": 1, "label": "50 Hz"},
            {"value": 2, "label": "60 Hz"},
        ])
        self.assertEqual(by_name["auto_exposure"]["value"], 3)
        self.assertFalse(by_name["exposure_time_absolute"]["writable"])
        self.assertTrue(by_name["exposure_dynamic_framerate"]["writable"])

    def test_parser_marks_invalid_defaults_unavailable_and_preserves_valid_defaults(self):
        output = """brightness 0x00980900 (int) : min=0 max=255 step=1 default=-8193 value=128
contrast 0x00980901 (int) : min=0 max=255 step=1 default=57343 value=128
focus_absolute 0x009a090a (int) : min=0 max=250 step=1 default=8189 value=0
zoom_absolute 0x009a090d (int) : min=100 max=500 step=1 default=57343 value=100
white_balance_automatic 0x0098090c (bool) : default=1 value=1
power_line_frequency 0x00980918 (menu) : min=0 max=2 default=2 value=2 (60 Hz)
        0: Disabled
        1: 50 Hz
        2: 60 Hz
auto_exposure 0x009a0901 (menu) : min=0 max=3 default=0 value=3 (Aperture Priority Mode)
        1: Manual Mode
        3: Aperture Priority Mode
"""
        controls = {control["name"]: control for control in MODULE.parse_v4l2_controls(output)}
        for name in ("brightness", "contrast", "focus_absolute", "zoom_absolute", "auto_exposure"):
            with self.subTest(control=name):
                self.assertIsNone(controls[name]["default"])
        self.assertEqual(controls["white_balance_automatic"]["default"], 1)
        self.assertEqual(controls["power_line_frequency"]["default"], 2)

    def test_camera_control_ui_labels_invalid_defaults_as_unavailable(self):
        self.assertIn("defaultLabel =", PAGE_AND_JS)
        self.assertIn("control.default === null", PAGE_AND_JS)
        self.assertIn('? "unavailable"', PAGE_AND_JS)
        self.assertIn('" · Default: "', PAGE_AND_JS)
        self.assertIn("defaultLabel", PAGE_AND_JS)
        self.assertIn("menuOption(control.default)?.label", PAGE_AND_JS)
        self.assertIn('"unavailable"', PAGE_AND_JS)

    def test_active_usb_camera_is_resolved_from_saved_physical_identity(self):
        camera = {
            "kind": "usb",
            "device": "/dev/video4",
            "physical_path": "/sys/devices/usb1/1-1.2",
        }
        config = {
            "SOURCE": "usb",
            "DEVICE": "",
            "USB_PHYSICAL_PATH": "/sys/devices/usb1/1-1.2",
        }
        with mock.patch.object(MODULE, "active_camera_config", return_value=config), \
                mock.patch.object(MODULE, "camera_inventory", return_value=[camera]):
            self.assertEqual(MODULE.active_usb_camera(), camera)

    def test_camera_controls_are_unavailable_for_non_usb_active_source(self):
        with mock.patch.object(MODULE, "active_camera_config", return_value={"SOURCE": "csi"}):
            result = MODULE.read_camera_controls()
        self.assertFalse(result["supported"])
        self.assertEqual(result["controls"], [])

    def test_read_camera_controls_uses_only_discovered_device(self):
        camera = {"device": "/dev/video4", "label": "USB camera"}
        completed = mock.Mock(returncode=0, stdout=self.SAMPLE_CONTROLS, stderr="")
        with mock.patch.object(MODULE.subprocess, "run", return_value=completed) as run:
            result = MODULE.read_camera_controls(camera)
        self.assertTrue(result["supported"])
        self.assertEqual(result["device"], "/dev/video4")
        self.assertEqual(len(result["controls"]), 6)
        self.assertEqual(run.call_args.args[0], [
            "/usr/bin/v4l2-ctl", "--device", "/dev/video4", "--list-ctrls-menus",
        ])

    def test_read_camera_controls_rejects_untrusted_device_paths(self):
        with self.assertRaisesRegex(ValueError, "invalid V4L2 device path"):
            MODULE.read_camera_controls({"device": "/tmp/fake-video"})

    def test_setting_integer_control_uses_validated_v4l2_command(self):
        camera = {"device": "/dev/video4"}
        control = {
            "name": "brightness", "type": "int", "min": 0, "max": 255,
            "step": 1, "menu": [], "writable": True,
        }
        snapshot = {"supported": True, "controls": [control]}
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(MODULE, "active_usb_camera", return_value=camera), \
                mock.patch.object(MODULE, "read_camera_controls", side_effect=[snapshot, snapshot]), \
                mock.patch.object(MODULE.subprocess, "run", return_value=completed) as run:
            result = MODULE.set_camera_control({"name": "brightness", "value": 200})
        self.assertEqual(result, snapshot)
        self.assertEqual(run.call_args.args[0], [
            "/usr/bin/v4l2-ctl", "--device", "/dev/video4", "--set-ctrl=brightness=200",
        ])

    def test_setting_boolean_control_accepts_json_boolean(self):
        camera = {"device": "/dev/video4"}
        control = {
            "name": "exposure_dynamic_framerate", "type": "bool",
            "min": None, "max": None, "step": 1, "menu": [], "writable": True,
        }
        snapshot = {"supported": True, "controls": [control]}
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(MODULE, "active_usb_camera", return_value=camera), \
                mock.patch.object(MODULE, "read_camera_controls", side_effect=[snapshot, snapshot]), \
                mock.patch.object(MODULE.subprocess, "run", return_value=completed) as run:
            MODULE.set_camera_control({"name": "exposure_dynamic_framerate", "value": False})
        self.assertTrue(run.call_args.args[0][-1].endswith("=0"))

    def test_setting_menu_control_rejects_unadvertised_values(self):
        camera = {"device": "/dev/video4"}
        control = {
            "name": "power_line_frequency", "type": "menu", "min": 0, "max": 2,
            "step": 1, "menu": [{"value": 0, "label": "Disabled"}], "writable": True,
        }
        with mock.patch.object(MODULE, "active_usb_camera", return_value=camera), \
                mock.patch.object(MODULE, "read_camera_controls", return_value={
                    "supported": True, "controls": [control],
                }), \
                mock.patch.object(MODULE.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "not an advertised menu option"):
                MODULE.set_camera_control({"name": "power_line_frequency", "value": 2})
        run.assert_not_called()

    def test_setting_control_rejects_out_of_range_and_inactive_values(self):
        camera = {"device": "/dev/video4"}
        control = {
            "name": "brightness", "type": "int", "min": 0, "max": 255,
            "step": 1, "menu": [], "writable": True,
        }
        with mock.patch.object(MODULE, "active_usb_camera", return_value=camera), \
                mock.patch.object(MODULE, "read_camera_controls", return_value={
                    "supported": True, "controls": [control],
                }), \
                mock.patch.object(MODULE.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "above the supported maximum"):
                MODULE.set_camera_control({"name": "brightness", "value": 300})
        run.assert_not_called()
        control["writable"] = False
        with mock.patch.object(MODULE, "active_usb_camera", return_value=camera), \
                mock.patch.object(MODULE, "read_camera_controls", return_value={
                    "supported": True, "controls": [control],
                }), \
                mock.patch.object(MODULE.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "inactive or read-only"):
                MODULE.set_camera_control({"name": "brightness", "value": 100})
        run.assert_not_called()

    def test_out_of_range_camera_values_are_reported_as_unknown(self):
        controls = MODULE.parse_v4l2_controls(
            "brightness 0x00980900 (int) : min=0 max=255 step=1 default=128 value=300 flags=has-min-max\n"
            "power_line_frequency 0x00980918 (menu) : min=0 max=2 default=2 value=9\n"
            "0: Disabled\n1: 50 Hz\n2: 60 Hz\n"
            "white_balance_automatic 0x0098090c (bool) : default=1 value=4"
        )
        self.assertEqual([control["value"] for control in controls], [None, None, None])
        self.assertEqual([control["default"] for control in controls], [128, 2, 1])

    def test_unknown_camera_control_values_are_visible_in_editors(self):
        self.assertIn('input.indeterminate = control.value === null;', PAGE_AND_JS)
        self.assertIn('unknown.textContent = "Unknown";', PAGE_AND_JS)
        self.assertIn('input.placeholder = control.value === null ? "Unknown" : "";', PAGE_AND_JS)

    def test_boolean_camera_controls_use_enabled_and_disabled_labels(self):
        self.assertIn('booleanLabel = (value) =>', PAGE_AND_JS)
        self.assertIn('"Enabled"', PAGE_AND_JS)
        self.assertIn('"Disabled"', PAGE_AND_JS)
        self.assertIn('booleanLabel(control.value)', PAGE_AND_JS)
        self.assertIn('booleanLabel(control.default)', PAGE_AND_JS)

    def test_management_page_exposes_dynamic_camera_controls(self):
        self.assertIn('id="camera-controls-list"', PAGE_AND_JS)
        self.assertIn("/api/camera-controls", PAGE_AND_JS)
        self.assertIn("Dynamic framerate", PAGE_AND_JS)
        self.assertIn("actual captured FPS", PAGE_AND_JS)

    def test_all_camera_control_editor_types_are_added_to_the_editor(self):
        self.assertIn('let input,', PAGE_AND_JS)
        self.assertIn('output,', PAGE_AND_JS)
        self.assertIn('isRange = false;', PAGE_AND_JS)
        self.assertIn('if (output) editor.append(input, output);', PAGE_AND_JS)
        self.assertIn('else editor.append(input);', PAGE_AND_JS)
        self.assertIn('input.type = "checkbox";', PAGE_AND_JS)
        self.assertIn('input.type = "range";', PAGE_AND_JS)
        self.assertIn('input.type = "number";', PAGE_AND_JS)
        self.assertIn('document.createElement("select")', PAGE_AND_JS)

class CaptureModeCatalogTests(unittest.TestCase):
    def test_camera_inventory_exposes_every_hardware_advertised_usb_mode(self):
        usb_devices = [{
            "device": "/dev/video0",
            "modes": [
                {"format": "YUYV", "width": 3840, "height": 2160, "fps": [60]},
                {"format": "MJPG", "width": 640, "height": 480, "fps": [30]},
            ],
        }]
        with (
            mock.patch.object(MODULE, "discover_devices", return_value=usb_devices),
            mock.patch.object(MODULE, "discover_csi_cameras", return_value=[]),
        ):
            cameras = MODULE.camera_inventory()
        modes = cameras[0]["capture_modes"]
        self.assertEqual([mode["format"] for mode in modes], ["YUYV", "MJPG"])
        self.assertEqual(modes[0]["width"], 3840)
        self.assertNotIn("exceeds_performance_budget", modes[0])


class CameraIdentityTests(unittest.TestCase):
    def test_usb_camera_identity_prefers_physical_path(self):
        camera = {"kind": "usb", "device": "/dev/video4", "physical_path": "/sys/devices/usb1/1-1"}
        identity = MODULE.camera_identity(camera)
        self.assertTrue(identity["stable_identity"])
        self.assertEqual(identity["id"], MODULE.camera_identity({
            **camera, "device": "/dev/video7",
        })["id"])

    def test_csi_camera_identity_uses_device_tree_path_when_available(self):
        camera = {"kind": "csi", "camera": 0, "sensor": "IMX219", "device_path": "/sys/firmware/devicetree/base/cam0"}
        identity = MODULE.camera_identity(camera)
        self.assertTrue(identity["stable_identity"])
        self.assertTrue(identity["id"].startswith("csi-"))

if __name__ == "__main__":
    unittest.main()
