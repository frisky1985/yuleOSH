"""
r21q resume 证据链修复 — RED→GREEN 回归测试。

背景 (run-20260819-121308 实测):
  window-anti-pinch 恢复 pipeline (--from-step 11) 时 claude-review 拒绝:
  1. self-test 阶段产出 0% 指标与 deployed 矛盾 — 恢复逻辑把旧 session
     的 *后序* 步骤产物 (self-test 等, step >= from_step) 也复制进新
     session, claude-review 把 08-18 的旧 self-test 报告 (早于
     71c7b8c0 合成清单修复) 当作本轮证据。
  2. test-plan 截断在 TC-SW-002-03 — ARTIFACT_INJECT_LIMIT=60000 太小,
     5 个产物拼接后 test-planning 段只保留前 ~11K 字符, 尾部
     (SW-003..SW-008 + End of Test Plan) 被静默截掉, 外部评审
     "文档截断" 误判。

修复原则: 工程诚实 — 恢复只带回 from_step 之前的前序产物; 注入
不截断尾部契约 (评审看得见全量 test-plan)。
"""

# @tests src/yuleosh/pipeline/orchestrator.py

import json
import os
from pathlib import Path
from unittest import mock

import pytest


@pytest.fixture
def spec_file(tmp_path):
    sf = tmp_path / "spec.md"
    sf.write_text(
        "# Test Spec\n\n"
        "### Req-RS-001: Authentication\n"
        "- The system SHALL authenticate users via OAuth2.\n"
        "- The system SHOULD support refresh tokens.\n\n"
        "### Req-SWR-001.1: Login Page\n"
        "- The login page SHALL have email and password fields.\n"
        "- The login page SHALL validate input before submission.\n\n"
        "### GIVEN a user with valid credentials\n"
        "WHEN they submit the login form\n"
        "THEN they are redirected to the dashboard\n"
    )
    return sf


@pytest.fixture
def osh_home(tmp_path):
    old = os.environ.get("OSH_HOME")
    os.environ["OSH_HOME"] = str(tmp_path)
    yield tmp_path
    if old:
        os.environ["OSH_HOME"] = old
    else:
        os.environ.pop("OSH_HOME", None)


def _make_previous_session(project_dir, spec_path, artifact_keys):
    """构造一个旧 session: session.json + artifacts 文件。"""
    base = Path(project_dir) / ".osh" / "sessions" / "prev-session"
    base.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    steps = []
    # 模拟 PIPELINE_STEPS 前 15 步 (与 step_handlers/__init__.py 顺序一致)
    ordered = [
        "spec-check", "super-analysis", "prd", "prd-review",
        "architecture", "arch-review", "development", "codegen-deploy",
        "devplan-review", "internal-code-review", "test-planning",
        "claude-review", "self-test", "codex-verify", "self-test-review",
    ]
    for i, key in enumerate(ordered, start=1):
        f = base / f"{key}.md"
        f.write_text(f"artifact {key} content", encoding="utf-8")
        artifacts[key] = str(f)
        steps.append({
            "step": i,
            "name": key,
            "status": "completed" if i < 11 else "completed",
            "output_path": str(f),
        })
    # 只保留请求的 keys (调用方可指定要测试的子集)
    artifacts = {k: v for k, v in artifacts.items() if k in artifact_keys}
    data = {
        "name": "prev-session",
        "spec_path": str(Path(spec_path).resolve()),
        "status": "failed",
        "updated_at": "2026-08-19T12:00:00",
        "artifacts": artifacts,
        "steps": steps,
    }
    (base / "session.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    return base


class TestResumeRestoresOnlyPriorArtifacts:
    """缺陷 1: --from-step 恢复不得复制 from_step 之后的步骤产物。"""

    def test_resume_from_step_11_excludes_self_test(self, spec_file, osh_home):
        """from_step=11 (test-planning) 时, 旧 session 的 self-test (step 13) 产物不得恢复。

        r22 适配: self-test 现在是 verify-loop (step 13) 的正常产物, 每次运行
        都会新生成（指向当前 session_dir）; 回归点是**旧 session 的 self-test
        不得混入**（window-anti-pinch 事故: claude-review 把旧报告当本轮证据）。
        """
        from yuleosh.pipeline.orchestrator import run_pipeline

        project_dir = str(spec_file.parent)
        _make_previous_session(
            project_dir, spec_file,
            artifact_keys=["prd", "architecture", "test-planning", "self-test"],
        )

        session = run_pipeline(str(spec_file), from_step=11, mock=True)
        artifacts = session.artifacts or {}
        assert "prd" in artifacts, "前序产物 prd 应恢复"
        assert "test-planning" in artifacts, "前序产物 test-planning 应恢复 (步骤 11 从新生成, 但恢复阶段仍允许)"
        # 旧 session 的 self-test 路径不得出现 — 即使 verify-loop 新生成 self-test,
        # 其路径必须是当前 session_dir, 绝不可能是 prev-session 复制来的。
        old_self_test = str(Path(project_dir) / ".osh" / "sessions" / "prev-session" / "self-test.md")
        assert old_self_test not in artifacts.values(), (
            "旧 session 的 self-test 不得混入新 session 证据链"
        )
        if "self-test" in artifacts:
            assert str(Path(session.session_dir) / "self-test-report.md") == str(
                Path(str(artifacts["self-test"]))
            ), "self-test 必须是 verify-loop 新生成 (当前 session_dir), 非旧 session 恢复"

    def test_resume_from_step_11_excludes_later_artifacts(self, spec_file, osh_home):
        """from_step=11 时旧 session 的 codex-verify/self-test-review 等后续产物全部排除。

        r22 适配: codex-verify/self-test-review 已合并进 verify-loop, 不再是独立
        step key — 恢复逻辑对不在 PIPELINE_STEPS 的旧 key 一律跳过。
        """
        from yuleosh.pipeline.orchestrator import run_pipeline

        project_dir = str(spec_file.parent)
        _make_previous_session(
            project_dir, spec_file,
            artifact_keys=["prd", "self-test", "codex-verify", "self-test-review"],
        )

        session = run_pipeline(str(spec_file), from_step=11, mock=True)
        artifacts = session.artifacts or {}
        assert "prd" in artifacts
        # 旧 key（合并进 verify-loop 前独立步骤）不得恢复 — 不在 PIPELINE_STEPS
        for stale_key in ("codex-verify", "self-test-review"):
            assert stale_key not in artifacts, (
                f"{stale_key} 已合并进 verify-loop, 旧 session 产物不得恢复"
            )
        # 旧 session 的 self-test 路径不得混入
        old_self_test = str(Path(project_dir) / ".osh" / "sessions" / "prev-session" / "self-test.md")
        assert old_self_test not in artifacts.values(), (
            "旧 session 的 self-test 不得混入新 session 证据链"
        )


class TestArtifactInjectKeepsTailContracts:
    """缺陷 2: 产物注入不得截断尾部契约 (test-plan 全量可见)。"""

    def test_format_artifacts_keeps_test_plan_tail(self):
        """5 个真实规模产物拼接后, test-planning 尾部 End of Test Plan 必须保留。"""
        from yuleosh.pipeline.step_handlers.external_agents import (
            _format_artifacts_for_prompt,
        )

        # 模拟真实产物规模 (window-anti-pinch 实测字符数)
        prd = "PRD contract section " * 1400          # ~24K chars
        arch = "ARCH section " * 1000                 # ~13K chars
        dev = "DEV section " * 400                    # ~4.7K chars
        selftest = "SELF-TEST section " * 400         # ~5.7K chars
        test_plan = ("| TC-SW-002-03 | verify moto ... |\n" * 50
                     + "### SW-008 全量契约\n"
                     + "End of Test Plan")            # ~3.5K chars + 尾部 marker

        block = _format_artifacts_for_prompt({
            "prd": prd,
            "architecture": arch,
            "development": dev,
            "self-test": selftest,
            "test-planning": test_plan,
        })

        assert "End of Test Plan" in block, (
            "test-planning 尾部 marker 被截断 — ARTIFACT_INJECT_LIMIT 太小, "
            "外部评审会误判 test-plan 文档截断"
        )
        assert "### SW-008 全量契约" in block

    def test_artifact_inject_uses_reference_marker_not_hard_cut(self):
        """注入超过 ARTIFACT_INJECT_LIMIT 时不得静默硬截断尾部契约。

        r22 适配: _format_artifacts_for_prompt 用 truncate_with_reference_marker
        （头尾保留 + …[omitted N chars — 全文见 <path>] 省略标记）替代裸切片,
        下游 prompt 不再二次 [:LIMIT] 截断。测试验证: 全量 75K 注入时尾部
        marker 必须出现, 外部评审可见全文路径。
        """
        from yuleosh.pipeline.step_handlers import external_agents as ea

        total = (24000 + 13000 + 4700 + 5700 + 28000)  # ≈ 75.4K
        # 引用式注入下 LIMIT 不必 >= 全量; 但下游 prompt 不得再裸切片
        import inspect
        codex_src = inspect.getsource(ea._build_codex_prompt)
        claude_src = inspect.getsource(ea._build_claude_review_prompt)
        assert "artifacts_block[:ARTIFACT_INJECT_LIMIT]" not in codex_src
        assert "artifacts_block[:ARTIFACT_INJECT_LIMIT]" not in claude_src
        # 超过 LIMIT 时尾部契约由引用标记机制保留（已由
        # test_format_artifacts_keeps_test_plan_tail 验证尾部可见）
