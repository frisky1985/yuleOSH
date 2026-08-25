
# @tests src/yuleosh/plugins/sandbox.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Sandbox security deep tests — P1-3c.

Covers the enforcement paths of plugins/sandbox.py that are
security-critical but were previously untested:

- File read outside plugin dir is rejected
- File write to extra_read_dirs is rejected (read/write isolation)
- Symlink escape attempt is rejected
- Parent-dir (..) escape attempt is rejected
- extra_read_dirs honored via constructor and manifest.permissions
- safe_import positive path for ALLOWED_STDLIB
- safe_import rejects non-whitelisted modules (os, subprocess)
- SAFE_BUILTINS excludes dangerous builtins (eval, exec, compile)
- Write inside plugin dir succeeds (positive case)
- Read from extra_read_dirs succeeds (positive case)
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from yuleosh.plugins import Plugin, PluginManifest
from yuleosh.plugins.sandbox import SAFE_BUILTINS, PluginSandbox, SandboxViolation


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def plugin_dir(tmp_path):
    d = tmp_path / "test_plugin"
    d.mkdir()
    return d


@pytest.fixture
def extra_dir(tmp_path):
    d = tmp_path / "extra_read"
    d.mkdir()
    (d / "data.txt").write_text("hello from extra")
    return d


@pytest.fixture
def outside_dir(tmp_path):
    d = tmp_path / "outside"
    d.mkdir()
    (d / "secret.txt").write_text("secret data")
    return d


def _make_sandbox(plugin_dir, extra_read_dirs=None, manifest=None):
    sandbox = PluginSandbox(plugin_dir, manifest=manifest, extra_read_dirs=extra_read_dirs)
    dummy = Mock(spec=Plugin)
    dummy.name = "test_plugin"
    dummy.entry_path = Path(plugin_dir) / "entry.py"
    dummy.manifest = manifest
    dummy.directory = Path(plugin_dir)
    return sandbox, dummy


# ---------------------------------------------------------------------------
# Filesystem access tests
# ---------------------------------------------------------------------------

class TestRestrictedOpenRead:
    """Read-path enforcement."""

    def test_read_outside_plugin_dir_rejected(self, plugin_dir, outside_dir):
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_open = sandbox._restricted_open(plugin)
        with pytest.raises(SandboxViolation, match="禁止读取沙箱外文件"):
            safe_open(str(outside_dir / "secret.txt"), "r")

    def test_read_inside_plugin_dir_allowed(self, plugin_dir):
        (plugin_dir / "local.txt").write_text("local data")
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_open = sandbox._restricted_open(plugin)
        with safe_open(str(plugin_dir / "local.txt"), "r") as f:
            assert f.read() == "local data"

    def test_read_from_extra_read_dirs_allowed(self, plugin_dir, extra_dir):
        sandbox, plugin = _make_sandbox(plugin_dir, extra_read_dirs=[extra_dir])
        safe_open = sandbox._restricted_open(plugin)
        with safe_open(str(extra_dir / "data.txt"), "r") as f:
            assert f.read() == "hello from extra"

    def test_read_from_manifest_extra_read_dirs(self, plugin_dir, extra_dir):
        manifest = PluginManifest(
            name="test", version="1.0.0", type="tool",
            description="test", author="test", entry="main.py",
            permissions={"extra_read_dirs": [str(extra_dir)]},
        )
        sandbox, plugin = _make_sandbox(plugin_dir, manifest=manifest)
        safe_open = sandbox._restricted_open(plugin)
        with safe_open(str(extra_dir / "data.txt"), "r") as f:
            assert f.read() == "hello from extra"

    def test_read_from_non_whitelisted_dir_rejected(self, plugin_dir, extra_dir, outside_dir):
        sandbox, plugin = _make_sandbox(plugin_dir, extra_read_dirs=[extra_dir])
        safe_open = sandbox._restricted_open(plugin)
        with pytest.raises(SandboxViolation):
            safe_open(str(outside_dir / "secret.txt"), "r")


class TestRestrictedOpenWrite:
    """Write-path enforcement — read/write isolation."""

    def test_write_outside_plugin_dir_rejected(self, plugin_dir, outside_dir):
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_open = sandbox._restricted_open(plugin)
        with pytest.raises(SandboxViolation, match="禁止写入沙箱外文件"):
            safe_open(str(outside_dir / "escaped.txt"), "w")

    def test_write_to_extra_read_dirs_rejected(self, plugin_dir, extra_dir):
        """extra_read_dirs grants READ only — write must be rejected."""
        sandbox, plugin = _make_sandbox(plugin_dir, extra_read_dirs=[extra_dir])
        safe_open = sandbox._restricted_open(plugin)
        with pytest.raises(SandboxViolation, match="禁止写入沙箱外文件"):
            safe_open(str(extra_dir / "hack.txt"), "w")

    def test_write_inside_plugin_dir_allowed(self, plugin_dir):
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_open = sandbox._restricted_open(plugin)
        with safe_open(str(plugin_dir / "output.txt"), "w") as f:
            f.write("output")
        assert (plugin_dir / "output.txt").read_text() == "output"

    def test_append_mode_treated_as_write(self, plugin_dir, outside_dir):
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_open = sandbox._restricted_open(plugin)
        with pytest.raises(SandboxViolation):
            safe_open(str(outside_dir / "append.txt"), "a")

    def test_exclusive_mode_treated_as_write(self, plugin_dir, outside_dir):
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_open = sandbox._restricted_open(plugin)
        with pytest.raises(SandboxViolation):
            safe_open(str(outside_dir / "excl.txt"), "x")

    def test_plus_mode_treated_as_write(self, plugin_dir, outside_dir):
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_open = sandbox._restricted_open(plugin)
        with pytest.raises(SandboxViolation):
            safe_open(str(outside_dir / "plus.txt"), "r+")


class TestPathEscape:
    """Symlink and .. escape prevention."""

    def test_dotdot_escape_rejected(self, plugin_dir, tmp_path):
        outside = tmp_path / "escaped"
        outside.mkdir()
        (outside / "stolen.txt").write_text("stolen")
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_open = sandbox._restricted_open(plugin)
        escape_path = str(plugin_dir / ".." / "escaped" / "stolen.txt")
        with pytest.raises(SandboxViolation):
            safe_open(escape_path, "r")

    def test_symlink_escape_rejected(self, plugin_dir, outside_dir, tmp_path):
        link = plugin_dir / "link_to_secret"
        os.symlink(outside_dir / "secret.txt", link)
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_open = sandbox._restricted_open(plugin)
        with pytest.raises(SandboxViolation):
            safe_open(str(link), "r")


# ---------------------------------------------------------------------------
# Import restriction tests
# ---------------------------------------------------------------------------

class TestRestrictedImport:
    """Import-path enforcement."""

    def test_import_os_rejected(self, plugin_dir):
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_import = sandbox._restricted_import(plugin)
        with pytest.raises(SandboxViolation, match="禁止导入模块"):
            safe_import("os")

    def test_import_subprocess_rejected(self, plugin_dir):
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_import = sandbox._restricted_import(plugin)
        with pytest.raises(SandboxViolation):
            safe_import("subprocess")

    def test_import_os_path_rejected(self, plugin_dir):
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_import = sandbox._restricted_import(plugin)
        with pytest.raises(SandboxViolation):
            safe_import("os.path")

    def test_relative_import_rejected(self, plugin_dir):
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_import = sandbox._restricted_import(plugin)
        with pytest.raises(SandboxViolation, match="禁止相对导入"):
            safe_import("foo", level=1)

    def test_import_json_allowed(self, plugin_dir):
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_import = sandbox._restricted_import(plugin)
        mod = safe_import("json")
        assert mod is not None
        assert hasattr(mod, "loads")

    def test_import_math_allowed(self, plugin_dir):
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_import = sandbox._restricted_import(plugin)
        mod = safe_import("math")
        assert hasattr(mod, "sqrt")

    def test_import_re_allowed(self, plugin_dir):
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_import = sandbox._restricted_import(plugin)
        mod = safe_import("re")
        assert hasattr(mod, "match")

    def test_import_datetime_allowed(self, plugin_dir):
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_import = sandbox._restricted_import(plugin)
        mod = safe_import("datetime")
        assert hasattr(mod, "datetime")

    def test_import_pathlib_allowed(self, plugin_dir):
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_import = sandbox._restricted_import(plugin)
        mod = safe_import("pathlib")
        assert hasattr(mod, "Path")

    def test_import_dotted_allowed_module(self, plugin_dir):
        """json.encoder is allowed because top-level json is whitelisted."""
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_import = sandbox._restricted_import(plugin)
        mod = safe_import("json.encoder")
        assert hasattr(mod, "JSONEncoder")


# ---------------------------------------------------------------------------
# SAFE_BUILTINS regression tests
# ---------------------------------------------------------------------------

class TestSafeBuiltinsExcludes:
    """Ensure dangerous builtins are NOT in the whitelist."""

    DANGEROUS = ["eval", "exec", "compile", "__build_class__",
                 "globals", "locals", "vars", "input",
                 "breakpoint", "memoryview"]

    @pytest.mark.parametrize("name", DANGEROUS)
    def test_dangerous_builtin_absent(self, name):
        assert name not in SAFE_BUILTINS, (
            f"{name} must NOT be in SAFE_BUILTINS — "
            f"it allows arbitrary code execution or introspection"
        )

    def test_open_is_whitelisted_but_replaced(self):
        assert "open" in SAFE_BUILTINS

    def test_import_is_whitelisted_but_replaced(self):
        assert "__import__" in SAFE_BUILTINS

    def test_print_allowed(self):
        assert "print" in SAFE_BUILTINS


# ---------------------------------------------------------------------------
# Subprocess blocking
# ---------------------------------------------------------------------------

class TestSubprocessBlocking:
    """Verify subprocess creation is blocked at the import level."""

    def test_block_subprocess_raises(self):
        with pytest.raises(SandboxViolation, match="禁止在沙箱中创建子进程"):
            PluginSandbox.block_subprocess()

    def test_subprocess_not_in_allowed_stdlib(self, plugin_dir):
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_import = sandbox._restricted_import(plugin)
        with pytest.raises(SandboxViolation):
            safe_import("subprocess")

    def test_os_system_not_accessible(self, plugin_dir):
        """os module is not importable, so os.system is unreachable."""
        sandbox, plugin = _make_sandbox(plugin_dir)
        safe_import = sandbox._restricted_import(plugin)
        with pytest.raises(SandboxViolation):
            safe_import("os")
