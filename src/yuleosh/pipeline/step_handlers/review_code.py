#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step 4.5: 小克 — 代码实现审查。

在 Code Implementation 完成后、Self-Test 之前自动执行：
- 检查代码是否与架构设计一致
- 检查是否有明显的问题（未处理的错误、死代码等）
- 预判测试盲区
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm, _try_parse_hermes_json
from yuleosh.pipeline.prompts import (
    _inject_spec,
    _inject_limited,
    SPEC_INJECT_LIMIT,
    _trunc_ref,
)
from yuleosh.pipeline.review_guard import numbered_source, validate_review_findings
log = logging.getLogger("pipeline.step_handlers.review_code")

__all__ = ["step_review_code"]


@timed_step
def step_review_code(session: PipelineSession) -> str:
    """Step: 小克 — 代码实现审查。

    Reads the spec, architecture design, and actual source files,
    then runs an LLM-powered review for consistency, issues, and
    test blind spots.
    """
    try:
        print("  🔍 [小克] 代码实现审查开始...")
        # ── Mock mode: skip real review ──────────────────────────
        from yuleosh.pipeline.step_handlers.mock_skip import is_mock, write_mock_skip
        if is_mock(session):
            print("  ⏭️  [代码实现审查]跳过 — mock 模式")
            return write_mock_skip(
                session, "internal-code-review",
                "mock mode — no real code to review",
            )

        # ── 审查锚定 (2026-08-12): 本次 run 无代码部署 → honest skip ──
        from yuleosh.pipeline.deploy_state import maybe_skip_code_review
        _deploy_skip = maybe_skip_code_review(session, 'internal-code-review', reviewer="小克")
        if _deploy_skip:
            print(f"  ⏭️  [小克] 代码实现审查跳过 — 本次 run 无代码部署")
            return _deploy_skip

        log.info("Running code implementation review")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()
        spec_path = Path(session.spec_path)

        # --- Read spec ---
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"

        # --- Read artifacts ---
        artifact_contents = {}
        for key in ["architecture", "development"]:
            if key in session.artifacts:
                ap = Path(session.artifacts[key])
                if ap.exists():
                    artifact_contents[key] = ap.read_text()

        # --- Scan actual source files ---
        source_files_summary = []
        src_dir = project_dir / "src"
        if src_dir.exists():
            for root, dirs, files in os.walk(src_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                for f in sorted(files):
                    if f.endswith((".py", ".c", ".h", ".go", ".rs", ".js", ".ts")):
                        fpath = Path(root) / f
                        rel = fpath.relative_to(project_dir)
                        try:
                            # 2026-08-16 r20: 3000 字符/文件 + 5000 总截断导致评审
                            # LLM 看不到任何 .c 实现 (全被 header 挤掉) → 26 findings
                            # 全是基于残缺信息的幻觉。提高单文件上限, 注入阶段再按
                            # .c 优先 + 每文件预算分配 (见 _build_code_review_prompt)。
                            # 上限 20000: 覆盖 window_control.c (364 行 ≈ 14.6KB) 全文。
                            content = fpath.read_text() if fpath.stat().st_size < 60000 else ""
                            source_files_summary.append({
                                "path": str(rel),
                                "lines": len(content.splitlines()),
                                "content": content[:20000],
                            })
                        except Exception:
                            source_files_summary.append({
                                "path": str(rel),
                                "lines": 0,
                                "content": "(cannot read)",
                            })

        # --- Build and call LLM ---
        system_prompt, user_prompt = _build_code_review_prompt(
            spec_content=spec_content,
            spec_name=spec_path.name,
            architecture_content=artifact_contents.get("architecture", ""),
            dev_plan_content=artifact_contents.get("development", ""),
            source_files=source_files_summary,
        )

        try:
            result = _call_llm(session, system_prompt, user_prompt, max_tokens=6144)
        except Exception as e:
            log.error(f"LLM call failed during code review: {e}")
            raise PipelineStepError(
                f"Code implementation review LLM call failed: {e}\n"
                f"Spec: {session.spec_path}"
            )

        raw = result["content"].strip()
        usage = result.get("usage", {})
        log.info(
            "LLM returned %d tokens for code review (prompt=%s, completion=%s)",
            usage.get("total_tokens", "?"),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
        )
        session.token_usage_total += usage.get("total_tokens", 0)
        session.token_usage_steps.append({"step": "internal-code-review", "usage": usage})

        # Parse structured response with robust fallback
        review = _try_parse_hermes_json(raw, session.name)

        # 2026-08-20 r22 real-4 复盘: 幻觉自动验证 — file:line 存在性检查,
        # 幻觉 finding 降级 info + hallucinated 标记, 不阻塞 pipeline。
        validate_review_findings(review, source_files_summary)

        # Ensure required fields
        review.setdefault("session", session.name)
        review.setdefault("reviewer", "小克")
        review.setdefault("step", "internal-code-review")
        review.setdefault("timestamp", datetime.now().isoformat())
        review.setdefault("status", "passed")
        review.setdefault("findings", [])
        review.setdefault("finding_breakdown", {"critical": 0, "major": 0, "minor": 0, "info": 0})
        review.setdefault("summary", "")
        review.setdefault("test_blind_spots", [])

        out_path = session.session_dir / "internal-code-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(review, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Cannot write code review: {e}")
            raise PipelineStepError(f"Cannot write code review: {e}")

        findings_count = len(review.get("findings", []))
        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄"}
        print(f"  {status_icon.get(review['status'], '❓')} [小克] 代码实现审查完成 "
              f"({findings_count} findings, status={review['status']})")
        log.info(f"Code implementation review: {findings_count} findings, status={review['status']}")
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Code review step failed: {e}")
        raise PipelineStepError(f"Code review step failed: {e}")


# ---------------------------------------------------------------------------
# Internal: build code review prompt
# ---------------------------------------------------------------------------


def _build_code_review_prompt(
    spec_content: str,
    spec_name: str,
    architecture_content: str,
    dev_plan_content: str,
    source_files: list[dict],
) -> tuple[str, str]:
    """Build prompts for the LLM-powered code implementation review.

    Returns (system_prompt, user_prompt).
    """
    system_prompt = (
        "You are a senior developer conducting a code implementation review.\n"
        "Review the actual source code against the specification and architecture design.\n"
        "Focus on:\n"
        "1. **Architecture consistency**: Does the code follow the architecture design?\n"
        "2. **Error handling**: Are there unhandled exceptions, missing try/except, silent failures?\n"
        "3. **Dead code / unused**: Unused imports, variables, functions, unreachable code.\n"
        "4. **Defensive programming**: Missing input validation, edge cases.\n"
        "5. **Test blind spots**: Which parts are likely untested or hard to test?\n\n"
        "## ANTI-HALLUCINATION RULES (strict — violations degrade the finding to info)\n"
        "- Source code below is injected with REAL line numbers (`N| code`). Every finding's "
        "`file`/`line` MUST reference a line number that actually appears in the injected snippet. "
        "NEVER invent a line number. Use `null` (not 0) for file-wide findings.\n"
        "- The injected snippet may be TRUNCATED (an `…[omitted …]` marker is present). "
        "Absence of a line in the snippet does NOT mean the file lacks it. If a claim depends on "
        "code you cannot see, either open the file yourself or mark the finding `severity: info` "
        "with `verification_needed: true`.\n"
        "- NEVER report syntax errors, missing functions, or missing suppressions unless the "
        "relevant lines are actually visible in the injected snippet. Guessing about unseen code "
        "is hallucination.\n"
        "- NEVER invent metrics (e.g. '0% coverage') unless a number was explicitly provided in "
        "the artifacts.\n"
        "- For every finding, include a short `snippet` field quoting the exact offending line(s) "
        "as they appear in the injected source (line number + text). If you cannot quote the line, "
        "the finding is not grounded — downgrade it.\n"
        "Output a structured JSON with:\n"
        "- `status`: \"passed\", \"failed\", or \"retry\"\n"
        "- `findings`: array of {\"severity\": \"critical\"/\"major\"/\"minor\"/\"info\", "
        "\"category\": \"consistency\"/\"error-handling\"/\"dead-code\"/\"defensive\"/\"test-blindspot\", "
        "\"file\": \"...\", \"line\": N, \"snippet\": \"...\", \"message\": \"...\"}\n"
        "- `finding_breakdown`: {critical: N, major: N, minor: N, info: N}\n"
        "- `test_blind_spots`: [\"description of untested area\", ...]\n"
        "- `summary`: \"Short summary paragraph\"\n"
        "Wrap the JSON in ```json ... ```.\n"
        "If the response cannot be parsed as JSON, it will be treated as unstructured markdown."
    )

    # Format source file summaries
    src_lines = []
    for sf in source_files[:30]:
        src_lines.append(f"- {sf['path']}  ({sf['lines']} lines)")
    src_str = "\n".join(src_lines)

    # Include content of key files for deep analysis.
    # 2026-08-16 r20: 原实现 source_files[:10] + snippets_str[:5000] 总截断 —
    # header 按字母序排在 .c 前面, 评审 LLM 只看到 main.c + 3 个 .h 的开头,
    # 所有实现文件 (window_control.c 等) 零注入 → 26 findings 全是"疑似缺失"
    # 的脑补 (它根本没看到实现)。修复: .c 实现优先 + 每文件预算 + 总预算提高,
    # 保证关键实现文件至少各有一段完整内容可评。
    # 每文件预算: .c 实现给足 (覆盖 window_control.c command/process 全文),
    # .h 声明只给轮廓。核心 .c 上限 16000 ≈ 400 行源文件全文。
    TOTAL_BUDGET = 40000
    key_snippets = []
    used = 0
    # .c 实现优先 (0), .h 次之 (1), 同类型按路径稳定排序
    ordered = sorted(
        source_files[:30],
        key=lambda sf: (0 if str(sf["path"]).endswith(".c") else 1, str(sf["path"])),
    )
    for sf in ordered:
        if used >= TOTAL_BUDGET:
            break
        if not sf["content"] or sf["content"] == "(cannot read)":
            continue
        # .c 实现给足预算 (覆盖中后部契约实现与 command/process), .h 只给轮廓
        per_file = 16000 if str(sf["path"]).endswith(".c") else 2000
        # 2026-08-20 r22 实测修复: 头截断 content[:per_file] 让评审 LLM 看不到
        # 文件中后部 (window_modes.c 的 (void) 抑制行 / window_control.c 的
        # mode-dispatch switch) → "excerpt truncated before X" fail-closed
        # critical 假阳性。改引用式截断 (头 60% + 省略标记 + 尾 40%):
        # 关键契约散落在文件中部/尾部时仍可见。
        # 2026-08-20 r22 real-4: 注入带真实行号前缀 (numbered_source), 评审
        # LLM 引用的行号必须来自真实编号, 配合 validate_review_findings
        # file:line 存在性检查, 拦截行号幻觉 (hal_hall.c:54 文件仅 53 行)。
        content = _trunc_ref(numbered_source(sf["content"]), per_file, sf["path"])
        piece = f"### {sf['path']}\n```\n{content}\n```"
        if used + len(piece) > TOTAL_BUDGET:
            piece = piece[: TOTAL_BUDGET - used]
        key_snippets.append(piece)
        used += len(piece)
    snippets_str = "\n\n".join(key_snippets)

    user_prompt = (
        f"## Spec: {spec_name}\n\n"
        f"### Specification\n"
        f"```\n{_inject_spec(spec_content)}\n```\n\n"
        f"### Architecture Design\n"
        f"```\n{_inject_limited(architecture_content, SPEC_INJECT_LIMIT, 'architecture')}\n```\n\n"
        f"### Development Plan\n"
        f"```\n{_inject_limited(dev_plan_content, SPEC_INJECT_LIMIT, 'development-plan')}\n```\n\n"
        f"### Source Files ({len(source_files)} total)\n"
        f"{src_str}\n\n"
        f"### Key File Contents\n"
        f"{snippets_str}\n\n"
        f"Review the implementation. Identify:\n"
        f"- Code that deviates from architecture\n"
        f"- Unhandled errors, missing validation\n"
        f"- Dead code or unused artifacts\n"
        f"- Test blind spots\n"
        f"Output your review as structured JSON."
    )

    return system_prompt, user_prompt
