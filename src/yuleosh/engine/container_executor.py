# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
ContainerExecutor — 容器内步骤执行器（EI-M2A）。

云端多租户后端：每步骤在独立容器内执行，进程/文件系统/网络全隔离。

安全默认值（EI-M2A.3/.4）:
- ``--network=none``: 默认禁止外联；LLM/包管理走显式代理 env 白名单
- 非 root 用户运行 + 根文件系统只读，仅项目目录可写
- 资源限额（--memory/--cpus）从 tenant plan TIER_LIMITS 映射（EI-M2A.2）

设计:
- 复用 subprocess_executor 的 worker 模块（``python -m yuleosh.engine.subprocess_executor worker``），
  容器镜像内置 yuleosh 包。
- 工作目录 = 挂载卷内的项目目录；artifacts.json 产物交接链保持
  ``.osh/sessions/<run_id>/`` 路径规则（容器卷内）。
- docker 不存在/不可用时返回清晰错误，不 crash（EI-M2A.5）。
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Any
from uuid import uuid4

from yuleosh.engine.executor import Executor
from yuleosh.engine.handler_adapter import StepResult

log = logging.getLogger("engine.container_executor")

# 默认镜像：内置 yuleosh + Python 3.12 + 工具链
DEFAULT_IMAGE = "yuleosh-runner:latest"

# 容器内项目挂载点
CONTAINER_WORK_DIR = "/work"


class ContainerExecutor(Executor):
    """容器执行器（EI-M2A）：docker run 封装，每步骤独立容器。

    ``tenant_dir``: 租户数据目录（挂载为容器工作卷，读写边界=租户目录）。
    ``image``: 运行镜像（含 yuleosh + python + 工具链）。
    ``memory_limit`` / ``cpus``: 资源限额（None = 不限制/宿主默认）。
    ``network_enabled``: 默认 False（--network=none）；True 时走代理 env。
    ``extra_env``: 注入容器 env（API key 等凭据，仅环境变量不落盘 EI-M2B.2）。
    """

    name = "container"

    def __init__(self, project_dir: str,
                 tenant_dir: str | None = None,
                 image: str = DEFAULT_IMAGE,
                 memory_limit: str | None = None,
                 cpus: float | None = None,
                 network_enabled: bool = False,
                 proxy_env: dict[str, str] | None = None,
                 extra_env: dict[str, str] | None = None,
                 mock_mode: bool = False,
                 timeout_s: int = 600,
                 run_id: str | None = None):
        self.project_dir = project_dir
        self.tenant_dir = tenant_dir
        self.image = image
        self.memory_limit = memory_limit
        self.cpus = cpus
        self.network_enabled = network_enabled
        self.proxy_env = proxy_env or {}
        self.extra_env = extra_env or {}
        self.mock_mode = mock_mode
        self.timeout_s = timeout_s
        self.run_id = run_id

    # ---- 资源限额映射（EI-M2A.2）----

    @staticmethod
    def limits_for_plan(plan: str) -> tuple[str | None, float | None]:
        """从 tenant plan 映射 (memory_limit, cpus)。

        free: 512m / 1 · pro: 2g / 2 · enterprise: 8g / 4
        未知 plan 返回 (None, None)（宿主默认）。
        """
        table = {
            "free": ("512m", 1.0),
            "pro": ("2g", 2.0),
            "enterprise": ("8g", 4.0),
        }
        return table.get(plan, (None, None))

    # ---- docker 可用性（EI-M2A.5）----

    @staticmethod
    def docker_available() -> bool:
        """docker CLI 是否存在（不在容器内运行也视为可用，交由 run 报错）。"""
        return shutil.which("docker") is not None

    # ---- 执行 ----

    def _build_env(self) -> list[str]:
        """容器 env 参数（--env k=v）。网络关闭时注入代理白名单。"""
        env = dict(self.extra_env)
        env["OSH_HOME"] = CONTAINER_WORK_DIR
        env["YULEOSH_MOCK"] = "1" if self.mock_mode else "0"
        if not self.network_enabled:
            # 代理 env 白名单：仅显式配置的代理可外联
            for k, v in self.proxy_env.items():
                env[k] = v
        return [f"{k}={v}" for k, v in env.items()]

    def _build_limits(self) -> list[str]:
        """资源限额参数。"""
        args: list[str] = []
        if self.memory_limit:
            args.extend(["--memory", self.memory_limit])
        if self.cpus:
            args.extend(["--cpus", str(self.cpus)])
        return args

    def execute(self, step_def: dict, artifacts: dict | None = None) -> StepResult:
        if not self.docker_available():
            return StepResult(
                verdict="failed",
                error="docker CLI not found — ContainerExecutor requires docker "
                      "(EI-M2A.5). Install docker or switch to --executor local.",
            )

        run_id = self.run_id or uuid4().hex[:12]

        # 产物交接：写 artifacts.json 到挂载卷内 session 目录（与 subprocess 同规则）
        if artifacts:
            session_dir = f"{CONTAINER_WORK_DIR}/.osh/sessions/{run_id}"
            self._write_artifacts(session_dir, artifacts)

        cmd = [
            "docker", "run", "--rm",
            # 网络默认禁（EI-M2A.3）
            "--network", "none" if not self.network_enabled else "bridge",
            # 非 root + 只读根（EI-M2A.4）
            "--user", "1000:1000",
            "--read-only",
            # 资源限额（EI-M2A.2）
            *self._build_limits(),
            # 项目目录挂载（EI-M2B.1: 租户卷）
            "-v", f"{self._host_project_dir()}:{CONTAINER_WORK_DIR}",
            # env
            *[e for e in self._build_env()],
            # 镜像 + worker 命令
            self.image,
            "python", "-m", "yuleosh.engine.subprocess_executor", "worker",
            "--step-id", step_def["step_id"],
            "--project-dir", CONTAINER_WORK_DIR,
            "--run-id", run_id,
        ]
        if self.mock_mode:
            cmd.append("--mock")
        spec_path = step_def.get("spec_path")
        if spec_path:
            cmd.extend(["--spec-path", spec_path])

        log.info("ContainerExecutor: %s", " ".join(cmd))
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.timeout_s, check=False,
            )
        except subprocess.TimeoutExpired:
            return StepResult(
                verdict="failed",
                error=f"step {step_def['step_id']} timed out in container after {self.timeout_s}s",
            )
        except OSError as e:
            return StepResult(verdict="failed", error=f"docker spawn failed: {e}")

        if proc.returncode != 0 and not proc.stdout.strip():
            return StepResult(
                verdict="failed",
                error=f"docker run failed (exit={proc.returncode}): {proc.stderr[-500:]}",
            )

        # stdout 最后一行是结果 JSON（与 subprocess worker 同协议）
        lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
        if not lines:
            return StepResult(
                verdict="failed",
                error=f"container worker 无输出 (exit={proc.returncode}, stderr={proc.stderr[-500:]})",
            )
        try:
            payload = json.loads(lines[-1])
        except json.JSONDecodeError as e:
            return StepResult(
                verdict="failed",
                error=f"container worker 输出非 JSON: {e} (last line={lines[-1][-200:]})",
            )

        return StepResult(
            verdict=payload.get("verdict", "failed"),
            output_path=payload.get("output_path"),
            error=payload.get("error"),
            fallback_stamped=bool(payload.get("fallback_stamped", False)),
        )

    # ---- helpers ----

    def _host_project_dir(self) -> str:
        """宿主侧项目目录（挂载源）。

        tenant_dir 优先（云端多租户：挂载租户卷内的项目），
        否则用 project_dir（单机模式）。
        """
        if self.tenant_dir:
            from pathlib import Path
            # 租户卷内找项目：tenant_dir/<project_name>
            return str(Path(self.tenant_dir) / Path(self.project_dir).name)
        import os
        return os.path.abspath(self.project_dir)

    def _write_artifacts(self, container_session_dir: str, artifacts: dict) -> None:
        """写 artifacts.json 到容器卷内 session 目录（宿主侧路径对应挂载）。"""
        # 容器路径 CONTAINER_WORK_DIR 对应宿主挂载源，替换前缀得到宿主路径
        host_root = self._host_project_dir()
        rel = container_session_dir[len(CONTAINER_WORK_DIR):].lstrip("/")
        host_session_dir = f"{host_root}/.osh/sessions/{rel.split('/')[-1]}"
        try:
            from pathlib import Path
            p = Path(host_session_dir)
            p.mkdir(parents=True, exist_ok=True)
            (p / "artifacts.json").write_text(
                json.dumps(artifacts, ensure_ascii=False), encoding="utf-8",
            )
        except OSError as e:
            log.warning("Failed to write artifacts.json: %s", e)


def register() -> None:
    """向 executor 工厂注册 container 后端（EI-M2A 接线）。"""
    from yuleosh.engine.executor import make_executor
    # 通过工厂 kwargs 分支支持 container —— 见 executor.py make_executor
    _ = make_executor
