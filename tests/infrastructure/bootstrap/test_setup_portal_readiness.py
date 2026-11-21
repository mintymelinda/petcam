import threading
import unittest
from unittest import mock

from petcam.bootstrap import setup_portal


class ManagerReadinessTests(unittest.TestCase):
    def test_disabled_manager_is_not_ready(self):
        with mock.patch.object(setup_portal, "web_ui_enabled", return_value=False):
            self.assertEqual(
                setup_portal.manager_readiness(),
                (False, "Full UI is disabled."),
            )

    def test_unhealthy_core_services_prevent_manager_probes(self):
        with (
            mock.patch.object(setup_portal, "web_ui_enabled", return_value=True),
            mock.patch.object(setup_portal, "core_services_healthy", return_value=False),
            mock.patch.object(setup_portal, "_manager_get") as manager_get,
        ):
            self.assertEqual(
                setup_portal.manager_readiness(),
                (False, "Waiting for core services to report healthy status."),
            )
        manager_get.assert_not_called()

    def test_dashboard_assets_are_probed_concurrently(self):
        barrier = threading.Barrier(len(setup_portal.MANAGER_STATIC_ASSETS))

        def manager_get(path):
            if path == "/":
                document = "".join(setup_portal.MANAGER_STATIC_ASSETS).encode("ascii")
                return 200, "text/html", document
            barrier.wait(timeout=2)
            return 200, "application/javascript", b"window.petcam = true;"

        with (
            mock.patch.object(setup_portal, "web_ui_enabled", return_value=True),
            mock.patch.object(setup_portal, "core_services_healthy", return_value=True),
            mock.patch.object(setup_portal, "_manager_get", side_effect=manager_get),
        ):
            self.assertEqual(
                setup_portal.manager_readiness(),
                (True, "Full UI is ready."),
            )

    def test_missing_dashboard_asset_reports_not_ready(self):
        def manager_get(path):
            if path == "/":
                document = "".join(setup_portal.MANAGER_STATIC_ASSETS).encode("ascii")
                return 200, "text/html", document
            if path == setup_portal.MANAGER_STATIC_ASSETS[0]:
                return 503, "text/plain", b"unavailable"
            return 200, "application/javascript", b"window.petcam = true;"

        with (
            mock.patch.object(setup_portal, "web_ui_enabled", return_value=True),
            mock.patch.object(setup_portal, "core_services_healthy", return_value=True),
            mock.patch.object(setup_portal, "_manager_get", side_effect=manager_get),
        ):
            self.assertEqual(
                setup_portal.manager_readiness(),
                (False, "One or more dashboard application assets are unavailable."),
            )


if __name__ == "__main__":
    unittest.main()
