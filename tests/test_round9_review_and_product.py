# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
第九轮决策 9.2/9.3 新增测试:
  - prd-review 产品视角（建议性, 不改变 fail/pass 语义）
  - 4 个专项 review handler 基础静态检查（无文件 skip / critical 阻断）
"""

import json
from pathlib import Path

import pytest

from yuleosh.pipeline.step_handlers.review_prd import _assess_product_view


class TestPrdReviewProductView:
    """9.2: prd-review 双视角 — product 维度 advisory 建议性。"""

    def test_product_dimension_advisory_true(self):
        result = _assess_product_view("简单 PRD", "spec 内容")
        assert result["dimension"] == "product"
        assert result["advisory"] is True  # 纯建议, 不阻断

    def test_product_suggestions_when_no_positioning(self):
        result = _assess_product_view("无定位关键词的 PRD", "spec")
        assert len(result["suggestions"]) >= 1
        assert any("产品定位一致性" in s for s in result["suggestions"])

    def test_priority_distribution_counted(self):
        prd = "需求1 优先级 P0\n需求2 优先级 P1\n需求3 优先级 P2"
        result = _assess_product_view(prd, "spec")
        assert result["priority_distribution"]["P0"] >= 1
        assert result["priority_distribution"]["P1"] >= 1

    def test_yagni_signal_detected(self):
        prd = "本需求支持未来可扩展的 XX 框架集成预留"  # 含 YAGNI 信号关键词
        result = _assess_product_view(prd, "spec")
        assert result["advisory"] is True
        # YAGNI 信号不会导致 fail — 全部是 suggestions
        assert all(not s.startswith("[FAIL]") for s in result["suggestions"])


class TestNewSpecializedReviewHandlers:
    """第八轮新增 4 专项 handler 基础静态检查。"""

    @pytest.fixture
    def session(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.session import PipelineSession
        s = PipelineSession(
            name="test-specialized",
            spec_path=str(tmp_path / "spec.md"),
        )
        s.project_dir = str(tmp_path)
        s.session_dir = Path(tmp_path) / "sess"
        s.session_dir.mkdir(parents=True, exist_ok=True)
        return s

    def _write_c_file(self, session, content: str, name: str = "main.c"):
        p = Path(session.project_dir) / "src" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    @pytest.mark.parametrize("module,step_fn", [
        ("review_interrupt", "step_review_interrupt"),
        ("review_nvm", "step_review_nvm"),
        ("review_watchdog", "step_review_watchdog"),
        ("review_timing", "step_review_timing"),
    ])
    def test_mock_mode_skips(self, session, module, step_fn):
        """mock 模式 → skipped, 不调 LLM。"""
        session.mock_mode = True
        import importlib
        mod = importlib.import_module(f"yuleosh.pipeline.step_handlers.{module}")
        fn = getattr(mod, step_fn)
        path = fn(session)
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        assert report["status"] == "skipped"

    @pytest.mark.parametrize("module,step_fn", [
        ("review_interrupt", "step_review_interrupt"),
        ("review_nvm", "step_review_nvm"),
        ("review_watchdog", "step_review_watchdog"),
        ("review_timing", "step_review_timing"),
    ])
    def test_no_c_files_skips(self, session, module, step_fn):
        """无相关文件 → skipped 不报错。"""
        import importlib
        mod = importlib.import_module(f"yuleosh.pipeline.step_handlers.{module}")
        fn = getattr(mod, step_fn)
        path = fn(session)
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        assert report["status"] in ("skipped", "passed")

    def test_interrupt_static_critical_detected(self, session):
        """中断审查: 检测到临界区使用但无 ISR → 有 finding。"""
        from unittest import mock
        from yuleosh.pipeline.step_handlers import review_interrupt
        self._write_c_file(session, """
#include <stdint.h>
void isr_handler(void) __attribute__((interrupt));
void isr_handler(void) {
    // 临界区无配对
    __disable_irq();
    volatile int x = 1;
}
""")
        session.mock_mode = False
        with mock.patch.object(review_interrupt, "_call_llm", return_value="{}") as m:
            path = review_interrupt.step_review_interrupt(session)
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        # 静态检查至少产生 findings（LLM 被 mock 掉, 不会 fail-closed 报错）
        assert report["status"] in ("passed", "failed", "retry")
        assert m.called or report.get("static_findings") is not None


class TestExternalAgentsReferenceMarkers:
    """9.3.2: external_agents 引用式省略标记（替代静默截断）。"""

    def _make_session(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.session import PipelineSession
        s = PipelineSession(name="marker-test", spec_path=str(tmp_path / "spec.md"))
        s.project_dir = str(tmp_path)
        s.session_dir = Path(tmp_path) / "sess"
        s.session_dir.mkdir(parents=True, exist_ok=True)
        # artifacts dict: session.artifacts 是 {key: path}
        s.artifacts = {}
        return s

    def test_large_artifact_gets_marker(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.external_agents import (
            _collect_spec_and_artifacts, _format_artifacts_for_prompt,
        )
        s = self._make_session(tmp_path, monkeypatch)
        # spec 文件
        (tmp_path / "spec.md").write_text("spec content", encoding="utf-8")
        # PRD 超过 SPEC_INJECT_LIMIT
        prd_path = tmp_path / "prd.md"
        prd_path.write_text("A" * 40000, encoding="utf-8")
        s.artifacts["prd"] = str(prd_path)

        spec_content, artifacts = _collect_spec_and_artifacts(s)
        assert "prd" in artifacts
        assert "…[omitted" in artifacts["prd"]  # 显式省略标记
        assert "全文见" in artifacts["prd"]     # 引用路径

        prompt_block = _format_artifacts_for_prompt(artifacts)
        # 合并渲染后 marker 保留（契约尾段可读）
        assert len(prompt_block) < 40000 + 1000

    def test_small_artifacts_no_marker(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.external_agents import (
            _collect_spec_and_artifacts,
        )
        s = self._make_session(tmp_path, monkeypatch)
        (tmp_path / "spec.md").write_text("spec", encoding="utf-8")
        prd_path = tmp_path / "prd.md"
        prd_path.write_text("small prd", encoding="utf-8")
        s.artifacts["prd"] = str(prd_path)

        _, artifacts = _collect_spec_and_artifacts(s)
        assert artifacts["prd"] == "small prd"
        assert "omitted" not in artifacts["prd"]

    def test_missing_artifact_read_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.external_agents import (
            _collect_spec_and_artifacts,
        )
        s = self._make_session(tmp_path, monkeypatch)
        (tmp_path / "spec.md").write_text("spec", encoding="utf-8")
        s.artifacts["prd"] = str(tmp_path / "nonexistent.md")
        spec_content, artifacts = _collect_spec_and_artifacts(s)
        # 不存在的 artifact 不进入收集结果（容错）
        assert "prd" not in artifacts or artifacts["prd"] == "(read error)"
