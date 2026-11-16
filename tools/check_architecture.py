#!/usr/bin/env python3
"""Enforce PetCam's package layout and inward dependency boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "petcam"
EXPECTED_TEST_PACKAGES = (
    "api",
    "application",
    "domain",
    "features",
    "infrastructure",
    "security",
    "static",
)
POLICY_MODULES = {
    "domain/camera/capabilities.py",
    "domain/camera/capture_modes.py",
    "domain/camera/capture_policy.py",
    "domain/motion/policy.py",
    "domain/timelapse/policy.py",
    "domain/streaming/status.py",
    "features/light_sensor/policy.py",
}
FORBIDDEN_POLICY_IMPORTS = {
    "subprocess",
    "socket",
    "ssl",
    "threading",
    "multiprocessing",
    "http",
    "urllib",
}
FORBIDDEN_POLICY_CALLS = {
    "Popen",
    "run",
    "system",
    "popen",
    "urlopen",
    "Thread",
    "ThreadPoolExecutor",
}


def imported_module(node: ast.AST) -> str | None:
    if isinstance(node, ast.Import):
        return node.names[0].name if node.names else None
    if isinstance(node, ast.ImportFrom):
        return node.module
    return None


def call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        function = node.func
        if isinstance(function, ast.Name):
            return function.id
        if isinstance(function, ast.Attribute):
            return function.attr
    return None


def violations() -> list[str]:
    problems: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as error:
            problems.append(f"{path.relative_to(ROOT)}: cannot parse Python source: {error}")
            continue

        relative = path.relative_to(PACKAGE)
        relative_name = relative.as_posix()

        if len(relative.parts) == 1 and relative.name != "__init__.py":
            problems.append(
                f"{path.relative_to(ROOT)}: package root may contain only __init__.py; move this module into its owning package"
            )

        if relative_name in POLICY_MODULES:
            for node in ast.walk(tree):
                root = imported_module(node)
                if root in FORBIDDEN_POLICY_IMPORTS:
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: policy imports infrastructure module {root!r}"
                    )
                name = call_name(node)
                if name in FORBIDDEN_POLICY_CALLS:
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: policy invokes infrastructure call {name!r}"
                    )

        package = relative.parts[0] if relative.parts else ""
        for node in ast.walk(tree):
            module = imported_module(node) or ""
            if package == "domain" and module.startswith((
                "petcam.api", "petcam.application", "petcam.infrastructure",
                "petcam.features", "petcam.security",
            )):
                problems.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}: domain must not depend on outer application layers"
                )
            if package in {"application", "features"} and module.startswith("petcam.api"):
                problems.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}: application/feature code must not depend on API routes"
                )
            if package == "infrastructure" and module.startswith((
                "petcam.api", "petcam.application", "petcam.features", "petcam.security",
            )):
                problems.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}: infrastructure must not depend on application or feature layers"
                )
            if package == "api" and module == "web_manager":
                problems.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}: API routes must not import the legacy composition-root module"
                )

    test_root = ROOT / "tests"
    for package in EXPECTED_TEST_PACKAGES:
        if not (test_root / package).is_dir():
            problems.append(f"tests/{package}: matching architectural test package is missing")

    return problems


def main() -> int:
    problems = violations()
    if problems:
        print("\n".join(problems))
        return 1
    print("Package layout and architecture boundaries verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
