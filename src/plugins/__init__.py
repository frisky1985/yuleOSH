# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH Plugin System — Plugin Manager, 本地加载/发现/安装/卸载。

对标 VS Code 扩展市场模式，支持 Target / Skill / Template / Tool 四种插件类型。
所有 Plugin 通过 manifest.json 声明元数据和依赖。
"""

from __future__ import annotations

import json
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional
from urllib.request import urlopen
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class PluginManifest:
    """Plugin 元数据，对应 manifest.json 的 Python 表示。"""
    name: str
    version: str
    type: str  # target | skill | template | tool
    description: str = ""
    author: str = ""
    entry: Optional[str] = None
    min_yuleosh_version: str = "0.4.0"
    max_yuleosh_version: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    dependencies: dict[str, str] = field(default_factory=dict)
    repository: Optional[dict[str, str]] = None
    license: Optional[str] = None
    icon: Optional[str] = None
    permissions: Optional[dict[str, Any]] = None
    timeout: int = 30

    @classmethod
    def from_dict(cls, data: dict) -> "PluginManifest":
        """从字典构建，忽略未知字段。"""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_file(cls, path: str | Path) -> "PluginManifest":
        """从 manifest.json 文件加载。"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_dict(self) -> dict:
        return asdict(self)

    def validate(self) -> list[str]:
        """返回验证错误列表，空列表表示通过。"""
        errors = []
        if not self.name or not isinstance(self.name, str):
            errors.append("name: 必须是非空字符串")
        if not self.version or not isinstance(self.version, str):
            errors.append("version: 必须是非空字符串")
        if self.type not in ("target", "skill", "template", "tool"):
            errors.append(f"type: 无效类型 '{self.type}'，应为 target/skill/template/tool")
        if not self.description:
            errors.append("description: 不能为空")
        if not self.author:
            errors.append("author: 不能为空")
        if self.entry and not isinstance(self.entry, str):
            errors.append("entry: 必须为字符串或 null")
        if self.entry and not os.path.isfile(self.entry) and not os.path.isabs(self.entry):
            # 相对路径检查仅在调用方提供目录上下文时有效，此处保留作为记录
            pass
        # 版本号基本格式检查
        parts = self.version.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            errors.append(f"version: '{self.version}' 不是有效的 SemVer")
        return errors


@dataclass
class PluginInfo:
    """已安装插件的摘要信息。"""
    name: str
    version: str
    type: str
    description: str
    author: str
    path: str
    manifest_path: str


# ---------------------------------------------------------------------------
# PluginManager
# ---------------------------------------------------------------------------

class PluginManager:
    """插件管理器 — 发现、加载、安装、卸载本地插件。"""

    def __init__(self, plugins_dir: str | Path):
        self.plugins_dir = Path(plugins_dir).resolve()
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

    # ---- 发现 ----

    def discover(self) -> list[PluginManifest]:
        """扫描 plugins_dir 下所有子目录，加载合法的 manifest.json。"""
        manifests: list[PluginManifest] = []
        if not self.plugins_dir.is_dir():
            return manifests
        for entry in sorted(self.plugins_dir.iterdir()):
            if not entry.is_dir():
                continue
            manifest_path = entry / "manifest.json"
            if not manifest_path.is_file():
                continue
            try:
                manifest = PluginManifest.from_file(manifest_path)
                manifests.append(manifest)
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                # 静默跳过损坏的 manifest
                continue
        return manifests

    # ---- 加载 ----

    def load(self, name: str) -> Optional["Plugin"]:
        """加载指定名称的插件（返回 Plugin 包装对象）。"""
        manifest = self.get_manifest(name)
        if manifest is None:
            return None
        plugin_dir = self.plugins_dir / name
        return Plugin(manifest, plugin_dir)

    # ---- 安装 ----

    def install(self, source: str) -> bool:
        """从本地路径或 URL 安装插件。

        Args:
            source: 本地目录路径、.yuleosh-plugin 文件路径或下载 URL。

        Returns:
            安装成功返回 True。
        """
        source = source.strip()

        # URL 下载
        if source.startswith(("http://", "https://")):
            return self._install_from_url(source)

        # 本地文件/目录
        src_path = Path(source)

        if src_path.is_dir():
            return self._install_from_dir(src_path)

        if not src_path.exists() and not src_path.suffix:
            raise FileNotFoundError(f"安装源不存在: {source}")

        if src_path.suffix == ".yuleosh-plugin":
            if not src_path.exists():
                raise FileNotFoundError(f"安装源不存在: {source}")
            return self._install_from_archive(src_path)

        raise ValueError(f"不支持的安装源: {source} (需要目录或 .yuleosh-plugin 文件)")

    def _install_from_dir(self, src: Path) -> bool:
        manifest_file = src / "manifest.json"
        if not manifest_file.is_file():
            raise ValueError(f"缺失 manifest.json: {src}")
        manifest = PluginManifest.from_file(manifest_file)
        errors = manifest.validate()
        if errors:
            raise ValueError(f"manifest 验证失败: {'; '.join(errors)}")

        target = self.plugins_dir / manifest.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target)
        return True

    def _install_from_archive(self, archive_path: Path) -> bool:
        with tempfile.TemporaryDirectory() as tmpdir:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=tmpdir, filter='data')
            extracted = Path(tmpdir)
            # 查找 manifest.json
            manifest_candidates = list(extracted.rglob("manifest.json"))
            if not manifest_candidates:
                raise ValueError("包内未找到 manifest.json")
            manifest = PluginManifest.from_file(manifest_candidates[0])
            errors = manifest.validate()
            if errors:
                raise ValueError(f"manifest 验证失败: {'; '.join(errors)}")

            # 确定插件根目录
            plugin_root = manifest_candidates[0].parent
            target = self.plugins_dir / manifest.name
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(plugin_root, target)
        return True

    def _install_from_url(self, url: str) -> bool:
        with tempfile.NamedTemporaryFile(suffix=".yuleosh-plugin", delete=False) as tmp:
            tmp_path = tmp.name
            with urlopen(url, timeout=60) as resp:
                tmp.write(resp.read())
        try:
            return self._install_from_archive(Path(tmp_path))
        finally:
            os.unlink(tmp_path)

    # ---- 卸载 ----

    def uninstall(self, name: str) -> bool:
        """卸载指定名称的插件。"""
        plugin_dir = self.plugins_dir / name
        if not plugin_dir.is_dir():
            return False
        shutil.rmtree(plugin_dir)
        return True

    # ---- 查询 ----

    def list_installed(self) -> list[PluginInfo]:
        """列出所有已安装插件的信息。"""
        infos: list[PluginInfo] = []
        for manifest in self.discover():
            plugin_dir = self.plugins_dir / manifest.name
            infos.append(PluginInfo(
                name=manifest.name,
                version=manifest.version,
                type=manifest.type,
                description=manifest.description,
                author=manifest.author,
                path=str(plugin_dir),
                manifest_path=str(plugin_dir / "manifest.json"),
            ))
        return infos

    def get_manifest(self, name: str) -> Optional[PluginManifest]:
        """获取指定插件的 Manifest。"""
        manifest_path = self.plugins_dir / name / "manifest.json"
        if not manifest_path.is_file():
            return None
        try:
            return PluginManifest.from_file(manifest_path)
        except (json.JSONDecodeError, KeyError, TypeError):
            return None


# ---------------------------------------------------------------------------
# Plugin 运行时包装
# ---------------------------------------------------------------------------

class Plugin:
    """已加载的插件运行时包装。"""

    def __init__(self, manifest: PluginManifest, directory: Path):
        self.manifest = manifest
        self.directory = directory

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def entry_path(self) -> Optional[Path]:
        if not self.manifest.entry:
            return None
        return (self.directory / self.manifest.entry).resolve()

    def __repr__(self) -> str:
        return f"Plugin(name={self.name!r}, version={self.manifest.version!r})"


__all__ = [
    "PluginManager",
    "PluginManifest",
    "PluginInfo",
    "Plugin",
]
