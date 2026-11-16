import http.client
import json
import ssl
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from petcam.bootstrap import setup_portal as MODULE
from petcam.security import sessions as web_auth


class SetupPortalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.cert = cls.root / "cert.pem"
        cls.key = cls.root / "key.pem"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=localhost", "-keyout", str(cls.key), "-out", str(cls.cert),
        ], check=True, capture_output=True)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MODULE.Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cls.cert, cls.key)
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.client_context = ssl._create_unverified_context()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temp.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.auth_patch = mock.patch.object(web_auth, "AUTH_FILE", Path(self.directory.name) / "auth.json")
        self.config_patch = mock.patch.object(MODULE, "WEB_CONFIG", Path(self.directory.name) / "web-manager.json")
        self.auth_patch.start()
        self.config_patch.start()
        with MODULE._sessions_lock:
            MODULE._sessions.clear()
        with MODULE._login_lock:
            MODULE._login_attempts.clear()
        MODULE.set_web_ui_enabled(False)

    def tearDown(self):
        self.auth_patch.stop()
        self.config_patch.stop()
        self.directory.cleanup()

    def request(self, method, path, body=None, cookie=None, csrf=None, origin=True):
        connection = http.client.HTTPSConnection(
            "127.0.0.1", self.port, context=self.client_context, timeout=5
        )
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if origin:
            headers["Origin"] = f"https://127.0.0.1:{self.port}"
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-PetCam-CSRF"] = csrf
        encoded = json.dumps(body).encode() if body is not None else None
        if encoded is not None:
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(encoded))
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        payload = response.read()
        result = (response.status, response.getheaders(), payload)
        connection.close()
        return result

    def test_stub_is_available_while_full_web_ui_is_disabled(self):
        status, _, payload = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"PetCam Setup", payload)
        self.assertFalse(MODULE.web_ui_enabled())

    def test_first_run_setup_login_and_web_ui_toggle(self):
        status, _, payload = self.request("GET", "/setup/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload), {"configured": False, "enabled": False})

        status, headers, payload = self.request(
            "POST", "/setup/api/setup",
            {"password": "correct horse battery staple", "password_confirmation": "correct horse battery staple"},
        )
        self.assertEqual(status, 201)
        cookie = next(value for key, value in headers if key.lower() == "set-cookie").split(";", 1)[0]
        csrf = json.loads(payload)["csrf_token"]
        self.assertTrue(web_auth.verify_password("correct horse battery staple"))

        status, _, _ = self.request(
            "POST", "/setup/api/web-ui", {"enabled": True}, cookie=cookie,
        )
        self.assertEqual(status, 403)
        status, _, payload = self.request(
            "POST", "/setup/api/web-ui", {"enabled": True}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(payload)["enabled"])
        self.assertTrue(MODULE.web_ui_enabled())

        status, _, payload = self.request("GET", "/setup/api/session", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)["csrf_token"], csrf)

        status, _, _ = self.request("POST", "/setup/api/logout", {}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        status, _, _ = self.request("GET", "/setup/api/session", cookie=cookie)
        self.assertEqual(status, 401)

    def test_setup_rejects_cross_origin_and_duplicate_initialization(self):
        status, _, _ = self.request(
            "POST", "/setup/api/setup",
            {"password": "correct horse battery staple", "password_confirmation": "correct horse battery staple"},
            origin=False,
        )
        self.assertEqual(status, 403)
        web_auth.initialize_password("correct horse battery staple")
        status, _, _ = self.request(
            "POST", "/setup/api/setup",
            {"password": "another correct horse battery staple", "password_confirmation": "another correct horse battery staple"},
        )
        self.assertEqual(status, 409)

    def test_login_requires_password_and_rate_limits_failures(self):
        web_auth.initialize_password("correct horse battery staple")
        for _ in range(5):
            status, _, _ = self.request("POST", "/setup/api/login", {"password": "wrong"})
            self.assertEqual(status, 401)
        status, _, _ = self.request("POST", "/setup/api/login", {"password": "wrong"})
        self.assertEqual(status, 429)

    def test_web_ui_setting_requires_boolean(self):
        with self.assertRaisesRegex(ValueError, "boolean"):
            MODULE.set_web_ui_enabled("yes")
        MODULE.set_web_ui_enabled(True)
        self.assertTrue(MODULE.web_ui_enabled())
        MODULE.set_web_ui_enabled(False)
        self.assertFalse(MODULE.web_ui_enabled())


if __name__ == "__main__":
    unittest.main()
