#!/usr/bin/env python3

# @req RS-001  @req SWR-001.1  @req FSR-002 @req NFR-001
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Pipeline Orchestrator — run_pipeline entry point, session status,
and CLI entry point (main).

Import chain:  orchestrator -> stages -> session
"""

import json
import logging
import os
import shutil
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.llm.fallback import apply_fallback_chain
from yuleosh.llm.validation import validate_llm_output
from yuleosh.agent_registry import (
    AGENT_SAFE_BASELINE as _AGENT_SAFE_BASELINE,
    load_agent_constraints_by_role,
)

log = logging.getLogger("pipeline.orchestrator")

# ── D2 并行组 (ADR-002: Pipeline Parallel Groups, 方案 A) ──────────────────
# 详见 docs/adr/ADR-002-pipeline-parallel-groups.md
# 组内步骤互不依赖（依赖图见 docs/planning/d2-parallel-brainstorm-2026-08-19.md）
# → 并发执行; 组间保持 PIPELINE_STEPS 顺序。
# 门禁语义不变: 组内任一 block → 整组等待结束后中断; 任一 failed →
# 整组等待结束后中断（与 verify-loop 合并语义一致）。
#
# P1: prd ∥ architecture — architecture 只读 spec+扫描 src, 不读 prd。
# P2: arch-review ∥ development — development 只读 architecture/prd/
#     super-analysis, 不读 arch-review。
# P3: development-review ∥ codegen-deploy ∥ claude-review — 三者都只依赖
#     development 产物, 互不依赖。
# ⚠️ internal-code-review 不在 P3 (2026-08-20 r22 实测): maybe_skip_code_review
#     读 codegen-deploy 报告 (handler 结尾才写) — 与 codegen-deploy 并行会
#     先读到旧/缺报告 → false-skip "本次 run 无代码部署"。部署状态消费者
#     必须在 producer 之后 (对齐「互换安全 ⟺ 双方都不消费对方产物」原则)。
PARALLEL_GROUPS: list[tuple[str, ...]] = [
    ("prd", "architecture"),
    ("arch-review", "development"),
    ("development-review", "codegen-deploy", "claude-review"),
]
# 并行组在 PIPELINE_STEPS 中可能不相邻（如 prd 与 architecture 隔 prd-review）,
# 预注册阶段按 PIPELINE_STEPS 顺序登记全部步骤, 执行阶段按组并发。
_GROUP_LOOKUP: dict[str, int] = {}
for _gi, _g in enumerate(PARALLEL_GROUPS):
    for _k in _g:
        _GROUP_LOOKUP[_k] = _gi

# Notifications (optional import)
_notify = None
try:
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from notify import notify_pipeline
    _notify = notify_pipeline
except ImportError:
    _notify = None

# ── Auto-detect project type from .yuleosh.yaml ──────────────────────

def _detect_project_type(project_dir: str) -> Optional[dict]:
    """Read .yuleosh.yaml and detect the project type (e.g. autosar).

    Returns a dict with 'type', 'name', and 'template_name' if found.
    Returns None if no config or no type field.
    """
    import yaml as _yaml
    proj_path = Path(project_dir)
    candidates = [
        proj_path / ".yuleosh.yaml",
        proj_path / "yuleosh.yaml",
        proj_path / ".yuleosh" / "config.yml",
    ]
    for cfg_file in candidates:
        if cfg_file.exists():
            try:
                raw = _yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
                if raw and isinstance(raw, dict):
                    ptype = raw.get("type") or raw.get("project", {}).get("type")
                    if ptype:
                        return {
                            "type": ptype,
                            "name": raw.get("name") or raw.get("project", {}).get("name", ptype),
                            "template_name": raw.get("template") or raw.get("project", {}).get("template", ptype),
                            "config_source": str(cfg_file),
                        }
            except Exception as e:
                log.debug("Could not parse %s: %s", cfg_file, e)
    return None


def _ensure_autosar_pipeline_config(project_dir: str, template_dir: Optional[Path] = None) -> bool:
    """If project type is autosar and no `.yuleosh/ci-config.yaml` exists,
    copy the template pipeline config.

    Returns True if a config was generated.
    """
    ci_config = Path(project_dir) / ".yuleosh" / "ci-config.yaml"
    if ci_config.exists():
        return False  # Already configured

    if template_dir is None:
        # Try built-in template path
        template_dir = Path(os.path.dirname(__file__)).parent.parent.parent / "templates" / "autosar"
        if not template_dir.exists():
            template_dir = Path(os.path.dirname(__file__)).parent.parent / "templates" / "autosar"

    pipeline_cfg = template_dir / "pipeline" / "config.yaml" if template_dir else None
    if pipeline_cfg and pipeline_cfg.exists():
        # Ensure .yuleosh dir exists
        (Path(project_dir) / ".yuleosh").mkdir(parents=True, exist_ok=True)
        ci_config.write_text(pipeline_cfg.read_text(encoding="utf-8"))
        log.info("Generated autosar pipeline config: %s", ci_config)
        return True

    return False


def _detect_and_bootstrap(project_dir: str) -> Optional[dict]:
    """Auto-detect project type and bootstrap missing config.

    Returns the detected project info dict, or None if not detected.
    """
    info = _detect_project_type(project_dir)
    if not info:
        return None

    ptype = info["type"]
    log.info("Detected project type: %s (name=%s)", ptype, info["name"])

    templates_base = Path(os.path.dirname(__file__)).parent.parent / "templates"
    if not templates_base.exists():
        templates_base = Path(os.path.dirname(__file__)).parent.parent.parent / "templates"

    if ptype == "autosar":
        tdir = templates_base / "autosar-classic" if templates_base.exists() else None
        if tdir and tdir.exists():
            # Register: ensure template.yaml is used
            template_yaml = tdir / "template.yaml"
            if template_yaml.exists():
                log.info("AUTOSAR template found: %s", template_yaml)
            _ensure_autosar_pipeline_config(project_dir, tdir)
        else:
            log.info("AUTOSAR template dir not found, skipping bootstrap")

    return info


# ── Agent constraints loading ──────────────────────────────────────

# A2 (2026-08-08): 原三角色混合的 _DEFAULT_AGENT_SPEC 拆分为
#   1. 共享最小安全基线 _AGENT_SAFE_BASELINE（无角色通用规则，
#      审计诚信 / 上下文安全 / 不静默降质）—— 与 agent_registry 同源；
#   2. per-role 默认规则 DEFAULT_ROLE_SPECS（简短，按角色隔离）。
# _DEFAULT_AGENT_SPEC 保留名称，内容改为指向拆分后的组合（向后兼容）。

DEFAULT_ROLE_SPECS = {
    "pm": (
        "### PM 角色默认规则\n"
        "- P0/P1 问题必须在阶段完成前闭环，禁止带病进入下一阶段。\n"
        "- 以项目全局视角裁决优先级，禁止局部最优。\n"
    ),
    "developer": (
        "### Developer 角色默认规则\n"
        "- 发现缺陷立即修复并回归，禁止悄悄跳过。\n"
        "- 实现必须可编译、可测试，禁止提交未验证代码。\n"
    ),
    "qa": (
        "### QA 角色默认规则\n"
        "- 审查必须基于真实产物与证据，禁止空泛放行。\n"
        "- 发现的问题按 P0/P1/P2 分级并显式记录。\n"
    ),
}

_DEFAULT_AGENT_SPEC = (
    "# Default Agent Spec (from ci-config.yaml)\n\n"
    "## Roles\n"
    "- 小明: Project Manager / Orchestrator\n"
    "- 小克: Architect / Developer / Tester\n"
    "- 小马: Quality Architect / Reviewer\n\n"
    "## Core Rules\n"
    f"{_AGENT_SAFE_BASELINE.strip()}\n\n"
    "## Role-Specific Defaults\n"
    + "\n\n".join(
        f"### {role}\n{spec.strip()}" for role, spec in DEFAULT_ROLE_SPECS.items()
    )
)


def load_agent_constraints(project_dir: str) -> tuple[str, str]:
    """Load agent constraints from `.yuleosh/agents/` directory.

    Reads all ``*.md`` files from ``.yuleosh/agents/`` and concatenates
    their content into a single string suitable for injection into the
    LLM system prompt.

    If the directory does not exist or is empty, falls back to the
    default agent spec from ``ci-config.yaml`` or the built-in default.

    Returns:
        Tuple of (constraints_text, source_description).
        ``source_description`` is one of:
            "agents_dir"    — loaded from .yuleosh/agents/*.md
            "ci_config"     — loaded from ci-config.yaml default_agent_spec
            "builtin_fallback" — built-in default spec
    """
    import yaml as _yaml

    agents_dir = Path(project_dir) / ".yuleosh" / "agents"

    if agents_dir.is_dir():
        md_files = sorted(agents_dir.glob("*.md"))
        if md_files:
            parts = []
            for f in md_files:
                try:
                    content = f.read_text(encoding="utf-8")
                    parts.append(f"<!-- from: {f.name} -->\n{content}")
                except Exception as e:
                    log.warning("Failed to read agent constraint %s: %s", f, e)
            if parts:
                log.info(
                    "Loaded %d agent constraint file(s) from .yuleosh/agents/",
                    len(parts),
                )
                return "\n\n".join(parts), "agents_dir"

    # Fallback: try ci-config.yaml default_agent_spec
    ci_config = Path(project_dir) / ".yuleosh" / "ci-config.yaml"
    if ci_config.exists():
        try:
            raw = _yaml.safe_load(ci_config.read_text(encoding="utf-8"))
            if raw and isinstance(raw, dict):
                default_spec = raw.get("default_agent_spec")
                if default_spec:
                    log.info(
                        "Loaded default agent spec from %s", ci_config.name
                    )
                    return str(default_spec), "ci_config"
        except Exception as e:
            log.debug("Could not parse %s for default_agent_spec: %s", ci_config, e)

    # Built-in fallback
    log.info("Using built-in default agent spec (no .yuleosh/agents/ or ci-config default)")
    return _DEFAULT_AGENT_SPEC.strip(), "builtin_fallback"


def _mock_llm_client() -> Callable:
    """Create a mock LLM client for demo/testing (--mock flag).

    Returns a function with the same signature as ``chat_completion``
    that returns a plausible OpenAI-style response dict without
    making any network calls.
    """
    import json as _json
    from datetime import datetime as _dt

    def _mock_callback(system_prompt: str, user_prompt: str, **kwargs) -> dict:
        """Mock LLM call that returns a canned response.

        Returns a flat dict with ``content`` at the top level,
        matching what yuleOSH pipeline step handlers expect
        (``result["content"]``).
        """
        content = (
            f"# Mock Response — yuleOSH --mock mode\n\n"
            f"**Generated at**: {_dt.now().isoformat()}\n\n"
            f"This is a mock LLM response generated by the ``--mock`` flag.\n\n"
            f"### Notes\n"
            f"- The pipeline ran in mock mode — no real LLM was called.\n"
            f"- All steps will produce placeholder outputs.\n"
            f"- Use a real API key (``LLM_API_KEY``) for production runs.\n"
            f"- Token usage statistics are simulated (1000 tokens per call)."
        )
        return {
            "content": content,
            "model": "mock-mode",
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "total_tokens": 1500,
            },
        }

    return _mock_callback


def _find_previous_session(spec_path: str, project_dir: str):
    """Find the most recent pipeline session for the same spec.

    Used by ``--from-step`` resume: restores prior-step artifacts so a
    re-run can continue from step N instead of paying for steps 1..N-1
    again (and re-running their LLM calls).

    Returns ``(updated_at, session_dir, data)`` or None.
    """
    base = Path(project_dir) / ".osh" / "sessions"
    best = None
    if not base.exists():
        return None
    resolved = str(Path(spec_path).resolve())
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        sfile = d / "session.json"
        if not sfile.exists():
            continue
        try:
            data = json.loads(sfile.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if str(data.get("spec_path", "")) != resolved:
            continue
        ts = str(data.get("updated_at", ""))
        if best is None or ts > best[0]:
            best = (ts, d, data)
    return best


def _print_step_timings(session) -> None:
    """Print per-step wall-clock timings from session.steps.

    性能可观测性 (2026-08-19): 每次 pipeline 结束后打印耗时表, 与
    scripts/profile_pipeline_steps.py 的聚合基线配合, 形成优化前后对比。
    数据来源: session.steps 的 started_at/completed_at (零额外采集)。
    """
    rows = []
    for st in session.steps or []:
        t0 = st.get("started_at")
        t1 = st.get("completed_at")
        if not t0 or not t1:
            continue
        try:
            from datetime import datetime as _dt
            elapsed = (_dt.fromisoformat(t1) - _dt.fromisoformat(t0)).total_seconds()
        except (ValueError, TypeError):
            continue
        if elapsed >= 0:
            rows.append((st.get("step_key") or st.get("name", "?"),
                         st.get("status", ""), elapsed))
    if not rows:
        return
    rows.sort(key=lambda r: -r[2])
    print("\n⏱ Step Timings (wall-clock)")
    for key, status, el in rows:
        flag = "🚀" if el >= 60 else ("⚡" if el >= 10 else "  ")
        print(f"   {flag} {key:<28} {el:>8.1f}s  ({status})")


def run_pipeline(spec_path: str, name: Optional[str] = None, llm_client: Optional[Callable] = None,
                mock: bool = False, profile: Optional[str] = None, org_id: int = 0,
                user_id: int | None = None, user_email: str | None = None,
                from_step: int = 0, run_id: Optional[str] = None):
    """Run the full OSH pipeline for a given spec.

    Args:
        run_id: Stage-6 (2026-09-05) —— 调用方（``POST /api/v1/pipeline/run``）
            预先生成的运行 ID。传入后 session 目录与所有 realtime 事件都用它，
            使「API 侧 run_id」「编排器 session.run_id」``SSE 事件 run_id``
            三者一致。之前编排器自生成 uuid，导致：
              * API 记录的 session_dir（``.osh/sessions/<api_run_id>``）与
                编排器实际写产物的目录（``.osh/sessions/<session.run_id>``）
                不是同一个 → 产出物面板 / 一键跑看板对不上；
              * SSE 的 stage_* 事件用 ``session.name``（"run-xxx"）而
                checkpoint/run_done 用 API run_id（"xxx"）→ 前端 store
                按 run_id 聚合时两个 key 各存一份，看板与左栏徽标错乱。
            不传时行为不变（自动生成 uuid），CLI / 测试无感。
    
    Args:
        spec_path: Path to the specification file.
        name: Optional session name (auto-generated if None).
        llm_client: Optional injected LLM callable for testing.
            When provided, all LLM-dependent steps use this callable
            instead of the global ``chat_completion``.
        mock: If True, run with a fake LLM that returns placeholder
            responses — no API key needed (for demo/testing).
        profile: Optional profile name override (default: from ci-config.yaml or "safety").
        org_id: 消费计量归属组织（Portal 方案 B, 2026-08-10；CLI 默认 0）。
        user_id/user_email: 用户归因（Phase 9, 2026-08-10；CLI 默认 None）。
    """

    # Deferred import from run shim so that test mocks on
    # yuleosh.pipeline.run.PIPELINE_STEPS and run._check_llm_key take effect.
    from yuleosh.pipeline.run import PIPELINE_STEPS as _steps, _check_llm_key as _check_key

    # When --mock is used, create a fake LLM client and inject it
    if mock:
        if llm_client is None:
            llm_client = _mock_llm_client()
        print("\n🧪 Pipeline running in MOCK mode — no real LLM will be called.\n")
    elif llm_client is None:
        # Check for LLM API key before starting
        key = _check_key()
        if not key:
            sys.exit(1)    
    # ── Auto-detect project type and bootstrap ──
    project_root = os.path.dirname(os.path.abspath(spec_path))
    project_info = _detect_and_bootstrap(project_root)
    if project_info:
        print(f"\n📋 Detected project: {project_info['name']} (type: {project_info['type']})")
        if project_info["type"] == "autosar":
            print(f"   AUTOSAR template auto-loaded from: {project_info.get('config_source', 'template')}")

    # ── Load agent constraints from .yuleosh/agents/ ──
    agent_constraints, constraints_source = load_agent_constraints(project_root)
    # A1-A4 (2026-08-08): 按角色隔离加载。扫描 .yuleosh/agents/*.md 并按
    # 角色分组；若存在可归因的角色约束，用「共享基线 + 各角色约束」拼一个
    # 总串作为向后兼容的 session.agent_constraints，同时保留 by_role 供
    # llm 层按当前步骤角色做隔离注入。无 agents/ 目录或不可归因时返回空
    # dict，此时完全走原逻辑。
    constraints_by_role = load_agent_constraints_by_role(project_root)
    if constraints_by_role:
        combined_parts = [_AGENT_SAFE_BASELINE.strip()] + [
            text.strip() for text in constraints_by_role.values()
        ]
        agent_constraints = "\n\n".join(combined_parts)
    if agent_constraints:
        source_labels = {
            "agents_dir": "📋 Agent constraints loaded from .yuleosh/agents/",
            "ci_config": "📋 Agent constraints loaded from ci-config.yaml default",
            "builtin_fallback": "📋 Agent constraints: built-in default",
        }
        label = source_labels.get(constraints_source, "📋 Agent constraints loaded")
        print(f"   {label}")

    # G-33: Profile validation
    project_dir = os.environ.get("OSH_HOME", os.path.dirname(os.path.abspath(spec_path)))
    try:
        from yuleosh.ci.profile import validate_active_profile, filter_steps_for_profile, get_current_profile
        active_profile = profile or get_current_profile(project_dir)
        valid, msg = validate_active_profile(project_dir)
        if not valid:
            print(f"\n⚠️  Profile validation: {msg}")
            print("   Falling back to 'safety' profile.")
            active_profile = "safety"
        else:
            print(f"\n📋 Active profile: '{active_profile}' ({msg})")
        _steps = filter_steps_for_profile(_steps, active_profile, project_dir)
        if not _steps:
            print("\n❌ No steps remaining after profile filtering!")
            sys.exit(1)
    except ImportError:
        active_profile = "safety"
        log.info("Profile module not available, using all steps")
    except Exception as e:
        log.warning("Profile validation skipped: %s", e)
        active_profile = "safety"

    # 方向2 (2026-08-11): diff 智能裁剪（OSH_DIFF_SKIP=1 显式开启）
    # Evaluator 门槛 G1-G5:
    #   G1 空 diff fail-safe（不裁剪）
    #   G2 skip 显式报告（打印 + 写入 session）
    #   G3 跨切面步骤不可跳过（CROSS_CUTTING_STEPS）
    #   G5 block 级门禁不可裁剪（gate_policy）
    diff_skip_decisions = []
    try:
        from yuleosh.ci.diff_planner import (
            collect_changed_files,
            get_step_file_globs,
            is_enabled,
            plan_skips,
            skip_summary,
        )
        from yuleosh.ci.gate_policy import load_gate_policy

        if is_enabled():
            _changed = collect_changed_files(project_dir)
            _globs = get_step_file_globs()
            _policy = load_gate_policy(project_dir)
            diff_skip_decisions = plan_skips(
                _steps, _changed, gate_policy=_policy, file_globs=_globs
            )
            if diff_skip_decisions:
                _skip_keys = {d.step_key for d in diff_skip_decisions}
                print(f"\n⏭️  {skip_summary(diff_skip_decisions)}")
                print("   (OSH_DIFF_SKIP=1 — skipped steps will NOT run)")
                _steps = [s for s in _steps if s[0] not in _skip_keys]
                if not _steps:
                    print("\n❌ No steps remaining after diff planning!")
                    sys.exit(1)
    except ImportError:
        log.debug("diff_planner not available, skipping diff planning")
    except Exception as e:
        log.warning("Diff planning skipped: %s", e)

    try:
        if name is None:
            name = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        session = PipelineSession(
            name,
            spec_path,
            llm_client=llm_client,
            agent_constraints=agent_constraints,
            org_id=org_id,
            user_id=user_id,
            user_email=user_email,
            # Stage-6: 让 session 目录 + realtime 事件与 API 侧 run_id 对齐
            run_id=run_id,
        )
        # A1-A4: 角色隔离所需的新字段 —— 按角色分组的约束 + 共享安全基线。
        session.agent_constraints_by_role = constraints_by_role
        session.agent_shared_baseline = _AGENT_SAFE_BASELINE
        # Propagate mock flag so gates (coverage, critical safety) can skip
        # scanning placeholder artifacts generated by the mock LLM.
        session.mock_mode = bool(mock)
        # D3: allow enabling generate-code mode via env (no code changes).
        env_dev_mode = os.environ.get("OSH_DEVELOPMENT_MODE", "").strip()
        if env_dev_mode:
            session.development_mode = env_dev_mode
            print(f"   📝 development_mode from env: {env_dev_mode}")
        session.profile = active_profile
        # G2 (方向2): diff 裁剪决策写入 session 报告（显式可见，禁止静默消失）
        if diff_skip_decisions:
            session.diff_skip_decisions = [d.to_dict() for d in diff_skip_decisions]
        else:
            session.diff_skip_decisions = []

        # ── 断点续跑 (2026-08-12): --from-step N ──
        # 从最近一次同 spec 的 session 恢复前序 artifacts, 步骤 1..N-1
        # 标记 skipped (不执行, 不烧 LLM token), 从第 N 步继续。
        restored_count = 0
        if from_step and from_step > 1:
            _prev = _find_previous_session(spec_path, project_dir)
            if _prev is None:
                print(f"\n⚠️  未找到同 spec 的上一 session — 从步骤 1 开始")
                from_step = 1
            else:
                _prev_ts, _prev_dir, _prev_data = _prev
                # r21q/r22: 恢复只带回 from_step 之前的前序产物 — 旧 session 的
                # 后序步骤产物（step >= from_step）不得混入新 session 证据链
                # （window-anti-pinch 实测: claude-review 把旧 self-test 当本轮证据）。
                # 按 PIPELINE_STEPS 顺序映射 step_key → 序号, 只恢复序号 < from_step 的产物。
                from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
                _step_order = {k: i + 1 for i, (k, *_rest) in enumerate(PIPELINE_STEPS)}
                for _key, _path in (_prev_data.get("artifacts") or {}).items():
                    _step_no = _step_order.get(_key)
                    # 旧 key（不在当前 PIPELINE_STEPS，如 codex-verify/self-test-review
                    # 已合并进 verify-loop）一律跳过 — r22 后无对应步骤，不得混入。
                    if _step_no is None:
                        log.info("Resume: skip stale artifact %s (no step in PIPELINE_STEPS)", _key)
                        continue
                    if _step_no >= from_step:
                        log.info("Resume: skip artifact %s (step %d >= from_step %d)",
                                 _key, _step_no, from_step)
                        continue
                    _src = Path(str(_path))
                    if not _src.exists():
                        continue
                    _dst = session.session_dir / _src.name
                    try:
                        shutil.copy2(_src, _dst)
                        session.set_artifact(_key, str(_dst))
                        restored_count += 1
                    except OSError as _e:
                        log.warning("Resume: cannot restore artifact %s: %s", _key, _e)
                if restored_count:
                    print(f"\n♻️  断点续跑: 从 {_prev_dir.name} 恢复 "
                          f"{restored_count} 个前序产物, 从步骤 {from_step} 继续")
        session.from_step = from_step
        print(f"\n🚀 Pipeline started: {name}")
        print(f"   Spec: {spec_path}")
        print(f"   Profile: {active_profile}")
        print(f"   Session: {session.session_dir}")
        print()
        
        log.info(f"Pipeline starting: {name}, spec={spec_path}, profile={active_profile}")
        
        _ran_final_report = False
        # D2 (2026-08-19): 预注册全部步骤 — 保证 step_idx 与 PIPELINE_STEPS
        # 顺序一致（断点续跑/缓存/verdict 都依赖稳定索引）, 执行阶段再按
        # 并行组并发调度。
        _registered: list[tuple[int, str, str, str, Callable]] = []
        for step_key, agent, step_name, handler in _steps:
            if step_key == "final-report":
                _ran_final_report = True
            step_idx = len(session.steps)
            session.add_step(step_key, agent, step_name)
            _registered.append((step_idx, step_key, agent, step_name, handler))

        _executed: set[str] = set()
        _blocked = False
        _failed = False
        _ri = 0
        while _ri < len(_registered):
            step_idx, step_key, agent, step_name, handler = _registered[_ri]
            # 断点续跑: 前序步骤标记 skipped（_execute_step 内处理）
            if step_idx + 1 < from_step:
                session.steps[step_idx]["status"] = "skipped"
                session.steps[step_idx]["completed_at"] = datetime.now().isoformat()
                _executed.add(step_key)
                _ri += 1
                continue
            # D2: 并行组 — 组内成员一次性并发执行
            # 例外：YULEOSH_PIPELINE_SERIAL==1 时串行化（单台本地 ollama 14B 并发
            # 会争用掉 step → transport_error；串行可干净跑完整链）。
            _gid = _GROUP_LOOKUP.get(step_key)
            if _gid is not None:
                _members = [r for r in _registered
                            if r[1] in PARALLEL_GROUPS[_gid] and r[1] not in _executed]
                if _members:
                    _gkeys = ", ".join(m[1] for m in _members)
                    if os.environ.get("YULEOSH_PIPELINE_SERIAL") == "1":
                        print(f"\n  🐢 [serial] 并行组 {_gid+1} 串行化: {_gkeys}")
                        for _m in _members:
                            _st = _execute_step(
                                session, _m[0], _m[1], _m[2], _m[3], _m[4],
                                spec_path, project_dir, from_step,
                            )
                            _executed.add(_m[1])
                            if _st == "block":
                                _blocked = True
                                break
                            if _st == "failed":
                                _failed = True
                                break
                        print()
                        if _blocked or _failed:
                            break
                    else:
                        print(f"\n  ⚡ [D2] 并行组 {_gid+1} 并发: {_gkeys}")
                        _blocked, _failed = _run_parallel_group(
                            session, _members, from_step, project_dir, spec_path,
                        )
                        for _m in _members:
                            _executed.add(_m[1])
                        print()
                        if _blocked or _failed:
                            break
                _ri += 1
                continue
            # 串行步骤
            _status = _execute_step(
                session, step_idx, step_key, agent, step_name, handler,
                spec_path, project_dir, from_step,
            )
            _executed.add(step_key)
            if _status == "block":
                _blocked = True
                break
            if _status == "failed":
                _failed = True
                break
            _ri += 1

        if _blocked:
            print("  ⛔ Block gate failed — pipeline interrupted")
            print()
        if _failed:
            print("  ❌ Step failed — pipeline interrupted")
            print()
        
        # E2E 修复 (2026-08-11): minimal 等白名单档不含 final-report —
        # 循环正常跑完即视为 completed（避免 status 停在 created 导致
        # CLI exit(1) 误判失败；block 中断/异常已在循环内置 failed）。
        if session.status != "failed" and not _ran_final_report:
            session.status = "completed"
            session.updated_at = datetime.now().isoformat()

        if session.status != "failed":
            session._save()

        # 编排层 10 Gate 报告聚合 (2026-08-19 方案 B):
        # gate status = 内部子步骤最差状态; 写 .osh/sessions/<id>/gate-summary.json。
        # 失败不阻断 pipeline 收尾（证据产物, 只记录）。
        try:
            from yuleosh.pipeline.gates import write_gate_summary
            _gate_path = write_gate_summary(session)
            log.info("Gate summary written: %s", _gate_path)
        except Exception as _gate_err:  # pragma: no cover - defensive  # noqa: BLE001
            log.warning("gate-summary write failed (non-fatal): %s", _gate_err)
        
        print(f"\n{'='*50}")
        # 三色结果分级 (2026-08-12):
        #   🟢 GREEN  — completed, 0 errors        → 可放行
        #   🟡 YELLOW — completed, errors>0        → 有 verdict 失败, 需人工复核
        #   🔴 RED    — failed (block gate/异常)   → 不可放行
        if session.status == "completed" and not session.errors:
            print(f"Pipeline: {session.status} 🎉 (GREEN — all gates passed)")
        elif session.status == "completed":
            print(f"Pipeline: {session.status} ⚠️  (YELLOW — completed with "
                  f"{len(session.errors)} step verdict failure(s))")
        else:
            print(f"Pipeline: {session.status} ❌ (RED)")
        print(f"Session: {session.session_dir}")
        print(f"Errors: {len(session.errors)}")
        if session.status == "completed" and session.errors:
            print("⚠️  Completed with step verdict failures — review session.errors "
                  "before treating this run as passing.")
        print()
        
        log.info(f"Pipeline finished: {session.status}, errors={len(session.errors)}")

        # Portal 方案 B (2026-08-10): 消费计量——LLM token 用量写入 usage_log。
        # 仅 org_id>0 时记录（CLI 无 org 上下文默认 0，单机部署不计量）；失败不阻塞 pipeline。
        # Phase 9 (2026-08-10): 携带用户归因（user_id/user_email/run_id）。
        if getattr(session, "org_id", 0):
            try:
                from yuleosh.store import Store
                from yuleosh.usage import record_pipeline_run
                record_pipeline_run(
                    Store(), session.org_id, 0,
                    llm_tokens=getattr(session, "token_usage_total", 0) or 0,
                    user_id=getattr(session, "user_id", None),
                    user_email=getattr(session, "user_email", None),
                    run_id=getattr(session, "run_id", None),
                )
                log.info("Usage recorded: org=%s llm_tokens=%d", session.org_id, session.token_usage_total)
            except Exception as _usage_err:
                log.warning("Usage recording failed (non-fatal): %s", _usage_err)

        # Token usage summary
        if session.token_usage_total > 0:
            step_tokens = [
                f"  {s['step']}: {s['usage'].get('total_tokens', 0)} tokens"
                for s in session.token_usage_steps
            ]
            log.info(
                "Pipeline token usage: %d total tokens across %d LLM calls:\n%s",
                session.token_usage_total,
                len(session.token_usage_steps),
                "\n".join(step_tokens),
            )
            print(f"\n📊 Token Usage: {session.token_usage_total} total tokens "
                  f"({len(session.token_usage_steps)} LLM calls)")
            for s in session.token_usage_steps:
                u = s["usage"]
                print(f"   {s['step']}: {u.get('total_tokens', 0)} tokens "
                      f"(prompt {u.get('prompt_tokens', 0)}, "
                      f"completion {u.get('completion_tokens', 0)})")

        # ⏱ Step-level timing summary (perf observability, 2026-08-19)
        # 基线: docs/planning/pipeline-perf-baseline-2026-08-19.md.
        # 聚合趋势: scripts/profile_pipeline_steps.py --dir <project_root>
        _print_step_timings(session)

        # Send notification on pipeline completion or failure
        if _notify:
            try:
                _notify(
                    name=session.name,
                    status=session.status,
                    total_steps=len(_steps),
                    completed_steps=sum(1 for s in session.steps if s.get("status") == "completed"),
                    errors=session.errors,
                )
            except Exception as ne:
                log.warning(f"Notification failed: {ne}")

        return session
    except Exception as e:
        log.critical(f"Pipeline orchestrator crashed: {e}")
        print(f"\n❌ Pipeline orchestrator crashed: {e}", file=sys.stderr)
        sys.exit(1)


def status_pipeline(name: Optional[str] = None) -> None:
    """Display pipeline session status(es).

    Args:
        name: Optional session name. If None, lists all sessions.

    Phase 9 (2026-08-10): session directories are named by run_id (unique
    per run). Display name comes from session.json['name'], not the dir
    name. Legacy name-dirs (pre-v9) are still matched for backward compat.
    """
    base = Path(os.environ.get("OSH_HOME", ".")) / ".osh" / "sessions"

    sessions = []
    if name:
        # Match by display name — scan dirs, compare session.json['name'].
        if base.exists():
            for d in sorted(base.iterdir()):
                if not d.is_dir():
                    continue
                sfile = d / "session.json"
                if not sfile.exists():
                    # Legacy: dir name itself is the session name.
                    if d.name == name:
                        sessions.append(d.name)
                    continue
                try:
                    with open(sfile) as f:
                        data = json.load(f)
                except (json.JSONDecodeError, OSError):
                    if d.name == name:
                        sessions.append(d.name)
                    continue
                if data.get("name") == name:
                    sessions.append(d.name)
    else:
        sessions = sorted([d.name for d in base.iterdir() if d.is_dir()])

    if not sessions:
        print("No pipeline sessions found.")
        return

    for sname in sessions:
        sfile = base / sname / "session.json"
        if sfile.exists():
            with open(sfile) as f:
                data = json.load(f)
            status_icon = {"completed": "✅", "running": "🔄", "failed": "❌", "created": "📋"}
            icon = status_icon.get(data["status"], "❓")
            steps_done = sum(1 for s in data["steps"] if s["status"] == "completed")
            steps_total = len(data["steps"])
            print(f"  {icon} {sname}: [{steps_done}/{steps_total}] {data['status']}")


# ------------------------------------------------------------------
# LLM Fallback Integration
# ------------------------------------------------------------------


def _propagate_step_verdict(
    session: "PipelineSession",
    step_idx: int,
    step_key: str,
    output_path: str,
) -> Optional[str]:
    """Propagate a step artifact's ``status`` field into session state.

    Review/test steps write their verdict into a JSON artifact (e.g.
    ``build-review.json`` with ``status: "failed"``) without raising.
    Without propagation, the session would report every step as
    ``completed`` and the final ``Errors`` count stays 0 even when
    reviews failed — a misleading "all green" summary.

    Gate policy (方向3, 2026-08-11): the strength of each step is
    resolved via ``yuleosh.ci.gate_policy.resolve_gate``:
      - block: verdict ``failed`` → step marked failed, error recorded,
        and the pipeline is interrupted (returns ``"block"`` so the
        caller breaks the step loop).
      - warn : verdict ``failed`` → step marked failed, warning recorded
        in ``session.errors``, pipeline continues (legacy behavior).
      - info : verdict ``failed`` → step stays ``completed`` with the
        detail recorded only on the step (no ``session.errors`` entry).

    Semantics (legacy, preserved for warn/info):
      - artifact status ``retry``/``warn`` → step marked ``completed`` with
        the note recorded in errors (informational).

    This never raises; verdict propagation must not break the pipeline
    except via the explicit ``"block"`` return.

    Returns
    -------
    Optional[str]
        ``"block"`` if the step's gate policy is ``block`` and the
        verdict was ``failed`` (caller should interrupt); ``None``
        otherwise.
    """
    try:
        # Resolve gate strength (defaults: warn — legacy behavior)
        gate = "warn"
        try:
            from yuleosh.ci.gate_policy import resolve_gate

            gate = resolve_gate(step_key)
        except Exception:  # pragma: no cover - defensive
            pass

        if not output_path:
            return None
        p = Path(str(output_path))
        if not p.exists() or p.suffix.lower() != ".json":
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        verdict = str(data.get("status", "")).strip().lower()
        if not verdict:
            return None
        # INCOMPLETE (2026-08-12): 验收类步骤 (test-qualification) 无法完成
        # 判定时 (如无系统级测试文件) 输出 status=incomplete。旧逻辑不认识
        # 该 verdict → 静默通过 → 假绿。现按 gate 强度同 failed 处置:
        #   block gate → 中断; warn → 记 errors; info → 仅 step 记录。
        if verdict in ("failed", "incomplete"):
            if step_idx < len(session.steps):
                session.steps[step_idx]["status"] = "failed"
                session.steps[step_idx]["completed_at"] = (
                    datetime.now().isoformat()
                )
            label = "FAILED" if verdict == "failed" else "INCOMPLETE"
            msg = f"[{step_key}] step verdict: {label} ({p.name})"
            if gate == "block":
                # ⛔ Blocking gate: interrupt pipeline
                if msg not in session.errors:
                    session.errors.append(msg)
                session.status = "failed"
                session.updated_at = datetime.now().isoformat()
                log.error(
                    "Step %s artifact verdict failed under BLOCK gate — pipeline interrupted",
                    step_key,
                )
                return "block"
            if gate == "info":
                # info: record on step detail only, no errors entry
                if step_idx < len(session.steps):
                    session.steps[step_idx]["detail"] = msg
                log.info("Step %s verdict failed under INFO gate (recorded only)", step_key)
                return None
            # warn (default): record error, continue
            if msg not in session.errors:
                session.errors.append(msg)
            session.updated_at = datetime.now().isoformat()
            log.warning("Step %s artifact verdict: failed (%s)", step_key, p.name)
        elif verdict in ("retry", "warn", "warning"):
            msg = f"[{step_key}] step verdict: {verdict.upper()} ({p.name})"
            if msg not in session.errors:
                session.errors.append(msg)
    except Exception as e:  # pragma: no cover - defensive
        log.debug("Verdict propagation skipped for %s: %s", output_path, e)
    return None


# ─── Realtime emit helpers (进程内总线, 失败不阻塞主链路) ───────────────────
# 2026-09-04: 接入 /api/v1/events/stream (SSE), 把 step 进出/文档证据落盘/
# run 终态广播给前端看板与左栏徽标。发射失败仅 debug log (业务线程不感知)。

import os as _os  # noqa: E402  (top-level 已导入 os, 此行仅为兼容性注释)

def _rt_run_id(session) -> str:
    """Realtime 事件的 run_id 取值 (Stage-6, 2026-09-05)。

    统一 ``session.run_id`` —— 与 API 侧 ``POST /api/v1/pipeline/run``
    返回的 run_id、checkpoint/run_done 事件、以及前端「跳到流水线」用的
    ``?run=<id>`` 完全一致。之前用 ``session.name``（形如 "run-abc123"）
    会与 API 的 "abc123" 错开, 前端 store 里同一个 run 被拆成两个 key。
    """
    return str(
        getattr(session, "run_id", "")
        or getattr(session, "session_id", "")
        or getattr(session, "name", "")
        or ""
    )


def _rt_project_dir(project_dir: str = "") -> str:
    """Realtime 事件的 project_dir 取值。

    Stage-6 (2026-09-05) 修正: 之前 4 个 emit helper 一律用 ``OSH_HOME``,
    导致所有 run 在前端都显示成同一个目录（OSH_HOME 根），且前端
    ``ProjectStatsFetcher`` 拿 basename 去查 projects-stats 时查的是
    OSH_HOME 的 basename（例如 "yuleOSH"），永远查不到项目 spec →
    数字徽标恒为 0。现在优先用编排器传入的真实 ``project_dir``,
    缺失时才回退 OSH_HOME。
    """
    return str(project_dir or _os.environ.get("OSH_HOME", ""))


def _emit_realtime_stage_start(session, step_idx: int, step_key: str,
                               step_name: str, agent: str,
                               project_dir: str = "") -> None:
    try:
        from yuleosh.realtime import emit_pipeline_stage_start
        emit_pipeline_stage_start(
            run_id=_rt_run_id(session),
            project_dir=_rt_project_dir(project_dir),
            step_index=step_idx,
            step_key=step_key,
            step_title=step_name,
            agent=agent,
        )
    except Exception as _e:  # noqa: BLE001
        log.debug("realtime stage_start swallowed: %s", _e)


def _emit_realtime_stage_end(session, step_idx: int, step_key: str,
                             step_name: str, agent: str, status: str,
                             started_at, finished_at,
                             project_dir: str = "") -> None:
    try:
        from yuleosh.realtime import emit_pipeline_stage_end
        _dur_ms: int | None = None
        try:
            if started_at and finished_at:
                _dur_ms = int((finished_at - started_at).total_seconds() * 1000)
        except Exception:  # noqa: BLE001
            _dur_ms = None
        emit_pipeline_stage_end(
            run_id=_rt_run_id(session),
            project_dir=_rt_project_dir(project_dir),
            step_index=step_idx,
            step_key=step_key,
            step_title=step_name,
            status=status,
            duration_ms=_dur_ms,
        )
    except Exception as _e:  # noqa: BLE001
        log.debug("realtime stage_end swallowed: %s", _e)


def _emit_realtime_stage_skipped(session, step_idx: int, step_key: str,
                                 step_name: str, agent: str,
                                 project_dir: str = "") -> None:
    try:
        from yuleosh.realtime import emit_pipeline_stage_end
        emit_pipeline_stage_end(
            run_id=_rt_run_id(session),
            project_dir=_rt_project_dir(project_dir),
            step_index=step_idx,
            step_key=step_key,
            step_title=step_name,
            status="skipped",
            duration_ms=None,
        )
    except Exception as _e:  # noqa: BLE001
        log.debug("realtime stage_end(skipped) swallowed: %s", _e)


def _emit_realtime_file_produced(output_path, step_key: str, session,
                                 project_dir: str = "") -> None:
    """给前端看板 「文档证据即时显示」用的 file_produced 事件。

    output_path 是 step handler 返回的文件路径。空 / 不存在则跳过。
    """
    try:
        from pathlib import Path as _P
        if not output_path:
            return
        _path = _P(str(output_path))
        if not _path.exists() or not _path.is_file():
            return
        from yuleosh.realtime import emit_pipeline_file_produced
        emit_pipeline_file_produced(
            run_id=_rt_run_id(session),
            project_dir=_rt_project_dir(project_dir),
            file_path=_path.name,
            category=_path.suffix.lstrip(".").lower() or "file",
            size_bytes=_path.stat().st_size,
        )
    except Exception as _e:  # noqa: BLE001
        log.debug("realtime file_produced swallowed: %s", _e)


def _execute_step(
    session: "PipelineSession",
    step_idx: int,
    step_key: str,
    agent: str,
    step_name: str,
    handler: Callable,
    spec_path: str,
    project_dir: str,
    from_step: int,
) -> str:
    """Execute a single pipeline step (serial or D2 parallel worker).

    Returns:
        ``"ok"`` — step completed (possibly cached); ``"block"`` — block
        gate verdict failed (pipeline must stop); ``"failed"`` — handler
        raised (pipeline must stop).

    D2 (2026-08-19): 单步执行逻辑从主循环抽出, 供串行与并行组共用 —
    并行 worker 线程内通过 ``step_context.set_step_key`` 设置 thread-local
    step_key (session.pipeline_knowledge_step_key 是共享字段, 并发会覆盖)。
    """
    from yuleosh.pipeline.step_context import set_step_key as _set_tl_key

    # ── Realtime emit: 断点续跑的 skipped 也要给前端一帧, 否则看板会缺位 ──
    if step_idx + 1 < from_step:
        session.steps[step_idx]["status"] = "skipped"
        session.steps[step_idx]["completed_at"] = datetime.now().isoformat()
        # 注意: 函数名是 _emit_realtime_stage_skipped (Stage-6 修正拼写,
        # 之前写成 _emit_realtime_skipped —— 断点续跑时会 NameError 中断)。
        _emit_realtime_stage_skipped(
            session, step_idx, step_key, step_name, agent,
            project_dir=project_dir,
        )
        return "ok"

    # ── B1 缓存 (2026-08-12): 确定性步骤内容寻址缓存 ──
    _cache_fp = None
    try:
        from yuleosh.pipeline import step_cache as _step_cache
    except ImportError:  # pragma: no cover - defensive
        _step_cache = None

    if _step_cache and _step_cache.is_cacheable(step_key) \
            and _step_cache.cache_enabled():
        _cache_fp = _step_cache.compute_fingerprint(session, step_key)
        if _step_cache.lookup(project_dir, step_key, _cache_fp):
            try:
                _restored = _step_cache.restore(
                    project_dir, step_key, _cache_fp, session
                )
            except OSError as _restore_err:
                log.warning("step-cache restore failed (fallback): %s",
                            _restore_err)
                _cache_fp = None
                _restored = None
            if _restored:
                _fp = _cache_fp or ""  # 命中路径下必非 None (类型收窄)
                session.complete_step(step_idx, _restored)
                session.set_artifact(step_key, _restored)
                session.steps[step_idx]["cached"] = True
                session.steps[step_idx]["detail"] = (
                    f"cached (指纹 {_fp[:10]})"
                )
                print(f"  ♻️  [{agent}] {step_name} — cached "
                      f"(指纹 {_fp[:10]}), 复用产物")
                _propagate_step_verdict(
                    session, step_idx, step_key, _restored
                )
                log.info("Step %s cache hit (%s)", step_key, _fp[:10])
                # Realtime: 缓存命中也要给前端一帧, 否则对未跑到的 step 看板永远 unknown
                _emit_realtime_stage_end(
                    session, step_idx, step_key, step_name, agent,
                    status="cached", started_at=None, finished_at=None,
                    project_dir=project_dir,
                )
                _emit_realtime_file_produced(
                    _restored, step_key, session, project_dir=project_dir,
                )
                return "ok"

    _rt_started_at = datetime.now()
    session.start_step(step_idx)
    # Realtime: 进入 step 立即推 stage_start, 前端阶段看板可以即时点亮
    _emit_realtime_stage_start(
        session, step_idx, step_key, step_name, agent,
        project_dir=project_dir,
    )
    # Stage-6 (2026-09-05): 设置当前 LLM 调用上下文 (ContextVar), 让低层
    # LLMClient.call 自动 emit pipeline.llm_call 关联到此 run/step。
    # step handler 可能递归/异步, ContextVar 在 asyncio task 与线程内独立,
    # 不会污染其它 run。reset 放在下方已有的 finally 里 (不新开 try 块 ——
    # 新开会让下方 `finally:` 与之配对, 破坏原有的 try/except/finally)。
    _ctx_token = None
    try:
        from yuleosh.realtime import (
            LLMCallContext,
            set_current_llm_call_context,
        )

        _ctx_token = set_current_llm_call_context(LLMCallContext(
            run_id=session.run_id,
            project_dir=_rt_project_dir(project_dir),
            step_key=step_key,
            step_index=step_idx,
        ))
    except Exception as _ctx_err:  # noqa: BLE001 — realtime 是 best-effort 装饰层
        _ctx_token = None
        log.debug("set LLM call context skipped: %s", _ctx_err)
    # 方案 A (2026-08-07): expose the current step key so the
    # unified knowledge injection at _call_llm can match per-step
    # skills and produce step-specific context.
    session.pipeline_knowledge_step_key = step_key
    # D2: worker 线程内 thread-local step_key (并发安全)。
    # try/finally 清理 — 防止 thread-local 残留到后续串行步骤/测试
    # （pytest 主线程复用, 残留会污染下一个测试的 role 解析）。
    from yuleosh.pipeline.step_context import clear_step_key as _clear_tl_key

    _set_tl_key(step_key)

    print(f"  [{step_idx+1}] {agent}: {step_name}")
    log.info(f"Step {step_idx+1}: [{agent}] {step_name}")

    try:
        # Run step handler
        if step_key == "final-report":
            session.status = "completed"

        # --- LLM Fallback Integration ---
        output_path = _run_step_with_fallback(
            handler, session, step_key, step_name, spec_path,
        )

        # B1 缓存: 执行完成后入库 (确定性步骤; 失败/异常不入库)
        if _cache_fp and _step_cache:
            try:
                _step_cache.store(project_dir, step_key, _cache_fp, output_path)
            except Exception as _store_err:  # pragma: no cover
                log.warning("step-cache store failed (non-fatal): %s",
                            _store_err)

        session.complete_step(step_idx, str(output_path))
        session.set_artifact(step_key, str(output_path))
        # Realtime: 成功完成推 stage_end + file_produced (给前端「文件即时显示」)
        _rt_finished_at = datetime.now()
        _emit_realtime_stage_end(
            session, step_idx, step_key, step_name, agent,
            status="completed", started_at=_rt_started_at, finished_at=_rt_finished_at,
            project_dir=project_dir,
        )
        _emit_realtime_file_produced(
            output_path, step_key, session, project_dir=project_dir,
        )
        if _propagate_step_verdict(session, step_idx, step_key, output_path) == "block":
            print(f"  ⛔ Block gate failed: {step_key} — pipeline interrupted")
            print()
            return "block"
        if step_key == "final-report":
            session._save()
        log.info(f"Step {step_idx+1} completed: {step_key}")
        print()
        return "ok"
    except (PipelineStepError, RuntimeError) as e:
        log.error(f"Step {step_idx+1} [{agent}] {step_name} failed: {e}")
        log.debug(traceback.format_exc())
        session.fail_step(step_idx, str(e))
        # Realtime: 失败也推 stage_end, 看板需要红点提示用户
        _rt_failed_at = datetime.now()
        _emit_realtime_stage_end(
            session, step_idx, step_key, step_name, agent,
            status="failed", started_at=_rt_started_at, finished_at=_rt_failed_at,
            project_dir=project_dir,
        )
        print(f"  ❌ Step failed: {e}")
        print()
        return "failed"
    finally:
        _clear_tl_key()
        # Stage-6 (2026-09-05): 还原 LLM 调用上下文, 避免污染后续 step/run
        if _ctx_token is not None:
            try:
                from yuleosh.realtime import reset_current_llm_call_context

                reset_current_llm_call_context(_ctx_token)
            except Exception as _ctx_reset_err:  # noqa: BLE001
                log.debug("reset LLM call context skipped: %s", _ctx_reset_err)


def _run_parallel_group(
    session: "PipelineSession",
    members: list[tuple[int, str, str, str, Callable]],
    from_step: int,
    project_dir: str,
    spec_path: str,
) -> tuple[bool, bool]:
    """Run a D2 parallel group's steps concurrently (ThreadPoolExecutor).

    Args:
        members: [(step_idx, step_key, agent, step_name, handler), ...]
        from_step / project_dir / spec_path: forwarded to _execute_step.

    Returns:
        (blocked, failed) — True when any member's gate blocked / handler
        failed.  Group semantics: all members run to completion (no early
        cancellation), then the worst outcome is aggregated — identical to
        verify-loop's merged semantics.  Block/fail interrupts the pipeline
        only AFTER the whole group finishes, so no partial state is lost.
    """
    from yuleosh.pipeline.step_context import (
        clear_step_key as _clear_tl_key,
        set_step_key as _set_tl_key,
    )

    results: dict[str, str] = {}

    def _worker(m: tuple[int, str, str, str, Callable]) -> tuple[str, str]:
        _idx, _key, _agent, _name, _handler = m
        _set_tl_key(_key)
        try:
            _status = _execute_step(
                session, _idx, _key, _agent, _name, _handler,
                spec_path, project_dir, from_step,
            )
            return _key, _status
        finally:
            _clear_tl_key()

    with ThreadPoolExecutor(max_workers=len(members)) as _ex:
        _futures = {_ex.submit(_worker, m): m[1] for m in members}
        for _fut in as_completed(_futures):
            _key = _futures[_fut]
            try:
                _key2, _status = _fut.result()
                results[_key2] = _status
            except Exception as _e:  # pragma: no cover - defensive
                log.error("Parallel worker for %s crashed: %s", _key, _e)
                results[_key] = "failed"

    blocked = any(s == "block" for s in results.values())
    failed = any(s == "failed" for s in results.values())
    _summary = ", ".join(f"{k}={v}" for k, v in results.items())
    log.info("Parallel group finished: %s", _summary)
    if blocked or failed:
        print(f"  ⛔ 并行组失败: {_summary}")
    return blocked, failed


def _run_step_with_fallback(
    handler: Callable,
    session: PipelineSession,
    step_key: str,
    step_name: str,
    spec_path: str,
) -> str:
    """Run a pipeline step handler with LLM output validation and fallback.

    The handler is called normally.  Afterward, if the output looks like
    LLM-generated content (contains certain markers or is structured),
    the fallback chain validates it.

    If the handler raises an exception, it's caught and surfaced as a
    PipelineStepError, which blocks dependent steps.
    """
    try:
        output_path = handler(session)
        return str(output_path)
    except PipelineStepError as e:
        # ⛔ Gate/blocking errors must NOT fall back — a failed gate is a
        # failed gate. Falling back here would silently mark the step done
        # and let the pipeline "complete" on placeholder output.
        log.error("Step [%s] hard-failed (no fallback): %s", step_key, e)
        raise
    except Exception as e:
        log.error("Step [%s] handler raised: %s", step_key, e)
        log.debug(traceback.format_exc())

        # Attempt template fallback
        fallback_result = apply_fallback_chain(
            step_name=step_key,
            llm_output="",
            template_ctx={"title": step_name},
            session_dir=session.session_dir,
            start_level=4,  # Skip straight to template
        )

        if fallback_result.status == "fallback":
            # Write the template fallback output
            fallback_path = session.session_dir / f"{step_key}-fallback.md"
            fallback_path.write_text(fallback_result.output)
            log.info("Step [%s] used template fallback: %s", step_key, fallback_path)
            return str(fallback_path)

        raise PipelineStepError(f"Step [{step_key}] failed: {e}") from e


def main():
    if len(sys.argv) < 2:
        print("Usage:", file=sys.stderr)
        print("  python3 run.py <spec.md>          — Run full pipeline", file=sys.stderr)
        print("  python3 run.py status [name]      — Show pipeline status", file=sys.stderr)
        print("  python3 run.py --profile <name> <spec.md>  — Run with specific profile", file=sys.stderr)
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    try:
        if cmd == "status":
            status_pipeline(sys.argv[2] if len(sys.argv) > 2 else None)
        elif cmd == "--profile" and len(sys.argv) >= 4:
            profile_name = sys.argv[2]
            spec_path = sys.argv[3]
            session = run_pipeline(spec_path, profile=profile_name)
            sys.exit(0 if session.status == "completed" else 1)
        else:
            session = run_pipeline(cmd)
            sys.exit(0 if session.status == "completed" else 1)
    except KeyboardInterrupt:
        log.warning("Pipeline interrupted by user")
        print("\n⚠️  Pipeline interrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        log.critical(f"Unhandled exception in pipeline: {e}")
        print(f"\n❌ Unhandled exception: {e}", file=sys.stderr)
        sys.exit(1)



if __name__ == "__main__":
    main()

