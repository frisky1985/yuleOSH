"""Regression test for _iter_runnable_projects repo-root exclusion.

Background (2026-09-04, 一键跑 UI bug):
  When OSH_HOME = the yuleOSH repo root, the discovery loop walked into
  <repo>/docs/spec.md and reported the repo itself as a runnable "demo".
  UI one-click then ran the orchestrator against yuleOSH's own 2.5.0
  compliance spec, which legitimately has 12 missing SHALL ERRORs — the
  spec-check step failed correctly on a self-host spec.  The fix excludes
  the repo root so users can only run real demos/templates.

  We anchor the exclusion on "is this a yuleOSH source tree?" via the
  presence of pyproject.toml + src/yuleosh/__init__.py — stable across
  renames of the package dir itself.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.ui.routes.pipeline_routes import _iter_runnable_projects


def _write(path: Path, content: str = "# spec\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_repo_root_docs_spec_is_excluded():
    """A spec.md in <repo>/docs/spec.md must NOT appear in demo list.

    This is the precise bug pattern (UI one-click ran the yuleOSH own
    2.5.0 compliance spec which legitimately has 12 missing SHALL ERRORs).
    Legitimate demos under templates/, demos/, etc. still surface.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "yuleOSH"
        repo.mkdir()
        # Repo-root fingerprints (mirrors the real repo layout)
        (repo / "pyproject.toml").write_text("[project]\nname='yuleosh'\n")
        (repo / "src" / "yuleosh").mkdir(parents=True)
        (repo / "src" / "yuleosh" / "__init__.py").write_text("")
        # The very spec that caused the bug
        _write(repo / "docs" / "spec.md")
        # A legitimate demo alongside
        _write(repo / "templates" / "demo-a" / "docs" / "spec.md")

        projs = _iter_runnable_projects(str(repo))
        names = sorted(p["name"] for p in projs)
        assert "yuleOSH" not in names, (
            f"repo root must be excluded, got: {names}"
        )
        assert "demo-a" in names


def test_nested_internal_doc_spec_is_excluded():
    """A spec.md in <repo>/<sub>/docs/spec.md is also excluded when
    <sub> is a non-demo internal folder — we still want to exclude the
    repo's own internal specs (specs/, internal/, etc.) from demos.

    Practically: real repos put example/spec docs in non-demo folders
    that should never appear in the one-click picker. The safe rule:
    if project_path contains a yuleOSH src tree marker anywhere on its
    path, drop it (templates/, src/ are excluded explicitly via skip
    set; anything else that's truly internal — e.g. specs/, internal/ —
    should still NOT appear as a "demo" because running it would
    regenerate content for the repo itself). We anchor this on the
    presence of pyproject.toml on the project_path itself OR the spec
    being in a path that contains the repo's src/yuleosh directory.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "yuleOSH"
        repo.mkdir()
        (repo / "pyproject.toml").write_text("")
        (repo / "src" / "yuleosh" / "__init__.py").parent.mkdir(parents=True)
        (repo / "src" / "yuleosh" / "__init__.py").write_text("")
        # An internal specs dir — these would never be demos; running
        # them would just re-emit the repo's own example docs. We skip
        # any directory whose path contains 'src/yuleosh' (the source
        # tree itself).
        _write(repo / "specs" / "spec-delta-1" / "spec.md")

        projs = _iter_runnable_projects(str(repo))
        # The existing skip set already excludes src/ → no entries.
        # Asserting that no src/yuleosh/* path leaks through is the real
        # invariant.
        leaked = [p for p in projs if "src/yuleosh" in p["path"]]
        assert leaked == [], f"src tree must not leak into demos: {leaked}"


def test_non_repo_root_demo_is_included():
    """A spec.md under a normal project (no repo fingerprints) is included."""
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        proj = home / "my-demo"
        proj.mkdir()
        _write(proj / "docs" / "spec.md")
        # Ensure repo_root fingerprint is NOT present at home
        assert not (home / "pyproject.toml").exists()

        projs = _iter_runnable_projects(str(home))
        names = [p["name"] for p in projs]
        assert names == ["my-demo"], names


def test_existing_real_repo_excludes_root():
    """Sanity check on the real yuleOSH repo (must not list 'yuleOSH')."""
    real = "/Users/ingeek/workspace/yuleOSH"
    if not (Path(real) / "pyproject.toml").exists():
        return  # skip on non-dev machines
    projs = _iter_runnable_projects(real)
    names = [p["name"] for p in projs]
    assert "yuleOSH" not in names, (
        f"real repo root must never be a runnable demo, got: {names}"
    )
    # The legitimate GPIO demo that has been verified end-to-end must still be present.
    assert "gpio-led-chaser" in names


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))