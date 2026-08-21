# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Embedding provider — 文本向量化接口（EI-M3C.1）。

统一 ``embed(texts) -> list[list[float]]`` 接口，默认 bge-m3/nomic 本地
Ollama 推理，API 模式（OpenAI 兼容）可配置切换。

设计:
- ``OllamaEmbeddingProvider``: 本地 Ollama 嵌入（默认模型 nomic-embed-text，
  可配置 bge-m3 等），无网络依赖、数据不出域（客户需求文档安全）。
- ``HttpEmbeddingProvider``: OpenAI 兼容 /embedding API（fallback 配置）。
- 无 Ollama/不可用时 ``embed`` 抛 EmbeddingUnavailableError，调用方降级
  FTS5 仍可用（EI-M3C.4 优雅降级）。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Protocol

log = logging.getLogger("kb.embedding")

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "nomic-embed-text"  # 轻量本地嵌入（274MB，CPU 可跑）
DEFAULT_API_MODEL = "text-embedding-3-small"


class EmbeddingUnavailableError(Exception):
    """嵌入服务不可用（调用方应降级 FTS5）。"""


class EmbeddingProvider(Protocol):
    """文本向量化接口（EI-M3C.1）。"""

    name: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        """把文本列表转成向量列表（同序）。"""
        ...

    def available(self) -> bool:
        """服务是否可用（不可用时调用方降级）。"""
        ...


class OllamaEmbeddingProvider:
    """Ollama 本地嵌入（默认，数据不出域）。"""

    name = "ollama"

    def __init__(self, model: str | None = None,
                 base_url: str | None = None,
                 timeout_s: int = 60):
        self.model = model or os.environ.get(
            "YULEOSH_EMBED_MODEL", DEFAULT_OLLAMA_MODEL)
        self.base_url = base_url or os.environ.get(
            "OLLAMA_HOST", DEFAULT_OLLAMA_URL)
        self.timeout_s = timeout_s

    def available(self) -> bool:
        if not shutil.which("ollama") and not self._http_ok():
            return False
        return True

    def _http_ok(self) -> bool:
        try:
            with urllib.request.urlopen(
                f"{self.base_url}/api/tags", timeout=3,
            ) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001
            return False

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for text in texts:
            # 新版 Ollama /api/embed 用 input 字段（旧版 prompt 兼容已移除）
            payload = json.dumps({
                "model": self.model,
                "input": text,
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/embed",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(
                    req, timeout=self.timeout_s,
                ) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                emb = data.get("embeddings")
                if not emb or not isinstance(emb, list) or not emb[0]:
                    raise EmbeddingUnavailableError(
                        f"Ollama /api/embed 无 embeddings (model={self.model})")
                vectors.append(list(emb[0]))
            except urllib.error.URLError as e:
                raise EmbeddingUnavailableError(
                    f"Ollama embed failed: {e} (is 'ollama serve' running?)"
                ) from e
        return vectors


class HttpEmbeddingProvider:
    """OpenAI 兼容 /embedding API（fallback 配置，默认不用）。"""

    name = "http"

    def __init__(self, api_key: str | None = None,
                 model: str | None = None,
                 url: str = "https://api.openai.com/v1/embeddings",
                 timeout_s: int = 60):
        self.api_key = api_key or os.environ.get("YULEOSH_EMBED_API_KEY", "")
        self.model = model or os.environ.get(
            "YULEOSH_EMBED_API_MODEL", DEFAULT_API_MODEL)
        self.url = url
        self.timeout_s = timeout_s

    def available(self) -> bool:
        return bool(self.api_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = json.dumps({
            "model": self.model,
            "input": texts,
        }).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise EmbeddingUnavailableError(
                f"HTTP embedding failed: {e}") from e
        out: list[list[float]] = []
        for item in data.get("data", []):
            out.append(list(item.get("embedding", [])))
        return out


def get_provider(provider: str = "ollama",
                 **kwargs) -> EmbeddingProvider:
    """Embedding 工厂（EI-M3C.1）。"""
    if provider == "ollama":
        return OllamaEmbeddingProvider(**kwargs)
    if provider == "http":
        return HttpEmbeddingProvider(**kwargs)
    raise ValueError(f"Unknown embedding provider '{provider}'. Available: ollama, http")
