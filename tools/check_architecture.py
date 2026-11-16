#!/usr/bin/env python3
"""Fail CI when core policy and HTTP composition boundaries are crossed."""

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


def violations() -> list[str]:
    problems: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as error:
            problems.append(f"{path.relative_to(ROOT)}: cannot parse Python source: {error}")
            continue

        relative = path.relative_to(PACKAGE)
        if relative.as_posix() in POLICY_MODULES:
            for node in ast.walk(tree):
                root = imported_root(node)
                if root in FORBIDDEN_POLICY_IMPORTS:
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: policy imports infrastructure module {root!r}"
                    )
                name = call_name(node)
                if name in FORBIDDEN_POLICY_CALLS:
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: policy invokes infrastructure call {name!r}"
                    )

        if relative.parts and relative.parts[0] == "api":
            for node in ast.walk(tree):
                root = imported_root(node)
                if root == "web_manager":
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: API routes must not import the composition root"
                    )

    return problems


def main() -> int:
    problems = violations()
    if problems:
        print("\n".join(problems))
        return 1
    print("Architecture boundaries verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
