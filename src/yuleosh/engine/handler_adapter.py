"""HandlerAdapter — CheckpointEngine 与 pipeline step handler 之间的签名适配层。

背景（PR0）：engine/checkpoint.py 的 ``_execute_steps`` 以 ``handler()`` 无参方式
调用步骤处理器，但真实 pipeline 步骤全部是 ``handler(session)`` 签名（见
pipeline/step_handlers/__init__.py 的 PIPELINE_STEPS），导致 agent_checkpoint
run/resume 时 TypeError。本模块在 CheckpointEngine 边界做适配（additive）：
不改 33 个 handler，不改 _execute_steps 现有逻辑，注册时 fail fast 拒绝
不支持的签名。
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# 合法的 verdict 取值
_VALID_VERDICTS = ("passed", "failed", "warn")

# 判定为 session 风格的首参名
_SESSION_PARAM_NAMES = ("session", "ctx", "context")


@dataclass
class StepResult:
    """适配层统一的步骤执行结果。"""

    verdict: str = "passed"
    output_path: str | None = None
    error: str | None = None
    fallback_stamped: bool = False

    def __post_init__(self) -> None:
        if self.verdict not in _VALID_VERDICTS:
            raise ValueError(
                f"非法 verdict: {self.verdict!r}"
                f"（允许值: {', '.join(_VALID_VERDICTS)}）"
            )


class HandlerAdapter:
    """
    把 session 风格 / no-arg 风格 handler 统一适配为 StepResult。

    - session 风格：``def handler(session)``（首参名 session/ctx/context）→ 调用 handler(session)
    - no-arg 风格：``def handler()`` → 调用 handler()
    - 其他签名：构造时抛 ValueError（fail fast，绝不静默接受）

    fallback_safe=True 时 handler 抛出的异常被捕获并转换为
    fallback_stamped=True 的 failed StepResult（不抛）；否则 re-raise
    （绝不静默降质）。
    """

    def __init__(self, handler: Callable, *, fallback_safe: bool = False) -> None:
        if not callable(handler):
            raise TypeError(f"handler 必须可调用，收到: {handler!r}")
        self.handler = handler
        self.fallback_safe = fallback_safe
        self.style = self._detect_style(handler)
        if self.style == "invalid":
            raise ValueError(
                f"handler 签名不受支持: {handler!r} — 首参必须为 "
                f"session/ctx/context（session 风格）或无参（noarg 风格）"
            )

    # ------------------------------------------------------------------
    # Style detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_style(handler: Callable) -> str:
        """返回 'session' | 'noarg' | 'invalid'。"""
        try:
            sig = inspect.signature(handler)
        except (TypeError, ValueError):
            return "invalid"

        positional = [
            p
            for p in sig.parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        if not positional:
            return "noarg"
        if positional[0].name in _SESSION_PARAM_NAMES:
            return "session"
        return "invalid"

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def __call__(self, session: Any) -> StepResult:
        """执行 handler 并规范化为 StepResult。"""
        try:
            if self.style == "session":
                raw = self.handler(session)
            else:  # noarg — 忽略 session，保持原无参调用语义
                raw = self.handler()
        except Exception as e:
            if self.fallback_safe:
                return StepResult(
                    verdict="failed",
                    error=str(e),
                    fallback_stamped=True,
                )
            raise
        return self._normalize(raw)

    def _normalize(self, raw: Any) -> StepResult:
        """把 handler 的任意返回值规范化为 StepResult。"""
        if isinstance(raw, StepResult):
            return raw  # verdict 已在 __post_init__ 校验
        if raw is None:
            return StepResult(verdict="passed")
        if isinstance(raw, str):
            return StepResult(verdict="passed", output_path=raw)
        if isinstance(raw, dict):
            return StepResult(
                verdict=raw.get("verdict", "passed"),
                output_path=raw.get("output_path"),
                error=raw.get("error"),
                fallback_stamped=bool(raw.get("fallback_stamped", False)),
            )
        # 其他类型：优先取 output_path 属性，否则字符串化
        output_path = getattr(raw, "output_path", None)
        if output_path is None:
            output_path = str(raw)
        return StepResult(verdict="passed", output_path=str(output_path))
