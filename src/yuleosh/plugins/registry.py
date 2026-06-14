# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH Plugin Registry — 插件市场注册表。

从 GitHub Releases / 自定义源拉取插件索引。
支持搜索、获取详情、下载安装包。
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

from . import PluginManifest


# ---------------------------------------------------------------------------
# Registry 数据模型
# ---------------------------------------------------------------------------

@dataclass
class RegistrySource:
    """注册表源配置。"""
    name: str
    url: str  # 指向 index.json 的 URL
    enabled: bool = True

    def to_dict(self) -> dict:
        return {"name": self.name, "url": self.url, "enabled": self.enabled}

    @classmethod
    def from_dict(cls, data: dict) -> "RegistrySource":
        return cls(
            name=data.get("name", "unknown"),
            url=data.get("url", ""),
            enabled=data.get("enabled", True),
        )


@dataclass
class PluginVersionEntry:
    """插件版本条目（来源于注册表索引）。"""
    version: str
    download_url: str
    sha256: str
    manifest: dict[str, Any]


@dataclass
class RegistryPluginEntry:
    """插件在注册表中的条目。"""
    name: str
    versions: dict[str, PluginVersionEntry] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 默认注册表源
# ---------------------------------------------------------------------------

DEFAULT_SOURCES: list[RegistrySource] = [
    RegistrySource(
        name="yuleOSH Registry",
        url="https://github.com/frisky1985/yuleOSH/releases/plugins/index.json",
        enabled=True,
    ),
]


# ---------------------------------------------------------------------------
# PluginRegistry
# ---------------------------------------------------------------------------

class PluginRegistry:
    """Plugin 市场注册表 — 从远程源发现和下载插件。"""

    def __init__(self, sources: Optional[list[RegistrySource]] = None):
        self.sources = sources or [
            RegistrySource(name=s.name, url=s.url, enabled=s.enabled)
            for s in DEFAULT_SOURCES
        ]
        self._cache: dict[str, RegistryPluginEntry] = {}
        self._cache_loaded = False

    # ---- 索引加载 ----

    def _load_indexes(self) -> dict[str, RegistryPluginEntry]:
        """从所有启用的源加载索引并合并。"""
        if self._cache_loaded:
            return self._cache

        merged: dict[str, RegistryPluginEntry] = {}

        for source in self.sources:
            if not source.enabled:
                continue
            try:
                index = self._fetch_json(source.url, timeout=15)
                plugins_raw = index.get("plugins", {}) if isinstance(index, dict) else {}
                for name, entry in plugins_raw.items():
                    if name not in merged:
                        merged[name] = RegistryPluginEntry(name=name)
                    versions = entry.get("versions", {}) if isinstance(entry, dict) else {}
                    for ver, ver_data in versions.items():
                        if isinstance(ver_data, dict):
                            merged[name].versions[ver] = PluginVersionEntry(
                                version=ver,
                                download_url=ver_data.get("download_url", ""),
                                sha256=ver_data.get("sha256", ""),
                                manifest=ver_data.get("manifest", {}),
                            )
            except (HTTPError, URLError, json.JSONDecodeError, OSError) as exc:
                # 单个源失败不阻断其他源
                continue

        self._cache = merged
        self._cache_loaded = True
        return merged

    # ---- 搜索 ----

    def search(self, query: str = "") -> list[PluginManifest]:
        """搜索插件。

        Args:
            query: 搜索关键词（匹配 name, tags, description）。空字符串返回全部。

        Returns:
            匹配的 PluginManifest 列表（最新版本）。
        """
        index = self._load_indexes()
        query_lower = query.lower().strip()
        results: list[PluginManifest] = []

        for name, entry in index.items():
            if not entry.versions:
                continue
            # 取最新版本
            latest_ver = sorted(entry.versions.keys(), key=self._semver_key, reverse=True)[0]
            ver_entry = entry.versions[latest_ver]
            manifest_data = ver_entry.manifest
            manifest = PluginManifest.from_dict(manifest_data)

            if not query_lower:
                results.append(manifest)
                continue

            # 搜索匹配
            if query_lower in manifest.name.lower():
                results.append(manifest)
                continue
            if query_lower in manifest.description.lower():
                results.append(manifest)
                continue
            if any(query_lower in t.lower() for t in manifest.tags):
                results.append(manifest)
                continue

        return results

    # ---- 详情 ----

    def get_details(self, name: str) -> Optional[PluginManifest]:
        """获取指定插件的最新版本 Manifest。"""
        index = self._load_indexes()
        entry = index.get(name)
        if not entry or not entry.versions:
            return None
        latest_ver = sorted(entry.versions.keys(), key=self._semver_key, reverse=True)[0]
        ver_entry = entry.versions[latest_ver]
        return PluginManifest.from_dict(ver_entry.manifest)

    # ---- 下载 ----

    def download(self, name: str, version: str = "") -> str:
        """下载插件包到临时文件，返回本地路径。

        Args:
            name: 插件名称。
            version: 版本号，空字符串表示最新版。

        Returns:
            下载到的本地临时文件路径。
        """
        index = self._load_indexes()
        entry = index.get(name)
        if not entry or not entry.versions:
            raise ValueError(f"插件 '{name}' 在注册表中不存在")

        if not version:
            version = sorted(entry.versions.keys(), key=self._semver_key, reverse=True)[0]

        ver_entry = entry.versions.get(version)
        if not ver_entry:
            raise ValueError(f"插件 '{name}' 版本 '{version}' 不存在")

        download_url = ver_entry.download_url
        expected_sha = ver_entry.sha256

        # 下载
        data = self._fetch_bytes(download_url, timeout=120)

        # SHA256 校验
        if expected_sha:
            actual_sha = hashlib.sha256(data).hexdigest()
            if actual_sha != expected_sha:
                raise ValueError(
                    f"SHA256 校验失败: 期望 {expected_sha}, 实际 {actual_sha}"
                )

        # 写入临时文件
        suffix = ".yuleosh-plugin"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            return tmp.name

    # ---- 注册表源管理 ----

    def add_source(self, source: RegistrySource) -> None:
        """添加自定义注册表源。"""
        self.sources.append(source)
        self._cache_loaded = False

    def remove_source(self, name: str) -> bool:
        """移除注册表源。"""
        before = len(self.sources)
        self.sources = [s for s in self.sources if s.name != name]
        self._cache_loaded = False
        return len(self.sources) < before

    def clear_cache(self) -> None:
        """清除索引缓存，下次搜索时重新加载。"""
        self._cache_loaded = False
        self._cache.clear()

    # ---- 内部工具方法 ----

    @staticmethod
    def _fetch_json(url: str, timeout: int = 15) -> Any:
        """HTTP GET 获取 JSON。"""
        req = Request(url, headers={"User-Agent": "yuleOSH/0.4.0"})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _fetch_bytes(url: str, timeout: int = 120) -> bytes:
        """HTTP GET 获取二进制数据。"""
        req = Request(url, headers={"User-Agent": "yuleOSH/0.4.0"})
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()

    @staticmethod
    def _semver_key(ver: str) -> tuple:
        """将 SemVer 转换为可排序的元组。"""
        parts = ver.split(".")
        try:
            return tuple(int(p) if p.isdigit() else p for p in parts)
        except ValueError:
            return (0, 0, 0)


__all__ = [
    "PluginRegistry",
    "RegistrySource",
    "RegistryPluginEntry",
    "PluginVersionEntry",
    "DEFAULT_SOURCES",
]
