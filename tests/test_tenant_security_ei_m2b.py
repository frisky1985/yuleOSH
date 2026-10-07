"""Tests for engine/tenant_security.py — tenant credentials + audit (EI-M2B)."""

# @tests src/yuleosh/tenant/model.py

import json
import os
import stat
from pathlib import Path

import pytest

from yuleosh.engine.container_executor import ContainerExecutor
from yuleosh.engine.tenant_security import (
    audit_container_start,
    list_container_audit,
    load_credentials,
    write_credentials,
)


@pytest.fixture
def tenant_dir(tmp_path):
    """临时租户目录。"""
    d = tmp_path / "tenants" / "acme"
    (d / "config").mkdir(parents=True)
    (d / "audit").mkdir(parents=True)
    return d


# ── EI-M2B.2: 凭据注入（SEC-PK：API key 走加密保险库，非机密走明文 0o600） ──

@pytest.fixture
def mock_vault(monkeypatch):
    """确定性内存保险库，使 write/load_credentials 在 vault 路径下可断言。

    真实 secret_vault 在本环境可用且跨用例持久化，会导致 load 读到上一次写入
    的残留值（非确定性）；此处替换为进程内字典，保证 write→load 严格成对。
    """
    import yuleosh.secret_vault  # 确保属性已绑定，便于 monkeypatch 替换

    store: dict[str, tuple[str, str]] = {}

    class FakeVault:
        def set_provider_secret(self, provider: str, key: str, val: str) -> None:
            store[provider] = (key, val)

        def resolve_provider_api_key(self, provider: str) -> str | None:
            item = store.get(provider)
            return item[1] if item else None

    fake = FakeVault()
    monkeypatch.setattr(yuleosh, "secret_vault", fake)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    return fake


class TestCredentials:
    def test_write_load_roundtrip(self, tenant_dir, mock_vault):
        """GIVEN 写 API key 到保险库 WHEN load THEN 白名单键往返一致。"""
        write_credentials(tenant_dir, {
            "DEEPSEEK_API_KEY": "sk-123",
            "OPENAI_API_KEY": "sk-456",
            "SOME_OTHER_SECRET": "should-not-save",  # 白名单外
        })
        creds = load_credentials(tenant_dir)
        assert creds["DEEPSEEK_API_KEY"] == "sk-123"
        assert creds["OPENAI_API_KEY"] == "sk-456"
        assert "SOME_OTHER_SECRET" not in creds

    def test_api_key_written_to_vault_not_plaintext(self, tenant_dir, mock_vault):
        """GIVEN 写 API key WHEN 落盘 THEN 绝不生成明文 credentials.json（SEC-PK）。"""
        write_credentials(tenant_dir, {"DEEPSEEK_API_KEY": "sk-123"})
        # 保险库收到写入（API key 的真实落盘路径）
        assert mock_vault.resolve_provider_api_key("deepseek") == "sk-123"
        # 明文凭据文件不应存在
        assert not (tenant_dir / "config" / "credentials.json").exists()

    def test_ollama_host_legacy_credentials_mode_0600(self, tenant_dir, mock_vault):
        """GIVEN 写非机密 OLLAMA_HOST THEN 遗留明文文件权限 0o600（防泄露）。"""
        write_credentials(tenant_dir, {"OLLAMA_HOST": "http://localhost:11434"})
        path = tenant_dir / "config" / "credentials.json"
        assert path.exists()
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == 0o600

    def test_load_missing_returns_empty(self, tenant_dir, mock_vault):
        """GIVEN 无凭据（保险库空、无明文文件）WHEN load THEN 空 dict。"""
        assert load_credentials(tenant_dir) == {}

    def test_load_corrupt_returns_empty(self, tenant_dir, mock_vault):
        """GIVEN 损坏明文文件（保险库空）WHEN load THEN 空 dict（不 crash）。"""
        (tenant_dir / "config" / "credentials.json").write_text("{not json")
        assert load_credentials(tenant_dir) == {}

    def test_container_env_injects_credentials(self, tenant_dir, mock_vault):
        """GIVEN 保险库含 API key WHEN _build_env THEN 注入 env 白名单键。"""
        write_credentials(tenant_dir, {"DEEPSEEK_API_KEY": "sk-123"})
        ex = ContainerExecutor(project_dir="/proj", tenant_dir=str(tenant_dir))
        env = ex._build_env()
        assert "DEEPSEEK_API_KEY=sk-123" in env

    def test_container_env_no_tenant_no_creds(self):
        """GIVEN 无 tenant_dir WHEN _build_env THEN 不含凭据。"""
        ex = ContainerExecutor(project_dir="/proj", tenant_dir=None)
        env = ex._build_env()
        assert not any(e.startswith("DEEPSEEK_API_KEY") for e in env)


# ── EI-M2B.3: 容器启动审计 ────────────────────────────────────────────

class TestContainerAudit:
    def test_audit_appends(self, tenant_dir):
        """GIVEN 审计一次 WHEN list THEN 一条记录。"""
        audit_container_start(
            tenant_dir, tenant_id="acme", project_name="proj-a",
            step_id="spec-check", image="yuleosh-runner:latest",
            limits={"memory": "2g", "cpus": 2.0}, network=False,
        )
        entries = list_container_audit(tenant_dir)
        assert len(entries) == 1
        assert entries[0]["tenant_id"] == "acme"
        assert entries[0]["step_id"] == "spec-check"
        assert entries[0]["image"] == "yuleosh-runner:latest"
        assert entries[0]["network_enabled"] is False

    def test_audit_multiple_reversed(self, tenant_dir):
        """GIVEN 审计多次 WHEN list THEN 最新在前。"""
        for i in range(3):
            audit_container_start(
                tenant_dir, tenant_id="acme", project_name=f"proj-{i}",
                step_id=f"step-{i}", image="img", limits={}, network=False,
            )
        entries = list_container_audit(tenant_dir)
        assert len(entries) == 3
        assert entries[0]["project"] == "proj-2"  # 最新在前

    def test_audit_no_file(self, tmp_path):
        """GIVEN 无审计文件 WHEN list THEN 空列表。"""
        assert list_container_audit(tmp_path) == []

    def test_execute_audits_when_tenant(self, tenant_dir, monkeypatch):
        """GIVEN tenant_dir + docker 可用 WHEN execute THEN 审计写入。"""
        monkeypatch.setattr(ContainerExecutor, "docker_available", staticmethod(lambda: True))
        monkeypatch.setattr(
            "yuleosh.engine.container_executor.subprocess.run",
            lambda *a, **k: type("R", (), {
                "returncode": 1, "stdout": "", "stderr": "fake",
            })(),
        )
        ex = ContainerExecutor(
            project_dir="/x/proj-a", tenant_dir=str(tenant_dir), tenant_id="acme",
        )
        ex.execute({"step_id": "spec-check", "name": "Spec Check"})
        entries = list_container_audit(tenant_dir)
        assert len(entries) == 1
        assert entries[0]["tenant_id"] == "acme"
        assert entries[0]["step_id"] == "spec-check"

    def test_execute_no_audit_without_tenant(self, tmp_path, monkeypatch):
        """GIVEN 无 tenant_dir WHEN execute THEN 不写审计。"""
        monkeypatch.setattr(ContainerExecutor, "docker_available", staticmethod(lambda: True))
        monkeypatch.setattr(
            "yuleosh.engine.container_executor.subprocess.run",
            lambda *a, **k: type("R", (), {
                "returncode": 1, "stdout": "", "stderr": "fake",
            })(),
        )
        ex = ContainerExecutor(project_dir="/x/proj-a", tenant_dir=None)
        ex.execute({"step_id": "spec-check", "name": "Spec Check"})
        assert list_container_audit(tmp_path) == []
