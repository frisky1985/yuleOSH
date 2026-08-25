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


def tenant_config_dir(tenant_dir: str | Path) -> Path:
    """租户 config 目录。"""
    return Path(tenant_dir) / "config"


def tenant_audit_dir(tenant_dir: str | Path) -> Path:
    """租户 audit 目录。"""
    return Path(tenant_dir) / "audit"


def load_credentials(tenant_dir: str | Path) -> dict[str, str]:
    """从租户 config/credentials.json 读取凭据（EI-M2B.2）。

    返回白名单键的子集；文件缺失/损坏返回空 dict（不 crash）。
    """
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


def write_credentials(tenant_dir: str | Path, creds: dict[str, str]) -> None:
    """写租户凭据（仅白名单键，模式 0o600 防泄露）。"""
    safe = {k: v for k, v in creds.items() if k in CREDENTIAL_KEYS}
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
