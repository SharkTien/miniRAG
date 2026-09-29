"""Run the repository quality gate and print a reproducible quality score."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "README.md",
    "Dockerfile",
    "docker-compose.yml",
    ".env.example",
    "requirements.txt",
    "docs/architecture.md",
)


def run(command: list[str]) -> bool:
    """Run a quality command from the repository root."""
    result = subprocess.run(command, cwd=ROOT, check=False)
    return result.returncode == 0


def public_documentation_ratio() -> float:
    """Return the documented public class/function ratio for application code."""
    total = 0
    documented = 0
    for path in (ROOT / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                total += 1
                documented += ast.get_docstring(node) is not None
    return documented / total if total else 1.0


def main() -> int:
    """Run static checks, tests and the repository quality score."""
    lint_ok = run(["ruff", "check", "app", "tests"])
    naming_ok = run(["ruff", "check", "app", "tests", "--select", "N"])
    docs_ratio = public_documentation_ratio()
    docs_ok = docs_ratio >= 0.90
    tests_ok = run([sys.executable, "-m", "pytest", "-q", "tests"])
    packaging_ok = all((ROOT / path).exists() for path in REQUIRED_FILES)

    score = 0.0
    score += 35.0 if lint_ok else 0.0
    score += 15.0 if naming_ok else 0.0
    score += min(25.0, docs_ratio * 25.0)
    score += 15.0 if tests_ok else 0.0
    score += 10.0 if packaging_ok else 0.0

    print(f"Public documentation: {docs_ratio * 100:.1f}%")
    print(f"Quality score: {score:.1f}/100")
    if score < 90.0:
        print("Quality gate failed: score must be at least 90/100.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
