# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for yuleOSH Plugin System — PluginManager, PluginSandbox, PluginRegistry, SkillManager.

Running: pytest tests/test_plugins.py -v
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from yuleosh.plugins import PluginManager, PluginManifest, PluginInfo, Plugin
from yuleosh.plugins.sandbox import PluginSandbox, SandboxViolation
from yuleosh.plugins.registry import PluginRegistry, RegistrySource
from yuleosh.skills import SkillManager, SkillManifest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PLUGIN_FIXTURES = FIXTURES_DIR / "plugins"
REGISTRY_FIXTURE = FIXTURES_DIR / "registry" / "index.json"
ARCHIVE_FIXTURE = FIXTURES_DIR / "sample-target-plugin-1.0.0.yuleosh-plugin"


@pytest.fixture
def temp_plugins_dir():
    """提供一个临时插件目录。"""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def sample_manifest():
    return PluginManifest.from_file(PLUGIN_FIXTURES / "sample-target-plugin" / "manifest.json")


@pytest.fixture
def registry_with_local_source():
    """使用本地 JSON 文件作为注册表源的 Registry。"""
    source = RegistrySource(
        name="test-source",
        url=f"file://{REGISTRY_FIXTURE}",
        enabled=True,
    )
    reg = PluginRegistry(sources=[source])
    return reg


# ---------------------------------------------------------------------------
# PluginManifest 解析与验证
# ---------------------------------------------------------------------------

class TestPluginManifest:
    def test_from_file_valid(self):
        """从有效的 manifest.json 文件加载。"""
        path = PLUGIN_FIXTURES / "sample-target-plugin" / "manifest.json"
        manifest = PluginManifest.from_file(path)
        assert manifest.name == "sample-target-plugin"
        assert manifest.version == "1.0.0"
        assert manifest.type == "target"
        assert manifest.author == "yuleOSH Test"
        assert manifest.tags == ["esp32", "freertos", "sample"]

    def test_from_dict(self):
        """从字典构建。"""
        data = {
            "name": "test-plugin",
            "version": "2.0.0",
            "type": "tool",
            "description": "Test tool plugin",
            "author": "tester",
            "tags": ["test"],
            "timeout": 60,
        }
        manifest = PluginManifest.from_dict(data)
        assert manifest.name == "test-plugin"
        assert manifest.type == "tool"
        assert manifest.timeout == 60

    def test_from_dict_ignores_unknown(self):
        """忽略未知字段。"""
        data = {
            "name": "p1",
            "version": "1.0.0",
            "type": "target",
            "description": "desc",
            "author": "a",
            "unknown_field": "should_be_ignored",
        }
        m = PluginManifest.from_dict(data)
        assert m.name == "p1"
        assert not hasattr(m, "unknown_field")

    def test_validate_valid(self, sample_manifest):
        """有效 manifest 验证通过。"""
        errors = sample_manifest.validate()
        assert errors == []

    def test_validate_missing_fields(self):
        """缺失必需字段的验证失败。"""
        manifest = PluginManifest(
            name="",
            version="",
            type="invalid",
            description="",
            author="",
        )
        errors = manifest.validate()
        assert len(errors) >= 4  # name, version, type, description, author 中至少4个错误

    def test_validate_invalid_version(self):
        """版本号格式错误。"""
        manifest = PluginManifest(
            name="test",
            version="abc",
            type="target",
            description="test",
            author="tester",
        )
        errors = manifest.validate()
        version_errors = [e for e in errors if "version" in e and "SemVer" in e]
        assert len(version_errors) >= 1

    def test_to_dict_roundtrip(self, sample_manifest):
        """to_dict / from_dict 往返一致。"""
        d = sample_manifest.to_dict()
        restored = PluginManifest.from_dict(d)
        assert restored.name == sample_manifest.name
        assert restored.version == sample_manifest.version
        assert restored.type == sample_manifest.type


# ---------------------------------------------------------------------------
# PluginManager — 发现
# ---------------------------------------------------------------------------

class TestPluginManagerDiscovery:
    def test_discover_finds_valid_plugins(self, temp_plugins_dir):
        """将 fixture 复制到临时目录后发现插件。"""
        dest = temp_plugins_dir / "sample-target-plugin"
        shutil.copytree(PLUGIN_FIXTURES / "sample-target-plugin", dest)
        pm = PluginManager(temp_plugins_dir)
        manifests = pm.discover()
        assert len(manifests) == 1
        assert manifests[0].name == "sample-target-plugin"

    def test_discover_ignores_invalid(self, temp_plugins_dir):
        """无效 manifest 的插件被跳过。"""
        shutil.copytree(PLUGIN_FIXTURES / "sample-target-plugin", temp_plugins_dir / "good")
        shutil.copytree(PLUGIN_FIXTURES / "invalid-plugin", temp_plugins_dir / "bad")
        pm = PluginManager(temp_plugins_dir)
        manifests = pm.discover()
        names = [m.name for m in manifests]
        assert "sample-target-plugin" in names
        assert "bad" not in names

    def test_discover_empty_dir(self, temp_plugins_dir):
        """空目录发现为空列表。"""
        pm = PluginManager(temp_plugins_dir)
        assert pm.discover() == []

    def test_discover_non_existent_dir(self):
        """不存在的目录发现为空列表。"""
        pm = PluginManager("/tmp/non_existent_xyz_12345")
        assert pm.discover() == []


# ---------------------------------------------------------------------------
# PluginManager — 加载与查询
# ---------------------------------------------------------------------------

class TestPluginManagerLoad:
    def test_load_existing(self, temp_plugins_dir):
        """加载已存在的插件。"""
        shutil.copytree(PLUGIN_FIXTURES / "sample-target-plugin", temp_plugins_dir / "sample-target-plugin")
        pm = PluginManager(temp_plugins_dir)
        plugin = pm.load("sample-target-plugin")
        assert plugin is not None
        assert plugin.name == "sample-target-plugin"
        assert isinstance(plugin, Plugin)

    def test_load_non_existent(self, temp_plugins_dir):
        """加载不存在的插件返回 None。"""
        pm = PluginManager(temp_plugins_dir)
        assert pm.load("non-existent-plugin") is None

    def test_get_manifest(self, temp_plugins_dir):
        """获取已安装插件的 manifest。"""
        shutil.copytree(PLUGIN_FIXTURES / "sample-target-plugin", temp_plugins_dir / "sample-target-plugin")
        pm = PluginManager(temp_plugins_dir)
        manifest = pm.get_manifest("sample-target-plugin")
        assert manifest is not None
        assert manifest.name == "sample-target-plugin"

    def test_get_manifest_not_found(self, temp_plugins_dir):
        """不存在的插件返回 None。"""
        pm = PluginManager(temp_plugins_dir)
        assert pm.get_manifest("non-existent") is None

    def test_list_installed(self, temp_plugins_dir):
        """列出已安装插件。"""
        shutil.copytree(PLUGIN_FIXTURES / "sample-target-plugin", temp_plugins_dir / "sample-target-plugin")
        pm = PluginManager(temp_plugins_dir)
        infos = pm.list_installed()
        assert len(infos) == 1
        info = infos[0]
        assert isinstance(info, PluginInfo)
        assert info.name == "sample-target-plugin"
        assert info.version == "1.0.0"
        assert info.type == "target"


# ---------------------------------------------------------------------------
# PluginManager — 安装与卸载
# ---------------------------------------------------------------------------

class TestPluginManagerInstall:
    def test_install_from_directory(self, temp_plugins_dir):
        """从目录安装插件。"""
        pm = PluginManager(temp_plugins_dir)
        result = pm.install(str(PLUGIN_FIXTURES / "sample-target-plugin"))
        assert result is True
        assert (temp_plugins_dir / "sample-target-plugin" / "manifest.json").exists()

    def test_install_missing_manifest(self, temp_plugins_dir):
        """缺少 manifest.json 的目录安装失败。"""
        with tempfile.TemporaryDirectory() as tmp:
            pm = PluginManager(temp_plugins_dir)
            with pytest.raises(ValueError, match="缺失 manifest.json"):
                pm.install(tmp)

    def test_install_from_archive(self, temp_plugins_dir):
        """从 .yuleosh-plugin 存档安装。"""
        assert ARCHIVE_FIXTURE.exists(), f"Archive fixture not found: {ARCHIVE_FIXTURE}"
        pm = PluginManager(temp_plugins_dir)
        result = pm.install(str(ARCHIVE_FIXTURE))
        assert result is True
        assert (temp_plugins_dir / "sample-target-plugin" / "manifest.json").exists()
        assert (temp_plugins_dir / "sample-target-plugin" / "main.py").exists()

    def test_install_replace_existing(self, temp_plugins_dir):
        """安装已存在的插件会覆盖。"""
        pm = PluginManager(temp_plugins_dir)
        pm.install(str(PLUGIN_FIXTURES / "sample-target-plugin"))
        old_info = pm.list_installed()
        # 再次安装应该成功（覆盖）
        result = pm.install(str(PLUGIN_FIXTURES / "sample-target-plugin"))
        assert result is True
        assert len(pm.list_installed()) == 1

    def test_install_invalid_source(self, temp_plugins_dir):
        """不支持的源路径。"""
        pm = PluginManager(temp_plugins_dir)
        with pytest.raises(ValueError, match="不支持的安装源"):
            pm.install("unsupported.txt")


class TestPluginManagerUninstall:
    def test_uninstall_existing(self, temp_plugins_dir):
        """卸载已安装的插件。"""
        pm = PluginManager(temp_plugins_dir)
        pm.install(str(PLUGIN_FIXTURES / "sample-target-plugin"))
        assert len(pm.list_installed()) == 1
        result = pm.uninstall("sample-target-plugin")
        assert result is True
        assert len(pm.list_installed()) == 0

    def test_uninstall_non_existent(self, temp_plugins_dir):
        """卸载不存在的插件返回 False。"""
        pm = PluginManager(temp_plugins_dir)
        assert pm.uninstall("non-existent") is False


# ---------------------------------------------------------------------------
# PluginSandbox — 安全执行
# ---------------------------------------------------------------------------

class TestPluginSandbox:
    def test_execute_valid_plugin(self, temp_plugins_dir):
        """执行有效插件的入口函数。"""
        shutil.copytree(PLUGIN_FIXTURES / "sample-target-plugin", temp_plugins_dir / "sample-target-plugin")
        pm = PluginManager(temp_plugins_dir)
        plugin = pm.load("sample-target-plugin")
        assert plugin is not None
        sandbox = PluginSandbox(plugin.directory, plugin.manifest)
        result = sandbox.execute(plugin, {"port": "/dev/ttyUSB0", "baud": 115200})
        assert result is not None
        assert result["status"] == "ok"
        assert result["port"] == "/dev/ttyUSB0"

    def test_execute_without_entry(self, temp_plugins_dir):
        """无入口文件的插件执行失败。"""
        plugin_dir = temp_plugins_dir / "no-entry"
        plugin_dir.mkdir()
        # 只有 manifest 但没有 entry 文件
        manifest = PluginManifest(
            name="no-entry",
            version="1.0.0",
            type="tool",
            description="no entry plugin",
            author="test",
            entry="nonexistent.py",
        )
        plugin = Plugin(manifest, plugin_dir)
        sandbox = PluginSandbox(plugin_dir, manifest)
        with pytest.raises(SandboxViolation):
            sandbox.execute(plugin, {})

    def test_sandbox_timeout(self, temp_plugins_dir):
        """超时控制。"""
        # 创建一个超时插件
        plugin_dir = temp_plugins_dir / "slow-plugin"
        plugin_dir.mkdir()
        main_py = plugin_dir / "main.py"
        main_py.write_text("""
import time
def run(args):
    time.sleep(100)
    return {"status": "done"}
""")
        manifest = PluginManifest(
            name="slow-plugin",
            version="1.0.0",
            type="tool",
            description="slow plugin",
            author="test",
            entry="main.py",
            timeout=1,  # 1秒超时
        )
        plugin = Plugin(manifest, plugin_dir)
        sandbox = PluginSandbox(plugin_dir, manifest)
        with pytest.raises(TimeoutError):
            sandbox.execute(plugin, {})

    def test_restricted_open_write_outside(self, temp_plugins_dir):
        """沙箱限制写入沙箱外文件。"""
        plugin_dir = temp_plugins_dir / "escape-plugin"
        plugin_dir.mkdir()
        main_py = plugin_dir / "main.py"
        main_py.write_text("""
def run(args):
    with open("/tmp/escaped.txt", "w") as f:
        f.write("pwned")
    return {"status": "ok"}
""")
        manifest = PluginManifest(
            name="escape-plugin",
            version="1.0.0",
            type="tool",
            description="escape attempt",
            author="test",
            entry="main.py",
        )
        plugin = Plugin(manifest, plugin_dir)
        sandbox = PluginSandbox(plugin_dir, manifest)

        with pytest.raises(SandboxViolation, match="禁止写入"):
            sandbox.execute(plugin, {})

    def test_restricted_import(self, temp_plugins_dir):
        """沙箱限制导入黑名单模块。"""
        plugin_dir = temp_plugins_dir / "import-plugin"
        plugin_dir.mkdir()
        main_py = plugin_dir / "main.py"
        main_py.write_text("""
import os
def run(args):
    return {"os": os.name}
""")
        manifest = PluginManifest(
            name="import-plugin",
            version="1.0.0",
            type="tool",
            description="import test",
            author="test",
            entry="main.py",
        )
        plugin = Plugin(manifest, plugin_dir)
        sandbox = PluginSandbox(plugin_dir, manifest)
        with pytest.raises(SandboxViolation, match="禁止导入"):
            sandbox.execute(plugin, {})


# ---------------------------------------------------------------------------
# PluginRegistry — 搜索与查询
# ---------------------------------------------------------------------------

class TestPluginRegistry:
    def test_search_local_index(self, registry_with_local_source):
        """从本地索引文件搜索。"""
        results = registry_with_local_source.search()
        names = {m.name for m in results}
        assert "esp32-blink" in names
        assert "autosar-helper" in names
        assert "zephyr-template" in names

    def test_search_with_query(self, registry_with_local_source):
        """按查询词搜索。"""
        results = registry_with_local_source.search("esp32")
        assert len(results) >= 1
        assert all("esp32" in m.name.lower() or "esp32" in m.description.lower()
                   or any("esp32" in t.lower() for t in m.tags)
                   for m in results)

    def test_search_with_partial_query(self, registry_with_local_source):
        """部分匹配搜索。"""
        results = registry_with_local_source.search("auto")
        assert len(results) >= 1
        assert "autosar-helper" in [m.name for m in results]

    def test_search_no_match(self, registry_with_local_source):
        """无匹配时返回空列表。"""
        results = registry_with_local_source.search("xyznonexistent")
        assert results == []

    def test_get_details(self, registry_with_local_source):
        """获取插件详情。"""
        manifest = registry_with_local_source.get_details("esp32-blink")
        assert manifest is not None
        assert manifest.name == "esp32-blink"
        assert manifest.version == "1.0.0"  # 最新版

    def test_get_details_not_found(self, registry_with_local_source):
        """不存在的插件返回 None。"""
        assert registry_with_local_source.get_details("non-existent") is None

    def test_add_remove_source(self):
        """添加和移除注册表源。"""
        reg = PluginRegistry()
        initial_count = len(reg.sources)
        reg.add_source(RegistrySource(name="custom", url="https://example.com/index.json"))
        assert len(reg.sources) == initial_count + 1
        reg.remove_source("custom")
        assert len(reg.sources) == initial_count


# ---------------------------------------------------------------------------
# SkillManager
# ---------------------------------------------------------------------------

class TestSkillManager:
    def test_discover_skills(self, temp_plugins_dir):
        """发现 Skill 类型插件。"""
        skills_dir = temp_plugins_dir / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        target = skills_dir / "sample-skill"
        shutil.copytree(PLUGIN_FIXTURES / "sample-skill", target, dirs_exist_ok=True)
        pm = PluginManager(temp_plugins_dir)
        sm = SkillManager(skills_dir, pm)
        skills = sm.discover_skills()
        assert len(skills) >= 1
        skill = skills[0]
        assert skill.type == "skill"
        assert skill.name == "sample-skill"

    def test_skill_manifest_workflow(self):
        """Skill manifest 包含 workflow。"""
        manifest = SkillManifest.from_file(PLUGIN_FIXTURES / "sample-skill" / "manifest.json")
        assert manifest.workflow is not None
        assert manifest.workflow.version == "1"
        assert len(manifest.workflow.steps) == 1
        assert manifest.workflow.steps[0].id == "step-1"
        assert manifest.workflow.steps[0].plugin == "sample-target-plugin"

    def test_skill_to_plugin_roundtrip(self):
        """SkillManifest 继承 PluginManifest 的字段。"""
        manifest = SkillManifest.from_file(PLUGIN_FIXTURES / "sample-skill" / "manifest.json")
        assert manifest.version == "0.1.0"
        assert manifest.author == "yuleOSH Test"
        assert manifest.min_yuleosh_version == "0.4.0"


# ---------------------------------------------------------------------------
# 集成测试
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_install_discover_load_execute(self, temp_plugins_dir):
        """完整流程：安装 → 发现 → 加载 → 执行。"""
        pm = PluginManager(temp_plugins_dir)

        # 安装
        pm.install(str(PLUGIN_FIXTURES / "sample-target-plugin"))

        # 发现
        manifests = pm.discover()
        assert len(manifests) == 1

        # 加载
        plugin = pm.load("sample-target-plugin")
        assert plugin is not None

        # 执行
        sandbox = PluginSandbox(plugin.directory, plugin.manifest)
        result = sandbox.execute(plugin, {"port": "COM3", "baud": 9600})
        assert result["status"] == "ok"
        assert result["port"] == "COM3"

    def test_install_uninstall_reinstall(self, temp_plugins_dir):
        """安装 → 卸载 → 重新安装。"""
        pm = PluginManager(temp_plugins_dir)

        pm.install(str(PLUGIN_FIXTURES / "sample-target-plugin"))
        assert len(pm.list_installed()) == 1

        pm.uninstall("sample-target-plugin")
        assert len(pm.list_installed()) == 0

        pm.install(str(PLUGIN_FIXTURES / "sample-target-plugin"))
        assert len(pm.list_installed()) == 1

    def test_registry_search_and_discover(self, registry_with_local_source):
        """注册表搜索与本地发现有不同结果。"""
        pm = PluginManager("/tmp/empty_plugins_test_dir")
        os.makedirs("/tmp/empty_plugins_test_dir", exist_ok=True)
        try:
            local_count = len(pm.discover())
            registry_count = len(registry_with_local_source.search())
            assert registry_count >= local_count  # 注册表应有更多结果
        finally:
            shutil.rmtree("/tmp/empty_plugins_test_dir", ignore_errors=True)
