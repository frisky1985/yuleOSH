"""Smoke tests for yuleosh.plugins — registry, sandbox, manager."""
import os, sys, json, tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestPluginsInit:
    def test_import(self):
        import yuleosh.plugins
        assert hasattr(yuleosh.plugins, "PluginManifest")
        assert hasattr(yuleosh.plugins, "PluginManager")
        assert hasattr(yuleosh.plugins, "PluginInfo")

    def test_plugin_manifest_create(self):
        from yuleosh.plugins import PluginManifest
        m = PluginManifest(name="test", version="1.0", type="tool",
                           description="desc", author="me")
        assert m.name == "test"

    def test_plugin_info_create(self):
        from yuleosh.plugins import PluginInfo
        info = PluginInfo(
            name="test-plugin", version="0.1", type="tool",
            description="desc", author="me", path="/tmp", manifest_path="/tmp/manifest.json"
        )
        assert info.name == "test-plugin"

    def test_plugin_manager_create(self):
        from yuleosh.plugins import PluginManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PluginManager(plugins_dir=tmpdir)
            assert mgr is not None


class TestRegistry:
    def test_import(self):
        from yuleosh.plugins.registry import PluginRegistry, RegistrySource
        assert PluginRegistry is not None

    def test_registry_source_defaults(self):
        from yuleosh.plugins.registry import RegistrySource
        src = RegistrySource(name="test", url="https://example.com")
        assert src.name == "test"

    def test_registry_plugin_entry(self):
        from yuleosh.plugins.registry import RegistryPluginEntry
        entry = RegistryPluginEntry(name="test-plugin")
        assert entry.name == "test-plugin"


class TestSandbox:
    def test_import(self):
        from yuleosh.plugins.sandbox import PluginSandbox
        assert PluginSandbox is not None

    def test_sandbox_violation(self):
        from yuleosh.plugins.sandbox import SandboxViolation
        err = SandboxViolation("access denied")
        assert "access" in str(err)

    def test_safe_builtins(self):
        from yuleosh.plugins.sandbox import SAFE_BUILTINS
        assert isinstance(SAFE_BUILTINS, set)
        assert "print" in SAFE_BUILTINS
