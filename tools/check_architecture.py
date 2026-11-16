#!/usr/bin/env python3
"""Fail CI when package, policy, and feature dependency boundaries are crossed."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "petcam"
POLICY_MODULES = {
    "domain/camera/capabilities.py",
    "domain/camera/capture_modes.py",
    "domain/camera/capture_policy.py",
    "domain/motion/policy.py",
    "domain/timelapse/policy.py",
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
FORBIDDEN_DOMAIN_IMPORTS = {
    "api",
    "application",
    "features",
    "infrastructure",
    "security",
}


def imported_root(node: ast.AST) -> str | None:
    if isinstance(node, ast.Import):
        return node.names[0].name.split(".", 1)[0] if node.names else None
    if isinstance(node, ast.ImportFrom):
        return (node.module or "").split(".", 1)[0]
    return None


def call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        function = node.func
        if isinstance(function, ast.Name):
            return function.id
        if isinstance(function, ast.Attribute):
            return function.attr
    return None


def feature_dependency(node: ast.AST, current_feature: str) -> str | None:
    """Resolve direct relative/absolute imports between feature packages."""
    if not isinstance(node, ast.ImportFrom):
        return None
    module = node.module or ""
    if module.startswith("petcam.features."):
        pieces = module.split(".")
        target = pieces[2] if len(pieces) > 2 else None
    elif node.level >= 2 and module:
        target = module.split(".", 1)[0]
    else:
        target = None
    if target and target in {"motion", "timelapse", "light_sensor", "home_assistant"} and target != current_feature:
        return target
    return None


def violations() -> list[str]:
    problems: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(PACKAGE)
        if len(relative.parts) == 1 and relative.name != "__init__.py":
            problems.append(
                f"{path.relative_to(ROOT)}: implementation modules must live in a responsibility package"
            )

        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as error:
            problems.append(f"{path.relative_to(ROOT)}: cannot parse Python source: {error}")
            continue

        for node in ast.walk(tree):
            root = imported_root(node)
            if relative.as_posix() in POLICY_MODULES:
                if root in FORBIDDEN_POLICY_IMPORTS:
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: policy imports infrastructure module {root!r}"
                    )
                name = call_name(node)
                if name in FORBIDDEN_POLICY_CALLS:
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: policy invokes infrastructure call {name!r}"
                    )

            if relative.parts and relative.parts[0] == "api" and root == "web_manager":
                problems.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}: API routes must not import the composition root"
                )

            if relative.parts and relative.parts[0] == "domain" and root in FORBIDDEN_DOMAIN_IMPORTS:
                problems.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}: domain code must not depend on {root!r}"
                )

            if relative.parts and relative.parts[0] == "features":
                current_feature = relative.parts[1] if len(relative.parts) > 1 else ""
                target = feature_dependency(node, current_feature)
                if target:
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: feature {current_feature!r} must not depend on feature {target!r}"
                    )

    return problems


def main() -> int:
    problems = violations()
    if problems:
        print(*problems, sep=chr(10))
        return 1
    print("Architecture boundaries verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
