#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
External agent step handlers — Codex (test verification) and Claude (review).

这些步骤把真实的外部 CLI agent（``codex`` / ``claude``）接入 yuleOSH
pipeline，形成「生成 → 验证 → 修复」与「方案 → 评审 → 一致」的自动闭环：

- ``step_codex_verify``（step key ``codex-verify``，agent 角色 ``verifier``）:
  对当前产出运行测试验证。Codex 在项目工作区执行测试并给出结构化缺陷
  清单；存在缺陷时步骤抛 ``PipelineStepError`` 阻断（orchestrator 记录
  fail 并停止后续步骤），主 agent（Hermes/用户）读取缺陷报告修复后
  重跑 pipeline 从失败步骤继续 —— 即验证失败 → 修复 → 再验证的闭环。
- ``step_claude_review``（step key ``claude-review``，agent 角色
  ``architect``）: 对当前方案/建议进行评审和头脑风暴。Claude 以独立
  视角给出评审结论（verdict + 问题 + 建议）；未达成一致时抛
  ``PipelineStepError`` 阻断，方案修订后再评审。

设计约定（对齐 yuleOSH 工程诚实原则）:
- CLI 缺失 / mock 模式 → 写 SKIPPED 报告并跳过（绝不假装验证通过）。
- 只有真实运行且无缺陷/已一致才算 PASS；任何缺陷/分歧都显式失败。
- 外部 CLI 通过 subprocess 调用，超时后失败（不挂死 pipeline）。
"""

import json
import logging
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step
from yuleosh.pipeline.step_handlers.mock_skip import is_mock, write_mock_skip
from yuleosh.pipeline.prompts import _inject_spec, SPEC_INJECT_LIMIT

# Combined cap for all pipeline artifacts rendered into codex/claude prompts.
# 2026-08-16: PRD alone is 26K+; per-artifact cap is SPEC_INJECT_LIMIT and the
# concatenated set (prd+arch+dev+test-plan ≈ 60K) must stay visible to external
# reviewers — the tail contract sections are exactly what claude-review flags.
ARTIFACT_INJECT_LIMIT = 60000

log = logging.getLogger("pipeline.step_handlers.external_agents")

__all__ = ["step_claude_review", "step_codex_verify"]

# 外部 CLI 单次调用超时（秒）——codex 跑测试可能较慢。
# 2026-08-17: 600s → 900s. 完整 prompt (spec 22K + contracts 6K + PRD 26K +
# arch 15K + test-plan 16K ≈ 100K chars) 让 codex exec 读代码验证耗时
# >600s (r19 实证: 死于 step 14 codex-verify, 启动 11 分钟后无输出 = 600s
# 超时被杀). 900s 与 CLAUDE_TIMEOUT 对齐, 覆盖大 prompt 验证, 仍防挂死。
CODEX_TIMEOUT = int(os.environ.get("YULEOSH_CODEX_TIMEOUT", "900"))
# claude-review 默认 300s 不够 (2026-08-16 实证: run c88797033141 超时,
# claude 读代码评审 14KB+ prompt 需 3-5 分钟) → 提到 600s。
# 2026-08-17: 600s → 900s. 完整 prompt (spec 22K + contracts 6K + PRD 26K +
# arch 15K + test-plan 16K ≈ 100K chars) 让 claude 评审耗时 ~6m20s (实测
# run-20260816-181130), 600s 超时误杀 (r18 claude exited 1). 900s 覆盖大
# prompt 评审, 仍防挂死。
CLAUDE_TIMEOUT = int(os.environ.get("YULEOSH_CLAUDE_TIMEOUT", "900"))
# claude-review: --max-turns 硬编码 3 对 8K+ 评审 prompt 不够 (claude CLI
# 2.1.220 报 "Reached max turns (3)" exit 1, 2026-08-16 实证)。实测 10 轮
# 仍不够 (25s 耗尽, claude 读代码验证烧轮次), 20 轮成功 (2m14s)。
# 可用 YULEOSH_CLAUDE_MAX_TURNS 覆盖。
CLAUDE_MAX_TURNS = int(os.environ.get("YULEOSH_CLAUDE_MAX_TURNS", "20"))


# ── 公共辅助 ──────────────────────────────────────────────────────────

def _find_cli(binary: str) -> str | None:
    """Locate an external CLI binary, or None."""
    path = shutil.which(binary)
    return path


def _load_env_key(key: str) -> str:
    """Load an API key from ``~/.hermes/.env`` when not already exported.

    外部 CLI（如 codex 的 deepseek proxy）需要 DEEPSEEK_API_KEY；在
    Hermes 托管环境下该 key 常驻 ``~/.hermes/.env`` 而非 shell env。
    """
    if os.environ.get(key):
        return os.environ[key]
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _write_report(session: PipelineSession, step_key: str, report: dict) -> str:
    """Write a structured step report JSON into the session dir."""
    out_path = Path(session.session_dir) / f"{step_key}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return str(out_path)


def _collect_spec_and_artifacts(session: PipelineSession) -> tuple[str, dict[str, str]]:
    """Collect spec content + existing artifact summaries for context."""
    spec_path = Path(session.spec_path)
    spec_content = spec_path.read_text(encoding="utf-8", errors="ignore") \
        if spec_path.exists() else "(spec file not found)"

    artifacts: dict[str, str] = {}
    for key in ("prd", "architecture", "development", "self-test", "test-planning"):
        p = session.artifacts.get(key)
        if not p:
            continue
        ap = Path(p)
        if ap.exists():
            try:
                # 2026-08-16: was [:8000] — truncated PRD at 8K chars, cutting
                # every contract section past FR-041 (SW-005..008, §8 interface
                # contract, guardrail map) → claude-review "FR 段止于 SW-004"
                # blocker (run-20260816-174313). PRD itself is 26K+; keep enough.
                artifacts[key] = ap.read_text(encoding="utf-8", errors="ignore")[:SPEC_INJECT_LIMIT]
            except OSError:
                artifacts[key] = "(read error)"
    return spec_content, artifacts


def _format_artifacts_for_prompt(artifacts: dict[str, str]) -> str:
    """Render artifact contents into a compact prompt section."""
    if not artifacts:
        return "(no artifacts available)"
    blocks = []
    for key, content in artifacts.items():
        blocks.append(f"### {key}\n```\n{content}\n```")
    joined = "\n\n".join(blocks)
    # Combined cap: all artifacts concatenated can exceed the per-file limit;
    # keep the full set (PRD 26K + arch 17K + test-plan 16K ≈ 60K) so reviewers
    # see the tail contracts instead of only the first artifact.
    return joined[:ARTIFACT_INJECT_LIMIT]


def _build_codex_prompt(spec_content: str, artifacts_block: str,
                        project_dir: str) -> str:
    """Build the Codex verification prompt (Chinese, structured JSON output)."""
    return f"""你在 yuleOSH 流水线中担任测试验证 agent（角色 verifier）。
对当前项目产出做真实测试验证，发现缺陷后以严格 JSON 输出。

项目目录: {project_dir}
规格 (docs/spec.md 摘要):
{_inject_spec(spec_content)}

当前产物:
{artifacts_block[:ARTIFACT_INJECT_LIMIT]}

验证要求（工程诚实，禁止假绿）:
1. 运行项目的测试（pytest / go test / ctest / 其他），确认真实测试结果。
2. 检查产物与 spec 的一致性：需求是否被实现、测试是否覆盖关键路径。
3. 如实报告：不通过就是失败，不要为通过而编造证据。

输出 ONLY 一个 JSON 对象（不要 markdown 代码块，不要多余文字）:
{{
  "passed": true|false,
  "summary": "一句话结论",
  "defects": [
    {{"severity": "critical|major|minor", "file": "路径", "line": 0,
      "message": "缺陷描述", "evidence": "复现/日志证据"}}
  ],
  "test_results": {{"runner": "pytest|go test|ctest|...", "passed": 0, "failed": 0}}
}}
若一切正常 defects 为空数组。
"""


def _build_claude_review_prompt(spec_content: str, artifacts_block: str,
                                project_dir: str) -> str:
    """Build the Claude review prompt (Chinese, structured JSON output)."""
    return f"""你在 yuleOSH 流水线中担任方案评审 agent（角色 architect）。
对当前建议/方案进行评审与头脑风暴，给出独立结论。不要取悦任何人，
以证据和工程判断为准。

项目目录: {project_dir}
规格 (docs/spec.md 摘要):
{_inject_spec(spec_content)}

待评审方案/建议:
{artifacts_block[:ARTIFACT_INJECT_LIMIT]}

评审要求:
1. 对照 spec 检查方案是否满足需求、有无遗漏或过度设计。
2. 检查架构合理性、可扩展性、与现有代码的兼容性。
3. 明确指出必须修改的问题（blockers）与可优化建议（suggestions）。

输出 ONLY 一个 JSON 对象（不要 markdown 代码块，不要多余文字）:
{{
  "verdict": "agree|disagree",
  "summary": "一句话结论",
  "blockers": [
    {{"severity": "critical|major|minor", "item": "问题描述", "rationale": "依据"}}
  ],
  "suggestions": ["优化建议1", "优化建议2"],
  "brainstorm": "头脑风暴要点（可选方向/风险/权衡）"
}}
verdict=agree 表示方向一致可推进；disagree 表示需要修订后再评审。
"""


def _run_cli(cmd: list[str], timeout: int, cwd: str | None,
             extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run an external CLI command with timeout + merged env. Never hangs."""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env,
        check=False,
    )


def _parse_json_output(stdout: str) -> dict | None:
    """Extract the first JSON object from CLI stdout (tolerates noise)."""
    # Try direct parse first
    try:
        parsed = json.loads(stdout.strip())
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    # Fallback: find first { ... } balanced block
    start = stdout.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(stdout)):
        if stdout[i] == "{":
            depth += 1
        elif stdout[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(stdout[start:i + 1])
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    return None
    return None


# ── Codex 验证步骤 ────────────────────────────────────────────────────

@timed_step
def step_codex_verify(session: PipelineSession) -> str:
    """Step: Codex — 对产出进行真实测试验证，发现缺陷即阻断（闭环起点）。

    Returns:
        Path to the ``codex-verify.json`` report.

    Raises:
        PipelineStepError: 验证发现缺陷或外部 CLI 运行失败。
    """
    step_key = "codex-verify"
    print("  🔎 [Codex] Running external test verification...")

    if is_mock(session):
        print("  ⏭️  [Codex] 测试验证跳过 — mock 模式")
        return write_mock_skip(session, step_key, "mock mode — no real code to verify")

    codex_bin = _find_cli("codex")
    if not codex_bin:
        print("  ⏭️  [Codex] CLI 未安装 — 跳过（不假装通过）")
        return write_mock_skip(session, step_key, "codex CLI not installed")

    project_dir = str(Path(os.environ.get("OSH_HOME", ".")).resolve())
    spec_content, artifacts = _collect_spec_and_artifacts(session)
    prompt = _build_codex_prompt(spec_content, _format_artifacts_for_prompt(artifacts),
                                 project_dir)

    api_key = _load_env_key("DEEPSEEK_API_KEY")
    extra_env = {"DEEPSEEK_API_KEY": api_key} if api_key else None

    log.info("Running codex exec (timeout=%ss)", CODEX_TIMEOUT)
    try:
        result = _run_cli(
            [codex_bin, "exec", "--full-auto", prompt],
            timeout=CODEX_TIMEOUT, cwd=project_dir, extra_env=extra_env,
        )
    except subprocess.TimeoutExpired:
        raise PipelineStepError(
            f"[{step_key}] Codex verification timed out after {CODEX_TIMEOUT}s"
        )
    except OSError as e:
        raise PipelineStepError(f"[{step_key}] Failed to launch codex: {e}") from e

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if result.returncode != 0:
        log.error("codex exited %d: %s", result.returncode, stderr[-2000:])
        raise PipelineStepError(
            f"[{step_key}] codex CLI exited {result.returncode}: {stderr[-2000:]}"
        )

    parsed = _parse_json_output(stdout)
    if parsed is None:
        # 无法解析结构化输出 → 诚实失败，绝不把乱输出当通过
        raise PipelineStepError(
            f"[{step_key}] codex output was not valid JSON. stdout head: "
            f"{stdout[:500]!r}"
        )

    passed = bool(parsed.get("passed", False))
    defects = parsed.get("defects") or []
    summary = str(parsed.get("summary", ""))
    test_results = parsed.get("test_results") or {}

    report = {
        "step": step_key,
        "session": getattr(session, "name", ""),
        "timestamp": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "summary": summary,
        "defect_count": len(defects),
        "defects": defects,
        "test_results": test_results,
        "exit_code": result.returncode,
    }
    report_path = _write_report(session, step_key, report)
    log.info("codex-verify report written: %s (passed=%s, defects=%d)",
             report_path, passed, len(defects))

    if not passed:
        # 缺陷阻断：orchestrator 记录 fail，主 agent 读报告修复后重跑
        raise PipelineStepError(
            f"[{step_key}] Codex verification FAILED: {summary} "
            f"({len(defects)} defect(s)) — 详见 {report_path}"
        )

    print(f"  ✅ [Codex] 测试验证通过 — {summary}")
    return report_path


# ── Claude 评审步骤 ───────────────────────────────────────────────────

@timed_step
def step_claude_review(session: PipelineSession) -> str:
    """Step: Claude — 对方案/建议进行评审与头脑风暴，未一致即阻断。

    Returns:
        Path to the ``claude-review.json`` report.

    Raises:
        PipelineStepError: 评审未达成一致（disagree）或外部 CLI 运行失败。
    """
    step_key = "claude-review"
    print("  💡 [Claude] Running external review & brainstorm...")

    if is_mock(session):
        print("  ⏭️  [Claude] 方案评审跳过 — mock 模式")
        return write_mock_skip(session, step_key, "mock mode — no real proposal to review")

    claude_bin = _find_cli("claude")
    if not claude_bin:
        print("  ⏭️  [Claude] CLI 未安装 — 跳过（不假装通过）")
        return write_mock_skip(session, step_key, "claude CLI not installed")

    project_dir = str(Path(os.environ.get("OSH_HOME", ".")).resolve())
    spec_content, artifacts = _collect_spec_and_artifacts(session)
    prompt = _build_claude_review_prompt(spec_content,
                                         _format_artifacts_for_prompt(artifacts),
                                         project_dir)

    # Claude CLI 通过 ANTHROPIC_API_KEY 或本地网关鉴权；显式注入 .env key
    extra_env = {}
    anthropic_key = _load_env_key("ANTHROPIC_API_KEY")
    if anthropic_key:
        extra_env["ANTHROPIC_API_KEY"] = anthropic_key

    log.info("Running claude -p (timeout=%ss)", CLAUDE_TIMEOUT)
    try:
        # --dangerously-skip-permissions (2026-08-16 r20 根因): claude 在项目
        # 目录会执行 Bash 工具读 src/ 验证评审, 非交互模式 (-p) 下权限提示
        # 无人确认 → 挂起 120s 后 exit 1 空 stderr。与 codex-verify 的
        # --full-auto 对等 (评审 agent 只读项目, 风险可控)。手动复现证实:
        # 无该 flag → disagree/失败; 有 → agree 且稳定。
        result = _run_cli(
            [claude_bin, "-p", prompt, "--max-turns", str(CLAUDE_MAX_TURNS),
             "--dangerously-skip-permissions"],
            timeout=CLAUDE_TIMEOUT, cwd=project_dir, extra_env=extra_env,
        )
    except subprocess.TimeoutExpired:
        raise PipelineStepError(
            f"[{step_key}] Claude review timed out after {CLAUDE_TIMEOUT}s"
        )
    except OSError as e:
        raise PipelineStepError(f"[{step_key}] Failed to launch claude: {e}") from e

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if result.returncode != 0:
        log.error("claude exited %d: %s", result.returncode, stderr[-2000:])
        raise PipelineStepError(
            f"[{step_key}] claude CLI exited {result.returncode}: {stderr[-2000:]}"
        )

    parsed = _parse_json_output(stdout)
    if parsed is None:
        raise PipelineStepError(
            f"[{step_key}] claude output was not valid JSON. stdout head: "
            f"{stdout[:500]!r}"
        )

    verdict = str(parsed.get("verdict", "disagree"))
    blockers = parsed.get("blockers") or []
    suggestions = parsed.get("suggestions") or []
    brainstorm = str(parsed.get("brainstorm", ""))
    summary = str(parsed.get("summary", ""))
    agreed = verdict == "agree"

    report = {
        "step": step_key,
        "session": getattr(session, "name", ""),
        "timestamp": datetime.now(UTC).isoformat(),
        "status": "passed" if agreed else "failed",
        "verdict": verdict,
        "summary": summary,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "suggestions": suggestions,
        "brainstorm": brainstorm,
        "exit_code": result.returncode,
    }
    report_path = _write_report(session, step_key, report)
    log.info("claude-review report written: %s (verdict=%s, blockers=%d)",
             report_path, verdict, len(blockers))

    if not agreed:
        # 未一致：阻断，方案修订后再评审
        raise PipelineStepError(
            f"[{step_key}] Claude review NOT agreed: {summary} "
            f"({len(blockers)} blocker(s)) — 详见 {report_path}"
        )

    print(f"  ✅ [Claude] 方案评审一致 — {summary}")
    return report_path
