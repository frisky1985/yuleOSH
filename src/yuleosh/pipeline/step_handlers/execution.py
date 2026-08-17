#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0
# 500-line guardrail: current 498 lines (2026-06-15). Monitor growth and split if reaching 500.

"""
Execution step handlers — architecture, development, test planning, self-test.

Exports:
  step_claude_arch      — AI-powered architecture design
  step_claude_dev       — AI-powered development planning
  step_test_planning    — AI-powered test planning
  step_claude_test      — self-test with real test runner output
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm, _parse_spec
from yuleosh.pipeline.prompts import (
    build_architecture_prompt,
    build_development_prompt,
    build_test_planning_prompt,
)
from yuleosh.codegen.prompts import collect_existing_headers, collect_seed_sources

log = logging.getLogger("pipeline.step_handlers.execution")

__all__ = ["step_claude_arch", "step_claude_dev", "step_test_planning", "step_claude_test"]


@timed_step
def step_claude_arch(session: PipelineSession) -> str:
    """Step 4: Claude — AI-powered architecture design.

    Scans the project directory to discover actual source structure,
    then sends the spec + structure to the LLM for real architecture analysis.
    """
    try:
        print("  💻 [Claude] Running AI-powered architecture analysis...")
        log.info("Running AI-powered architecture analysis")

        # Discover project structure
        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()
        src_dir = project_dir / "src"

        directories = []
        source_files = []
        tech_stack = set()
        src_tree_lines = []

        if src_dir.exists():
            for root, dirs, files in os.walk(src_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                rel_dir = Path(root).relative_to(project_dir)
                directories.append(str(rel_dir))
                indent = "  " * (len(Path(rel_dir).parts) - 1) if len(Path(rel_dir).parts) > 1 else ""
                src_tree_lines.append(f"{indent}{Path(rel_dir).name}/")
                for f in sorted(files):
                    if f.endswith((".py", ".sh", ".html", ".js", ".css", ".ts", ".go", ".rs", ".json", ".toml", ".yaml", ".yml", ".md")):
                        source_files.append(str(Path(rel_dir) / f))
                        src_tree_lines.append(f"{indent}  {f}")
                        ext = Path(f).suffix
                        if ext == ".py":
                            tech_stack.add("Python")
                        elif ext == ".go":
                            tech_stack.add("Go")
                        elif ext == ".rs":
                            tech_stack.add("Rust")
                        elif ext in (".html", ".js", ".css", ".ts"):
                            tech_stack.add("Web (HTML/JS/CSS)")
                        elif ext == ".sh":
                            tech_stack.add("Shell")

        # Read spec
        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"

        # Read key source files for context
        key_file_snippets = []
        for sf in sorted(source_files)[:15]:
            fpath = project_dir / sf
            if fpath.exists() and fpath.stat().st_size < 10000:
                try:
                    content = fpath.read_text()[:2000]
                    key_file_snippets.append(f"### {sf}\n```\n{content}\n```")
                except Exception:
                    pass

        tech_stack_str = ", ".join(sorted(tech_stack)) if tech_stack else "Python"
        tree_str = "\n".join(src_tree_lines[:80])

        system_prompt, user_prompt = build_architecture_prompt(
            spec_content=spec_content,
            spec_name=spec_path.name,
            session_name=session.name,
            directories=directories,
            source_files=source_files,
            tech_stack=sorted(tech_stack),
            source_tree_str=tree_str,
            key_file_snippets=key_file_snippets,
        )

        try:
            # max_tokens=6144 (2026-08-17): 架构文档随 spec 增长而变长,
            # 默认 4096 会截断输出 (r18 architecture.md §5.1 表截断被
            # claude-review 指出). 对齐 TASK_BUDGETS architecture_design.
            result = _call_llm(session, system_prompt, user_prompt, max_tokens=6144)
        except Exception as e:
            log.error(f"LLM call failed during architecture analysis: {e}")
            raise PipelineStepError(
                f"Architecture analysis LLM call failed: {e}\n"
                f"Spec: {session.spec_path}"
            )

        analysis = result["content"]
        usage = result.get("usage", {})
        log.info(
            "LLM returned %d tokens (prompt=%s, completion=%s)",
            usage.get("total_tokens", "?"),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
        )
        session.token_usage_total += usage.get("total_tokens", 0)
        session.token_usage_steps.append({"step": "architecture", "usage": usage})

        out_path = session.session_dir / "architecture.md"
        try:
            out_path.write_text(analysis)
        except OSError as e:
            log.error(f"Cannot write architecture: {e}")
            raise PipelineStepError(f"Cannot write architecture: {e}")
        print(f"  ✅ [Claude] AI architecture analysis at {out_path}")
        log.info(f"AI architecture analysis saved to {out_path}")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Architecture step failed: {e}")
        raise PipelineStepError(f"Architecture step failed: {e}")


@timed_step
def step_claude_dev(session: PipelineSession) -> str:
    """Step 5: Claude — AI-powered development.

    Default mode: reads spec content + architecture analysis from artifacts,
    sends to LLM, and generates a real development plan with task breakdown
    and tech debt identification.

    When ``session.development_mode == "generate-code"`` (D3), directly
    generates code files from spec/architecture/PRD, runs compile
    verification, and auto-fixes up to 3 rounds.  Files land under
    ``artifacts/generated-code/<session>/``.
    """
    if getattr(session, "development_mode", None) == "generate-code":
        return _step_claude_dev_codegen(session)
    return _step_claude_dev_planning(session)


def _detect_project_language(project_dir: Path) -> Optional[str]:
    """Heuristic project language detection for codegen language_hint.

    Returns ``c`` for CMake/C projects (CMakeLists.txt present or .c/.h
    sources dominate), ``python`` for Python projects, else None.

    2026-08-14 headlamp dogfood: language_hint 未设置时 LLM 自由发挥 →
    生成 Python 到 C 项目假绿。此探测给 codegen 明确语言约束。
    """
    root = Path(project_dir)
    if (root / "CMakeLists.txt").exists() or (root / "Makefile").exists():
        return "c"
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        return "python"
    return None


def _step_claude_dev_codegen(session: PipelineSession) -> str:
    """D3 codegen branch: spec/arch/PRD → code → verify → auto-fix."""
    from yuleosh.codegen.engine import CodegenEngine, build_codegen_report
    from yuleosh.codegen.prompts import build_codegen_prompt
    from yuleosh.pipeline.step_classes import (
        _collect_seed_contract,
        _make_behavior_verify,
    )

    print("  💻 [Claude] Running generate-code mode (D3)...")
    log.info("Running generate-code mode (D3)")
    try:
        # 2026-08-12: 优先用 session 创建时解析的 project_dir (OSH_HOME),
        # 避免在 handler 内重新解析 — 测试/嵌套调用时环境变量可能已变,
        # 退化为 cwd 会把错误目录当项目根 (seed 复制/API 契约全错)。
        project_dir = Path(getattr(session, "project_dir", None)
                           or os.environ.get("OSH_HOME", ".")).resolve()
        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"
        architecture_content = artifacts_read(session.artifacts, "architecture") or ""
        prd_content = artifacts_read(session.artifacts, "prd") or ""
        super_content = artifacts_read(session.artifacts, "super-analysis") or ""

        cfg = session.config.get("codegen", {}) if getattr(session, "config", None) else {}
        # 结构性 smoke 特征 (2026-08-17, r21): 从项目 pipeline/config.yaml
        # codegen.structural_features 读入 — 编译通过后检查关键功能路径
        # (防夹检测调用/反转序列) 未被 LLM 全量重写删除。session.config 未
        # 注入时回退读项目配置文件, 保证独立运行时也生效。
        structural_features = cfg.get("structural_features") or {}
        forbidden_features = cfg.get("forbidden_features") or {}
        if not structural_features or not forbidden_features:
            try:
                _proj_cfg = project_dir / "pipeline" / "config.yaml"
                if _proj_cfg.exists():
                    import yaml as _yaml
                    _raw = _yaml.safe_load(_proj_cfg.read_text(encoding="utf-8")) or {}
                    _cg = _raw.get("codegen") or {}
                    if not structural_features:
                        structural_features = _cg.get("structural_features") or {}
                    if not forbidden_features:
                        forbidden_features = _cg.get("forbidden_features") or {}
            except Exception as e:
                log.warning("structural_features load failed (non-fatal): %s", e)
        skills = cfg.get("skills") or ["autosar-coding"]
        target_language = cfg.get("target_language")
        build_cmd = cfg.get("build_cmd")
        language_hint = cfg.get("language")
        if not language_hint:
            language_hint = _detect_project_language(project_dir)

        # 方案 C seed 增量 (2026-08-12): 注入现有 src 代码作为基线,
        # engine 复制 seed 到输出目录, LLM 只增量修改。
        seed_sources = collect_seed_sources(project_dir)

        # CONTEXT.md 注入 (2026-08-14, headlamp dogfood): 领域术语 + 语言约束
        # 必须传给 codegen — 否则 LLM 不知项目语言, 生成错误语言代码假绿。
        context_content = ""
        context_path = project_dir / "CONTEXT.md"
        if context_path.exists():
            context_content = context_path.read_text(encoding="utf-8", errors="replace")

        # 机器抽取契约 (方案 A, 2026-08-16): spec-check 步骤抽取的 contracts.json
        # (接口签名/护栏/参数边界/NVM 布局) — codegen 的硬契约, 不依赖 PRD 转述。
        contracts_json = ""
        contracts_path = Path(session.session_dir) / "contracts.json"
        if contracts_path.exists():
            try:
                contracts_data = json.loads(contracts_path.read_text(encoding="utf-8"))
                contracts_json = json.dumps(
                    contracts_data.get("contracts", {}), ensure_ascii=False, indent=1
                )
            except (OSError, json.JSONDecodeError) as e:
                log.warning(f"contracts.json read failed (non-fatal): {e}")

        system_prompt, user_prompt = build_codegen_prompt(
            spec_content=spec_content,
            spec_name=Path(session.spec_path).name,
            architecture_content=architecture_content,
            prd_content=prd_content,
            super_analysis_content=super_content,
            skills=skills,
            target_language=target_language,
            existing_headers=collect_existing_headers(project_dir),
            seed_sources=seed_sources,
            context_content=context_content,
            contracts_json=contracts_json,
        )

        engine = CodegenEngine(
            output_dir=cfg.get("output_dir"),
            max_retries=int(cfg.get("max_retries", 3)),
            llm_client=getattr(session, "llm_client", None),
            max_tokens=int(cfg.get("max_tokens", 16000)),
            seed_dir=project_dir if seed_sources else None,
            seed_contract=_collect_seed_contract(project_dir),
            behavior_verify=_make_behavior_verify(project_dir),
            structural_features=structural_features,
            forbidden_features=forbidden_features,
        )
        result = engine.generate(
            session, system_prompt, user_prompt,
            language_hint=language_hint, build_cmd=build_cmd,
        )

        note = (
            f"# Development (generate-code mode): {session.name}\n\n"
            f"> Status: {result.status}\n"
            f"> Generated files: {len(result.files)}\n"
            f"> Output dir: {result.output_dir}\n"
            f"> Report: {result.report_path}\n"
            f"> Rounds: {result.rounds} (max retries {result.max_retries})\n\n"
            + build_codegen_report(result, session)
        )
        out_path = session.session_dir / "development-plan.md"
        out_path.write_text(note, encoding="utf-8")
        print(f"  ✅ [Claude] generate-code: {len(result.files)} files, "
              f"status={result.status}, report={result.report_path}")
        log.info(
            "Codegen complete: status=%s files=%d rounds=%d",
            result.status, len(result.files), result.rounds,
        )
        return result.report_path
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Codegen step failed: {e}")
        raise PipelineStepError(f"Codegen step failed: {e}")


def _step_claude_dev_planning(session: PipelineSession) -> str:
    """Legacy planning behavior (unchanged)."""
    try:
        print("  💻 [Claude] Running AI-powered development planning...")
        log.info("Running AI-powered development planning")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # --- Gather project metrics (git stats + line counts) ---
        git_log = ""
        git_commits = 0
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-10", "--format=%h %s (%ar)"],
                capture_output=True, text=True, timeout=10, cwd=project_dir
            )
            if result.returncode == 0:
                git_log = result.stdout.strip()
                git_commits = len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0
        except Exception as e:
            log.warning(f"Git log failed (non-fatal): {e}")
            git_log = "(not a git repository or git not available)"

        src_lines = 0
        test_lines = 0
        src_files = list(project_dir.glob("src/**/*.py")) + list(project_dir.glob("src/**/*.sh")) + list(project_dir.glob("src/**/*.html"))
        test_files = list(project_dir.glob("tests/**/*.py"))

        for f in src_files:
            try:
                src_lines += len(f.read_text().splitlines())
            except Exception:
                pass
        for f in test_files:
            try:
                test_lines += len(f.read_text().splitlines())
            except Exception:
                pass

        # --- Read spec content ---
        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"

        # --- Read artifacts ---
        architecture_content = artifacts_read(session.artifacts, "architecture")
        prd_content = artifacts_read(session.artifacts, "prd")
        super_content = artifacts_read(session.artifacts, "super-analysis")

        # --- Build LLM prompt ---
        system_prompt, user_prompt = build_development_prompt(
            spec_content=spec_content,
            spec_name=Path(session.spec_path).name,
            architecture_content=architecture_content,
            prd_content=prd_content,
            super_analysis_content=super_content,
            src_lines=src_lines,
            src_file_count=len(src_files),
            test_lines=test_lines,
            test_file_count=len(test_files),
            git_commits=git_commits,
            git_log=git_log,
        )

        try:
            result = _call_llm(session, system_prompt, user_prompt, max_tokens=4096)
        except Exception as e:
            log.error(f"LLM call failed during development planning: {e}")
            raise PipelineStepError(
                f"Development planning LLM call failed: {e}\n"
                f"Spec: {session.spec_path}"
            )

        plan = result["content"]
        usage = result.get("usage", {})
        log.info(
            "LLM returned %d tokens (prompt=%s, completion=%s)",
            usage.get("total_tokens", "?"),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
        )
        session.token_usage_total += usage.get("total_tokens", 0)
        session.token_usage_steps.append({"step": "development", "usage": usage})

        full_output = (
            f"# Development Plan: {session.name}\n\n"
            f"> Generated by: LLM ({result.get('model', 'unknown')})\n"
            f"> Source spec: {session.spec_path}\n"
            f"> Tokens: {usage.get('total_tokens', '?')} "
            f"(prompt {usage.get('prompt_tokens', '?')} + "
            f"completion {usage.get('completion_tokens', '?')})\n\n"
            f"{plan}"
        )

        out_path = session.session_dir / "development-plan.md"
        try:
            out_path.write_text(full_output)
        except OSError as e:
            log.error(f"Cannot write development plan: {e}")
            raise PipelineStepError(f"Cannot write development plan: {e}")
        print(f"  ✅ [Claude] AI development plan at {out_path}")
        log.info(f"AI development plan saved to {out_path}")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Development step failed: {e}")
        raise PipelineStepError(f"Development step failed: {e}")


@timed_step
def step_codegen_deploy(session: PipelineSession) -> str:
    """Step: 小明 — 代码产物部署 (codegen artifacts → project src/).

    The development/codegen step writes generated files under
    ``artifacts/generated-code/<session>/``.  This step deploys the generated
    ``src/`` tree into the project so downstream build/test/coverage steps
    measure the real generated code instead of template stubs.

    Behaviour:
      - No generated artifacts → skipped (planning mode), never fails.
      - Only the ``src/`` tree is deployed; top-level files (CMakeLists.txt
        etc.) are left untouched so the project's host test/coverage build
        harness is preserved.
      - 0-byte files are skipped with a warning (LLM truncated-output anomaly,
        e.g. a stray empty ``hal_h``).
    """
    project_dir = Path(session.project_dir)
    report_dir = project_dir / ".yuleosh" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "codegen-deploy.json"

    try:
        from yuleosh.codegen.engine import default_output_dir
        gen_dir = Path(default_output_dir(project_dir, session.name))
    except Exception:
        gen_dir = project_dir / "artifacts" / "generated-code" / session.name

    if not gen_dir.exists() or not (gen_dir / "src").exists():
        print("  ⏭️  [小明] codegen-deploy: no generated src/ artifacts — skipped")
        report = {"status": "skipped", "deployed": [], "skipped_empty": []}
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return str(report_path)

    # Guardrail: never deploy failed codegen output (LLM produced broken or
    # incomplete code — verify loop exhausted retries). Deploying it would
    # overwrite known-good src/ with broken files.
    report_md = gen_dir / "codegen-report.md"
    if report_md.exists():
        content = report_md.read_text(encoding="utf-8", errors="replace")
        if "Status: ❌ failed" in content or "Status: failed" in content:
            print("  ⏭️  [小明] codegen-deploy: codegen status=failed — skipped "
                  "(broken artifacts not deployed)")
            report = {"status": "skipped_codegen_failed", "deployed": [],
                      "skipped_empty": []}
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            return str(report_path)

    # Guardrail: API contract — generated headers must preserve the public
    # function API of the existing project headers.  A codegen that
    # re-architects the API (e.g. global-singleton vs context-struct) breaks
    # the established tests/harness; keep the known-good src/ and flag it.
    def _header_api_functions(h: Path) -> set[str]:
        text = h.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"//[^\n]*", "", text)
        funcs: set[str] = set()
        for m in re.finditer(r"\b([a-zA-Z_]\w*)\s*\([^;{}]*\);", text, flags=re.S):
            name = m.group(1)
            if name in {"if", "for", "while", "switch", "return",
                        "sizeof", "defined"}:
                continue
            funcs.add(name)
        return funcs

    existing_api: dict[str, set[str]] = {}
    generated_api: dict[str, set[str]] = {}
    for rel in ("src/app/include", "src/hal/include"):
        for h in sorted((project_dir / rel).glob("*.h")):
            existing_api[str(h.relative_to(project_dir))] = _header_api_functions(h)
        for h in sorted((gen_dir / rel).glob("*.h")):
            generated_api[str(h.relative_to(gen_dir))] = _header_api_functions(h)

    api_mismatch: list[str] = []
    for rel, funcs in sorted(existing_api.items()):
        gen_funcs = generated_api.get(rel, set())
        missing = funcs - gen_funcs
        if missing:
            api_mismatch.append(f"{rel}: missing {sorted(missing)}")
    if api_mismatch:
        print("  ⏭️  [小明] codegen-deploy: generated API breaks contract — "
              "skipped (keep known-good src/)")
        for m in api_mismatch:
            log.warning("codegen-deploy API mismatch: %s", m)
        report = {"status": "skipped_api_mismatch", "deployed": [],
                  "skipped_empty": [], "api_mismatch": api_mismatch}
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return str(report_path)

    src_gen = gen_dir / "src"
    deployed = []
    skipped_empty = []

    # ── 行为护栏 (2026-08-13) ──────────────────────────────────────
    # 编译+API 双护栏捕获不了"逻辑正确但行为回归"的代码 (LLM 删除既有
    # 状态机/reset/FAULT 处理 → 编译通过但测试失败)。行为护栏在部署前
    # 跑一次基线测试、部署后跑一次验证测试, 对比失败数: 增加即回归 →
    # 自动回滚 src/ 并标记, 让 pipeline 用 known-good 基线继续。
    # 2026-08-13 (体系化): 备份/回滚/runner 抽象到 guardrail 模块 —
    #   - 备份持久化落盘 .yuleosh/guardrail/backup-<run_id>/ (门禁联动前提)
    #   - CCTestRunner 统一测试执行 (TestRunner 协议)
    #   - OSH_GUARD_PROTECT_SRC=1 保护用户手动改动的 src/
    from yuleosh.pipeline.guardrail import (
        CCTestRunner,
        apply_change_set,
        protect_src_enabled,
        save_change_set,
        src_has_uncommitted_changes,
    )
    guard_enabled = os.environ.get("OSH_BEHAVIOR_GUARD", "1") != "0"
    guard_baseline = None
    guard_after = None
    guard_rollback = False
    guard_runner = CCTestRunner()
    # 部署前 src 备份 (回滚用) — 记录将被覆盖文件的原始内容
    pre_deploy_backup: dict[str, Optional[bytes]] = {}
    # 部署后 src 内容 (undo 用 — 门禁联动发现非部署问题时恢复部署)
    deployed_after: dict[str, bytes] = {}

    # ── 4️⃣ OSH_GUARD_PROTECT_SRC: 保护用户手动改动的 src ──
    if guard_enabled and protect_src_enabled():
        uncommitted = src_has_uncommitted_changes(project_dir)
        if uncommitted:
            print(f"  🛡️ [小明] OSH_GUARD_PROTECT_SRC=1 且 src/ 有 "
                  f"{len(uncommitted)} 个未提交改动 — 跳过部署 (保护用户手动代码)")
            log.warning(
                "codegen-deploy skipped: OSH_GUARD_PROTECT_SRC=1 and src/ has "
                "%d uncommitted change(s)", len(uncommitted),
            )
            report = {
                "status": "skipped_src_protected",
                "deployed": [],
                "skipped_empty": [],
                "protected_uncommitted": uncommitted[:20],
            }
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            return str(report_path)

    if guard_enabled:
        deployed_candidates = [
            p for p in sorted(src_gen.rglob("*"))
            if p.is_file() and p.stat().st_size > 0
        ]
    else:
        deployed_candidates = []
    if deployed_candidates:
        try:
            log.info("Behavior guardrail: running baseline tests before deploy")
            guard_baseline = guard_runner.run(project_dir, force_rebuild=True)
            print(f"  🛡️ [小明] 行为护栏: 基线测试 "
                  f"{guard_baseline.passed} passed / "
                  f"{guard_baseline.failed} failed "
                  f"(runner={guard_baseline.runner})")
        except Exception as e:
            log.warning("Behavior guardrail baseline test failed: %s", e)
            guard_baseline = None
    else:
        guard_baseline = None

    for src_file in sorted(src_gen.rglob("*")):
        if src_file.is_dir():
            continue
        if src_file.stat().st_size == 0:
            skipped_empty.append(str(src_file.relative_to(src_gen)))
            continue
        # relative to gen_dir so the generated tree keeps its src/ prefix
        # (relative_to(src_gen) would drop it and deploy to <proj>/app/…)
        rel = src_file.relative_to(gen_dir)
        dst = project_dir / rel
        # 备份部署前的原始内容 (回滚恢复用; 新文件记为 None → 回滚时删除)
        if dst.exists():
            try:
                pre_deploy_backup[str(rel)] = dst.read_bytes()
            except OSError:
                pre_deploy_backup[str(rel)] = None
        else:
            pre_deploy_backup[str(rel)] = None
        dst.parent.mkdir(parents=True, exist_ok=True)
        # 用 copy 而非 copy2: copy2 保留源 mtime → 若 gen 文件比 build 里的
        # object 旧, cmake 增量构建跳过重编 → ctest 测旧二进制 → 行为护栏
        # 假通过。copy 更新 mtime 为当前时间, 强制下游构建检测到变化。
        shutil.copy(src_file, dst)
        deployed.append(str(rel))
        try:
            deployed_after[str(rel)] = dst.read_bytes()
        except OSError:
            pass

    # 备份持久化落盘 (1️⃣) — 门禁联动/断点续跑从磁盘恢复
    try:
        backup_path = save_change_set(
            project_dir,
            str(getattr(session, "run_id", "") or "unknown"),
            pre_deploy_backup,
            deployed_after,
        )
    except OSError as e:
        log.warning("Behavior guardrail backup persist failed (non-fatal): %s", e)
        backup_path = None

    # 部署后验证测试 — 行为回归则回滚
    if guard_enabled and guard_baseline is not None and deployed:
        try:
            log.info("Behavior guardrail: running verification tests after deploy")
            guard_after = guard_runner.run(project_dir, force_rebuild=True)
            print(f"  🛡️ [小明] 行为护栏: 部署后测试 "
                  f"{guard_after.passed} passed / "
                  f"{guard_after.failed} failed "
                  f"(runner={guard_after.runner})")
            base_failed = guard_baseline.failed or 0
            after_failed = guard_after.failed or 0
            # 回归判定: 基线测试真实运行过 (runner != "none" 表示有测试框架)
            baseline_ran = guard_baseline.runner not in (None, "none")
            # 2026-08-13 (e2e 修复): 编译失败也算回归 — after runner 为
            # ctest-build-failed 时 failed 计数为 0, 旧判定 (after_failed >
            # base_failed) 漏掉「基线通过 → 部署后编译失败」场景。编译失败
            # 比测试失败更严重, 必须回滚。
            after_build_failed = guard_after.runner == "ctest-build-failed"
            if (baseline_ran and guard_baseline.status == "passed"
                    and (guard_after.status == "failed" or after_build_failed)):
                guard_rollback = True
                log.warning(
                    "Behavior guardrail REGRESSION: baseline passed → after "
                    "failed (runner=%s, status=%s) — rolling back src/",
                    guard_after.runner, guard_after.status,
                )
            elif baseline_ran and after_failed > base_failed:
                guard_rollback = True
                log.warning(
                    "Behavior guardrail REGRESSION: baseline failed=%d → "
                    "after failed=%d — rolling back src/",
                    base_failed, after_failed,
                )
            if guard_rollback:
                # 恢复部署前的原始 src 内容 (不是生成目录 — 生成目录就是回归版)
                apply_change_set(project_dir, pre_deploy_backup)
                print("  🔄 [小明] 行为护栏: 测试回归 → 已回滚 src/ 至基线")
        except Exception as e:
            log.warning("Behavior guardrail verification test failed: %s", e)
            guard_after = None

    not_verified_reason = None
    if not guard_enabled:
        not_verified_reason = "guard disabled (OSH_BEHAVIOR_GUARD=0)"
    elif guard_baseline is None:
        not_verified_reason = "baseline test failed or skipped"
    elif not deployed:
        not_verified_reason = "no files deployed"
    elif guard_after is None:
        not_verified_reason = "verification test failed"
    if not_verified_reason:
        log.warning("Behavior guardrail NOT verified: %s", not_verified_reason)

    report = {
        "status": "deployed" if deployed else "empty",
        "generated_dir": str(gen_dir),
        "deployed": deployed,
        "skipped_empty": skipped_empty,
        # 行为护栏结果 (2026-08-13)
        "behavior_guardrail": {
            "enabled": bool(guard_enabled),
            "baseline": guard_baseline and {
                "runner": guard_baseline.runner,
                "passed": guard_baseline.passed,
                "failed": guard_baseline.failed,
                "status": guard_baseline.status,
            },
            "after": guard_after and {
                "runner": guard_after.runner,
                "passed": guard_after.passed,
                "failed": guard_after.failed,
                "status": guard_after.status,
            },
            "rolled_back": guard_rollback,
            "verdict": ("regression_rolled_back" if guard_rollback
                        else "passed" if (guard_enabled and guard_after)
                        else "not_verified"),
            "not_verified_reason": not_verified_reason,
        },
        "guardrail_backup": str(backup_path) if backup_path else None,
    }
    if guard_rollback:
        report["status"] = "deployed_behavior_regression"
        # 0️⃣ 回滚后清空 deployed — 部署内容已回滚, 不视为本次部署
        report["deployed"] = []
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"  ✅ [小明] codegen-deploy: {len(deployed)} files → src/ "
          f"(skipped {len(skipped_empty)} empty)")
    for f in deployed:
        log.info("  deployed: %s", f)
    if skipped_empty:
        log.warning("codegen-deploy: skipped 0-byte files: %s", skipped_empty)
    return str(report_path)


@timed_step
def step_test_planning(session: PipelineSession) -> str:
    """Step 6: Claude — AI-powered test planning.

    Reads spec + architecture + development plan from artifacts,
    sends to LLM, and generates a comprehensive test plan with
    strategy, requirement traceability matrix, and coverage targets.
    """
    try:
        print("  📋 [Claude] Running AI-powered test planning...")
        log.info("Running AI-powered test planning")

        # --- Gather inputs ---
        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"
        parsed = _parse_spec(session.spec_path)
        requirements = parsed["requirements"]

        # Artifacts from prior steps
        architecture_content = artifacts_read(session.artifacts, "architecture")
        dev_plan_content = artifacts_read(session.artifacts, "development")

        # --- Build prompt ---
        system_prompt, user_prompt = build_test_planning_prompt(
            spec_content=spec_content,
            requirements=requirements,
            architecture_content=architecture_content,
            development_plan_content=dev_plan_content,
        )

        # --- Call LLM ---
        try:
            # max_tokens=6144 (2026-08-17): 测试计划随 spec 增长而变长,
            # 4096 会截断 (r18 test-plan 16K 被截断). 对齐 TASK_BUDGETS.
            result = _call_llm(session, system_prompt, user_prompt, max_tokens=6144)
        except Exception as e:
            log.error(f"LLM call failed during test planning: {e}")
            raise PipelineStepError(
                f"Test planning LLM call failed: {e}\n"
                f"Spec: {session.spec_path}"
            )

        plan = result["content"]
        usage = result.get("usage", {})
        log.info(
            "LLM returned %d tokens (prompt=%s, completion=%s)",
            usage.get("total_tokens", "?"),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
        )
        session.token_usage_total += usage.get("total_tokens", 0)
        session.token_usage_steps.append({"step": "test-planning", "usage": usage})

        total_shall = sum(len(r.get("shall_statements", [])) for r in requirements)
        full_output = (
            f"# Test Plan: {session.name}\n\n"
            f"> Generated by: LLM ({result.get('model', 'unknown')})\n"
            f"> Source spec: {session.spec_path}\n"
            f"> Requirements: {len(requirements)}  |  SHALLs: {total_shall}\n"
            f"> Tokens: {usage.get('total_tokens', '?')} "
            f"(prompt {usage.get('prompt_tokens', '?')} + "
            f"completion {usage.get('completion_tokens', '?')})\n\n"
            f"{plan}"
        )

        out_path = session.session_dir / "test-plan.md"
        try:
            out_path.write_text(full_output)
        except OSError as e:
            log.error(f"Cannot write test plan: {e}")
            raise PipelineStepError(f"Cannot write test plan: {e}")
        print(f"  ✅ [Claude] AI test plan generated at {out_path}")
        log.info(f"AI test plan saved to {out_path}")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Test planning step failed: {e}")
        raise PipelineStepError(f"Test planning step failed: {e}")


@timed_step
def step_claude_test(session: PipelineSession) -> str:
    """Step 7: Claude — Self-test with real test runner output.

    Runs pytest or go test to get actual test results, parse them,
    and write a meaningful test report.
    """
    try:
        print("  🧪 [Claude] Self-testing...")
        log.info("Running self-test step")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # Try pytest first
        test_output = ""
        test_summary = ""
        passed = 0
        failed = 0
        total = 0
        is_python = True
        test_runner_name = "pytest"

        # Check if go.mod exists for Go project
        has_go = (project_dir / "go.mod").exists()

        # Check for C/CMake project (ctest-based)
        has_cmake = any(
            (project_dir / d / "CTestTestfile.cmake").exists()
            for d in ["build", "cmake-build-coverage", "cmake-build-debug", "cmake-build-release"]
        ) or (project_dir / "CMakeLists.txt").exists()

        if has_cmake:
            is_python = False
            test_runner_name = "ctest"
            try:
                # Find a build dir with CTestTestfile.cmake; if only
                # CMakeLists.txt exists, configure a fresh coverage build.
                build_dirs = [
                    project_dir / d
                    for d in ["build", "cmake-build-coverage", "cmake-build-debug", "cmake-build-release"]
                    if (project_dir / d / "CTestTestfile.cmake").exists()
                ]
                if not build_dirs:
                    build_dir = project_dir / "cmake-build-coverage"
                    subprocess.run(
                        ["cmake", "-S", str(project_dir), "-B", str(build_dir),
                         "-DENABLE_COVERAGE=ON", "-DCMAKE_BUILD_TYPE=Debug"],
                        capture_output=True, text=True, timeout=120, cwd=project_dir,
                    )
                    build_dirs = [build_dir]
                for build_dir in build_dirs:
                    result = subprocess.run(
                        ["cmake", "--build", str(build_dir), "-j4"],
                        capture_output=True, text=True, timeout=300, cwd=project_dir,
                    )
                    result = subprocess.run(
                        ["ctest", "--output-on-failure", "-j4"],
                        capture_output=True, text=True, timeout=300, cwd=build_dir,
                    )
                    test_output = result.stdout + "\n" + result.stderr
                    m = re.search(r"(\d+)% tests passed,\s*(\d+) tests failed", result.stdout or "")
                    if m:
                        failed = int(m.group(2))
                        total_m = re.search(r"out of\s+(\d+)", result.stdout or "")
                        passed = (int(total_m.group(1)) - failed) if total_m else 0
                        total = passed + failed
                    test_summary = f"ctest: {result.returncode == 0 and 'PASS' or 'FAIL'} (exit {result.returncode})"
                    break
            except FileNotFoundError:
                log.warning("cmake/ctest not installed — tests cannot run")
                test_summary = "cmake/ctest not installed — tests skipped"
            except subprocess.TimeoutExpired:
                log.warning("ctest timed out")
                test_summary = "ctest timed out"
            except Exception as e:
                log.warning(f"ctest error: {e}")
                test_summary = f"ctest error: {e}"
        elif has_go:
            is_python = False
            test_runner_name = "go test"
            try:
                result = subprocess.run(
                    ["go", "test", "./...", "-count=1"],
                    capture_output=True, text=True, timeout=120, cwd=project_dir
                )
                test_output = result.stdout + "\n" + result.stderr
                for line in result.stdout.split("\n"):
                    if line.startswith("ok "):
                        passed += 1
                        total += 1
                    elif line.startswith("FAIL "):
                        failed += 1
                        total += 1
                test_summary = f"Go test: {total} packages, {passed} passed, {failed} failed"
            except FileNotFoundError:
                log.warning("Go not installed \u2014 tests cannot run")
                test_summary = "Go not installed \u2014 tests skipped"
            except subprocess.TimeoutExpired:
                log.warning("Go tests timed out")
                test_summary = "Go tests timed out"
            except Exception as e:
                log.warning(f"Go test error: {e}")
                test_summary = f"Go test error: {e}"
        else:
            if os.environ.get("PYTEST_CURRENT_TEST"):
                # 递归保护 (2026-08-10, P1): step_claude_test 若在 pytest 会话内被真调用
                # （例如某测试未 mock subprocess.run），再 spawn 全量 pytest 会无限递归
                # （实测 25+ 进程失控，CPU 打满）。pytest 运行时设置 PYTEST_CURRENT_TEST，
                # 检测到即跳过真实执行——只生成跳过说明报告，不产生子进程。
                log.warning(
                    "Skipping nested pytest: running inside a pytest session (PYTEST_CURRENT_TEST set)"
                )
                test_summary = "pytest skipped (nested execution guard)"
                test_output = ""
            else:
                try:
                    result = subprocess.run(
                        [sys.executable, "-m", "pytest", "tests/", "-q", "--ignore=tests/test_e2e.py"],
                        capture_output=True, text=True, timeout=120, cwd=project_dir
                    )
                    test_output = result.stdout + "\n" + result.stderr
                    for line in result.stdout.split("\n"):
                        line = line.strip()
                        if "passed" in line or "failed" in line:
                            test_summary = line
                            m = re.search(r"(\d+) passed", line)
                            if m:
                                passed = int(m.group(1))
                            m = re.search(r"(\d+) failed", line)
                            if m:
                                failed = int(m.group(1))
                            total = passed + failed
                    if not test_summary:
                        test_summary = f"pytest completed (exit code {result.returncode})"
                except FileNotFoundError:
                    log.warning("pytest not installed \u2014 tests cannot run")
                    test_summary = "pytest not installed \u2014 tests skipped"
                except subprocess.TimeoutExpired:
                    log.warning("Tests timed out")
                    test_summary = "Tests timed out"
                except Exception as e:
                    log.warning(f"Test error: {e}")
                    test_summary = f"Test error: {e}"

        # Read spec scenarios for mapping
        spec_scenarios = []
        spec_path = Path(session.spec_path)
        if spec_path.exists():
            try:
                content = spec_path.read_text()
                current_scenario = ""
                for line in content.split("\n"):
                    if line.strip().startswith("### ") and "GIVEN" in line.upper():
                        if current_scenario:
                            spec_scenarios.append(current_scenario)
                        current_scenario = line.strip().replace("### ", "")
                if current_scenario:
                    spec_scenarios.append(current_scenario)
            except Exception:
                pass

        status_icon = "\u2705" if failed == 0 else "\u274c"
        runner = test_runner_name

        out_path = session.session_dir / "self-test-report.md"
        content = f"""# Self-Test Report: {session.name}

## Test Runner
- **Runner**: {runner}
- **Total Tests**: {total}
- **Passed**: {passed}
- **Failed**: {failed}
- **Status**: {status_icon}

## Test Summary
```
{test_summary}
```

## Test Output
```
{test_output[:2000]}
```

## Spec Scenarios ({len(spec_scenarios)})
"""
        for s in spec_scenarios:
            content += f"- {s}\n"

        content += """
## Coverage Note
Run CI Layer 1 to generate detailed coverage metrics for compliance.
"""
        try:
            out_path.write_text(content)
        except OSError as e:
            log.error(f"Cannot write test report: {e}")
            raise PipelineStepError(f"Cannot write test report: {e}")
        print(f"  \u2705 [Claude] Self-test report at {out_path}")
        log.info(f"Self-test report saved to {out_path}")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Self-test step failed: {e}")
        raise PipelineStepError(f"Self-test step failed: {e}")


# ---------------------------------------------------------------------------
# Internal helper: read artifact content from session artifacts dict
# ---------------------------------------------------------------------------


def artifacts_read(artifacts: dict[str, str], key: str) -> str | None:
    """Read the content of a prior-step artifact if it exists.

    Returns the content string, or None if the artifact key is absent
    or the file does not exist or cannot be read.
    """
    if key in artifacts:
        p = Path(artifacts[key])
        if p.exists():
            try:
                return p.read_text()
            except Exception:
                pass
    return None
