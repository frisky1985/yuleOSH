"""Smoke tests for plugins/ module — registry, sandbox, and __init__ exports."""
import pytest
from unittest.mock import MagicMock, patch, mock_open
import json
import tempfile
import os
from pathlib import Path

from yuleosh.plugins import PluginManifest, PluginManager, PluginInfo, Plugin
from yuleosh.plugins.registry import (
    PluginRegistry, RegistrySource, RegistryPluginEntry, PluginVersionEntry,
    DEFAULT_SOURCES,
)
from yuleosh.plugins.sandbox import PluginSandbox, SandboxViolation, SAFE_BUILTINS


class TestPluginManifest:
    """Smoke tests for PluginManifest."""

    def test_create_minimal(self):
        m = PluginManifest(name="my-plugin", version="1.0.0", type="skill",
                           description="A plugin", author="me")
        assert m.name == "my-plugin"
        assert m.type == "skill"
        assert m.timeout == 30

    def test_from_dict(self):
        m = PluginManifest.from_dict({
            "name": "test", "version": "0.1.0", "type": "target",
            "description": "desc", "author": "author",
        })
        assert m.name == "test"
        assert m.type == "target"

    def test_from_dict_ignores_unknown(self):
        m = PluginManifest.from_dict({
            "name": "test", "version": "0.1.0", "type": "tool",
            "description": "desc", "author": "author",
            "unknown_field": "should be ignored",
        })
        assert hasattr(m, "name")
        assert not hasattr(m, "unknown_field")

    def test_to_dict(self):
        m = PluginManifest(name="test", version="1.0.0", type="skill",
                           description="d", author="a")
        d = m.to_dict()
        assert d["name"] == "test"

    def test_validate_ok(self):
        m = PluginManifest(name="ok", version="1.0.0", type="target",
                           description="ok", author="me")
        assert m.validate() == []

    def test_validate_missing_name(self):
        m = PluginManifest(name="", version="1.0.0", type="target",
                           description="ok", author="me")
        errors = m.validate()
        assert any("name" in e for e in errors)

    def test_validate_bad_type(self):
        m = PluginManifest(name="test", version="1.0.0", type="invalid_type",
                           description="ok", author="me")
        errors = m.validate()
        assert any("type" in e for e in errors)

    def test_validate_bad_version(self):
        m = PluginManifest(name="test", version="abc", type="target",
                           description="ok", author="me")
        errors = m.validate()
        assert any("version" in e for e in errors)

    def test_validate_missing_author(self):
        m = PluginManifest(name="test", version="1.0.0", type="target",
                           description="ok", author="")
        errors = m.validate()
        assert any("author" in e for e in errors)

    def test_from_file(self, tmp_path):
        manifest_data = {
            "name": "file-plugin", "version": "1.0.0", "type": "skill",
            "description": "loaded from file", "author": "tester",
        }
        mf = tmp_path / "manifest.json"
        mf.write_text(json.dumps(manifest_data))
        m = PluginManifest.from_file(str(mf))
        assert m.name == "file-plugin"


class TestPluginManager:
    """Smoke tests for PluginManager."""

    def test_create_manager(self, tmp_path):
        pm = PluginManager(str(tmp_path / "plugins"))
        assert pm.plugins_dir.exists()

    def test_discover_empty(self, tmp_path):
        pm = PluginManager(str(tmp_path / "empty"))
        assert pm.discover() == []

    def test_install_from_dir(self, tmp_path):
        plugin_dir = tmp_path / "src-plugin"
        plugin_dir.mkdir()
        manifest = {
            "name": "installed-plugin", "version": "1.0.0", "type": "skill",
            "description": "test", "author": "me",
        }
        (plugin_dir / "manifest.json").write_text(json.dumps(manifest))
        (plugin_dir / "run.py").write_text("def run(args): return 'ok'")

        pm = PluginManager(str(tmp_path / "store"))
        ok = pm.install(str(plugin_dir))
        assert ok is True

        # Verify it was installed
        m = pm.get_manifest("installed-plugin")
        assert m is not None
        assert m.name == "installed-plugin"

    def test_uninstall(self, tmp_path):
        plugin_dir = tmp_path / "src-plugin2"
        plugin_dir.mkdir()
        manifest = {
            "name": "to-remove", "version": "1.0.0", "type": "skill",
            "description": "test", "author": "me",
        }
        (plugin_dir / "manifest.json").write_text(json.dumps(manifest))
        pm = PluginManager(str(tmp_path / "store2"))
        pm.install(str(plugin_dir))
        assert pm.get_manifest("to-remove") is not None
        ok = pm.uninstall("to-remove")
        assert ok is True
        assert pm.get_manifest("to-remove") is None

    def test_uninstall_nonexistent(self, tmp_path):
        pm = PluginManager(str(tmp_path / "store3"))
        assert pm.uninstall("nonexistent") is False

    def test_list_installed(self, tmp_path):
        plugin_dir = tmp_path / "src-plugin3"
        plugin_dir.mkdir()
        manifest = {
            "name": "list-test", "version": "1.0.0", "type": "target",
            "description": "test", "author": "me",
        }
        (plugin_dir / "manifest.json").write_text(json.dumps(manifest))
        pm = PluginManager(str(tmp_path / "store4"))
        pm.install(str(plugin_dir))
        infos = pm.list_installed()
        names = [i.name for i in infos]
        assert "list-test" in names

    def test_load_returns_none_for_missing(self, tmp_path):
        pm = PluginManager(str(tmp_path / "store5"))
        assert pm.load("nonexistent") is None

    def test_load_returns_plugin(self, tmp_path):
        src = tmp_path / "src-plugin4"
        src.mkdir()
        manifest = {
            "name": "load-test", "version": "1.0.0", "type": "target",
            "description": "test", "author": "me", "entry": "run.py",
        }
        (src / "manifest.json").write_text(json.dumps(manifest))
        (src / "run.py").write_text("def run(args): return 'ok'")
        pm = PluginManager(str(tmp_path / "store6"))
        pm.install(str(src))
        plugin = pm.load("load-test")
        assert plugin is not None
        assert plugin.name == "load-test"
        assert plugin.entry_path is not None

    def test_install_with_bad_manifest_raises(self, tmp_path):
        src = tmp_path / "bad-plugin"
        src.mkdir()
        (src / "manifest.json").write_text("not json")
        pm = PluginManager(str(tmp_path / "store7"))
        with pytest.raises(json.JSONDecodeError):
            pm.install(str(src))

    def test_install_from_url(self, tmp_path):
        pm = PluginManager(str(tmp_path / "store8"))
        # Mock the _install_from_archive directly to avoid tarfile issues
        with patch.object(pm, '_install_from_archive', return_value=True) as mock_install:
            with patch("yuleosh.plugins.urlopen") as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = b"dummy"
                mock_urlopen.return_value.__enter__.return_value = mock_resp
                result = pm.install("https://example.com/plugin.yuleosh-plugin")
                assert result is True
                mock_install.assert_called_once()

    def test_install_from_archive_no_manifest(self, tmp_path):
        import tarfile
        archive = tmp_path / "test.tar.gz"
        with tarfile.open(str(archive), "w:gz") as tar:
            info = tarfile.TarInfo("empty.txt")
            tar.addfile(info)
        pm = PluginManager(str(tmp_path / "store9"))
        with pytest.raises(ValueError, match="manifest"):
            pm._install_from_archive(archive)


class TestPlugin:
    """Smoke tests for Plugin wrapper."""

    def test_create(self, tmp_path):
        m = PluginManifest(name="test", version="1.0.0", type="skill",
                           description="d", author="a")
        p = Plugin(m, tmp_path)
        assert p.name == "test"

    def test_entry_path_none(self):
        m = PluginManifest(name="test", version="1.0.0", type="skill",
                           description="d", author="a", entry=None)
        p = Plugin(m, Path("/tmp"))
        assert p.entry_path is None

    def test_repr(self):
        m = PluginManifest(name="my-plugin", version="2.0.0", type="skill",
                           description="d", author="a")
        p = Plugin(m, Path("/tmp"))
        r = repr(p)
        assert "my-plugin" in r
        assert "2.0.0" in r


class TestPluginInfo:
    def test_create(self):
        info = PluginInfo(name="p", version="1.0", type="skill",
                          description="d", author="a", path="/p", manifest_path="/p/manifest.json")
        assert info.name == "p"


class TestPluginRegistry:
    """Smoke tests for PluginRegistry."""

    def test_default_sources(self):
        assert len(DEFAULT_SOURCES) > 0
        assert DEFAULT_SOURCES[0].name == "yuleOSH Registry"

    def test_create_registry(self):
        reg = PluginRegistry()
        assert reg._cache_loaded is False

    def test_clear_cache(self):
        reg = PluginRegistry()
        reg._cache["test"] = RegistryPluginEntry(name="test")
        reg._cache_loaded = True
        reg.clear_cache()
        assert reg._cache == {}
        assert reg._cache_loaded is False

    def test_add_source(self):
        reg = PluginRegistry(sources=[])
        # sources=[] is falsy so __init__ uses defaults; force clear them
        reg.sources = []
        reg.add_source(RegistrySource(name="custom", url="http://example.com"))
        assert len(reg.sources) == 1
        assert reg._cache_loaded is False

    def test_remove_source(self):
        reg = PluginRegistry()
        before = len(reg.sources)
        reg.remove_source("nonexistent")
        assert len(reg.sources) == before

    def test_search_no_query(self):
        reg = PluginRegistry()
        # With no cache loaded, will try to fetch from URLs
        results = reg.search(query="")
        # Should at least have default results (might be empty if fetch fails)
        assert isinstance(results, list)

    def test_search_with_query(self):
        reg = PluginRegistry()
        results = reg.search(query="nonexistent-plugin")
        assert isinstance(results, list)

    def test_get_details_missing(self):
        reg = PluginRegistry()
        result = reg.get_details("nonexistent")
        assert result is None

    def test_download_nonexistent(self):
        reg = PluginRegistry()
        with pytest.raises(ValueError, match="不存在"):
            reg.download("nonexistent")

    def test_semver_key(self):
        key = PluginRegistry._semver_key("1.2.3")
        assert key == (1, 2, 3)

    def test_semver_key_bad(self):
        key = PluginRegistry._semver_key("abc")
        # non-digit parts are kept as-is
        assert key == ("abc",)

    def test_registry_source_to_dict(self):
        s = RegistrySource(name="test", url="http://test.com")
        d = s.to_dict()
        assert d["name"] == "test"

    def test_registry_source_from_dict(self):
        s = RegistrySource.from_dict({"name": "test", "url": "http://test.com"})
        assert s.name == "test"
        assert s.enabled is True

    def test_registry_plugin_entry(self):
        e = RegistryPluginEntry(name="test")
        assert e.name == "test"
        assert e.versions == {}


class TestPluginSandbox:
    """Smoke tests for PluginSandbox."""

    def test_safe_builtins_contains_basics(self):
        assert "int" in SAFE_BUILTINS
        assert "str" in SAFE_BUILTINS
        assert "dict" in SAFE_BUILTINS
        assert "Exception" in SAFE_BUILTINS

    def test_create_sandbox(self, tmp_path):
        sb = PluginSandbox(tmp_path)
        assert sb.plugin_dir == tmp_path.resolve()

    def test_create_sandbox_with_manifest(self, tmp_path):
        m = PluginManifest(name="test", version="1.0.0", type="skill",
                           description="d", author="a", timeout=60)
        sb = PluginSandbox(tmp_path, m)
        assert sb._timeout == 60

    def test_sandbox_default_timeout(self, tmp_path):
        sb = PluginSandbox(tmp_path)
        assert sb._timeout == 30

    def test_execute_no_entry_file(self, tmp_path):
        m = PluginManifest(name="test", version="1.0.0", type="skill",
                           description="d", author="a", entry="missing.py")
        p = Plugin(m, tmp_path)
        sb = PluginSandbox(tmp_path)
        with pytest.raises(SandboxViolation, match="无入口文件"):
            sb.execute(p, {})

    def test_restricted_import_allows_stdlib(self, tmp_path):
        m = PluginManifest(name="test", version="1.0.0", type="skill",
                           description="d", author="a")
        p = Plugin(m, tmp_path)
        sb = PluginSandbox(tmp_path)
        safe_import = sb._restricted_import(p)
        with pytest.raises(SandboxViolation, match="禁止导入"):
            safe_import("os")

    def test_restricted_import_rejects_relative(self, tmp_path):
        sb = PluginSandbox(tmp_path)
        safe_import = sb._restricted_import(Plugin(
            PluginManifest(name="t", version="1.0.0", type="skill", description="d", author="a"),
            tmp_path))
        with pytest.raises(SandboxViolation, match="相对导入"):
            safe_import("json", level=1)

    def test_block_subprocess(self):
        with pytest.raises(SandboxViolation, match="子进程"):
            PluginSandbox.block_subprocess()

    def test_build_safe_globals_key_present(self, tmp_path):
        m = PluginManifest(name="test", version="1.0.0", type="skill",
                           description="d", author="a")
        p = Plugin(m, tmp_path)
        sb = PluginSandbox(tmp_path)
        globals_ = sb._build_safe_globals(p)
        assert "__builtins__" in globals_
        assert "__yuleosh_plugin__" in globals_


class TestInitExports:
    def test_all_exported(self):
        import yuleosh.plugins
        assert hasattr(yuleosh.plugins, "PluginManager")
        assert hasattr(yuleosh.plugins, "PluginManifest")
        assert hasattr(yuleosh.plugins, "PluginInfo")
        assert hasattr(yuleosh.plugins, "Plugin")
