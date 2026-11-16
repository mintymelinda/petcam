from pathlib import Path


def test_dashboard_and_browser_source_assets_are_packaged():
    static = Path(__file__).resolve().parents[2] / "src" / "petcam" / "static"
    for asset in (
        "dashboard.html",
        "dashboard.js",
        "dashboard-api.js",
        "dashboard-camera.js",
        "dashboard-features.js",
        "browser-source.html",
        "browser-source.js",
    ):
        assert (static / asset).is_file()
