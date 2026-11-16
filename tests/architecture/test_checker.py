from __future__ import annotations

from pathlib import Path

from tools import check_architecture


def violations_for(tmp_path, monkeypatch, modules: dict[str, str]) -> list[str]:
    root = tmp_path
    package = root / "src" / "petcam"
    for relative, content in modules.items():
        path = package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(check_architecture, "ROOT", root)
    monkeypatch.setattr(check_architecture, "PACKAGE", package)
    return check_architecture.violations()


def test_domain_rejects_absolute_infrastructure_imports(tmp_path, monkeypatch):
    problems = violations_for(
        tmp_path,
        monkeypatch,
        {
            "domain/camera/policy.py": (
                "from petcam.infrastructure.persistence import configuration\n"
            ),
        },
    )

    assert any("domain code must not depend on 'infrastructure'" in problem for problem in problems)


def test_api_routes_reject_application_imports(tmp_path, monkeypatch):
    problems = violations_for(
        tmp_path,
        monkeypatch,
        {
            "api/camera_routes.py": (
                "from ..application.camera_inventory import build_camera_inventory\n"
            ),
        },
    )

    assert any("API route handlers must use injected services" in problem for problem in problems)


def test_features_reject_cross_feature_absolute_and_relative_imports(tmp_path, monkeypatch):
    problems = violations_for(
        tmp_path,
        monkeypatch,
        {
            "features/motion/service.py": (
                "from petcam.features.timelapse.service import capture_frame\n"
            ),
            "features/light_sensor/service.py": (
                "from ..motion import worker\n"
            ),
        },
    )

    assert sum("must not depend on feature" in problem for problem in problems) == 2


def test_root_level_implementation_modules_are_rejected(tmp_path, monkeypatch):
    problems = violations_for(
        tmp_path,
        monkeypatch,
        {"legacy.py": "def main():\n    return 0\n"},
    )

    assert any("implementation modules must live in a responsibility package" in problem for problem in problems)


def test_valid_layered_dependencies_are_allowed(tmp_path, monkeypatch):
    problems = violations_for(
        tmp_path,
        monkeypatch,
        {
            "domain/camera/policy.py": "class CameraPolicy:\n    pass\n",
            "infrastructure/persistence/store.py": "class Store:\n    pass\n",
            "application/camera_service.py": (
                "from ..domain.camera.policy import CameraPolicy\n"
                "from ..infrastructure.persistence.store import Store\n"
            ),
            "features/motion/service.py": (
                "from ...domain.camera.policy import CameraPolicy\n"
                "from ...infrastructure.persistence.store import Store\n"
            ),
            "api/application.py": (
                "from ..application.camera_service import CameraPolicy\n"
                "from ..infrastructure.persistence.store import Store\n"
            ),
            "api/camera_routes.py": (
                "def handle_get(handler, services):\n"
                "    return services.camera_inventory()\n"
            ),
        },
    )

    assert problems == []
