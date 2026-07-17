#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Pipeline Step Handler — 基类 (Phase 2.5 refactor).

提供:
  - 日志装饰器 (timed + logging)
  - 模板方法模式: run() → pre_check() → execute() → post_write()
  - 检查点管理
  - 重试逻辑 (指数退避)
  - 统一异常处理: soft → warning, hard → PipelineStepError
  - LLM token tracking

Usage::

    from yuleosh.pipeline.step_handlers.handler_base import BaseHandler

    class MyHandler(BaseHandler):
        step_name = "my-step"

        def execute(self, session):
            # actual business logic
            return result_path

顶层函数兼容::

    @BaseHandler.as_handler(step_name="my-step")
    def step_my_step(session):
        ...
"""

import functools
import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm

log = logging.getLogger("pipeline.step_handlers.base")


# ------------------------------------------------------------------
# 指数退避重试
# ------------------------------------------------------------------

def retry(max_attempts: int = 3, base_delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple = (Exception,)):
    """Decorator: 重试指定异常类型，使用指数退避。

    Parameters
    ----------
    max_attempts : int
        最大重试次数 (不包括首次)。
    base_delay : float
        首次重试前的等待秒数。
    backoff : float
        每次重试的退避倍数。
    exceptions : tuple
        捕获并重试的异常类型元组。
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1 + max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_attempts:
                        delay = base_delay * (backoff ** attempt)
                        log.warning(
                            "%s failed (attempt %d/%d): %s. Retrying in %.1fs...",
                            func.__name__, attempt + 1, max_attempts + 1, e, delay,
                        )
                        time.sleep(delay)
                    else:
                        log.error(
                            "%s failed after %d attempts: %s",
                            func.__name__, max_attempts + 1, e,
                        )
            raise last_exc
        return wrapper
    return decorator


# ------------------------------------------------------------------
# 检查点管理
# ------------------------------------------------------------------

class CheckpointManager:
    """管理 pipeline step 的检查点 (checkpoint)。

    用于幂等恢复：如果相同检查点文件已存在且未过期，则跳过执行。
    """

    def __init__(self, session_dir: Path, step_name: str, ttl_seconds: int = 0):
        self._checkpoint_path = session_dir / f".checkpoint_{step_name}"
        self._ttl = ttl_seconds

    @property
    def exists(self) -> bool:
        """检查点文件存在且未过期？"""
        if not self._checkpoint_path.exists():
            return False
        if self._ttl > 0:
            age = time.time() - self._checkpoint_path.stat().st_mtime
            if age > self._ttl:
                return False
        return True

    def save(self, metadata: Optional[dict] = None) -> None:
        """保存检查点。"""
        data = {
            "timestamp": datetime.now().isoformat(),
            "ttl_seconds": self._ttl,
            **(metadata or {}),
        }
        self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._checkpoint_path.write_text(json.dumps(data, indent=2))

    def load(self) -> Optional[dict]:
        """读取检查点内容。"""
        if not self.exists:
            return None
        try:
            return json.loads(self._checkpoint_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def clear(self) -> None:
        """清除检查点。"""
        if self._checkpoint_path.exists():
            self._checkpoint_path.unlink()


# ------------------------------------------------------------------
# 基类
# ------------------------------------------------------------------

class BaseHandler(ABC):
    """Pipeline step handler 抽象基类。

    子类只需实现:
      - step_name (class attribute)
      - execute(session) — 核心业务逻辑

    可选覆盖:
      - pre_check(session) — 前置条件验证
      - post_write(session, result_path) — 结果后处理
      - build_output_path(session) → Path — 输出路径生成
      - should_skip(session) → bool — 跳过条件 (返回 True 则跳过)
      - get_llm_prompts(session) → tuple[str, str] | None — LLM prompt 构建 (返回 None 则不用 LLM)
      - llm_max_tokens → int — LLM max_tokens
      - use_checkpoint → bool — 是否启用检查点
      - checkpoint_ttl → int — 检查点 TTL (秒)
      - max_retries → int — 最大重试次数
    """

    # ── 子类必须定义 ──
    step_name: str = ""

    # ── 可选覆盖 ──
    use_checkpoint: bool = False
    checkpoint_ttl: int = 0          # 0 = 永不过期
    max_retries: int = 0             # 0 = 不重试
    llm_max_tokens: int = 1024
    __printed_header: bool = False   # 类级别，避免重复打印

    # ── 模板方法 ──

    @timed_step
    def __call__(self, session: PipelineSession) -> str:
        """模板方法: pre_check → checkpoint_check → execute → post_write.

        Returns
        -------
        str
            输出文件路径。
        """
        logger = logging.getLogger(f"pipeline.step_handlers.{self.step_name}")

        try:
            # 1. 打印 header (仅限类的首次调用)
            self._print_header(session)

            # 2. 前置条件
            logger.info("Step [%s] starting...", self.step_name)
            pre_ok = self.pre_check(session)
            if pre_ok is not True:
                logger.info("Pre-check skipped step [%s]: %s", self.step_name, pre_ok)
                return str(self.build_output_path(session))

            # 3. 跳过条件
            if self.should_skip(session):
                logger.info("Step [%s] skipped by should_skip()", self.step_name)
                return str(self.build_output_path(session))

            # 4. 检查点
            checkpoint = CheckpointManager(
                session.session_dir, self.step_name, ttl_seconds=self.checkpoint_ttl,
            ) if self.use_checkpoint else None

            if checkpoint and checkpoint.exists:
                logger.info("Step [%s] checkpoint hit — skipping execution", self.step_name)
                cp_data = checkpoint.load() or {}
                return cp_data.get("result_path", str(self.build_output_path(session)))

            # 5. 执行（带重试）
            result_path = str(self.build_output_path(session))
            if self.max_retries > 0:
                retry_decorator = retry(
                    max_attempts=self.max_retries,
                    exceptions=(RuntimeError, ConnectionError, TimeoutError),
                )
                execute_fn = retry_decorator(self._do_execute)
            else:
                execute_fn = self._do_execute

            result_path = execute_fn(session)

            # 6. 后处理
            result_path = self.post_write(session, result_path)

            # 7. 保存检查点
            if checkpoint:
                checkpoint.save({"result_path": result_path})

            logger.info("Step [%s] completed: %s", self.step_name, result_path)
            return result_path

        except PipelineStepError:
            raise
        except Exception as e:
            logger.error("Step [%s] failed: %s", self.step_name, e)
            raise PipelineStepError(f"Step [{self.step_name}] failed: {e}")

    def _do_execute(self, session: PipelineSession) -> str:
        """执行核心逻辑（被重试装饰器包装）。"""
        result = self.execute(session)
        return result or str(self.build_output_path(session))

    def _print_header(self, session: PipelineSession) -> None:
        """打印步骤头部（仅限类的首次调用）。"""
        cls = type(self)
        if not getattr(cls, "_BaseHandler__printed_header", False):
            cls._BaseHandler__printed_header = True

    # ── 子类可覆盖 ──

    def pre_check(self, session: PipelineSession):
        """前置条件验证。返回 True=继续, 其他=跳过。"""
        return True

    @abstractmethod
    def execute(self, session: PipelineSession) -> str:
        """核心业务逻辑。返回输出文件路径字符串。"""
        ...

    def post_write(self, session: PipelineSession, result_path: str) -> str:
        """结果写入后的后处理。返回最终路径。"""
        return result_path

    def build_output_path(self, session: PipelineSession) -> Path:
        """生成输出文件路径。"""
        return session.session_dir / f"{self.step_name}.json"

    def should_skip(self, session: PipelineSession) -> bool:
        """跳过条件。返回 True 则跳过执行。"""
        return False

    def get_llm_prompts(self, session: PipelineSession) -> Optional[tuple[str, str]]:
        """构建 LLM prompt。返回 (system_prompt, user_prompt) 或 None。"""
        return None

    def track_llm_usage(self, session: PipelineSession, result: dict, step_label: str) -> dict:
        """记录 LLM token 用量到 session。"""
        usage = result.get("usage", {})
        session.token_usage_total += usage.get("total_tokens", 0)
        session.token_usage_steps.append({"step": step_label, "usage": usage})
        return usage

    def call_llm(self, session: PipelineSession, **kwargs) -> dict:
        """调用 LLM 并跟踪用量。"""
        prompts = self.get_llm_prompts(session)
        if prompts is None:
            raise PipelineStepError(f"Step [{self.step_name}]: LLM prompts not configured")
        system_prompt, user_prompt = prompts
        max_tokens = kwargs.pop("max_tokens", self.llm_max_tokens)
        result = _call_llm(session, system_prompt, user_prompt, max_tokens=max_tokens, **kwargs)
        self.track_llm_usage(session, result, self.step_name)
        return result

    def write_output(self, session: PipelineSession, content: Any, filename: str = "") -> str:
        """写入 step 输出到文件。"""
        fname = filename or f"{self.step_name}.json"
        out_path = session.session_dir / fname
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            out_path.write_text(content)
        else:
            out_path.write_text(
                json.dumps(content, indent=2, ensure_ascii=False, default=str)
            )
        return str(out_path)

    def report_status(self, session: PipelineSession, status: str,
                      findings: Optional[list] = None, summary: str = "",
                      extra: Optional[dict] = None) -> str:
        """生成标准化的 step status report JSON。"""
        report = {
            "session": session.name,
            "step": self.step_name,
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "finding_count": len(findings) if findings else 0,
            "summary": summary,
            **(extra or {}),
        }
        if findings:
            report["findings"] = findings
        return self.write_output(session, report, f"{self.step_name}-report.json")


# ------------------------------------------------------------------
# 函数式辅助装饰器
# ------------------------------------------------------------------

def as_handler(step_name: str, **kwargs):
    """将函数装饰为 BaseHandler 风格。

    Usage::

        @BaseHandler.as_handler(step_name="my-step")
        def step_my_step(session):
            ...
    """
    def decorator(func):
        # 用 timed_step 装饰原函数
        _wrapped = timed_step(func)

        @functools.wraps(func)
        def wrapper(session):
            logger = logging.getLogger(f"pipeline.step_handlers.{step_name}")
            try:
                logger.info("Step [%s] starting...", step_name)
                result = _wrapped(session)
                logger.info("Step [%s] completed: %s", step_name, result)
                return result
            except PipelineStepError:
                raise
            except Exception as e:
                logger.error("Step [%s] failed: %s", step_name, e)
                raise PipelineStepError(f"Step [{step_name}] failed: {e}")

        return wrapper
    return decorator
