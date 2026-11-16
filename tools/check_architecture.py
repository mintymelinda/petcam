#!/usr/bin/env python3
"""Fail CI when package, policy, and feature dependency boundaries are crossed."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src"

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
FORBIDDEN_APPLICATION_IMPORTS = {"api", "features", "security"}
FORBIDDEN_INFRASTRUCTURE_IMPORTS = {"api", "application", "features", "security"}
FORBIDDEN_FEATURE_IMPORTS = {"api", "application", "security"}
FORBIDDEN_SECURITY_IMPORTS = {"api", "application", "features", "infrastructure"}


def imported_modules(node: ast.AST, relative: Path) -> list[str]:
    """Return import module paths normalized relative to the petcam package."""
    if isinstance(node, ast.Import):
        modules = [alias.name for alias in node.names]
    elif isinstance(node, ast.ImportFrom):
        if not node.level and node.module == "petcam":
            modules = [f"petcam.{alias.name}" for alias in node.names]
        elif node.level:
            package_parts = list(relative.parts[:-1])
            keep = max(0, len(package_parts) - node.level + 1)
            base = package_parts[:keep]
            suffix = (node.module or "").split(".") if node.module else []
            if suffix:
                modules = [".".join((*base, *suffix))]
            else:
                modules = [".".join((*base, alias.name)) for alias in node.names]
        else:
            modules = [node.module or ""]
    else:
        return []

    normalized = []
    for module in modules:
        if module == "petcam":
            normalized.append("")
        elif module.startswith("petcam."):
            normalized.append(module.removeprefix("petcam."))
        else:
            normalized.append(module)
    return normalized


def imported_roots(node: ast.AST, relative: Path) -> set[str]:
    return {
        module.split(".", 1)[0]
        for module in imported_modules(node, relative)
        if module
    }


def call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        function = node.func
        if isinstance(function, ast.Name):
            return function.id
        if isinstance(function, ast.Attribute):
            return function.attr
    return None


def feature_dependencies(node: ast.AST, current_feature: str, relative: Path) -> set[str]:
    """Resolve direct relative and absolute imports between feature packages."""
    targets = set()
    for module in imported_modules(node, relative):
        pieces = module.split(".")
        if len(pieces) >= 2 and pieces[0] == "features":
            target = pieces[1]
            if target in {"motion", "timelapse", "light_sensor", "home_assistant"} and target != current_feature:
                targets.add(target)
    return targets


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
            roots = imported_roots(node, relative)
            if relative.as_posix() in POLICY_MODULES:
                for root in roots & FORBIDDEN_POLICY_IMPORTS:
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: policy imports infrastructure module {root!r}"
                    )
                name = call_name(node)
                if name in FORBIDDEN_POLICY_CALLS:
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: policy invokes infrastructure call {name!r}"
                    )

            if relative.parts and relative.parts[0] == "api" and relative.name != "application.py":
                for root in roots & (FORBIDDEN_DOMAIN_IMPORTS - {"api"}):
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: API route handlers must use injected services, not import {root!r}"
                    )

            if relative.parts and relative.parts[0] == "domain":
                for root in roots & FORBIDDEN_DOMAIN_IMPORTS:
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: domain code must not depend on {root!r}"
                    )

            if relative.parts and relative.parts[0] == "application":
                for root in roots & FORBIDDEN_APPLICATION_IMPORTS:
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: application code must not depend on {root!r}"
                    )

            if relative.parts and relative.parts[0] == "infrastructure":
                for root in roots & FORBIDDEN_INFRASTRUCTURE_IMPORTS:
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: infrastructure code must not depend on {root!r}"
                    )

            if relative.parts and relative.parts[0] == "features":
                current_feature = relative.parts[1] if len(relative.parts) > 1 else ""
                for root in roots & FORBIDDEN_FEATURE_IMPORTS:
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: feature code must not depend on {root!r}"
                    )
                for target in feature_dependencies(node, current_feature, relative):
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: feature {current_feature!r} must not depend on feature {target!r}"
                    )

            if relative.parts and relative.parts[0] == "security":
                for root in roots & FORBIDDEN_SECURITY_IMPORTS:
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: security code must not depend on {root!r}"
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
