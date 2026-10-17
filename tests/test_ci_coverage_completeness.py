"""Regression checks for development CI and previously excluded execution paths."""

from __future__ import annotations

import builtins
import runpy
from pathlib import Path
from unittest.mock import patch

import pytest

from benchmark.paths import PathBoundaryError, resolve_within
from conftest import ROOT, load_script


def test_dev_push_runs_full_validation_workflow():
    checker = load_script("ci_contract_workflows", "bin/check_workflows.py")
    workflow = checker.strict_load(
        (ROOT / ".github/workflows/validate-skill.yml").read_text(encoding="utf-8")
    )
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["push"]["branches"] == ["main", "dev/**"]
    assert workflow["permissions"] == {"contents": "read"}
    assert "coverage" in workflow["jobs"]
    coverage_command = workflow["jobs"]["coverage"]["steps"][3]["run"]
    assert "coverage run -m pytest -q -rs tests/" in coverage_command
    assert "coverage report --fail-under=100" in coverage_command


def test_direct_script_import_fallback_is_covered(monkeypatch):
    real_import = builtins.__import__
    rejected = False

    def missing_package_once(name, globals=None, locals=None, fromlist=(), level=0):
        nonlocal rejected
        if name == "benchmark.paths" and not rejected:
            rejected = True
            raise ImportError("simulated direct-script path")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", missing_package_once)
    namespace = runpy.run_path(
        str(ROOT / "benchmark/evaluate.py"), run_name="import_fallback_coverage"
    )
    assert rejected
    assert callable(namespace["require_within"])


@pytest.mark.parametrize("error", [OSError("link error"), RuntimeError("symlink loop")])
def test_path_resolution_failures_are_covered(tmp_path: Path, error: Exception):
    original = Path.resolve

    def fail_target_only(path, *args, **kwargs):
        if path.name == "candidate":
            raise error
        return original(path, *args, **kwargs)

    with (
        patch.object(Path, "resolve", fail_target_only),
        pytest.raises(PathBoundaryError, match="cannot resolve"),
    ):
        resolve_within(tmp_path, "candidate")
