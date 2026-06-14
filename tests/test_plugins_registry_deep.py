# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Deep tests for plugins/registry.py — PluginRegistry.

Target: 80%+ branch coverage.
Covers: RegistrySource, PluginVersionEntry, RegistryPluginEntry,
        PluginRegistry init, load_indexes, search, get_details,
        download, source management, internal helpers.
"""

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest


# ======================================================================
# RegistrySource
# ======================================================================

class TestRegistrySource:
    def test_to_dict(self):
        from yuleosh.plugins.registry import RegistrySource
        src = RegistrySource(name="test", url="https://example.com/index.json")
        d = src.to_dict()
        assert d["name"] == "test"
        assert d["url"] == "https://example.com/index.json"
        assert d["enabled"] is True

    def test_to_dict_disabled(self):
        from yuleosh.plugins.registry import RegistrySource
        src = RegistrySource(name="off", url="https://x.com", enabled=False)
        d = src.to_dict()
        assert d["enabled"] is False

    def test_from_dict(self):
        from yuleosh.plugins.registry import RegistrySource
        src = RegistrySource.from_dict({
            "name": "custom", "url": "https://custom.io/idx.json",
            "enabled": False
        })
        assert src.name == "custom"
        assert src.enabled is False

    def test_from_dict_defaults(self):
        from yuleosh.plugins.registry import RegistrySource
        src = RegistrySource.from_dict({})
        assert src.name == "unknown"
        assert src.url == ""
        assert src.enabled is True


# ======================================================================
# PluginVersionEntry
# ======================================================================

class TestPluginVersionEntry:
    def test_create(self):
        from yuleosh.plugins.registry import PluginVersionEntry
        entry = PluginVersionEntry(
            version="1.2.3",
            download_url="https://example.com/p.v1.2.3.tar.gz",
            sha256="abc123",
            manifest={},
        )
        assert entry.version == "1.2.3"
        assert entry.download_url.startswith("https://")

    def test_create_with_manifest(self):
        from yuleosh.plugins.registry import PluginVersionEntry
        entry = PluginVersionEntry(
            version="2.0.0",
            download_url="https://example.com/p2.tar.gz",
            sha256="def456",
            manifest={"name": "plugin2", "version": "2.0.0"},
        )
        assert entry.manifest["name"] == "plugin2"


# ======================================================================
# PluginRegistry — initialization
# ======================================================================

class TestRegistryInit:
    def test_default_sources(self):
        from yuleosh.plugins.registry import PluginRegistry, DEFAULT_SOURCES
        reg = PluginRegistry()
        assert len(reg.sources) >= 1
        assert reg.sources[0].name == "yuleOSH Registry"

    def test_custom_sources(self):
        from yuleosh.plugins.registry import PluginRegistry, RegistrySource
        src = RegistrySource(name="custom", url="https://custom.io/idx.json")
        reg = PluginRegistry(sources=[src])
        assert len(reg.sources) == 1
        assert reg.sources[0].name == "custom"


# ======================================================================
# PluginRegistry — _load_indexes
# ======================================================================

class TestLoadIndexes:
    SAMPLE_INDEX = {
        "plugins": {
            "hello-plugin": {
                "versions": {
                    "1.0.0": {
                        "download_url": "https://dl.example.com/hello-1.0.0.tar.gz",
                        "sha256": "a" * 64,
                        "manifest": {
                            "name": "hello-plugin",
                            "version": "1.0.0",
                            "type": "skill",
                            "description": "A hello plugin",
                            "tags": ["hello", "demo"],
                        },
                    },
                    "2.0.0": {
                        "download_url": "https://dl.example.com/hello-2.0.0.tar.gz",
                        "sha256": "b" * 64,
                        "manifest": {
                            "name": "hello-plugin",
                            "version": "2.0.0",
                            "type": "skill",
                            "description": "A hello plugin v2",
                            "tags": ["hello", "demo", "v2"],
                        },
                    },
                },
            },
        }
    }

    def test_load_index_success(self):
        from yuleosh.plugins.registry import PluginRegistry, RegistrySource
        src = RegistrySource(name="test", url="https://test.io/index.json", enabled=True)
        reg = PluginRegistry(sources=[src])
        with patch.object(reg, "_fetch_json", return_value=self.SAMPLE_INDEX):
            index = reg._load_indexes()
            assert "hello-plugin" in index
            assert len(index["hello-plugin"].versions) == 2

    def test_load_index_disabled_source(self):
        from yuleosh.plugins.registry import PluginRegistry, RegistrySource
        src = RegistrySource(name="disabled", url="https://off.io", enabled=False)
        reg = PluginRegistry(sources=[src])
        with patch.object(reg, "_fetch_json") as mock_fetch:
            index = reg._load_indexes()
            mock_fetch.assert_not_called()
            assert index == {}

    def test_load_index_http_error(self):
        from yuleosh.plugins.registry import PluginRegistry, RegistrySource
        from urllib.error import HTTPError
        src = RegistrySource(name="broken", url="https://broken.io", enabled=True)
        reg = PluginRegistry(sources=[src])
        with patch.object(reg, "_fetch_json", side_effect=HTTPError(
                "https://broken.io", 404, "Not Found", {}, None)):
            index = reg._load_indexes()
            assert index == {}

    def test_load_index_url_error(self):
        from yuleosh.plugins.registry import PluginRegistry, RegistrySource
        from urllib.error import URLError
        src = RegistrySource(name="offline", url="https://offline.io", enabled=True)
        reg = PluginRegistry(sources=[src])
        with patch.object(reg, "_fetch_json", side_effect=URLError("connection refused")):
            index = reg._load_indexes()
            assert index == {}

    def test_load_index_json_decode_error(self):
        from yuleosh.plugins.registry import PluginRegistry, RegistrySource
        src = RegistrySource(name="badjson", url="https://bad.io", enabled=True)
        reg = PluginRegistry(sources=[src])
        with patch.object(reg, "_fetch_json", side_effect=json.JSONDecodeError("bad", "doc", 0)):
            index = reg._load_indexes()
            assert index == {}

    def test_load_index_oserror(self):
        from yuleosh.plugins.registry import PluginRegistry, RegistrySource
        src = RegistrySource(name="ioerror", url="https://ioerr.io", enabled=True)
        reg = PluginRegistry(sources=[src])
        with patch.object(reg, "_fetch_json", side_effect=OSError("too many files")):
            index = reg._load_indexes()
            assert index == {}

    def test_load_index_cached(self):
        from yuleosh.plugins.registry import PluginRegistry, RegistrySource
        src = RegistrySource(name="test", url="https://test.io", enabled=True)
        reg = PluginRegistry(sources=[src])
        reg._cache = {"cached": "yes"}
        reg._cache_loaded = True
        index = reg._load_indexes()
        assert index == {"cached": "yes"}

    def test_load_index_unexpected_error(self):
        """If plugins_raw is not a dict, items() raises AttributeError (bug in code)."""
        from yuleosh.plugins.registry import PluginRegistry, RegistrySource
        src = RegistrySource(name="test", url="https://test.io", enabled=True)
        reg = PluginRegistry(sources=[src])
        with patch.object(reg, "_fetch_json", return_value={"plugins": "not dict"}):
            with pytest.raises(AttributeError):
                reg._load_indexes()

    def test_load_index_non_dict_index(self):
        """index is not a dict, so plugins_raw = {}."""
        from yuleosh.plugins.registry import PluginRegistry, RegistrySource
        src = RegistrySource(name="test", url="https://test.io", enabled=True)
        reg = PluginRegistry(sources=[src])
        with patch.object(reg, "_fetch_json", return_value=["not a dict"]):
            index = reg._load_indexes()
            assert index == {}

    def test_load_versions_entry_not_dict(self):
        from yuleosh.plugins.registry import PluginRegistry, RegistrySource
        src = RegistrySource(name="test", url="https://test.io", enabled=True)
        reg = PluginRegistry(sources=[src])
        bad_data = {"plugins": {"p1": {"versions": {"1.0": "not a dict"}}}}
        with patch.object(reg, "_fetch_json", return_value=bad_data):
            index = reg._load_indexes()
            assert "p1" in index
            assert "1.0" not in index["p1"].versions


# ======================================================================
# PluginRegistry — search
# ======================================================================

class TestSearch:
    def test_search_empty_query(self):
        from yuleosh.plugins.registry import PluginRegistry
        reg = PluginRegistry()
        with patch.object(reg, "_load_indexes", return_value={}):
            results = reg.search("")
            assert results == []

    def test_search_by_name(self):
        from yuleosh.plugins.registry import (PluginRegistry, RegistryPluginEntry,
                                               PluginVersionEntry)
        entry = RegistryPluginEntry(name="hello-plugin")
        entry.versions["3.0.0"] = PluginVersionEntry(
            version="3.0.0",
            download_url="https://dl.example.com/h.tar.gz",
            sha256="aaaa",
            manifest={"name": "hello-plugin", "version": "3.0.0", "type": "skill",
                      "description": "A test plugin", "tags": ["test"]},
        )
        reg = PluginRegistry()
        with patch.object(reg, "_load_indexes", return_value={"hello-plugin": entry}):
            results = reg.search("hello")
            assert len(results) == 1
            assert results[0].name == "hello-plugin"

    def test_search_by_description(self):
        from yuleosh.plugins.registry import (PluginRegistry, RegistryPluginEntry,
                                               PluginVersionEntry)
        entry = RegistryPluginEntry(name="tool")
        entry.versions["1.0.0"] = PluginVersionEntry(
            version="1.0.0",
            download_url="https://dl.example.com/t.tar.gz",
            sha256="bbbb",
            manifest={"name": "tool", "version": "1.0.0", "type": "target",
                      "description": "A helpful debugging tool", "tags": []},
        )
        reg = PluginRegistry()
        with patch.object(reg, "_load_indexes", return_value={"tool": entry}):
            results = reg.search("debugging")
            assert len(results) == 1

    def test_search_by_tag(self):
        from yuleosh.plugins.registry import (PluginRegistry, RegistryPluginEntry,
                                               PluginVersionEntry)
        entry = RegistryPluginEntry(name="demo")
        entry.versions["1.0.0"] = PluginVersionEntry(
            version="1.0.0",
            download_url="https://dl.example.com/d.tar.gz",
            sha256="cccc",
            manifest={"name": "demo", "version": "1.0.0", "type": "template",
                      "description": "Demo", "tags": ["sensor", "demo"]},
        )
        reg = PluginRegistry()
        with patch.object(reg, "_load_indexes", return_value={"demo": entry}):
            results = reg.search("sensor")
            assert len(results) == 1

    def test_search_no_versions(self):
        from yuleosh.plugins.registry import PluginRegistry, RegistryPluginEntry
        entry = RegistryPluginEntry(name="empty")
        reg = PluginRegistry()
        with patch.object(reg, "_load_indexes", return_value={"empty": entry}):
            results = reg.search("empty")
            assert results == []

    def test_search_no_match(self):
        from yuleosh.plugins.registry import (PluginRegistry, RegistryPluginEntry,
                                               PluginVersionEntry)
        entry = RegistryPluginEntry(name="other")
        entry.versions["1.0.0"] = PluginVersionEntry(
            version="1.0.0",
            download_url="https://dl.example.com/o.tar.gz",
            sha256="dddd",
            manifest={"name": "other", "version": "1.0.0", "type": "tool",
                      "description": "Other", "tags": ["other"]},
        )
        reg = PluginRegistry()
        with patch.object(reg, "_load_indexes", return_value={"other": entry}):
            results = reg.search("nonexistent")
            assert results == []


# ======================================================================
# PluginRegistry — get_details
# ======================================================================

class TestGetDetails:
    def test_not_found(self):
        from yuleosh.plugins.registry import PluginRegistry
        reg = PluginRegistry()
        with patch.object(reg, "_load_indexes", return_value={}):
            result = reg.get_details("nonexistent")
            assert result is None

    def test_no_versions(self):
        from yuleosh.plugins.registry import PluginRegistry, RegistryPluginEntry
        reg = PluginRegistry()
        with patch.object(reg, "_load_indexes",
                          return_value={"empty": RegistryPluginEntry(name="empty")}):
            result = reg.get_details("empty")
            assert result is None

    def test_found(self):
        from yuleosh.plugins.registry import (PluginRegistry, RegistryPluginEntry,
                                               PluginVersionEntry)
        entry = RegistryPluginEntry(name="p1")
        entry.versions["2.0.0"] = PluginVersionEntry(
            version="2.0.0",
            download_url="https://dl.example.com/p1.tar.gz",
            sha256="eeee",
            manifest={"name": "p1", "type": "skill", "version": "2.0.0"},
        )
        reg = PluginRegistry()
        with patch.object(reg, "_load_indexes", return_value={"p1": entry}):
            result = reg.get_details("p1")
            assert result is not None
            assert result.name == "p1"


# ======================================================================
# PluginRegistry — download
# ======================================================================

class TestDownload:
    def test_plugin_not_found(self):
        from yuleosh.plugins.registry import PluginRegistry
        reg = PluginRegistry()
        with patch.object(reg, "_load_indexes", return_value={}):
            with pytest.raises(ValueError, match=".*不存在"):
                reg.download("nonexistent")

    def test_version_not_found(self):
        from yuleosh.plugins.registry import (PluginRegistry, RegistryPluginEntry,
                                               PluginVersionEntry)
        entry = RegistryPluginEntry(name="p1")
        entry.versions["1.0.0"] = PluginVersionEntry(
            version="1.0.0",
            download_url="https://dl.example.com/p1.tar.gz",
            sha256="ffff",
            manifest={"name": "p1"},
        )
        reg = PluginRegistry()
        with patch.object(reg, "_load_indexes", return_value={"p1": entry}):
            with pytest.raises(ValueError, match=".*不存在"):
                reg.download("p1", version="99.99.99")

    def test_download_success(self):
        from yuleosh.plugins.registry import (PluginRegistry, RegistryPluginEntry,
                                               PluginVersionEntry)
        content = b"plugin package data"
        sha256 = hashlib.sha256(content).hexdigest()
        entry = RegistryPluginEntry(name="p1")
        entry.versions["1.0.0"] = PluginVersionEntry(
            version="1.0.0",
            download_url="https://dl.example.com/p1.tar.gz",
            sha256=sha256,
            manifest={"name": "p1"},
        )
        reg = PluginRegistry()
        with patch.object(reg, "_load_indexes", return_value={"p1": entry}):
            with patch.object(reg, "_fetch_bytes", return_value=content):
                local_path = reg.download("p1")
                assert isinstance(local_path, str)
                assert Path(local_path).exists()
                data = Path(local_path).read_bytes()
                assert data == content
                Path(local_path).unlink()

    def test_download_sha256_mismatch(self):
        from yuleosh.plugins.registry import (PluginRegistry, RegistryPluginEntry,
                                               PluginVersionEntry)
        content = b"package data"
        entry = RegistryPluginEntry(name="p1")
        entry.versions["1.0.0"] = PluginVersionEntry(
            version="1.0.0",
            download_url="https://dl.example.com/p1.tar.gz",
            sha256="wrong_sha256_hash_here",
            manifest={"name": "p1"},
        )
        reg = PluginRegistry()
        with patch.object(reg, "_load_indexes", return_value={"p1": entry}):
            with patch.object(reg, "_fetch_bytes", return_value=content):
                with pytest.raises(ValueError, match="SHA256"):
                    reg.download("p1")

    def test_download_specific_version(self):
        from yuleosh.plugins.registry import (PluginRegistry, RegistryPluginEntry,
                                               PluginVersionEntry)
        content = b"v2 data"
        sha256 = hashlib.sha256(content).hexdigest()
        entry = RegistryPluginEntry(name="p1")
        entry.versions["1.0.0"] = PluginVersionEntry(
            version="1.0.0",
            download_url="https://dl.example.com/v1.tar.gz",
            sha256="v1_hash",
            manifest={},
        )
        entry.versions["2.0.0"] = PluginVersionEntry(
            version="2.0.0",
            download_url="https://dl.example.com/v2.tar.gz",
            sha256=sha256,
            manifest={},
        )
        reg = PluginRegistry()
        with patch.object(reg, "_load_indexes", return_value={"p1": entry}):
            with patch.object(reg, "_fetch_bytes", return_value=content):
                local_path = reg.download("p1", version="2.0.0")
                assert Path(local_path).exists()
                assert Path(local_path).read_bytes() == content
                Path(local_path).unlink()


# ======================================================================
# PluginRegistry — source management
# ======================================================================

class TestSourceManagement:
    def test_add_source(self):
        from yuleosh.plugins.registry import PluginRegistry, RegistrySource
        reg = PluginRegistry()
        count_before = len(reg.sources)
        reg.add_source(RegistrySource(name="new", url="https://new.io"))
        assert len(reg.sources) == count_before + 1
        assert reg._cache_loaded is False

    def test_remove_source(self):
        from yuleosh.plugins.registry import PluginRegistry, RegistrySource
        reg = PluginRegistry()
        reg.add_source(RegistrySource(name="temp", url="https://temp.io"))
        assert reg.remove_source("temp") is True
        assert reg.remove_source("nonexistent") is False

    def test_clear_cache(self):
        from yuleosh.plugins.registry import PluginRegistry
        reg = PluginRegistry()
        reg._cache = {"old": "data"}
        reg._cache_loaded = True
        reg.clear_cache()
        assert reg._cache == {}
        assert reg._cache_loaded is False


# ======================================================================
# PluginRegistry — internal helpers
# ======================================================================

class TestInternalHelpers:
    def test_fetch_json(self):
        from yuleosh.plugins.registry import PluginRegistry
        with patch("yuleosh.plugins.registry.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"key": "value"}'
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp
            result = PluginRegistry._fetch_json("https://example.com/data.json")
            assert result == {"key": "value"}

    def test_fetch_json_http_error(self):
        from yuleosh.plugins.registry import PluginRegistry
        from urllib.error import HTTPError
        with patch("yuleosh.plugins.registry.urlopen",
                   side_effect=HTTPError("url", 500, "Error", {}, None)):
            with pytest.raises(HTTPError):
                PluginRegistry._fetch_json("https://bad.com/data.json")

    def test_fetch_bytes(self):
        from yuleosh.plugins.registry import PluginRegistry
        with patch("yuleosh.plugins.registry.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"binary data"
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp
            result = PluginRegistry._fetch_bytes("https://example.com/data.bin")
            assert result == b"binary data"

    def test_semver_key_normal(self):
        from yuleosh.plugins.registry import PluginRegistry
        key = PluginRegistry._semver_key("1.2.3")
        assert key == (1, 2, 3)

    def test_semver_key_mixed(self):
        from yuleosh.plugins.registry import PluginRegistry
        key = PluginRegistry._semver_key("1.2.3-alpha")
        assert key[0] == 1
        assert key[1] == 2

    def test_semver_key_invalid(self):
        from yuleosh.plugins.registry import PluginRegistry
        key = PluginRegistry._semver_key("not-semver")
        # not-semver.split('.') gives ['not-semver'] and it's not a digit so returns as-is
        assert isinstance(key, tuple)

    def test_semver_key_non_numeric(self):
        from yuleosh.plugins.registry import PluginRegistry
        key = PluginRegistry._semver_key("v1.2.3")
        assert isinstance(key, tuple)
