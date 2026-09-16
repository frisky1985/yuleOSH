"""Unit tests for the integration-test stale-build-cache detection helpers.

These guard the 2026-09-16 fix: a project copied/relocated (e.g. the demo runner
copying templates/gpio-led-chaser to a temp dir) can carry a build/ whose
CMakeCache records the ORIGINAL source path. Reusing that cache made ctest look
for executables at the wrong location (rc=8). The helpers detect & remove such
dirs so the step reconfigures fresh.
"""
import shutil
import textwrap
from pathlib import Path

import pytest

from yuleosh.pipeline.step_handlers.test_integration import (
    _cmake_cache_source_dir,
    _remove_stale_build_dirs,
)


def _write_cache(build_dir: Path, source_dir: str) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "CMakeCache.txt").write_text(
        textwrap.dedent(
            f"""\
            # For build in directory: {source_dir}/build
            gpio_led_chaser_SOURCE_DIR:STATIC={source_dir}
            gpio_led_chaser_BINARY_DIR:STATIC={source_dir}/build
            """
        )
    )
    (build_dir / "CTestTestfile.cmake").write_text("add_test(NAME x COMMAND true)\n")


def test_cache_source_dir_parses(tmp_path):
    d = tmp_path / "build"
    _write_cache(d, "/some/original/path")
    assert _cmake_cache_source_dir(d) == "/some/original/path"


def test_cache_source_dir_none_when_missing(tmp_path):
    assert _cmake_cache_source_dir(tmp_path / "nope") is None


def test_remove_stale_build_dirs_removes_foreign_cache(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    # a build/ whose cache points at a DIFFERENT source tree
    stale = proj / "build"
    _write_cache(stale, "/some/foreign/path")
    # a cmake-build dir whose cache matches THIS project
    good = proj / "cmake-build-keep"
    _write_cache(good, str(proj))

    removed = _remove_stale_build_dirs(proj)

    assert str(stale) in removed
    assert not stale.exists()
    # the matching one must be kept
    assert good.exists()
    assert str(good) not in removed


def test_remove_stale_build_dirs_keeps_matching(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    keep = proj / "build"
    _write_cache(keep, str(proj))  # matches after resolve()

    removed = _remove_stale_build_dirs(proj)

    assert removed == []
    assert keep.exists()


def test_remove_stale_handles_build_and_cmake_build_globs(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    b1 = proj / "build"
    b2 = proj / "cmake-build-dead"
    _write_cache(b1, "/foreign/1")
    _write_cache(b2, "/foreign/2")

    removed = _remove_stale_build_dirs(proj)

    assert len(removed) == 2
    assert not b1.exists() and not b2.exists()
