# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Tenant security — 容器执行的租户凭据注入与启动审计（EI-M2B）。

安全原则:
- API key 仅从租户 config 读取并注入容器 env（EI-M2B.2），SHALL NOT
  写入项目目录/工作卷。
- 容器启动参数写入租户 audit log（EI-M2B.3），可追溯谁跑了什么。
- 凭据字段名白名单（防误注入未知敏感键）。

目录约定（与 tenant/model.py 一致）:
    data/{slug}/config/       ← 租户配置（含 credentials.json）
    data/{slug}/audit/        ← 租户审计日志
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

# @req CR-002
log = logging.getLogger("engine.tenant_security")

# 允许注入容器的凭据键（白名单，防误注入）
CREDENTIAL_KEYS = {
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "YULEOSH_EMBED_API_KEY",
    "OLLAMA_HOST",
}

# API key 类 → 保险库 provider（OLLAMA_HOST 非机密，不进保险库）。
CREDENTIAL_KEY_TO_PROVIDER = {
    "DEEPSEEK_API_KEY": "deepseek",
    "OPENAI_API_KEY": "openai",
    "ANTHROPIC_API_KEY": "anthropic",
    "YULEOSH_EMBED_API_KEY": "embed",
}


def tenant_config_dir(tenant_dir: str | Path) -> Path:
    """租户 config 目录。"""
    return Path(tenant_dir) / "config"


def tenant_audit_dir(tenant_dir: str | Path) -> Path:
    """租户 audit 目录。"""
    return Path(tenant_dir) / "audit"


def _read_legacy_credentials(tenant_dir: str | Path) -> dict[str, str]:
    """读取遗留明文 credentials.json（向后兼容，仅作兜底）。"""
    cred_path = tenant_config_dir(tenant_dir) / "credentials.json"
    if not cred_path.exists():
        return {}
    try:
        data = json.loads(cred_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to read credentials.json: %s", e)
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: str(v) for k, v in data.items() if k in CREDENTIAL_KEYS and v}


def _write_legacy_credentials(tenant_dir: str | Path, creds: dict[str, str]) -> None:
    """写遗留明文 credentials.json（仅 OLLAMA_HOST 等非机密项或保险库降级）。

    仅白名单键、模式 0o600。新写入的 API key 不应再走此路径（见 write_credentials）。
    """
    safe = {k: str(v) for k, v in creds.items() if k in CREDENTIAL_KEYS and v}
    if not safe:
        return
    d = tenant_config_dir(tenant_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "credentials.json"
    path.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_credentials(tenant_dir: str | Path) -> dict[str, str]:
    """读取租户凭据用于容器 env 注入（EI-M2B.2）。

    解析优先级（机密性优先，绝不要求明文文件存在）:
      1. 进程环境变量（运维显式注入，最高优先级）;
      2. 加密保险库 provider_secrets 表（SEC-PK，密文落盘）;
      3. 遗留明文 credentials.json（仅向后兼容，新部署不应再生成）。

    返回白名单键子集；任何来源缺失均不 crash。
    """
    from yuleosh import secret_vault as _vault

    result: dict[str, str] = {}
    # 1) API key 类：env → 保险库（env 优先，保险库兜底）
    for key, provider in CREDENTIAL_KEY_TO_PROVIDER.items():
        val = _vault.resolve_provider_api_key(provider)
        if val:
            result[key] = val
    # 2) OLLAMA_HOST 非机密：env → 遗留文件
    oh = os.environ.get("OLLAMA_HOST")
    if oh:
        result["OLLAMA_HOST"] = oh
    # 3) 遗留明文文件兜底（向后兼容已落盘部署 / 保险库不可用）
    for k, v in _read_legacy_credentials(tenant_dir).items():
        result.setdefault(k, v)
    return result


def write_credentials(tenant_dir: str | Path, creds: dict[str, str]) -> None:
    """写租户凭据（SEC-PK：API key 经加密保险库落盘，绝不写明文文件）。

    - API key 类（DEEPSEEK/OPENAI/ANTHROPIC/EMBED）→ 加密写入 provider_secrets
      表，进程内瞬时明文、落库即密文；
    - OLLAMA_HOST 非机密 → 按遗留方式写入 credentials.json（0o600）供向后兼容；
    - 保险库不可用（缺主密钥）时降级为整体写遗留文件（异常配置下的安全兜底）。

    Args:
        tenant_dir: 租户目录（仅非机密项 / 降级路径使用）。
        creds: 待写入凭据（仅白名单键生效）。
    """
    from yuleosh import secret_vault as _vault

    safe = {k: str(v) for k, v in creds.items() if k in CREDENTIAL_KEYS and v}
    if not safe:
        return

    legacy_only: dict[str, str] = {}
    for key, val in safe.items():
        provider = CREDENTIAL_KEY_TO_PROVIDER.get(key)
        if not provider:
            # 非机密（OLLAMA_HOST）走遗留文件
            legacy_only[key] = val
            continue
        try:
            _vault.set_provider_secret(provider, key, val)
        except Exception as e:  # vault 不可用 / 约束失败 → 降级写遗留文件
            log.warning("write_credentials: 保险库写入失败，降级明文(%s): %s", key, e)
            legacy_only[key] = val

    if legacy_only:
        _write_legacy_credentials(tenant_dir, legacy_only)


def audit_container_start(tenant_dir: str | Path, tenant_id: str,
                          project_name: str, step_id: str,
                          image: str, limits: dict,
                          network: bool) -> None:
    """记录容器启动审计（EI-M2B.3）。

    追加写 ``data/{slug}/audit/containers.jsonl``，每行一条 JSON。
    """
    d = tenant_audit_dir(tenant_dir)
    d.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now().isoformat(),
        "tenant_id": tenant_id,
        "project": project_name,
        "step_id": step_id,
        "image": image,
        "limits": limits,
        "network_enabled": network,
    }
    try:
        with (d / "containers.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        log.warning("Failed to write container audit: %s", e)


def list_container_audit(tenant_dir: str | Path, limit: int = 50) -> list[dict]:
    """读取容器启动审计（倒序，最新在前）。"""
    path = tenant_audit_dir(tenant_dir) / "containers.jsonl"
    if not path.exists():
        return []
    entries: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return list(reversed(entries))[:limit]
