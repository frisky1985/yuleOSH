# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Executor interface — 步骤执行器抽象（EI-M1A）。

yuleOSH pipeline 的步骤执行统一走 ``Executor`` 接口，本地/云端双后端：

- ``LocalExecutor``: 独立子进程执行（复用 subprocess_executor worker 语义），
  支持项目 venv 隔离（EI-M1B 在其上叠加）。
- ``ContainerExecutor`` (EI-M2A): 容器内执行（docker/K8s），后续实现。

设计要点（EI-M1A.3 默认路径零回归）:
- runner 钩子签名 ``runner(step_def, artifacts) -> StepResult`` 保持不变，
  CheckpointEngine 不感知后端差异。
- LocalExecutor 内部直接复用 ``_run_step_in_subprocess``，行为与旧
  ``make_subprocess_runner`` 完全一致。
- 默认 executor 名为 "local"，不显式指定时行为与现状一致。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from yuleosh.engine.handler_adapter import StepResult

log = logging.getLogger("engine.executor")


class Executor:
    """步骤执行器接口。

    execute(step_def, artifacts) 语义与 CheckpointEngine runner 钩子等价：
    - step_def: 步骤定义（step_id/name/agent/spec_path）
    - artifacts: 前序步骤产物注册表（step_id → output_path）
    返回 StepResult（verdict/passed/failed + output_path/error）。
    """

    name = "base"

    def execute(self, step_def: dict, artifacts: dict | None = None) -> StepResult:
        raise NotImplementedError

    # runner 钩子形态：CheckpointEngine 直接赋给 engine.runner
    def as_runner(self) -> Callable[[dict, dict | None], StepResult]:
        return self.execute


class LocalExecutor(Executor):
    """本地子进程执行器（EI-M1A.2）。

    保持现有 worker 语义：每步独立子进程 + JSON 回传 + HandlerAdapter 包装。
    """

    name = "local"

    def __init__(self, project_dir: str, mock_mode: bool = False,
                 spec_path: str | None = None, timeout_s: int = 600,
                 session_name: str | None = None,
                 run_id: str | None = None,
                 venv_dir: str | None = None):
        self.project_dir = project_dir
        self.mock_mode = mock_mode
        self.spec_path = spec_path
        self.timeout_s = timeout_s
        self.session_name = session_name
        self.run_id = run_id
        self.venv_dir = venv_dir  # EI-M1B: 项目 venv 目录（None = 系统环境）

    def _python_executable(self) -> str:
        """worker 解释器路径。

        EI-M1B.3: venv_dir 存在时优先用 venv 内 python，保证步骤在项目
        依赖环境内执行；未配置 venv 时回退当前解释器（零回归）。
        """
        if self.venv_dir:
            import os
            from pathlib import Path
            venv_py = Path(self.venv_dir) / "bin" / "python"
            if venv_py.exists():
                return str(venv_py)
            log.warning("venv python not found at %s, falling back to sys.executable", venv_py)
        import sys
        return sys.executable

    def execute(self, step_def: dict, artifacts: dict | None = None) -> StepResult:
        from yuleosh.engine.subprocess_executor import _run_step_in_subprocess
        return _run_step_in_subprocess(
            step_def, self.project_dir, self.mock_mode, self.spec_path,
            self.timeout_s, self.session_name, self.run_id, artifacts,
            python_executable=self._python_executable(),
        )


def make_executor(name: str = "local", **kwargs: Any) -> Executor:
    """执行器工厂（EI-M1A.1）。

    ``name`` 支持: local（默认，零回归）。
    ContainerExecutor (EI-M2A) 后续按同接口接入。

    kwargs 透传给具体 Executor 构造（project_dir/mock_mode/spec_path/
    timeout_s/session_name/run_id/venv_dir）。
    """
    if name == "local":
        return LocalExecutor(**kwargs)
    raise ValueError(
        f"Unknown executor '{name}'. Available: local"
    )
