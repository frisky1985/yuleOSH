"""
A1-A4: agent 约束按角色隔离 — agent_registry + llm 层隔离注入测试。

覆盖：
  - AGENT_ROLES 角色分类映射
  - STEP_AGENT_MAP 生成（已知 step_key -> agent）
  - resolve_agent_for_step / resolve_agent_role 已知与未知
  - load_agent_constraints_by_role（xiaoke.md 只归小克、无目录返回空、
    不可归因文件跳过）
  - _build_effective_system_prompt 角色隔离（小克步骤只含小克约束不含
    小明；无角色文件 fallback 共享基线；去重标记生效）
  - 向后兼容（无 by_role 字段时走原 session.agent_constraints 路径）
"""

# @tests src/yuleosh/agent_registry.py

from types import SimpleNamespace
from unittest.mock import MagicMock

from yuleosh.agent_registry import (
    AGENT_ROLES,
    STEP_AGENT_MAP,
    get_step_agent_map,
    load_agent_constraints_by_role,
    resolve_agent_for_step,
    resolve_agent_role,
)
from yuleosh.pipeline.stages.llm import (
    _build_effective_system_prompt,
    _build_role_scoped_prompt,
    _call_llm,
)

# ═══════════════════════════════════════════════════════════════════
# AGENT_ROLES 角色分类
# ═══════════════════════════════════════════════════════════════════

class TestAgentRoles:
    def test_full_role_mapping(self):
        assert AGENT_ROLES["小明"] == "pm"
        assert AGENT_ROLES["小克"] == "developer"
        assert AGENT_ROLES["小马"] == "qa"
        assert AGENT_ROLES["Hermes"] == "requirements"
        assert AGENT_ROLES["Claude"] == "architect"
        assert AGENT_ROLES["QEMU"] == "tool"

    def test_roles_are_unique(self):
        """每个角色只对应一个 agent，反查无歧义。"""
        assert len(set(AGENT_ROLES.values())) == len(AGENT_ROLES)


# ═══════════════════════════════════════════════════════════════════
# STEP_AGENT_MAP 生成 + resolve_* 解析
# ═══════════════════════════════════════════════════════════════════

class TestStepAgentMap:
    def test_map_generation_known_pairs(self):
        """已知 step_key -> agent 断言（来源 PIPELINE_STEPS）。"""
        assert STEP_AGENT_MAP["spec-check"] == "小明"
        assert STEP_AGENT_MAP["prd"] == "Hermes"
        assert STEP_AGENT_MAP["architecture"] == "Claude"
        assert STEP_AGENT_MAP["arch-review"] == "小克"
        assert STEP_AGENT_MAP["misra-review"] == "小马"
        assert STEP_AGENT_MAP["qemu-verify"] == "小克"  # r22: qemu-run → qemu-verify (QEMU 仿真 + 覆盖率门禁合并)
        assert STEP_AGENT_MAP["merge-gate"] == "小仓"
        assert STEP_AGENT_MAP["final-report"] == "小明"

    def test_map_is_lazy_and_cached(self):
        first = get_step_agent_map()
        second = get_step_agent_map()
        assert first is second  # 缓存同一份
        assert "spec-check" in first

    def test_resolve_agent_for_step_known(self):
        assert resolve_agent_for_step("spec-check") == "小明"
        assert resolve_agent_for_step("arch-review") == "小克"

    def test_resolve_agent_for_step_unknown(self):
        assert resolve_agent_for_step("no-such-step") is None
        assert resolve_agent_for_step("") is None
        assert resolve_agent_for_step(None) is None

    def test_resolve_agent_role_known(self):
        assert resolve_agent_role("小明") == "pm"
        assert resolve_agent_role("小克") == "developer"
        assert resolve_agent_role("小马") == "qa"
        assert resolve_agent_role("QEMU") == "tool"

    def test_resolve_agent_role_unknown(self):
        assert resolve_agent_role("不存在") is None
        assert resolve_agent_role(None) is None


# ═══════════════════════════════════════════════════════════════════
# load_agent_constraints_by_role — 按文件名归角色
# ═══════════════════════════════════════════════════════════════════

class TestLoadConstraintsByRole:
    def test_xiaoke_md_only_goes_to_xiaoke(self, tmp_path):
        """xiaoke.md 只归小克（developer），不落入小明/小马。"""
        agents_dir = tmp_path / ".yuleosh" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "xiaoke.md").write_text("# 小克规则\n禁止提交未验证代码。", encoding="utf-8")

        by_role = load_agent_constraints_by_role(str(tmp_path))
        assert set(by_role.keys()) == {"developer"}
        assert "小克规则" in by_role["developer"]
        assert "禁止提交未验证代码" in by_role["developer"]

    def test_chinese_label_file(self, tmp_path):
        """中文标签 小克.md 同样归小克。"""
        agents_dir = tmp_path / ".yuleosh" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "小克.md").write_text("# 小克中文名规则", encoding="utf-8")

        by_role = load_agent_constraints_by_role(str(tmp_path))
        assert set(by_role.keys()) == {"developer"}
        assert "小克中文名规则" in by_role["developer"]

    def test_role_name_file(self, tmp_path):
        """qa.md 通过角色名反查归小马（qa）。"""
        agents_dir = tmp_path / ".yuleosh" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "qa.md").write_text("# QA 规则\n审查必须基于证据。", encoding="utf-8")

        by_role = load_agent_constraints_by_role(str(tmp_path))
        assert set(by_role.keys()) == {"qa"}
        assert "审查必须基于证据" in by_role["qa"]

    def test_multiple_files_grouped_by_role(self, tmp_path):
        """同角色多文件合并；不同角色分桶。"""
        agents_dir = tmp_path / ".yuleosh" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "xiaoke.md").write_text("DEV-A", encoding="utf-8")
        (agents_dir / "xiaoke-extra.md").write_text("DEV-B", encoding="utf-8")
        (agents_dir / "xiaoming.md").write_text("PM-A", encoding="utf-8")

        by_role = load_agent_constraints_by_role(str(tmp_path))
        assert set(by_role.keys()) == {"developer", "pm"}
        assert "DEV-A" in by_role["developer"]
        assert "DEV-B" in by_role["developer"]
        assert "PM-A" in by_role["pm"]

    def test_no_agents_dir_returns_empty(self, tmp_path):
        assert load_agent_constraints_by_role(str(tmp_path)) == {}

    def test_unattributable_files_skipped(self, tmp_path):
        """AGENTS.md / RULES.md 无法归因到单一角色 -> 跳过，不泄漏。"""
        agents_dir = tmp_path / ".yuleosh" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "AGENTS.md").write_text("混合规则", encoding="utf-8")
        (agents_dir / "RULES.md").write_text("通用规则", encoding="utf-8")

        assert load_agent_constraints_by_role(str(tmp_path)) == {}


# ═══════════════════════════════════════════════════════════════════
# _build_effective_system_prompt — 角色隔离注入
# ═══════════════════════════════════════════════════════════════════

def _role_session(step_key, by_role, baseline="SHARED-BASELINE"):
    return SimpleNamespace(
        pipeline_knowledge_step_key=step_key,
        agent_constraints_by_role=by_role,
        agent_shared_baseline=baseline,
        agent_constraints="LEGACY-CONSTRAINTS",
    )


class TestRoleIsolationPrompt:
    def test_xiaoke_step_only_gets_developer_constraints(self):
        """小克步骤（arch-review）只含 developer 约束 + 基线，不含小明/pm。"""
        session = _role_session(
            "arch-review",
            {"pm": "PM-RULES", "developer": "DEV-RULES"},
        )
        result = _build_effective_system_prompt(session, "You are a reviewer.")
        assert "DEV-RULES" in result
        assert "SHARED-BASELINE" in result
        assert "PM-RULES" not in result
        assert "You are a reviewer." in result
        assert "[End Agent Constraints]" in result

    def test_xiaoming_step_gets_pm_not_developer(self):
        """小明步骤（spec-check）只含 pm 约束，不含 developer。"""
        session = _role_session(
            "spec-check",
            {"pm": "PM-RULES", "developer": "DEV-RULES"},
        )
        result = _build_effective_system_prompt(session, "You are a PM.")
        assert "PM-RULES" in result
        assert "DEV-RULES" not in result

    def test_no_role_file_falls_back_to_shared_baseline(self):
        """Claude（architect）无角色文件 -> 只注入共享基线，绝不混入其他角色。"""
        session = _role_session(
            "architecture",
            {"pm": "PM-RULES", "developer": "DEV-RULES"},
        )
        result = _build_effective_system_prompt(session, "You are an architect.")
        assert "SHARED-BASELINE" in result
        assert "PM-RULES" not in result
        assert "DEV-RULES" not in result

    def test_unknown_step_falls_back_to_shared_baseline(self):
        """未知 step_key -> 只注入共享基线。"""
        session = _role_session(
            "mystery-step",
            {"pm": "PM-RULES"},
        )
        result = _build_effective_system_prompt(session, "sys")
        assert "SHARED-BASELINE" in result
        assert "PM-RULES" not in result

    def test_dedup_marker_unified_prefix(self):
        """system prompt 已含 '[Agent Constraints' 前缀 -> 不再重复注入。"""
        session = _role_session(
            "arch-review",
            {"developer": "DEV-RULES"},
        )
        already = "[Agent Constraints — role-scoped (developer)]\n\nDEV-RULES\n\n[End Agent Constraints]\n\nsys"
        result = _build_effective_system_prompt(session, already)
        assert result == already

    def test_legacy_marker_still_deduped(self):
        """旧标记 # AGENTS.md / # RULES.md 仍触发去重（向后兼容）。"""
        session = _role_session("arch-review", {"developer": "DEV-RULES"})
        for marker in ("# AGENTS.md\nold", "# RULES.md\nold"):
            assert _build_effective_system_prompt(session, marker) == marker

    def test_legacy_path_without_by_role(self):
        """无 by_role 字段（空 dict）-> 走原 session.agent_constraints 逻辑。"""
        from yuleosh.pipeline.session import PipelineSession

        session = PipelineSession(
            "legacy-test",
            "/tmp/spec.md",
            agent_constraints="# AGENTS.md\n小明: PM",
        )
        result = _build_effective_system_prompt(session, "Be a reviewer.")
        assert "[Agent Constraints" in result
        assert "小明: PM" in result
        assert "[End Agent Constraints]" in result
        assert "Be a reviewer." in result

    def test_legacy_path_empty_constraints_unchanged(self):
        from yuleosh.pipeline.session import PipelineSession

        session = PipelineSession("legacy-empty", "/tmp/spec.md")
        assert _build_effective_system_prompt(session, "sys") == "sys"

    def test_role_scoped_prompt_direct(self):
        session = _role_session(
            "misra-review",
            {"qa": "QA-RULES", "pm": "PM-RULES"},
        )
        result = _build_role_scoped_prompt(session, "sys", session.agent_constraints_by_role)
        assert "QA-RULES" in result
        assert "PM-RULES" not in result
        assert "role-scoped (qa)" in result


# ═══════════════════════════════════════════════════════════════════
# _call_llm 端到端：by_role 会话注入 + orchestrator 拆分冒烟
# ═══════════════════════════════════════════════════════════════════

class TestCallLlmRoleIsolation:
    def test_call_llm_injects_role_scoped_constraints(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.session import PipelineSession

        mock_client = MagicMock(return_value={"content": "ok", "model": "mock"})
        session = PipelineSession("role-llm", "/tmp/spec.md", llm_client=mock_client)
        session.mock_mode = True  # 跳过知识注入，保持确定性
        session.agent_constraints_by_role = {"pm": "PM-RULES", "developer": "DEV-RULES"}
        session.agent_shared_baseline = "SHARED-BASELINE"
        session.pipeline_knowledge_step_key = "arch-review"  # 小克 -> developer

        _call_llm(session, "Be a reviewer.", "Review the code.")

        call_system, call_user = mock_client.call_args[0]
        assert "DEV-RULES" in call_system
        assert "PM-RULES" not in call_system
        assert "SHARED-BASELINE" in call_system
        assert call_user == "Review the code."

    def test_orchestrator_split_components_present(self):
        """_DEFAULT_AGENT_SPEC 拆分为基线 + 角色默认，且保留向后兼容内容。"""
        from yuleosh.pipeline.orchestrator import (
            _AGENT_SAFE_BASELINE,
            _DEFAULT_AGENT_SPEC,
            DEFAULT_ROLE_SPECS,
        )

        assert set(DEFAULT_ROLE_SPECS.keys()) == {"pm", "developer", "qa"}
        assert "审计诚信" in _AGENT_SAFE_BASELINE
        assert "不静默降质" in _AGENT_SAFE_BASELINE
        assert "Default Agent Spec" in _DEFAULT_AGENT_SPEC
        assert "Roles" in _DEFAULT_AGENT_SPEC
        assert "Core Rules" in _DEFAULT_AGENT_SPEC
        # 组合 = 基线 + 各角色默认（拆分后指向组合）
        assert _AGENT_SAFE_BASELINE.strip() in _DEFAULT_AGENT_SPEC
        assert "PM 角色默认规则" in _DEFAULT_AGENT_SPEC
        assert "Developer 角色默认规则" in _DEFAULT_AGENT_SPEC
        assert "QA 角色默认规则" in _DEFAULT_AGENT_SPEC
