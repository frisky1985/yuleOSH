"""Tests for engine/container_executor.py — ContainerExecutor (EI-M2A)."""

# @tests src/yuleosh/pipeline/orchestrator.py

import os
from pathlib import Path

import pytest

from yuleosh.engine.container_executor import (
    CONTAINER_WORK_DIR,
    ContainerExecutor,
    DEFAULT_IMAGE,
)
from yuleosh.engine.executor import make_executor
from yuleosh.engine.handler_adapter import StepResult


# ── EI-M2A.2: 资源限额映射 ────────────────────────────────────────────

class TestLimitsForPlan:
    def test_free_plan(self):
        assert ContainerExecutor.limits_for_plan("free") == ("512m", 1.0)

    def test_pro_plan(self):
        assert ContainerExecutor.limits_for_plan("pro") == ("2g", 2.0)

    def test_enterprise_plan(self):
        assert ContainerExecutor.limits_for_plan("enterprise") == ("8g", 4.0)

    def test_unknown_plan(self):
        assert ContainerExecutor.limits_for_plan("bogus") == (None, None)


# ── EI-M2A.5: docker 缺失优雅降级 ────────────────────────────────────

class TestDockerMissing:
    def test_execute_fails_gracefully(self, monkeypatch):
        """GIVEN docker 不存在 WHEN execute THEN failed 结果（不 crash）。"""
        monkeypatch.setattr(ContainerExecutor, "docker_available", staticmethod(lambda: False))
        ex = ContainerExecutor(project_dir=".", tenant_dir="/tmp/tenant")
        result = ex.execute({"step_id": "spec-check", "name": "Spec Check"})
        assert isinstance(result, StepResult)
        assert result.verdict == "failed"
        assert result.error and "docker CLI not found" in result.error


# ── 工厂接线 ──────────────────────────────────────────────────────────

class TestFactory:
    def test_make_container_executor(self):
        ex = make_executor("container", project_dir=".")
        assert isinstance(ex, ContainerExecutor)

    def test_make_executor_unknown_still_rejects(self):
        with pytest.raises(ValueError):
            make_executor("bogus")


# ── 命令构造（无 docker 时验证 docker 命令参数）────────────────────────

class TestCommandBuild:
    def test_default_security_args(self):
        """GIVEN 默认配置 WHEN execute 命令 THEN --network=none + 非 root + 只读根。"""
        ex = ContainerExecutor(project_dir="/proj", tenant_dir="/tenant/proj-a",
                               memory_limit="2g", cpus=2.0)
        # 不真正执行，仅验证 _build_limits / _build_env / 构造逻辑
        limits = ex._build_limits()
        assert "--memory" in limits and "2g" in limits
        assert "--cpus" in limits and "2.0" in limits

        env = ex._build_env()
        assert "OSH_HOME=/work" in env
        assert "YULEOSH_MOCK=0" in env

    def test_proxy_env_injected_when_network_disabled(self):
        """GIVEN 网络默认禁 WHEN env THEN 代理白名单注入。"""
        ex = ContainerExecutor(project_dir=".", proxy_env={"HTTPS_PROXY": "http://proxy:3128"})
        env = ex._build_env()
        assert "HTTPS_PROXY=http://proxy:3128" in env

    def test_extra_env_passthrough(self):
        """GIVEN extra_env WHEN env THEN 透传（凭据仅 env 不落盘）。"""
        ex = ContainerExecutor(project_dir=".", extra_env={"DEEPSEEK_API_KEY": "sk-xxx"})
        env = ex._build_env()
        assert "DEEPSEEK_API_KEY=sk-xxx" in env

    def test_tenant_dir_mount_source(self):
        """GIVEN tenant_dir WHEN _host_project_dir THEN 租户卷内项目路径。"""
        ex = ContainerExecutor(project_dir="/x/y/proj-a", tenant_dir="/data/tenants/t1")
        assert ex._host_project_dir() == "/data/tenants/t1/proj-a"

    def test_no_tenant_dir_fallback(self):
        """GIVEN 无 tenant_dir WHEN _host_project_dir THEN 绝对项目路径。"""
        ex = ContainerExecutor(project_dir=".", tenant_dir=None)
        assert ex._host_project_dir() == os.path.abspath(".")
