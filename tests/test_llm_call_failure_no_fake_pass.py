"""守护 _call_llm 兜底行为（2026-09-03 本地 Ollama 推进任务）。

单步 LLM 调用失败时，_call_llm 必须：
  1. 抛 PipelineStepError（让 orchestrator 标记 step failed、不写模板占位假绿）；
  2. 绝不静默吞掉异常、也绝不返回一个带空 content 的 dict（那会被 handler
     当成成功写出 passed 报告，制造假绿）。

这是「单步失败跳过而非整链崩溃」且不引入「假绿 2.0」的硬保证。
"""

import pytest
from unittest.mock import MagicMock

from yuleosh.pipeline.stages.llm import _call_llm
from yuleosh.pipeline.session import PipelineStepError


def _make_failing_session(side_effect):
    """最小 session：mock_mode=True 跳过 knowledge injection / context_guard，
    聚焦 client 调用失败时的兜底路径。"""
    failing = MagicMock(side_effect=side_effect)
    s = MagicMock()
    s.mock_mode = True
    s.llm_client = failing
    s.pipeline_knowledge_step_key = ""
    return s


def test_call_llm_failure_raises_pipeline_step_error():
    s = _make_failing_session(RuntimeError("llm down"))
    with pytest.raises(PipelineStepError):
        _call_llm(s, "system", "user")


def test_call_llm_failure_does_not_swallow_to_content():
    s = _make_failing_session(RuntimeError("timeout"))
    try:
        _call_llm(s, "system", "user")
    except PipelineStepError:
        return
    pytest.fail("_call_llm 未抛 PipelineStepError — LLM 失败被静默，会制造假绿")
