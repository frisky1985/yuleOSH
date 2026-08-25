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


# ── EI-M2B.2: 凭据注入 ────────────────────────────────────────────────

class TestCredentials:
    def test_write_load_roundtrip(self, tenant_dir):
        """GIVEN 写凭据 WHEN load THEN 白名单键往返一致。"""
        write_credentials(tenant_dir, {
            "DEEPSEEK_API_KEY": "sk-123",
            "OPENAI_API_KEY": "sk-456",
            "SOME_OTHER_SECRET": "should-not-save",  # 白名单外
        })
        creds = load_credentials(tenant_dir)
        assert creds["DEEPSEEK_API_KEY"] == "sk-123"
        assert creds["OPENAI_API_KEY"] == "sk-456"
        assert "SOME_OTHER_SECRET" not in creds

    def test_credentials_file_mode_0600(self, tenant_dir):
        """GIVEN 写凭据 THEN 文件权限 0o600（防泄露）。"""
        write_credentials(tenant_dir, {"DEEPSEEK_API_KEY": "sk-123"})
        path = tenant_dir / "config" / "credentials.json"
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == 0o600

    def test_load_missing_returns_empty(self, tenant_dir):
        """GIVEN 无凭据文件 WHEN load THEN 空 dict。"""
        assert load_credentials(tenant_dir) == {}

    def test_load_corrupt_returns_empty(self, tenant_dir):
        """GIVEN 损坏凭据文件 WHEN load THEN 空 dict（不 crash）。"""
        (tenant_dir / "config" / "credentials.json").write_text("{not json")
        assert load_credentials(tenant_dir) == {}

    def test_container_env_injects_credentials(self, tenant_dir):
        """GIVEN tenant_dir 含凭据 WHEN _build_env THEN 注入 env 白名单键。"""
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
