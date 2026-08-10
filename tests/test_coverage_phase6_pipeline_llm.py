"""Phase 6 coverage boost — pipeline/llm 域 3 个 0% 覆盖文件。

Target modules (Phase 6 baseline, 2026-08-10):
  - src/yuleosh/pipeline/knowledge_injection.py    0.0%  → 配置解析/各知识源装配/总预算截断
  - src/yuleosh/pipeline/step_classes.py           0.0%  → 6 个步骤类 build_prompts/process_result/
                                                            DevelopmentStep 双模式 __call__
  - src/yuleosh/llm/provider_fallback.py           0.0%  → 回退链解析/provider 可用性/异常分类/
                                                            call_with_fallback 全分支/事件审计

风格：类组织 + 详细 docstring（与 tests/test_coverage_phase6_ci.py 一致）。
所有 LLM/外部调用均用 unittest.mock 打补丁，不碰网络、不调真实 API；
异步入口统一用 ``asyncio.run`` 包一层，不依赖 pytest-asyncio 的全局模式。
"""

import asyncio
import json
import os
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from yuleosh.llm.provider_fallback import (
    DEFAULT_FALLBACK_ORDER,
    FallbackEvent,
    _classify_reason,
    _flush_events,
    _http_code,
    _parse_order,
    _reason_for_code,
    call_with_fallback,
    fallback_enabled,
    is_fallback_eligible,
    provider_available,
    resolve_fallback_order,
)
from yuleosh.llm.providers.base import LLMConfig, LLMResponse

# =====================================================================
# 公共辅助
# =====================================================================


class _FakeProvider:
    """最小 provider 双胞胎：可配置失败异常 / skeleton 标记 / 调用记录。"""

    def __init__(self, name, fail_with=None, skeleton=False):
        self.name = name
        self.fail_with = fail_with
        self.is_skeleton = skeleton
        self.calls = []

    async def chat(self, messages, config):
        self.calls.append(self.name)
        if self.fail_with is not None:
            raise self.fail_with
        return LLMResponse(
            content=f"ok:{self.name}",
            model=config.model,
            provider=self.name,
            token_usage={"prompt": 1, "completion": 1, "total": 2},
            cost=0.001,
        )


def _make_factory(specs, fail_names=()):
    """由 {name: _FakeProvider} 生成 provider_factory；fail_names 中的名字实例化即抛错。"""

    def factory(name):
        if name in fail_names:
            raise LookupError(f"cannot instantiate {name}")
        return specs[name]

    return factory


def _no_key_env():
    """清空所有 provider API key 环境变量（保证 no_key 分支确定性）。"""
    return mock.patch.dict(
        os.environ,
        {
            "DEEPSEEK_API_KEY": "",
            "LLM_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY": "",
        },
        clear=False,
    )


def _key_env():
    """设置 deepseek 的 API key（保证 deepseek 会被真正尝试调用）。"""
    return mock.patch.dict(
        os.environ,
        {"DEEPSEEK_API_KEY": "test-key", "LLM_API_KEY": "test-key"},
        clear=False,
    )


def _flaky_read_text(bad_marker="bad"):
    """让路径含 bad_marker 的 read_text 抛 OSError，其余走真实实现。"""
    real_read = Path.read_text

    def flaky(self, *args, **kwargs):
        if bad_marker in str(self):
            raise OSError(f"boom: {self}")
        return real_read(self, *args, **kwargs)

    return mock.patch.object(Path, "read_text", flaky)


# =====================================================================
# knowledge_injection.py — 配置解析
# =====================================================================


class TestPipelineKnowledgeConfig:
    """PipelineKnowledgeConfig 默认值 / from_dict / 配置文件加载。"""

    def test_defaults(self):
        from yuleosh.pipeline.knowledge_injection import (
            DEFAULT_MAX_CHARS,
            PipelineKnowledgeConfig,
        )

        cfg = PipelineKnowledgeConfig()
        assert cfg.inject_memory is True
        assert cfg.inject_rag is True
        assert cfg.inject_skills is True
        assert cfg.inject_active is True
        assert cfg.inject_pending is False
        assert cfg.max_chars == DEFAULT_MAX_CHARS
        assert cfg.rag_sources is None
        assert cfg.skills == []
        assert cfg.skills_by_step == {}
        assert cfg.memory_max_chars == 1500
        assert cfg.rag_max_chars == 1500

    def test_from_dict_none_and_empty(self):
        from yuleosh.pipeline.knowledge_injection import PipelineKnowledgeConfig

        assert PipelineKnowledgeConfig.from_dict(None) == PipelineKnowledgeConfig()
        assert PipelineKnowledgeConfig.from_dict({}) == PipelineKnowledgeConfig()
        assert PipelineKnowledgeConfig.from_dict("not-a-dict") == PipelineKnowledgeConfig()

    def test_from_dict_full(self):
        from yuleosh.pipeline.knowledge_injection import PipelineKnowledgeConfig

        cfg = PipelineKnowledgeConfig.from_dict(
            {
                "inject_memory": False,
                "inject_rag": False,
                "inject_skills": False,
                "inject_active": False,
                "inject_pending": True,
                "max_chars": 500,
                "rag_sources": ["misra"],
                "skills": ["autosar-coding"],
                "skills_by_step": {"development": ["x"]},
                "memory_max_chars": 100,
                "rag_max_chars": 200,
            }
        )
        assert cfg.inject_memory is False
        assert cfg.inject_pending is True
        assert cfg.max_chars == 500
        assert cfg.rag_sources == ["misra"]
        assert cfg.skills == ["autosar-coding"]
        assert cfg.skills_by_step == {"development": ["x"]}
        assert cfg.memory_max_chars == 100
        assert cfg.rag_max_chars == 200

    def test_from_dict_falsy_values_fall_back_to_defaults(self):
        from yuleosh.pipeline.knowledge_injection import (
            DEFAULT_MAX_CHARS,
            PipelineKnowledgeConfig,
        )

        cfg = PipelineKnowledgeConfig.from_dict(
            {
                "max_chars": 0,
                "memory_max_chars": None,
                "rag_max_chars": "",
                "rag_sources": [],
                "skills": None,
                "skills_by_step": None,
            }
        )
        assert cfg.max_chars == DEFAULT_MAX_CHARS
        assert cfg.memory_max_chars == 1500
        assert cfg.rag_max_chars == 1500
        assert cfg.rag_sources is None
        assert cfg.skills == []
        assert cfg.skills_by_step == {}

    def test_load_config_missing_file_returns_defaults(self, tmp_path):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            load_pipeline_knowledge_config,
        )

        cfg = load_pipeline_knowledge_config(tmp_path)
        assert cfg == PipelineKnowledgeConfig()

    def test_load_config_parses_yaml(self, tmp_path):
        from yuleosh.pipeline.knowledge_injection import (
            load_pipeline_knowledge_config,
        )

        conf_dir = tmp_path / ".yuleosh"
        conf_dir.mkdir()
        (conf_dir / "pipeline-knowledge.yaml").write_text(
            "inject_memory: false\nmax_chars: 321\nskills:\n  - s1\n",
            encoding="utf-8",
        )
        cfg = load_pipeline_knowledge_config(tmp_path)
        assert cfg.inject_memory is False
        assert cfg.max_chars == 321
        assert cfg.skills == ["s1"]

    def test_load_config_bad_yaml_returns_defaults(self, tmp_path, caplog):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            load_pipeline_knowledge_config,
        )

        conf_dir = tmp_path / ".yuleosh"
        conf_dir.mkdir()
        (conf_dir / "pipeline-knowledge.yaml").write_text(
            "::: not: [valid yaml", encoding="utf-8"
        )
        cfg = load_pipeline_knowledge_config(tmp_path)
        assert cfg == PipelineKnowledgeConfig()
        assert "unreadable" in caplog.text


# =====================================================================
# knowledge_injection.py — 各知识源装配
# =====================================================================


class TestKnowledgeInjectionSources:
    """_resolve_skill_names / _sync_rag_context / 四个 _assemble_* 助手。"""

    def test_resolve_skill_names_merges_per_step_then_global_dedup(self):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            _resolve_skill_names,
        )

        cfg = PipelineKnowledgeConfig(
            skills=["a", "c"],
            skills_by_step={"dev": ["b", "a"]},
        )
        assert _resolve_skill_names("dev", cfg) == ["b", "a", "c"]
        assert _resolve_skill_names("other", cfg) == ["a", "c"]
        # 空配置 → 空列表
        assert _resolve_skill_names("dev", PipelineKnowledgeConfig()) == []

    def test_sync_rag_context_uses_explicit_engine(self):
        from yuleosh.pipeline.knowledge_injection import _sync_rag_context

        engine = SimpleNamespace(
            retrieve_as_context=mock.AsyncMock(return_value="rag-body")
        )
        result = _sync_rag_context("q", ["s1"], rag_engine=engine, top_k=3)
        assert result == "rag-body"
        engine.retrieve_as_context.assert_awaited_once_with(
            "q", sources=["s1"], top_k=3
        )

    def test_sync_rag_context_default_engine(self):
        from yuleosh.pipeline.knowledge_injection import _sync_rag_context

        engine = SimpleNamespace(
            retrieve_as_context=mock.AsyncMock(return_value="ctx")
        )
        with mock.patch(
            "yuleosh.llm.rag.engine.get_default_engine", return_value=engine
        ):
            assert _sync_rag_context("q", None) == "ctx"

    def test_sync_rag_context_running_loop_degrades(self):
        from yuleosh.pipeline.knowledge_injection import _sync_rag_context

        engine = SimpleNamespace(
            retrieve_as_context=mock.AsyncMock(
                side_effect=RuntimeError("loop already running")
            )
        )
        assert _sync_rag_context("q", None, rag_engine=engine) == ""

    def test_sync_rag_context_generic_failure_degrades(self):
        from yuleosh.pipeline.knowledge_injection import _sync_rag_context

        engine = SimpleNamespace(
            retrieve_as_context=mock.AsyncMock(side_effect=ValueError("nope"))
        )
        assert _sync_rag_context("q", None, rag_engine=engine) == ""

    def test_assemble_memory_success(self):
        from yuleosh.pipeline.knowledge_injection import (
            MEMORY_HEADER,
            PipelineKnowledgeConfig,
            _assemble_memory,
        )

        with mock.patch(
            "yuleosh.memory.llm_context.assemble_memory_context",
            return_value="mem-facts",
        ) as amc:
            out = _assemble_memory("prompt", PipelineKnowledgeConfig())
            amc.assert_called_once_with(query="prompt", max_chars=1500)
            assert out == f"{MEMORY_HEADER}\n\nmem-facts"

    def test_assemble_memory_empty_and_failure(self):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            _assemble_memory,
        )

        with mock.patch(
            "yuleosh.memory.llm_context.assemble_memory_context",
            return_value="",
        ):
            assert _assemble_memory("p", PipelineKnowledgeConfig()) == ""
        with mock.patch(
            "yuleosh.memory.llm_context.assemble_memory_context",
            side_effect=RuntimeError("mem broken"),
        ):
            assert _assemble_memory("p", PipelineKnowledgeConfig()) == ""

    def test_assemble_rag_disabled(self):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            _assemble_rag,
        )

        cfg = PipelineKnowledgeConfig(inject_rag=False)
        assert _assemble_rag("p", cfg) == ""

    def test_assemble_rag_success_and_header_normalization(self):
        from yuleosh.pipeline.knowledge_injection import (
            RAG_HEADER,
            PipelineKnowledgeConfig,
            _assemble_rag,
        )

        cfg = PipelineKnowledgeConfig()
        with mock.patch(
            "yuleosh.pipeline.knowledge_injection._sync_rag_context",
            return_value="plain ctx",
        ):
            assert _assemble_rag("p", cfg) == f"{RAG_HEADER}\nplain ctx"

        with mock.patch(
            "yuleosh.pipeline.knowledge_injection._sync_rag_context",
            return_value="## Knowledge Context (RAG)\nnormalized body",
        ):
            assert _assemble_rag("p", cfg) == f"{RAG_HEADER}\nnormalized body"

        # 只有旧 header 没有正文 → 只剩我们的 header
        with mock.patch(
            "yuleosh.pipeline.knowledge_injection._sync_rag_context",
            return_value="## Knowledge Context (RAG)",
        ):
            assert _assemble_rag("p", cfg) == RAG_HEADER

    def test_assemble_rag_empty_and_failure(self):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            _assemble_rag,
        )

        cfg = PipelineKnowledgeConfig()
        with mock.patch(
            "yuleosh.pipeline.knowledge_injection._sync_rag_context",
            return_value="",
        ):
            assert _assemble_rag("p", cfg) == ""
        with mock.patch(
            "yuleosh.pipeline.knowledge_injection._sync_rag_context",
            side_effect=RuntimeError("rag broken"),
        ):
            assert _assemble_rag("p", cfg) == ""

    def test_assemble_skills_disabled_and_no_names(self):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            _assemble_skills,
        )

        assert _assemble_skills("dev", PipelineKnowledgeConfig(inject_skills=False)) == ""
        assert _assemble_skills("dev", PipelineKnowledgeConfig()) == ""

    def test_assemble_skills_success(self):
        from yuleosh.pipeline.knowledge_injection import (
            SKILLS_HEADER,
            PipelineKnowledgeConfig,
            _assemble_skills,
        )

        cfg = PipelineKnowledgeConfig(skills=["autosar-coding"])
        with mock.patch(
            "yuleosh.skills.prompt.render_skills", return_value="skill block"
        ) as rs:
            out = _assemble_skills("dev", cfg)
            rs.assert_called_once_with(["autosar-coding"])
            assert out == f"{SKILLS_HEADER}\n\nskill block"

    def test_assemble_skills_empty_render_and_failure(self):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            _assemble_skills,
        )

        cfg = PipelineKnowledgeConfig(skills=["x"])
        with mock.patch("yuleosh.skills.prompt.render_skills", return_value=""):
            assert _assemble_skills("dev", cfg) == ""
        with mock.patch(
            "yuleosh.skills.prompt.render_skills",
            side_effect=RuntimeError("skills broken"),
        ):
            assert _assemble_skills("dev", cfg) == ""

    def test_assemble_active_disabled(self):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            _assemble_active,
        )

        assert (
            _assemble_active(
                PipelineKnowledgeConfig(inject_active=False), "/tmp/proj"
            )
            == ""
        )

    def test_assemble_active_success_with_pending(self, tmp_path):
        from yuleosh.pipeline.knowledge_injection import (
            ACTIVE_HEADER,
            PipelineKnowledgeConfig,
            _assemble_active,
        )

        indexer = mock.Mock()
        indexer.list_active.return_value = [
            {"kind": "lesson", "content": "  alpha  "},
            {"kind": "knowledge", "content": "   "},  # 空白内容被过滤
        ]
        indexer.list_pending.return_value = [{"kind": "article", "content": "beta"}]
        with mock.patch(
            "yuleosh.knowledge.indexer.KnowledgeIndexer", return_value=indexer
        ):
            out = _assemble_active(
                PipelineKnowledgeConfig(inject_pending=True), tmp_path
            )
        assert out == (
            f"{ACTIVE_HEADER}\n\n"
            "- [lesson] alpha\n"
            "- [pending-review][article] beta"
        )

    def test_assemble_active_no_pending_flag(self, tmp_path):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            _assemble_active,
        )

        indexer = mock.Mock()
        indexer.list_active.return_value = [{"kind": "lesson", "content": "alpha"}]
        indexer.list_pending.return_value = [{"kind": "article", "content": "beta"}]
        with mock.patch(
            "yuleosh.knowledge.indexer.KnowledgeIndexer", return_value=indexer
        ):
            out = _assemble_active(PipelineKnowledgeConfig(), tmp_path)
        assert "pending-review" not in out
        assert "- [lesson] alpha" in out

    def test_assemble_active_empty_and_import_error_and_failure(self, tmp_path):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            _assemble_active,
        )

        cfg = PipelineKnowledgeConfig()
        indexer = mock.Mock()
        indexer.list_active.return_value = []
        with mock.patch(
            "yuleosh.knowledge.indexer.KnowledgeIndexer", return_value=indexer
        ):
            assert _assemble_active(cfg, tmp_path) == ""

        with mock.patch(
            "yuleosh.knowledge.indexer.KnowledgeIndexer",
            side_effect=ImportError("no module"),
        ):
            assert _assemble_active(cfg, tmp_path) == ""

        indexer.list_active.side_effect = RuntimeError("indexer broken")
        with mock.patch(
            "yuleosh.knowledge.indexer.KnowledgeIndexer", return_value=indexer
        ):
            assert _assemble_active(cfg, tmp_path) == ""


# =====================================================================
# knowledge_injection.py — 总装配
# =====================================================================


class TestAssemblePipelineKnowledge:
    """assemble_pipeline_knowledge：来源开关、配置装载、总预算截断。"""

    def test_all_sources_joined(self):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            assemble_pipeline_knowledge,
        )

        cfg = PipelineKnowledgeConfig(max_chars=4000)
        with (
            mock.patch(
                "yuleosh.pipeline.knowledge_injection._assemble_memory",
                return_value="## Pipeline Memory\n\nm",
            ),
            mock.patch(
                "yuleosh.pipeline.knowledge_injection._assemble_rag",
                return_value="## Pipeline RAG Context\nr",
            ),
            mock.patch(
                "yuleosh.pipeline.knowledge_injection._assemble_skills",
                return_value="## Pipeline Skills\ns",
            ),
            mock.patch(
                "yuleosh.pipeline.knowledge_injection._assemble_active",
                return_value="## Active Knowledge\na",
            ),
        ):
            out = assemble_pipeline_knowledge(
                step_key="dev",
                prompt="p",
                config=cfg,
                project_dir="/proj",
            )
        assert "## Pipeline Memory" in out
        assert "## Pipeline RAG Context" in out
        assert "## Pipeline Skills" in out
        assert "## Active Knowledge" in out

    def test_all_disabled_returns_empty(self):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            assemble_pipeline_knowledge,
        )

        cfg = PipelineKnowledgeConfig(
            inject_memory=False,
            inject_rag=False,
            inject_skills=False,
            inject_active=False,
        )
        assert assemble_pipeline_knowledge(step_key="dev", config=cfg) == ""

    def test_project_dir_triggers_active_section(self, tmp_path):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            assemble_pipeline_knowledge,
        )

        with mock.patch(
            "yuleosh.pipeline.knowledge_injection._assemble_active",
            return_value="## Active Knowledge\nx",
        ) as aa:
            out = assemble_pipeline_knowledge(
                step_key="dev",
                config=PipelineKnowledgeConfig(inject_memory=False, inject_rag=False, inject_skills=False),
                project_dir=str(tmp_path),
            )
            aa.assert_called_once()
            assert out == "## Active Knowledge\nx"

    def test_config_none_loads_from_project_dir(self, tmp_path):
        from yuleosh.pipeline.knowledge_injection import (
            assemble_pipeline_knowledge,
        )

        conf_dir = tmp_path / ".yuleosh"
        conf_dir.mkdir()
        (conf_dir / "pipeline-knowledge.yaml").write_text(
            "inject_memory: false\ninject_rag: false\ninject_skills: false\ninject_active: false\n",
            encoding="utf-8",
        )
        # 配置文件把全部来源关掉 → 空输出，证明配置确实被加载
        assert (
            assemble_pipeline_knowledge(step_key="dev", project_dir=str(tmp_path))
            == ""
        )

    def test_config_none_without_project_dir_uses_defaults(self):
        from yuleosh.pipeline.knowledge_injection import (
            assemble_pipeline_knowledge,
        )

        with mock.patch(
            "yuleosh.pipeline.knowledge_injection._assemble_memory",
            return_value="m",
        ):
            out = assemble_pipeline_knowledge(step_key="dev", prompt="p")
        assert out == "m"

    def test_truncation_appends_marker(self):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            assemble_pipeline_knowledge,
        )

        cfg = PipelineKnowledgeConfig(max_chars=10, inject_active=False)
        with mock.patch(
            "yuleosh.pipeline.knowledge_injection._assemble_memory",
            return_value="memory-section-long",
        ):
            out = assemble_pipeline_knowledge(step_key="dev", config=cfg)
        assert out.endswith("…[knowledge context truncated by max_chars]")
        assert len(out) > 10

    def test_no_truncation_within_budget(self):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            assemble_pipeline_knowledge,
        )

        cfg = PipelineKnowledgeConfig(max_chars=4000, inject_active=False)
        with mock.patch(
            "yuleosh.pipeline.knowledge_injection._assemble_memory",
            return_value="short",
        ):
            out = assemble_pipeline_knowledge(step_key="dev", config=cfg)
        assert out == "short"
        assert "truncated" not in out


# =====================================================================
# step_classes.py — 注册表 & 元数据
# =====================================================================


class TestStepRegistry:
    """STEP_CLASSES / get_step_instance / register_step。"""

    def test_step_classes_map_has_all_six_steps(self):
        from yuleosh.pipeline.step_classes import STEP_CLASSES

        assert set(STEP_CLASSES) == {
            "super-analysis",
            "prd",
            "architecture",
            "development",
            "test-planning",
            "code-review",
        }
        assert STEP_CLASSES["development"].step_key == "development"

    def test_step_metadata(self):
        from yuleosh.pipeline.step_classes import STEP_CLASSES

        assert STEP_CLASSES["super-analysis"].agent == "小明"
        assert STEP_CLASSES["prd"].description == "产品需求分析"
        assert STEP_CLASSES["architecture"].output_filename == "architecture.md"
        assert STEP_CLASSES["development"].max_tokens == 4096
        assert STEP_CLASSES["test-planning"].output_filename == "test-plan.md"
        assert STEP_CLASSES["code-review"].output_filename == "code-review.json"

    def test_get_step_instance_hit_and_miss(self):
        from yuleosh.pipeline.step_classes import (
            get_step_instance,
        )

        assert get_step_instance("development") is not None
        assert get_step_instance("does-not-exist") is None

    def test_register_step(self):
        from yuleosh.pipeline.step_classes import (
            STEP_CLASSES,
            get_step_instance,
            register_step,
        )

        custom = mock.Mock()
        custom.step_key = "custom"
        register_step("custom", custom)
        try:
            assert get_step_instance("custom") is custom
        finally:
            STEP_CLASSES.pop("custom", None)

    def test_artifact_keys(self):
        from yuleosh.pipeline.step_classes import STEP_CLASSES

        assert STEP_CLASSES["prd"]._artifact_keys() == ["super-analysis"]
        assert STEP_CLASSES["architecture"]._artifact_keys() == []
        assert STEP_CLASSES["development"]._artifact_keys() == [
            "architecture",
            "prd",
            "super-analysis",
        ]
        assert STEP_CLASSES["test-planning"]._artifact_keys() == [
            "architecture",
            "development",
        ]
        assert "self-test" in STEP_CLASSES["code-review"]._artifact_keys()

    def test_icons(self):
        from yuleosh.pipeline.step_classes import STEP_CLASSES

        assert STEP_CLASSES["super-analysis"]._icon() == "📊"
        assert STEP_CLASSES["prd"]._icon() == "🔮"
        assert STEP_CLASSES["architecture"]._icon() == "💻"
        assert STEP_CLASSES["development"]._icon() == "💻"
        assert STEP_CLASSES["test-planning"]._icon() == "📋"
        assert STEP_CLASSES["code-review"]._icon() == "🔮"


# =====================================================================
# step_classes.py — build_prompts
# =====================================================================


def _make_session(spec_path, name="s1", **extra):
    """构造 build_prompts 所需的最小 session 假对象。"""
    return SimpleNamespace(spec_path=str(spec_path), name=name, **extra)


class TestStepBuildPrompts:
    """各步骤 build_prompts：prompt builder 调用参数透传。"""

    def test_super_analysis_build_prompts(self, tmp_path):
        from yuleosh.pipeline.step_classes import SuperAnalysisStep

        spec = tmp_path / "spec.md"
        spec.write_text("# spec", encoding="utf-8")
        session = _make_session(spec)
        parsed = {"requirements": [{"id": "R1"}], "scenarios": ["S1"]}
        with mock.patch(
            "yuleosh.pipeline.prompts.build_super_analysis_prompt",
            return_value=("sys", "user"),
        ) as bp:
            out = SuperAnalysisStep().build_prompts(
                session, "content", parsed, {}
            )
        assert out == ("sys", "user")
        bp.assert_called_once_with(
            spec_content="content",
            spec_name="spec.md",
            requirements=[{"id": "R1"}],
            scenarios=["S1"],
        )

    def test_prd_build_prompts_passes_super_analysis(self, tmp_path):
        from yuleosh.pipeline.step_classes import PrdStep

        spec = tmp_path / "spec.md"
        spec.write_text("# spec", encoding="utf-8")
        session = _make_session(spec)
        parsed = {"requirements": [], "scenarios": []}
        with mock.patch(
            "yuleosh.pipeline.prompts.build_prd_prompt",
            return_value=("sys", "user"),
        ) as bp:
            PrdStep().build_prompts(
                session, "content", parsed, {"super-analysis": "sa"}
            )
        bp.assert_called_once()
        assert bp.call_args.kwargs["super_analysis_content"] == "sa"

    def test_architecture_build_prompts_without_src(self, tmp_path):
        from yuleosh.pipeline.step_classes import ArchitectureStep

        spec = tmp_path / "spec.md"
        spec.write_text("# spec", encoding="utf-8")
        session = _make_session(spec)
        parsed = {"requirements": [], "scenarios": []}
        with (
            mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}, clear=False),
            mock.patch(
                "yuleosh.pipeline.prompts.build_architecture_prompt",
                return_value=("sys", "user"),
            ) as bp,
        ):
            out = ArchitectureStep().build_prompts(
                session, "content", parsed, {}
            )
        assert out == ("sys", "user")
        assert bp.call_args.kwargs["directories"] == []
        assert bp.call_args.kwargs["source_files"] == []
        assert bp.call_args.kwargs["tech_stack"] == []
        assert bp.call_args.kwargs["source_tree_str"] == ""

    def test_architecture_build_prompts_scans_src(self, tmp_path):
        from yuleosh.pipeline.step_classes import ArchitectureStep

        spec = tmp_path / "spec.md"
        spec.write_text("# spec", encoding="utf-8")
        src = tmp_path / "src"
        (src / "sub").mkdir(parents=True)
        (src / "app.py").write_text("x = 1\n", encoding="utf-8")
        (src / "sub" / "main.go").write_text("package main\n", encoding="utf-8")
        (src / "page.html").write_text("<html></html>\n", encoding="utf-8")
        (src / ".hidden").mkdir(parents=True)
        (src / ".hidden" / "secret.py").write_text("hidden\n", encoding="utf-8")
        (src / "__pycache__").mkdir(parents=True)
        (src / "__pycache__" / "c.py").write_text("cache\n", encoding="utf-8")
        (src / "big.rs").write_text("z" * 20000, encoding="utf-8")  # >10KB 跳过
        (src / "note.txt").write_text("ignore me\n", encoding="utf-8")  # 非代码扩展名
        (src / "run.sh").write_text("#!/bin/sh\necho hi\n", encoding="utf-8")

        session = _make_session(spec)
        parsed = {"requirements": [], "scenarios": []}
        with (
            mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}, clear=False),
            mock.patch(
                "yuleosh.pipeline.prompts.build_architecture_prompt",
                return_value=("sys", "user"),
            ) as bp,
        ):
            ArchitectureStep().build_prompts(session, "content", parsed, {})
        kwargs = bp.call_args.kwargs
        assert "src/app.py" in kwargs["source_files"]
        assert "src/sub/main.go" in kwargs["source_files"]
        assert "src/page.html" in kwargs["source_files"]
        assert "src/big.rs" in kwargs["source_files"]  # .rs 是合法源码扩展名
        assert not any("secret" in f or "cache" in f for f in kwargs["source_files"])
        assert set(kwargs["tech_stack"]) == {
            "Python", "Go", "Web (HTML/JS/CSS)", "Rust", "Shell",
        }
        # key_file_snippets：只有小文件被读取；big.rs 因体积被跳过
        snippets = "".join(kwargs["key_file_snippets"])
        assert "### src/app.py" in snippets
        assert "big.rs" not in snippets

    def test_architecture_build_prompts_read_failure_is_non_fatal(self, tmp_path):
        from yuleosh.pipeline.step_classes import ArchitectureStep

        spec = tmp_path / "spec.md"
        spec.write_text("# spec", encoding="utf-8")
        src = tmp_path / "src"
        src.mkdir()
        (src / "bad.py").write_text("boom\n", encoding="utf-8")

        session = _make_session(spec)
        parsed = {"requirements": [], "scenarios": []}
        with (
            mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}, clear=False),
            _flaky_read_text(),
            mock.patch(
                "yuleosh.pipeline.prompts.build_architecture_prompt",
                return_value=("sys", "user"),
            ) as bp,
        ):
            out = ArchitectureStep().build_prompts(session, "c", parsed, {})
        assert out == ("sys", "user")
        # bad.py 读失败 → 不进 snippets，但步骤继续
        assert bp.call_args.kwargs["key_file_snippets"] == []

    def test_test_planning_build_prompts(self, tmp_path):
        from yuleosh.pipeline.step_classes import TestPlanningStep

        spec = tmp_path / "spec.md"
        spec.write_text("# spec", encoding="utf-8")
        session = _make_session(spec)
        parsed = {"requirements": [{"id": "R1"}], "scenarios": []}
        with mock.patch(
            "yuleosh.pipeline.prompts.build_test_planning_prompt",
            return_value=("sys", "user"),
        ) as bp:
            TestPlanningStep().build_prompts(
                session, "c", parsed, {"architecture": "a", "development": "d"}
            )
        bp.assert_called_once()
        assert bp.call_args.kwargs["architecture_content"] == "a"
        assert bp.call_args.kwargs["development_plan_content"] == "d"

    def test_code_review_build_prompts_scans_src(self, tmp_path):
        from yuleosh.pipeline.step_classes import HermesReviewStep

        spec = tmp_path / "spec.md"
        spec.write_text("# spec", encoding="utf-8")
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("x = 1\n" * 10, encoding="utf-8")
        (src / "big.py").write_text("y" * 30000, encoding="utf-8")  # >20KB → 空内容
        (src / "note.txt").write_text("nope", encoding="utf-8")  # 非 .py 忽略

        session = _make_session(spec, name="review-session")
        parsed = {"requirements": [], "scenarios": []}
        with (
            mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}, clear=False),
            mock.patch(
                "yuleosh.pipeline.prompts.build_code_review_prompt",
                return_value=("sys", "user"),
            ) as bp,
        ):
            out = HermesReviewStep().build_prompts(session, "c", parsed, {})
        assert out == ("sys", "user")
        files = bp.call_args.kwargs["source_files"]
        assert len(files) == 2
        by_path = {f["path"]: f for f in files}
        assert by_path["src/a.py"]["lines"] == 10
        assert by_path["src/big.py"]["content"] == ""
        assert bp.call_args.kwargs["session_name"] == "review-session"

    def test_code_review_build_prompts_without_src(self, tmp_path):
        from yuleosh.pipeline.step_classes import HermesReviewStep

        spec = tmp_path / "spec.md"
        spec.write_text("# spec", encoding="utf-8")
        session = _make_session(spec, name="s1")
        parsed = {"requirements": [], "scenarios": []}
        with (
            mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}, clear=False),
            mock.patch(
                "yuleosh.pipeline.prompts.build_code_review_prompt",
                return_value=("sys", "user"),
            ) as bp,
        ):
            out = HermesReviewStep().build_prompts(session, "c", parsed, {})
        assert out == ("sys", "user")
        assert bp.call_args.kwargs["source_files"] == []


# =====================================================================
# step_classes.py — ArchitectureStep / HermesReviewStep process_result
# =====================================================================


class TestProcessResult:
    """process_result 覆盖：architecture 原样透传，code-review JSON 规范化。"""

    def test_architecture_process_result_passthrough(self, tmp_path):
        from yuleosh.pipeline.step_classes import ArchitectureStep

        session = _make_session(tmp_path / "spec.md")
        assert ArchitectureStep().process_result(session, "raw", {}) == "raw"

    def test_code_review_process_result_valid_json(self, tmp_path):
        from yuleosh.pipeline.step_classes import HermesReviewStep

        session = _make_session(tmp_path / "spec.md", name="rs")
        content = json.dumps({"findings": [{"severity": "minor"}]}, ensure_ascii=False)
        out = HermesReviewStep().process_result(session, content, {})
        parsed = json.loads(out)
        assert parsed["session"] == "rs"
        assert parsed["reviewer"] == "Hermes"
        assert parsed["timestamp"]
        assert parsed["status"] == "passed"
        assert parsed["findings"] == [{"severity": "minor"}]
        assert parsed["finding_breakdown"] == {
            "critical": 0, "major": 0, "minor": 0, "info": 0,
        }

    def test_code_review_process_result_garbage_input(self, tmp_path):
        from yuleosh.pipeline.step_classes import HermesReviewStep

        session = _make_session(tmp_path / "spec.md", name="rs")
        out = HermesReviewStep().process_result(session, "not json at all", {})
        parsed = json.loads(out)
        assert parsed["session"] == "rs"
        # 真实解析器对垃圾输入返回结构化 reviewer-error finding
        assert parsed["findings"][0]["category"] == "reviewer-error"
        assert parsed["summary"] != ""


# =====================================================================
# step_classes.py — DevelopmentStep 双模式
# =====================================================================


class TestDevelopmentStep:
    """DevelopmentStep：构造参数、模式解析、build_prompts、planning/codegen 双路径。"""

    def test_init_defaults_and_custom(self):
        from yuleosh.pipeline.step_classes import DevelopmentStep

        step = DevelopmentStep()
        assert step.mode == "planning"
        assert step.max_retries == 3
        step2 = DevelopmentStep(mode="generate-code", max_retries=5)
        assert step2.mode == "generate-code"
        assert step2.max_retries == 5

    def test_effective_mode_precedence(self):
        from yuleosh.pipeline.step_classes import DevelopmentStep

        step = DevelopmentStep(mode="planning")
        # session 配置优先
        assert (
            step._effective_mode(
                SimpleNamespace(development_mode="generate-code")
            )
            == "generate-code"
        )
        # 无 session 配置 → 构造参数
        assert step._effective_mode(SimpleNamespace(development_mode=None)) == "planning"
        # 构造参数为空 → planning
        empty = DevelopmentStep(mode="")
        assert empty._effective_mode(SimpleNamespace(development_mode=None)) == "planning"

    def test_build_prompts_git_success_and_counting(self, tmp_path):
        from yuleosh.pipeline.step_classes import DevelopmentStep

        spec = tmp_path / "spec.md"
        spec.write_text("# spec\n", encoding="utf-8")
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("line1\nline2\n", encoding="utf-8")
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "t.py").write_text("t1\n", encoding="utf-8")

        session = _make_session(spec)
        parsed = {"requirements": [], "scenarios": []}
        git_result = SimpleNamespace(returncode=0, stdout="abc123 fix\n")
        with (
            mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}, clear=False),
            mock.patch("subprocess.run", return_value=git_result),
            mock.patch(
                "yuleosh.pipeline.prompts.build_development_prompt",
                return_value=("sys", "user"),
            ) as bp,
        ):
            out = DevelopmentStep().build_prompts(session, "c", parsed, {})
        assert out == ("sys", "user")
        kwargs = bp.call_args.kwargs
        assert kwargs["src_lines"] == 2
        assert kwargs["src_file_count"] == 1
        assert kwargs["test_lines"] == 1
        assert kwargs["test_file_count"] == 1
        assert kwargs["git_commits"] == 1
        assert kwargs["git_log"] == "abc123 fix"

    def test_build_prompts_git_failure_and_read_errors(self, tmp_path):
        from yuleosh.pipeline.step_classes import DevelopmentStep

        spec = tmp_path / "spec.md"
        spec.write_text("# spec\n", encoding="utf-8")
        src = tmp_path / "src"
        src.mkdir()
        (src / "bad.py").write_text("boom\n", encoding="utf-8")
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "bad_test.py").write_text("boom\n", encoding="utf-8")

        session = _make_session(spec)
        parsed = {"requirements": [], "scenarios": []}
        with (
            mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}, clear=False),
            mock.patch(
                "subprocess.run",
                side_effect=FileNotFoundError("git not found"),
            ),
            _flaky_read_text(),
            mock.patch(
                "yuleosh.pipeline.prompts.build_development_prompt",
                return_value=("sys", "user"),
            ) as bp,
        ):
            out = DevelopmentStep().build_prompts(session, "c", parsed, {})
        assert out == ("sys", "user")
        kwargs = bp.call_args.kwargs
        assert kwargs["git_log"] == "(not a git repository or git not available)"
        assert kwargs["git_commits"] == 0
        assert kwargs["src_lines"] == 0  # bad.py 读失败被跳过
        assert kwargs["test_lines"] == 0  # bad_test.py 读失败被跳过

    def test_build_prompts_git_nonzero_returncode(self, tmp_path):
        from yuleosh.pipeline.step_classes import DevelopmentStep

        spec = tmp_path / "spec.md"
        spec.write_text("# spec\n", encoding="utf-8")
        session = _make_session(spec)
        parsed = {"requirements": [], "scenarios": []}
        git_result = SimpleNamespace(returncode=128, stdout="")
        with (
            mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}, clear=False),
            mock.patch("subprocess.run", return_value=git_result),
            mock.patch(
                "yuleosh.pipeline.prompts.build_development_prompt",
                return_value=("sys", "user"),
            ) as bp,
        ):
            DevelopmentStep().build_prompts(session, "c", parsed, {})
        kwargs = bp.call_args.kwargs
        assert kwargs["git_log"] == ""
        assert kwargs["git_commits"] == 0

    def test_call_planning_mode_writes_plan(self, tmp_path):
        from yuleosh.pipeline.step_classes import DevelopmentStep

        spec = tmp_path / "spec.md"
        spec.write_text("# spec\n", encoding="utf-8")
        session = SimpleNamespace(
            spec_path=str(spec),
            name="s1",
            session_dir=tmp_path,
            artifacts={},
            token_usage_total=0,
            token_usage_steps=[],
        )
        with (
            mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}, clear=False),
            mock.patch("subprocess.run", side_effect=FileNotFoundError("no git")),
            mock.patch(
                "yuleosh.pipeline.steps._parse_spec",
                return_value={"requirements": [], "scenarios": []},
            ),
            mock.patch(
                "yuleosh.pipeline.steps._call_llm",
                return_value={
                    "content": "plan body",
                    "usage": {"total_tokens": 10, "prompt_tokens": 5, "completion_tokens": 5},
                    "model": "m",
                },
            ),
        ):
            out_path = DevelopmentStep()(session)
        assert out_path == str(tmp_path / "development-plan.md")
        assert "plan body" in (tmp_path / "development-plan.md").read_text(
            encoding="utf-8"
        )

    def test_call_generate_code_mode_runs_engine(self, tmp_path):
        from yuleosh.pipeline.step_classes import DevelopmentStep

        spec = tmp_path / "spec.md"
        spec.write_text("# spec\n", encoding="utf-8")
        session = SimpleNamespace(
            spec_path=str(spec),
            name="s1",
            session_dir=tmp_path,
            artifacts={},
            config={
                "codegen": {
                    "skills": ["custom-skill"],
                    "target_language": "C",
                    "build_cmd": "make",
                    "language": "c",
                    "output_dir": str(tmp_path / "out"),
                    "max_retries": "2",
                }
            },
            llm_client=None,
        )
        result = SimpleNamespace(
            status="ok",
            files=["a.c", "b.c"],
            output_dir=str(tmp_path / "out"),
            report_path=str(tmp_path / "out" / "codegen-report.md"),
            rounds=2,
            max_retries=3,
        )
        engine = mock.Mock()
        engine.generate.return_value = result
        with (
            mock.patch(
                "yuleosh.codegen.prompts.build_codegen_prompt",
                return_value=("sys", "user"),
            ) as bcp,
            mock.patch(
                "yuleosh.codegen.engine.CodegenEngine", return_value=engine
            ),
            mock.patch(
                "yuleosh.codegen.engine.build_codegen_report",
                return_value="## Codegen Report\n",
            ),
        ):
            out = DevelopmentStep(mode="generate-code")(session)
        assert out == result.report_path
        bcp.assert_called_once()
        assert bcp.call_args.kwargs["skills"] == ["custom-skill"]
        engine.generate.assert_called_once()
        note = (tmp_path / "development-plan.md").read_text(encoding="utf-8")
        assert "generate-code" in note
        assert "Codegen Report" in note
        assert "Status: ok" in note


# =====================================================================
# provider_fallback.py — 配置解析
# =====================================================================


class TestFallbackConfig:
    """fallback_enabled / _parse_order / resolve_fallback_order。"""

    def test_fallback_enabled_config_wins(self):
        assert fallback_enabled(LLMConfig(fallback_enabled=False)) is False
        assert fallback_enabled(LLMConfig(fallback_enabled=True)) is True

    @pytest.mark.parametrize("raw", [None, "1", "true", "yes", "on", "banana"])
    def test_fallback_enabled_env_truthy(self, raw):
        env = {} if raw is None else {"YULEOSH_LLM_FALLBACK_ENABLED": raw}
        with mock.patch.dict(os.environ, env, clear=False):
            assert fallback_enabled() is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off", " FALSE "])
    def test_fallback_enabled_env_falsy(self, raw):
        with mock.patch.dict(
            os.environ, {"YULEOSH_LLM_FALLBACK_ENABLED": raw}, clear=False
        ):
            assert fallback_enabled() is False

    def test_parse_order_valid(self):
        with mock.patch.dict(
            os.environ,
            {"YULEOSH_LLM_FALLBACK_ORDER": " openai , mock ,deepseek "},
            clear=False,
        ):
            assert _parse_order(os.environ["YULEOSH_LLM_FALLBACK_ORDER"]) == [
                "openai",
                "mock",
                "deepseek",
            ]

    def test_parse_order_invalid_raises(self):
        with pytest.raises(ValueError, match="合法 provider"):
            _parse_order("openai,alien-llm")

    def test_resolve_fallback_order_config_provider_first(self):
        cfg = LLMConfig(provider="anthropic")
        assert resolve_fallback_order(cfg)[0] == "anthropic"

    def test_resolve_fallback_order_default_without_config(self):
        with mock.patch.dict(
            os.environ,
            {"YULEOSH_LLM_PROVIDER": "", "YULEOSH_LLM_FALLBACK_ORDER": ""},
            clear=False,
        ):
            assert resolve_fallback_order() == list(DEFAULT_FALLBACK_ORDER)

    def test_resolve_fallback_order_env_provider(self):
        with mock.patch.dict(
            os.environ,
            {"YULEOSH_LLM_PROVIDER": "openai", "YULEOSH_LLM_FALLBACK_ORDER": ""},
            clear=False,
        ):
            chain = resolve_fallback_order()
            assert chain[0] == "openai"
            assert "mock" in chain

    def test_resolve_fallback_order_config_order_and_mock_appended(self):
        cfg = LLMConfig(provider="deepseek", fallback_order=["anthropic"])
        chain = resolve_fallback_order(cfg)
        assert chain == ["deepseek", "anthropic", "mock"]

    def test_resolve_fallback_order_env_order(self):
        with mock.patch.dict(
            os.environ,
            {
                "YULEOSH_LLM_PROVIDER": "deepseek",
                "YULEOSH_LLM_FALLBACK_ORDER": "mock,openai",
            },
            clear=False,
        ):
            assert resolve_fallback_order() == ["deepseek", "mock", "openai"]

    def test_resolve_fallback_order_invalid_config_order_raises(self):
        cfg = LLMConfig(provider="deepseek", fallback_order=["alien-llm"])
        with pytest.raises(ValueError, match="合法 provider"):
            resolve_fallback_order(cfg)

    def test_resolve_fallback_order_primary_custom_name_kept(self):
        cfg = LLMConfig(provider="my-custom")
        chain = resolve_fallback_order(cfg)
        assert chain[0] == "my-custom"
        assert chain[-1] == "mock"


# =====================================================================
# provider_fallback.py — 可用性 & 异常分类
# =====================================================================


class TestFallbackAvailability:
    """provider_available / _http_code / _reason_for_code / 分类函数。"""

    def test_provider_available_mock_always(self):
        assert provider_available("mock", _FakeProvider("mock")) is True

    def test_provider_available_skeleton_skipped(self):
        p = _FakeProvider("deepseek", skeleton=True)
        assert provider_available("deepseek", p) is False

    def test_provider_available_no_key(self):
        with _no_key_env():
            assert provider_available("deepseek", _FakeProvider("deepseek")) is False
            assert provider_available("anthropic", _FakeProvider("anthropic")) is False

    def test_provider_available_with_key(self):
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "k"}, clear=False):
            assert provider_available("deepseek", _FakeProvider("deepseek")) is True

    def test_provider_available_unknown_name_no_key_envs(self):
        assert provider_available("custom", _FakeProvider("custom")) is True

    def test_http_code_http_error_direct(self):
        exc = urllib.error.HTTPError("http://x", 429, "rate", {}, None)
        assert _http_code(exc) == 429

    def test_http_code_from_runtime_error_message(self):
        assert _http_code(RuntimeError("HTTP Error 401: Unauthorized")) == 401
        assert _http_code(RuntimeError("HTTPError 503: Service Unavailable")) == 503
        assert _http_code(RuntimeError("got status code 500 from api")) == 500

    def test_http_code_no_match(self):
        assert _http_code(RuntimeError("HTTP Error")) is None
        assert _http_code(ValueError("plain")) is None

    def test_reason_for_code(self):
        assert _reason_for_code(429) == "rate_limit"
        assert _reason_for_code(500) == "http_5xx"
        assert _reason_for_code(503) == "http_5xx"
        assert _reason_for_code(400) == "http_4xx"

    def test_is_fallback_eligible_http_codes(self):
        assert is_fallback_eligible(
            urllib.error.HTTPError("http://x", 429, "r", {}, None)
        ) is True
        assert is_fallback_eligible(
            urllib.error.HTTPError("http://x", 503, "r", {}, None)
        ) is True
        assert is_fallback_eligible(
            urllib.error.HTTPError("http://x", 401, "r", {}, None)
        ) is False

    def test_is_fallback_eligible_network_errors(self):
        assert is_fallback_eligible(ConnectionError("refused")) is True
        assert is_fallback_eligible(TimeoutError("slow")) is True
        assert is_fallback_eligible(urllib.error.URLError("dns")) is True
        assert is_fallback_eligible(OSError("socket")) is True
        assert is_fallback_eligible(json.JSONDecodeError("bad", "doc", 0)) is True

    def test_is_fallback_eligible_value_error_never(self):
        assert is_fallback_eligible(ValueError("bad config")) is False

    def test_is_fallback_eligible_budget_marker_and_runtime_error(self):
        assert is_fallback_eligible(RuntimeError("budget exceeded for deepseek")) is True
        assert is_fallback_eligible(RuntimeError("超预算")) is True
        assert is_fallback_eligible(RuntimeError("transport failed")) is True
        assert is_fallback_eligible(Exception("other")) is False

    def test_classify_reason_all_branches(self):
        assert _classify_reason(
            urllib.error.HTTPError("http://x", 429, "r", {}, None)
        ) == "rate_limit"
        assert _classify_reason(
            urllib.error.HTTPError("http://x", 503, "r", {}, None)
        ) == "http_5xx"
        assert _classify_reason(
            urllib.error.HTTPError("http://x", 400, "r", {}, None)
        ) == "http_4xx"
        assert _classify_reason(TimeoutError("t")) == "timeout"
        assert _classify_reason(ConnectionError("c")) == "connection_error"
        assert _classify_reason(urllib.error.URLError("u")) == "connection_error"
        assert _classify_reason(OSError("o")) == "connection_error"
        assert _classify_reason(RuntimeError("budget 预算 exceeded")) == "budget_exceeded"
        assert _classify_reason(RuntimeError("mystery")) == "transport_error"


# =====================================================================
# provider_fallback.py — call_with_fallback 全分支
# =====================================================================


class TestCallWithFallback:
    """call_with_fallback：单 provider 模式 / 降级链 / 跳过 / 中止 / 耗尽。"""

    def _run(self, *args, **kwargs):
        return asyncio.run(call_with_fallback(*args, **kwargs))

    def test_single_provider_mode_success(self):
        cfg = LLMConfig(provider="deepseek", fallback_enabled=False)
        p = _FakeProvider("deepseek")
        resp = self._run([{"role": "user", "content": "hi"}], cfg, _make_factory({"deepseek": p}))
        assert resp.provider == "deepseek"
        assert resp.content == "ok:deepseek"
        assert p.calls == ["deepseek"]

    def test_single_provider_mode_failure_returns_error_response(self):
        cfg = LLMConfig(provider="deepseek", fallback_enabled=False)
        p = _FakeProvider("deepseek", fail_with=ConnectionError("down"))
        resp = self._run([{"role": "user", "content": "hi"}], cfg, _make_factory({"deepseek": p}))
        assert resp.content == ""
        assert resp.provider == "deepseek"
        assert "down" in resp.error

    def test_primary_success_no_events(self):
        cfg = LLMConfig(provider="deepseek")
        p = _FakeProvider("deepseek")
        with _key_env(), mock.patch(
            "yuleosh.llm.cost.CostLogger.log_fallback_event"
        ) as lfe:
            resp = self._run(
                [{"role": "user", "content": "hi"}], cfg, _make_factory({"deepseek": p})
            )
        assert resp.content == "ok:deepseek"
        assert resp.duration_s >= 0.0
        lfe.assert_not_called()

    def test_degrade_to_mock_on_connection_error(self):
        # 限定链为 [deepseek, mock]，事件里的 to_provider 即链中下一个 provider
        cfg = LLMConfig(provider="deepseek", fallback_order=["mock"])
        ds = _FakeProvider("deepseek", fail_with=ConnectionError("refused"))
        mk = _FakeProvider("mock")
        with _key_env(), mock.patch(
            "yuleosh.llm.cost.CostLogger.log_fallback_event"
        ) as lfe:
            resp = self._run(
                [{"role": "user", "content": "hi"}],
                cfg,
                _make_factory({"deepseek": ds, "mock": mk}),
            )
        assert resp.provider == "mock"
        assert resp.content == "ok:mock"
        assert ds.calls == ["deepseek"]
        assert mk.calls == ["mock"]
        assert lfe.call_count == 1
        args = lfe.call_args.kwargs
        assert args["from_provider"] == "deepseek"
        assert args["to_provider"] == "mock"
        assert args["reason"] == "connection_error"

    def test_degrade_on_http_5xx(self):
        cfg = LLMConfig(provider="deepseek")
        ds = _FakeProvider(
            "deepseek",
            fail_with=urllib.error.HTTPError("http://x", 503, "down", {}, None),
        )
        mk = _FakeProvider("mock")
        with _key_env(), mock.patch(
            "yuleosh.llm.cost.CostLogger.log_fallback_event"
        ) as lfe:
            resp = self._run(
                [{"role": "user", "content": "hi"}],
                cfg,
                _make_factory({"deepseek": ds, "mock": mk}),
            )
        assert resp.provider == "mock"
        assert lfe.call_args.kwargs["reason"] == "http_5xx"

    def test_skip_primary_reason_records_event(self):
        cfg = LLMConfig(provider="deepseek", fallback_order=["mock"])
        ds = _FakeProvider("deepseek")
        mk = _FakeProvider("mock")
        with _key_env(), mock.patch(
            "yuleosh.llm.cost.CostLogger.log_fallback_event"
        ) as lfe:
            resp = self._run(
                [{"role": "user", "content": "hi"}],
                cfg,
                _make_factory({"deepseek": ds, "mock": mk}),
                skip_primary_reason="budget_exceeded",
            )
        assert resp.provider == "mock"
        assert ds.calls == []  # 主 provider 未被调用
        assert lfe.call_count == 1
        assert lfe.call_args.kwargs["reason"] == "budget_exceeded"
        assert lfe.call_args.kwargs["from_provider"] == "deepseek"
        assert lfe.call_args.kwargs["to_provider"] == "mock"

    def test_factory_failure_continues_chain(self):
        cfg = LLMConfig(provider="deepseek")
        mk = _FakeProvider("mock")
        with mock.patch("yuleosh.llm.cost.CostLogger.log_fallback_event"):
            resp = self._run(
                [{"role": "user", "content": "hi"}],
                cfg,
                _make_factory({"mock": mk}, fail_names=("deepseek",)),
            )
        assert resp.provider == "mock"
        assert resp.content == "ok:mock"

    def test_skeleton_provider_skipped_with_reason(self):
        cfg = LLMConfig(provider="deepseek")
        ds = _FakeProvider("deepseek", skeleton=True)
        mk = _FakeProvider("mock")
        with mock.patch("yuleosh.llm.cost.CostLogger.log_fallback_event") as lfe:
            resp = self._run(
                [{"role": "user", "content": "hi"}],
                cfg,
                _make_factory({"deepseek": ds, "mock": mk}),
            )
        assert resp.provider == "mock"
        assert ds.calls == []
        assert lfe.call_args.kwargs["reason"] == "skeleton"

    def test_no_key_provider_skipped(self):
        cfg = LLMConfig(provider="deepseek", fallback_order=["anthropic", "mock"])
        ds = _FakeProvider("deepseek")
        anth = _FakeProvider("anthropic")
        mk = _FakeProvider("mock")
        with _no_key_env(), mock.patch(
            "yuleosh.llm.cost.CostLogger.log_fallback_event"
        ) as lfe:
            resp = self._run(
                [{"role": "user", "content": "hi"}],
                cfg,
                _make_factory(
                    {"deepseek": ds, "anthropic": anth, "mock": mk}
                ),
            )
        assert resp.provider == "mock"
        assert ds.calls == [] and anth.calls == []
        assert lfe.call_count == 2
        assert lfe.call_args.kwargs["reason"] == "no_key"

    def test_non_degradable_error_aborts_chain(self):
        cfg = LLMConfig(provider="deepseek")
        ds = _FakeProvider("deepseek", fail_with=ValueError("bad config"))
        mk = _FakeProvider("mock")
        with _key_env(), mock.patch(
            "yuleosh.llm.cost.CostLogger.log_fallback_event"
        ) as lfe:
            resp = self._run(
                [{"role": "user", "content": "hi"}],
                cfg,
                _make_factory({"deepseek": ds, "mock": mk}),
            )
        assert mk.calls == []  # 4xx/配置错误 → 不降级
        assert resp.error.startswith("All providers failed:")
        assert lfe.call_args.kwargs["to_provider"] == "(abort)"
        assert lfe.call_args.kwargs["reason"] == "non_degradable"

    def test_http_4xx_aborts_chain(self):
        cfg = LLMConfig(provider="deepseek")
        ds = _FakeProvider(
            "deepseek",
            fail_with=urllib.error.HTTPError("http://x", 401, "unauth", {}, None),
        )
        mk = _FakeProvider("mock")
        with _key_env(), mock.patch(
            "yuleosh.llm.cost.CostLogger.log_fallback_event"
        ) as lfe:
            resp = self._run(
                [{"role": "user", "content": "hi"}],
                cfg,
                _make_factory({"deepseek": ds, "mock": mk}),
            )
        assert mk.calls == []
        assert "401" in resp.error
        assert lfe.call_args.kwargs["reason"] == "non_degradable"

    def test_chain_exhausted_returns_last_error(self):
        cfg = LLMConfig(provider="deepseek")
        ds = _FakeProvider("deepseek", fail_with=ConnectionError("a"))
        mk = _FakeProvider("mock", fail_with=TimeoutError("b"))
        with mock.patch("yuleosh.llm.cost.CostLogger.log_fallback_event") as lfe:
            resp = self._run(
                [{"role": "user", "content": "hi"}],
                cfg,
                _make_factory({"deepseek": ds, "mock": mk}),
            )
        assert resp.content == ""
        assert resp.provider == "deepseek"
        assert resp.error == "All providers failed: b"
        assert lfe.call_count == 2

    def test_mock_is_final_safety_net(self):
        """deepseek 是 skeleton 被跳过 → mock 兜底成功（mock 永远可用）。"""
        cfg = LLMConfig(provider="deepseek", fallback_order=[])
        ds = _FakeProvider("deepseek", skeleton=True)
        mk = _FakeProvider("mock", skeleton=True)  # 即使 mock 标了 skeleton 也照样可用
        with mock.patch("yuleosh.llm.cost.CostLogger.log_fallback_event"):
            resp = self._run(
                [{"role": "user", "content": "hi"}],
                cfg,
                _make_factory({"deepseek": ds, "mock": mk}),
            )
        assert resp.provider == "mock"
        assert resp.content == "ok:mock"

    def test_default_provider_factory_used(self):
        cfg = LLMConfig(provider="deepseek")
        p = _FakeProvider("deepseek")
        with _key_env(), mock.patch(
            "yuleosh.llm.client._get_provider", return_value=p
        ) as gp:
            resp = self._run([{"role": "user", "content": "hi"}], cfg)
        gp.assert_called_once_with("deepseek")
        assert resp.content == "ok:deepseek"

    def test_skip_primary_reason_single_provider_chain(self):
        """skip_primary_reason 且链只有 mock 一个元素 → to_provider 为 (none)，
        且链耗尽后无 last_error → 返回 'No providers available' 错误。"""
        cfg = LLMConfig(provider="mock", fallback_order=["mock"])
        mk = _FakeProvider("mock")
        with mock.patch("yuleosh.llm.cost.CostLogger.log_fallback_event") as lfe:
            resp = self._run(
                [{"role": "user", "content": "hi"}],
                cfg,
                _make_factory({"mock": mk}),
                skip_primary_reason="budget_exceeded",
            )
        assert lfe.call_args.kwargs["to_provider"] == "(none)"
        assert mk.calls == []  # start_idx=1 > len(chain) → 链直接耗尽
        assert resp.error == "No providers available in fallback chain"


# =====================================================================
# provider_fallback.py — 事件审计 _flush_events
# =====================================================================


class TestFlushEvents:
    """_flush_events：空列表短路 / 逐条写入 / 写入失败不抛。"""

    def test_empty_events_noop(self):
        with mock.patch("yuleosh.llm.cost.CostLogger.log_fallback_event") as lfe:
            _flush_events([])
        lfe.assert_not_called()

    def test_writes_each_event(self):
        events = [
            FallbackEvent(
                from_provider="a", to_provider="b", reason="timeout",
                duration_s=0.5, error="boom",
            ),
            FallbackEvent(from_provider="b", to_provider="c", reason="no_key"),
        ]
        with mock.patch("yuleosh.llm.cost.CostLogger.log_fallback_event") as lfe:
            _flush_events(events)
        assert lfe.call_count == 2
        first = lfe.call_args_list[0].kwargs
        assert first["from_provider"] == "a"
        assert first["to_provider"] == "b"
        assert first["reason"] == "timeout"
        assert first["duration_s"] == 0.5
        assert first["error"] == "boom"
        second = lfe.call_args_list[1].kwargs
        assert second["reason"] == "no_key"
        assert second["duration_s"] == 0.0  # 默认值

    def test_logger_failure_is_non_fatal(self, caplog):
        events = [FallbackEvent(from_provider="a", to_provider="b", reason="x")]
        with mock.patch(
            "yuleosh.llm.cost.CostLogger.log_fallback_event",
            side_effect=RuntimeError("disk full"),
        ):
            _flush_events(events)  # 不抛异常
        assert "审计日志写入失败" in caplog.text
