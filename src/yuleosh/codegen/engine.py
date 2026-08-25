#!/usr/bin/env python3

# @req RS-001  @req SWR-001.1  @req RS-011
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Code generation engine — the D3 coding loop (spec → code → verify → fix).

Flow for one generation run:

1. Build the codegen prompt (spec + architecture + PRD + skills).
2. Call the LLM; parse the response into files (``### FILE: path`` markers
   or JSON payload).
3. Write files under ``artifacts/generated-code/<session>/``.
4. Compile-verify locally (``py_compile`` / ``gcc -fsyntax-only``).
5. On failure, retry up to ``max_retries`` times, each time feeding the
   compiler errors back into the LLM prompt.
6. Write a markdown report (file list / verification / retry rounds) and
   return it.

The engine is deliberately dependency-light: everything is driven by plain
dicts, so tests can inject fake LLM callables and fake verifiers.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from yuleosh.codegen import compilers
from yuleosh.pipeline.session import PipelineSession, PipelineStepError

log = logging.getLogger("yuleosh.codegen.engine")

# Output base relative to the project root.
DEFAULT_OUTPUT_REL = "artifacts/generated-code"

# LLM response marker: "### FILE: path/to/file.py" followed by a fenced block.
_FILE_RE = re.compile(
    r"^###\s*FILE:\s*(?P<path>[^\s]+)\s*$", re.IGNORECASE | re.MULTILINE
)
_FENCE_RE = re.compile(r"^```(?P<lang>[A-Za-z0-9_+-]*)\s*$", re.MULTILINE)


@dataclass
class GeneratedFile:
    """One code file parsed from the LLM response."""

    path: str
    content: str
    language: str = ""


@dataclass
class RoundFailure:
    """One failed codegen round — feeds the brainstorm analysis (2026-08-16)."""

    round_idx: int
    error_signature: str      # 归一化错误签名 (去行号/数字)
    err_count: int            # 该轮错误数 (error: + FAIL:)
    is_behavior: bool         # 是否行为失败 (ctest FAIL) — 区别于纯编译错误
    files: list[str]          # 本轮 LLM 输出的文件


@dataclass
class CodegenResult:
    """Outcome of a codegen run (also serialized into the report)."""

    status: str = "pending"  # generated | verified | failed | no-files
    output_dir: str = ""
    files: list[str] = field(default_factory=list)
    rounds: int = 0
    max_retries: int = 0
    last_errors: str = ""
    verify: dict = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: str = ""
    report_path: str = ""
    # 2026-08-16 (框住 LLM): repair 轮白名单过滤丢弃的文件
    dropped_files: list[str] = field(default_factory=list)
    # 2026-08-16 (3 次失败头脑风暴): 触发时的失败模式分析
    brainstorm: dict = field(default_factory=dict)
    # 2026-08-17 (claude-review run-175442 blocker 1): 编译后行为验证
    # (behavior_verify: 部署生成代码 → 跑真实测试套件 → 回滚) 的结果。
    # 报告必须记录它 — 否则 dev 报告只写 -fsyntax-only, 评审误判
    # "护栏测试从未执行", 且真回归 (FAULT/STOP 门控、阈值公式) 被掩盖。
    behavior_verify_result: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "output_dir": self.output_dir,
            "files": list(self.files),
            "rounds": self.rounds,
            "max_retries": self.max_retries,
            "last_errors": self.last_errors,
            "verify": self.verify,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "report_path": self.report_path,
            "dropped_files": list(self.dropped_files),
            "brainstorm": self.brainstorm,
            "behavior_verify_result": self.behavior_verify_result,
        }


def default_output_dir(project_dir: str | Path, session_name: str) -> Path:
    """``<project_dir>/artifacts/generated-code/<session_name>``.

    Overridable via the ``OSH_CODEGEN_DIR`` env var (absolute or relative
    to the project dir).
    """
    project_dir = Path(project_dir)
    env_dir = os.environ.get("OSH_CODEGEN_DIR")
    if env_dir:
        base = Path(env_dir)
        if not base.is_absolute():
            base = project_dir / base
    else:
        base = project_dir / DEFAULT_OUTPUT_REL
    return (base / session_name).resolve()


def parse_generated_files(llm_output: str) -> list[GeneratedFile]:
    """Parse an LLM codegen response into :class:`GeneratedFile` objects.

    Supports two formats:

    1. JSON payload::

           {"files": [{"path": "src/foo.py", "content": "..."}]}

    2. Markdown markers::

           ### FILE: src/foo.py
           ```python
           ... code ...
           ```

    Returns an empty list when nothing parseable is found.
    """
    text = (llm_output or "").strip()
    if not text:
        return []

    # --- Format 1: JSON payload ---
    try:
        data = json.loads(text)
        entries = data.get("files") if isinstance(data, dict) else data
        if isinstance(entries, list) and entries:
            files: list[GeneratedFile] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                path = entry.get("path") or entry.get("file")
                content = entry.get("content")
                if path and content is not None:
                    files.append(
                        GeneratedFile(path=str(path), content=str(content),
                                      language=entry.get("language", ""))
                    )
            if files:
                return files
    except (json.JSONDecodeError, AttributeError, ValueError):
        pass  # fall through to marker format

    # --- Format 2: ### FILE: markers ---
    files = []
    matches = list(_FILE_RE.finditer(text))
    for i, m in enumerate(matches):
        path = m.group("path").strip().strip("`").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        lang = ""
        content = body
        fences = list(_FENCE_RE.finditer(body))
        if len(fences) >= 2:
            lang = fences[0].group("lang")
            content = body[fences[0].end(): fences[-1].start()]
        elif fences:
            # Truncated response: only an opening fence (or unpaired fences).
            # Strip a leading fence so the file content itself is clean.
            lang = fences[0].group("lang")
            content = body[fences[0].end():]
            # If there is a trailing fence without a matching opener, drop it.
            if content.rstrip().endswith("```"):
                idx = content.rstrip().rfind("```")
                content = content[:idx]
        files.append(GeneratedFile(path=path, content=content.strip("\n"),
                                   language=lang))
    return files


def _safe_relative_path(raw: str) -> str:
    """Sanitize a generated relative path (strip ``../`` and leading slashes)."""
    p = raw.replace("\\", "/").lstrip("/")
    parts = [part for part in p.split("/") if part not in ("", ".", "..")]
    return "/".join(parts) if parts else "generated.txt"


class CodegenEngine:
    """Runs the generate → verify → fix loop.

    Args:
        output_dir: Where generated files land.  Defaults to
            ``<project>/artifacts/generated-code/<session>``.
        max_retries: Max repair rounds after a failed compile (default 3).
        llm_client: Optional callable ``(system, user, **kw) -> dict``.
            Defaults to ``None`` → resolved via the session at run time.
        verifier: Optional ``callable(files) -> dict`` override (tests).
        max_tokens: LLM max_tokens kwarg.
    """

    def __init__(
        self,
        output_dir: Optional[str | Path] = None,
        max_retries: int = 3,
        llm_client: Optional[Callable] = None,
        verifier: Optional[Callable] = None,
        max_tokens: int = 4096,
        seed_dir: Optional[str | Path] = None,
        seed_contract: Optional[dict[str, set[str]]] = None,
        behavior_verify: Optional[Callable] = None,
        brainstorm_after_failures: int = 3,
        structural_features: Optional[dict[str, list[str]]] = None,
        forbidden_features: Optional[dict[str, list[str]]] = None,
    ):
        self.output_dir = Path(output_dir) if output_dir else None
        self.max_retries = max(0, int(max_retries))
        self.llm_client = llm_client
        self.verifier = verifier or compilers.compile_verify
        self.max_tokens = max_tokens
        # 方案 C seed 增量 (2026-08-12): 项目现有代码基线目录。
        # 提供时 engine 把 src/** 复制到输出目录, LLM 只增量修改。
        self.seed_dir = Path(seed_dir) if seed_dir else None
        # seed 契约 (2026-08-16, C): rel_path -> 现有公共函数名集合。
        # 生成代码删除既有公共函数 → 判定回归, 进入 repair 轮。
        self.seed_contract = seed_contract
        # 行为验证钩子 (2026-08-16, A): callable(out_dir) -> 错误文本 or ""。
        # 编译通过后额外跑真实行为测试, 失败反馈给 LLM 修复 — 防止
        # "编译通过但删了 PINCH_REVERSAL 启动序列" 类逻辑回归流到 deploy。
        self.behavior_verify = behavior_verify
        # 3 次失败 → 头脑风暴 (2026-08-16, 老板指令): 连续失败达到阈值时
        # 引擎做失败模式分析 + 强制恢复 seed 基线, 下一轮用脑暴指令。
        self.brainstorm_after_failures = max(1, int(brainstorm_after_failures))
        # 结构性 smoke 特征 (2026-08-17, window-anti-pinch r21): 项目配置的
        # {rel_path_glob: [必须保留的特征子串]} — 编译通过后、行为验证前
        # 检查。LLM 全量重写时"编译能过但删了核心功能路径" (防夹检测/
        # 反转序列) 是静默回归, 行为验证可能因环境 (ARM 链接) 根本没跑到;
        # 特征级检查在链接之前拦截, 给 LLM 明确修复指令。
        self.structural_features = structural_features or {}
        # 禁止特征 (2026-08-17, r21b): {rel_path_glob: [禁止出现的子串]} —
        # 链接级/语义级反模式。行为验证能报链接错误 (如 ARM __aeabi_ldivmod
        # 因 int64 除法), 但 4 轮 repair 里 LLM 不理解为啥要改 (报错信息是
        # 链接器输出, 不指代码行)。禁止特征在链接前直接说"这里不能出现
        # (int64_t)", 修复指令明确可执行。
        self.forbidden_features = forbidden_features or {}
        # seed 基线内存快照 (rel_path -> content), _sync_seed 后立即抓取,
        # 供头脑风暴强制恢复 — 不依赖 seed_dir 磁盘 (测试里 seed_dir 可能
        # 指向 out_dir, 磁盘已被 LLM 污染)。
        self._seed_baseline: dict[str, str] = {}

    # ---- Main entry ---------------------------------------------------

    def generate(
        self,
        session: PipelineSession,
        system_prompt: str,
        user_prompt: str,
        language_hint: Optional[str] = None,
        build_cmd: Optional[list[str]] = None,
        cflags: Optional[list[str]] = None,
    ) -> CodegenResult:
        """Run the full generate → verify → fix loop.

        Returns a :class:`CodegenResult` (never raises on compile failure —
        the failure is recorded in the result/report).  LLM transport errors
        still raise :class:`PipelineStepError`.

        方案 C seed 增量 (2026-08-12):
        - 提供 seed_dir 时先把项目 src 基线复制到输出目录, LLM 只输出
          新增/修改文件, 未修改文件保留 seed 副本 → 不再从零全量重写。
        - verify 验证**整个输出目录** (seed + 本轮修改), 而非只验证本轮
          LLM 输出的文件 — 跨文件引用 (app→hal) 才能被捕获。
        - best-state 回滚: 每轮 verify 失败时比较错误数, 只更新到更优的
          版本; 越修越坏的轮次回滚到历史最佳 → 杜绝"全量重发越改越坏"。
        """
        result = CodegenResult(max_retries=self.max_retries)
        out_dir = self.output_dir or default_output_dir(
            session.project_dir, session.name
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        result.output_dir = str(out_dir)

        # seed 基线复制 (方案 C)
        if self.seed_dir is not None:
            copied = self._sync_seed(self.seed_dir, out_dir)
            log.info("Codegen seed sync: %d baseline files copied", len(copied))
            # 2026-08-16: 复制后立即内存快照 — 头脑风暴强制恢复用
            self._seed_baseline = self._snapshot_files(out_dir)

        repair_context = ""
        best_state: dict[str, str] = {}   # rel_path -> content (错误数最少版本)
        best_error_count: Optional[int] = None
        # 2026-08-16 (框住 LLM): repair 轮白名单 = 上一轮错误涉及文件 +
        # seed_contract 文件 + (行为失败时)上轮 LLM 输出文件。LLM 输出
        # 白名单外文件 → 引擎丢弃, 不写盘。
        allowlist: Optional[set[str]] = None
        # 2026-08-16 (3 次失败头脑风暴): 失败历史 + 触发标记
        failure_history: list[RoundFailure] = []
        brainstorm_done = False
        for round_idx in range(self.max_retries + 1):
            result.rounds = round_idx + 1
            llm_output = self._call_llm(session, system_prompt, user_prompt, repair_context)
            files = parse_generated_files(llm_output)
            if not files:
                result.status = "no-files"
                result.last_errors = (
                    "LLM response contained no parseable files "
                    "(expected '### FILE: <path>' markers or JSON payload)"
                )
                break

            # ── 框住 LLM: repair 轮白名单硬过滤 (2026-08-16) ─────────
            if allowlist is not None:
                kept, dropped = self._filter_out_of_scope(files, allowlist)
                if dropped:
                    result.dropped_files.extend(dropped)
                    log.warning(
                        "Codegen round %d: dropped out-of-scope files %s "
                        "(allowlist: %s)",
                        round_idx + 1, sorted(dropped), sorted(allowlist),
                    )
                files = kept
                if not files:
                    result.status = "failed"
                    result.last_errors = (
                        "LLM only emitted files outside the allowed repair "
                        f"scope ({sorted(allowlist)}); all dropped. "
                        "Stop touching unrelated files."
                    )
                    break

            written = self.write_files(files, out_dir)
            result.files = [str(p) for p in written]

            # ── 确定性修复 (2026-08-20, G-17) ────────────────────────
            # LLM 重写会丢掉 seed 基线的 (void)param; 未用参数抑制 →
            # 项目真实 -Werror -Wunused-parameter 失败且 4 轮 repair 修不好。
            # 机械转换引擎直接做, 不让已知编译错误进入 repair LLM。
            sync_n = self._sync_void_suppressions(out_dir, written)
            if sync_n:
                log.info(
                    "Codegen void-suppression sync: %d suppression(s) applied",
                    sync_n,
                )

            # verify 整个输出目录 (seed 副本 + 本轮修改) — 跨文件引用可被捕获
            verify_files = self._collect_code_files(out_dir)
            # 2026-08-12: 默认 verifier 透传项目根 → 生成的 app 代码可
            # 编译验证宿主项目 HAL API (src/hal/include 等)。自定义
            # verifier 不接收 project_root, 保持旧调用。
            if self.verifier is compilers.compile_verify:
                verify = self.verifier(
                    verify_files, language=language_hint, build_cmd=build_cmd,
                    project_root=getattr(session, "project_dir", None),
                    cflags=cflags,
                )
            else:
                verify = self.verifier(
                    verify_files, language=language_hint, build_cmd=build_cmd,
                    cflags=cflags,
                )
            result.verify = verify
            if verify.get("ok"):
                # ── 编译通过后的追加验证 (2026-08-16) ──────────────────
                # 编译通过 ≠ 行为正确: LLM 会删掉"它觉得多余"的修复块
                # (PINCH_REVERSAL 启动序列 3 次被删, 行为护栏在 deploy 才
                # 拦截)。编译后追加两道检查, 失败也进 repair 轮:
                #   C) seed 契约: 生成代码不得删除既有公共函数
                #   A) 行为验证: 真实测试套件跑一遍生成代码
                extra_errors = self._check_seed_contract(out_dir)
                # ── 结构性 smoke 特征 (2026-08-17) ──────────────────
                # 编译通过但核心功能路径被删 (防夹检测/反转序列) — 行为验证
                # 可能因环境 (ARM 链接) 无法执行, 特征级检查在链接前拦截。
                extra_errors = self._check_structural_features(
                    out_dir, extra_errors
                )
                # ── 禁止特征 (2026-08-17, r21b) ─────────────────────
                # 链接级反模式 (int64 除法 → ARM __aeabi_ldivmod): 行为验证
                # 报错但不指代码行, LLM 4 轮修不好; 这里直接点名禁止子串。
                extra_errors = self._check_forbidden_features(
                    out_dir, extra_errors
                )
                if self.behavior_verify is not None:
                    try:
                        behavior_errors = self.behavior_verify(out_dir)
                        result.behavior_verify_result = (
                            "PASS (临时部署验证: 生成代码暂替 src/ 跑真实测试套件, "
                            "验证后恢复原代码, 0 失败)"
                            if not behavior_errors
                            else f"FAIL ({behavior_errors})"
                        )
                        if behavior_errors:
                            extra_errors = (
                                (extra_errors + "\n" if extra_errors else "")
                                + behavior_errors
                            )
                    except Exception as e:  # pragma: no cover - defensive
                        log.warning("Codegen behavior verify failed: %s", e)
                        result.behavior_verify_result = f"ERROR ({e})"
                else:
                    result.behavior_verify_result = "SKIPPED (no behavior_verify configured)"
                if extra_errors:
                    errors = extra_errors
                    result.last_errors = errors
                    log.warning(
                        "Codegen round %d: compile ok but contract/behavior "
                        "FAILED — repair round",
                        round_idx + 1,
                    )
                    # 落入下方 repair 逻辑 (truncated/best-state/repair_context)
                else:
                    result.status = "verified"
                    result.last_errors = ""
                    break

            errors = (verify.get("errors") or "").strip()
            if not errors and result.last_errors:
                errors = result.last_errors
            result.last_errors = errors or f"verification failed ({verify.get('command')})"
            log.warning(
                "Codegen round %d failed verification: %s",
                round_idx + 1, result.last_errors[:300],
            )

            # 2026-08-14 (headlamp dogfood #4): LLM 输出截断检测 — 大项目
            # 一次输出超 max_tokens → 文件被截断, 编译错误永远存在。检测到
            # 截断文件时, repair 提示要求**只重发这些完整文件**, 避免再次
            # 全量输出 → 再次截断 (无效 repair 循环)。
            truncated = self._detect_truncated_files(files)
            if truncated:
                log.warning(
                    "Codegen round %d: truncated files detected: %s",
                    round_idx + 1, truncated,
                )

            # best-state 回滚 (方案 C): 错误数更少才更新快照; 否则回滚到
            # 历史最佳, 下一轮基于最佳版本修复而非"越修越坏"的当前版本。
            err_count = self._error_count(errors)
            if best_error_count is None or err_count < best_error_count:
                best_error_count = err_count
                best_state = self._snapshot_files(out_dir)
                log.info(
                    "Codegen round %d: new best state (%d errors)",
                    round_idx + 1, err_count,
                )
            else:
                self._restore_files(out_dir, best_state)
                log.info(
                    "Codegen round %d: worse (%d >= %d) — rolled back to best state",
                    round_idx + 1, err_count, best_error_count,
                )

            # ── 3 次失败 → 头脑风暴 (2026-08-16, 老板指令) ────────────
            # 记录失败模式 (错误签名 / 趋势 / 是否行为失败), 连续失败达到
            # 阈值时: 引擎做失败模式分析 + 强制恢复 seed 基线, 下一轮用
            # 脑暴指令 (恢复基线语义 vs 最小修改 vs 停止恶化), 不再盲目重试。
            failure_history.append(RoundFailure(
                round_idx=round_idx,
                error_signature=self._error_signature(errors),
                err_count=err_count,
                is_behavior=("FAIL" in errors or "行为" in errors),
                files=[f.path for f in files],
            ))
            if not brainstorm_done and len(failure_history) >= self.brainstorm_after_failures:
                brainstorm_done = True
                analysis = self._brainstorm(failure_history)
                result.brainstorm = analysis
                # 引擎强制恢复 seed 基线 (LLM 新增文件保留) — 不靠 LLM 自觉
                restored = self._restore_seed_baseline(out_dir)
                log.warning(
                    "Codegen round %d: BRAINSTORM triggered (strategy=%s, "
                    "reason=%s) — restored %d files to seed baseline",
                    round_idx + 1, analysis.get("strategy"),
                    analysis.get("reason"), restored,
                )

            if round_idx < self.max_retries:
                # 下一轮的允许修改范围: 错误涉及文件 + seed_contract 文件;
                # 行为失败 (错误文本只有测试文件) 时加上本轮 LLM 输出文件。
                if brainstorm_done:
                    repair_context = self._format_brainstorm_context(
                        result.brainstorm, result.last_errors, files, best_state,
                        seed_baseline=self._seed_baseline,
                    )
                else:
                    repair_context = self._format_repair_context(
                        result.last_errors, files, best_state,
                        truncated_files=truncated,
                        seed_baseline=self._seed_baseline,
                    )
                allowlist = self._build_allowlist(
                    result.last_errors, files, self.seed_contract,
                )

        result.finished_at = datetime.now().isoformat()
        if result.status == "pending":
            result.status = "failed"

        # ── 最终产物终验 (2026-08-18, r21j blocker 2/3 根因) ──────────
        # 循环内 result.verify / behavior_verify_result 记录的是最后一次
        # verify 时刻的状态; 之后 best-state 回滚 / brainstorm seed 恢复
        # 可能覆盖磁盘产物 → report 与最终产物失步 (评审用磁盘实测对不上
        # report 的 PASS/FAIL)。终验对**最终磁盘产物**重新执行完整验证链,
        # report 以此为准; 全过则惊喜晋级 verified (部署照常), 否则如实
        # 报告失败 (含全量失败文本, 不截断到 2 条)。
        # 例外: result.files 为空 (no-files / 首轮即无有效输出) 时跳过 —
        # 磁盘产物只是 seed 自身, LLM 没有产出, 不得借终验假晋级。
        if result.status != "verified" and result.files:
            self._final_verify(result, session, out_dir, language_hint,
                               build_cmd, cflags)

        result.report_path = str(self._write_report(result, session))
        return result

    # ---- Steps ---------------------------------------------------------

    def _call_llm(
        self,
        session: PipelineSession,
        system_prompt: str,
        user_prompt: str,
        repair_context: str = "",
    ) -> str:
        client = self.llm_client or getattr(session, "llm_client", None)
        if client is None:
            from yuleosh.pipeline.run import chat_completion

            client = chat_completion
        prompt = user_prompt + repair_context
        # Codegen prompts carry the full spec + PRD + architecture + seed
        # sources and generate up to max_tokens (default 16000) — DeepSeek
        # regularly exceeds the 60s chat_completion default on long outputs.
        # 120s baseline, overridable via YULEOSH_CODEGEN_LLM_TIMEOUT.
        timeout_s = int(os.environ.get("YULEOSH_CODEGEN_LLM_TIMEOUT", "120"))
        try:
            response = client(
                system_prompt, prompt, max_tokens=self.max_tokens, timeout=timeout_s
            )
        except Exception as e:  # LLM transport failure is fatal
            raise PipelineStepError(f"Codegen LLM call failed: {e}") from e
        if isinstance(response, dict):
            return str(response.get("content", ""))
        return str(response)

    def write_files(self, files: list[GeneratedFile], out_dir: Path) -> list[Path]:
        """Write generated files under ``out_dir`` (path-traversal safe)."""
        written: list[Path] = []
        for f in files:
            rel = _safe_relative_path(f.path)
            target = (out_dir / rel).resolve()
            if not str(target).startswith(str(out_dir.resolve())):
                log.warning("Blocked path escaping output dir: %s", f.path)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f.content, encoding="utf-8")
            written.append(target)
            log.debug("Wrote generated file %s (%d bytes)", target, len(f.content))
        return written

    # ---- 确定性 void 抑制同步 (2026-08-20, G-17) ----------------------

    # G-17 根因 (r21f/r22 反复): LLM 重写 .c 文件时会丢掉 seed 基线里
    # ``(void)param;`` 未用参数抑制 (window_modes.c 丢 (void)lastCheckTimeMs;),
    # 项目真实 -Werror -Wunused-parameter 构建失败, 且 4 轮 LLM repair 都
    # 修不好 (worsening → 回退 seed 基线)。该转换是机械的 — 由引擎直接做,
    # 不依赖 LLM: 每轮 write 后把 seed 基线的 (void)param; 抑制同步进生成文件。
    _VOID_CAST_RE = re.compile(r"\(void\)\s*(\w+)\s*;")
    # 函数定义: 返回类型必须以单词字符开头 (禁止全空白类型 → 否则
    # `if (`/`for (` 控制流被误判为函数定义, 见 test_static_function_and_nested_block)。
    # re.MULTILINE: finditer 需要 ^ 匹配每行行首。
    _FUNC_DEF_RE = re.compile(
        r"^\s*(?:static\s+)?(?:\w[\w\s\*]*?)\s+(\w+)\s*\(",
        re.MULTILINE,
    )

    def _iter_void_suppressions(
        self, seed_content: str
    ) -> list[tuple[str, str]]:
        """Extract ``(param, enclosing_function)`` from a seed .c file.

        Scans each ``(void)X;`` statement and walks backwards to the nearest
        function-definition line to attribute it to a function.
        """
        out: list[tuple[str, str]] = []
        lines = seed_content.splitlines()
        for idx, line in enumerate(lines):
            m = self._VOID_CAST_RE.search(line)
            if not m:
                continue
            param = m.group(1)
            fn_name: str | None = None
            for back in range(idx - 1, -1, -1):
                fm = self._FUNC_DEF_RE.match(lines[back])
                if fm:
                    fn_name = fm.group(1)
                    break
            if fn_name:
                out.append((param, fn_name))
        return out

    @staticmethod
    def _signature_region(content: str, fn_start: int) -> str:
        """Return the parameter-list text of the function starting at
        ``fn_start`` (the opening paren .. matching close paren)."""
        i = content.find("(", fn_start)
        if i == -1:
            return ""
        depth = 0
        j = i
        while j < len(content):
            c = content[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        return content[i:j]

    def _sync_void_suppressions(
        self, out_dir: Path, written: list[Path]
    ) -> int:
        """Deterministic G-17 guard: carry ``(void)param;`` suppressions over.

        For each written .c file that has a seed-baseline counterpart:
          - take every ``(void)X;`` statement from the seed file and its
            enclosing function name;
          - if the generated file defines the same function AND declares the
            same parameter X but lacks the suppression anywhere, insert
            ``(void)X;`` right after the function's opening brace.

        Applied after every write (initial + each repair round), so this
        known compile error never reaches the repair LLM.
        """
        applied = 0
        for target in written:
            if target.suffix.lower() != ".c":
                continue
            rel = target.relative_to(out_dir).as_posix()
            seed_content = self._seed_baseline.get(rel)
            if not seed_content:
                continue
            gen_content = target.read_text(encoding="utf-8", errors="replace")
            original = gen_content
            for param, fn_name in self._iter_void_suppressions(seed_content):
                marker = f"(void){param};"
                if marker in gen_content:
                    continue
                # 只在同名函数且参数列表含 X 时插入 — 避免误伤其它函数
                fn_found = False
                for fm in self._FUNC_DEF_RE.finditer(gen_content):
                    if fm.group(1) != fn_name:
                        continue
                    fn_found = True
                    sig = self._signature_region(gen_content, fm.start())
                    if not re.search(r"\b" + re.escape(param) + r"\b", sig):
                        continue
                    gen_content = self._insert_void_suppression(
                        gen_content, fm.start(), param
                    )
                    applied += 1
                    log.info(
                        "Codegen void-suppression sync: inserted (void)%s; "
                        "in %s (%s)", param, rel, fn_name,
                    )
                    break
                if not fn_found:
                    log.debug(
                        "Codegen void-suppression sync: function %s missing "
                        "in generated %s (seed_contract will flag if public)",
                        fn_name, rel,
                    )
            if gen_content != original:
                target.write_text(gen_content, encoding="utf-8")
        return applied

    @staticmethod
    def _insert_void_suppression(
        content: str, fn_start: int, param: str
    ) -> str:
        """Insert ``(void)param;`` after the function body's opening brace."""
        sig = content[fn_start:]
        # 参数列表内无花括号 (嵌入式 C 契约, 不支持函数指针参数), 第一个
        # '{' 即函数体起始。
        brace = sig.find("{")
        if brace == -1:
            return content
        brace_abs = fn_start + brace
        line_start = content.rfind("\n", 0, brace_abs) + 1
        indent = content[line_start:brace_abs]
        insertion = (
            f"{indent}    (void){param};"
            "  /* deterministic sync from seed baseline (G-17) */\n"
        )
        return (
            content[: brace_abs + 1]
            + "\n"
            + insertion
            + content[brace_abs + 1:]
        )

    # ---- Seed 增量 (方案 C, 2026-08-12) --------------------------------

    def _sync_seed(self, seed_dir: Path, out_dir: Path) -> list[Path]:
        """Copy the project's existing src code into the output dir.

        Only ``.c`` / ``.h`` files under ``<seed_dir>/src`` are copied
        (excluding build/cache dirs).  The output dir becomes the working
        tree the LLM incrementally modifies — unmodified files keep their
        baseline content.
        """
        from yuleosh.codegen.prompts import SEED_EXCLUDE_DIRS

        src_dir = seed_dir / "src"
        if not src_dir.is_dir():
            return []
        copied: list[Path] = []
        for p in sorted(src_dir.rglob("*")):
            if p.suffix.lower() not in (".c", ".h"):
                continue
            if any(part in SEED_EXCLUDE_DIRS for part in p.relative_to(src_dir).parts):
                continue
            rel = p.relative_to(seed_dir)
            target = (out_dir / rel).resolve()
            if not str(target).startswith(str(out_dir.resolve())):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(p.read_text(encoding="utf-8", errors="replace"),
                              encoding="utf-8")
            copied.append(target)
        return copied

    def _collect_code_files(self, out_dir: Path) -> list[Path]:
        """All ``.c`` / ``.h`` / ``.py`` files under the output dir.

        Excludes ``tests/`` (2026-08-14 headlamp dogfood): LLM 生成的测试
        引用 Unity 等测试框架头 (``#include "unity.h"``), verify_c 的 -I
        收集不含框架头 → 3 个 fatal error → codegen 假失败。测试由
        c-unit-test 步骤用项目真实构建 (ctest) 验证, 不属于 codegen
        verify 范围。
        """
        exts = {".c", ".h", ".py"}
        return [p for p in sorted(out_dir.rglob("*"))
                if p.is_file()
                and p.suffix.lower() in exts
                and "tests" not in p.relative_to(out_dir).parts]

    @staticmethod
    def _error_count(errors: str) -> int:
        """Count compiler error lines (``error:`` / ``Error``) in output.

        2026-08-16: behavior-failure output (``FAIL ...`` from ctest) is also
        counted — a behavior regression with 0 compile errors must NOT become
        a "new best state" (which would let the LLM keep building on its own
        broken edits instead of rolling back to the seed baseline).
        """
        if not errors:
            return 0
        errs = re.findall(r"(?m)^.*\berror\b.*$", errors)
        fails = re.findall(r"(?m)^.*\bFAIL\b.*$", errors)
        return len(errs) + len(fails)

    # ---- 框住 LLM + 头脑风暴 (2026-08-16) ---------------------------

    @staticmethod
    def _error_signature(errors: str) -> str:
        """归一化错误签名: 去行号/列号/数字差异, 保留错误类型与消息。

        用于判断"同一错误反复出现" — window-anti-pinch 实证 LLM 会
        连续 3+ 轮修同一个错误 (行号每次都变)。签名相同 → 自由修改
        无效 → 触发头脑风暴的 restore_baseline 策略。
        """
        if not errors:
            return ""
        sig_lines = []
        for line in errors.splitlines():
            # 去 gcc/ctest 行号列号 (file:LINE:COL:), 去临时路径前缀
            line = re.sub(r":\d+(:\d+)?", "", line)
            line = re.sub(r"(/[\w.\-]+)+/", "", line)
            line = re.sub(r"\d+", "#", line)
            line = re.sub(r"\s+", " ", line).strip()
            if not line:
                continue
            if line.startswith(("Test ", "Start testing", "End testing")):
                continue
            sig_lines.append(line[:120])
        return "\n".join(sig_lines[:30])

    @staticmethod
    def _extract_error_files(errors: str) -> set[str]:
        """从错误文本提取涉及的文件路径 (编译错误行 / FAIL 行 / include 链)。

        白名单的基础: LLM 只允许修改错误真正涉及的代码文件。
        """
        if not errors:
            return set()
        files: set[str] = set()
        # file:LINE:COL: error / file:LINE: FAIL / In file included from file:
        for m in re.finditer(
            r"(?m)(?<![\w./-])([\w./\-]+\.(?:c|h|cpp|hpp|py))(?::\d+)?",
            errors,
        ):
            files.add(m.group(1))
        # 行为失败文本可能只有测试名: "FAIL test.c:20: state == IDLE"
        # — 测试文件不算允许修改的 src, 但保留路径以供判断。
        return files

    @staticmethod
    def _norm_path(p: str) -> str:
        """路径归一化: 绝对路径 → 项目相对路径, 供白名单比较。

        Python 编译错误给绝对路径 (``/tmp/.../src/ok.py``), LLM 输出
        相对路径 (``src/ok.py``) — 精确字符串比较会误伤。统一取
        ``src/`` / ``tests/`` / ``include/`` 之后的相对部分。
        """
        for marker in ("src/", "tests/", "include/"):
            idx = p.find(marker)
            if idx >= 0:
                return p[idx:]
        return Path(p).name

    @staticmethod
    def _build_allowlist(
        errors: str,
        round_files: list[GeneratedFile],
        seed_contract: Optional[dict[str, set[str]]] = None,
    ) -> set[str]:
        """计算下一轮允许 LLM 修改的文件集合 (框住 LLM 的核心)。

        白名单 = 错误涉及文件 + seed_contract 文件 (既有公共函数,
        删除即回归 — 允许 LLM 恢复它们) + 本轮 LLM 输出文件 (它自己
        生成/修改过的文件, 修复编译错误时可能需连带修改配套文件 —
        如新 .c 依赖的头文件声明; 行为失败时 ctest FAIL 文本往往不
        含 src 路径, 错误来源正是本轮改动的文件)。

        白名单外的文件即使 LLM 输出了也会被引擎丢弃 — 不靠 prompt 自觉。
        新文件在第一轮 (无 allowlist) 可自由生成; 之后 LLM 想改某个
        文件必须先出现在错误指向或它自己的历史输出里。
        """
        allow = {CodegenEngine._norm_path(p)
                 for p in CodegenEngine._extract_error_files(errors)}
        if seed_contract:
            allow |= {CodegenEngine._norm_path(p) for p in seed_contract}
        allow |= {f.path for f in round_files}
        # 过滤掉测试文件路径 (行为失败文本提取的 test.c 之类)
        return {p for p in allow if not any(
            part == "tests" or part.endswith("_test") or part.startswith("test")
            for part in Path(p).parts)}

    def _filter_out_of_scope(
        self, files: list[GeneratedFile], allowlist: set[str],
    ) -> tuple[list[GeneratedFile], list[str]]:
        """把白名单外的生成文件剔除 — 硬过滤, 不写盘。"""
        kept: list[GeneratedFile] = []
        dropped: list[str] = []
        for f in files:
            if self._norm_path(f.path) in allowlist:
                kept.append(f)
            else:
                dropped.append(f.path)
        return kept, dropped

    @staticmethod
    def _brainstorm(failures: list[RoundFailure]) -> dict:
        """失败模式分析 — 3 次失败后决定下一轮策略 (确定性, 不调 LLM)。

        策略:
        - restore_baseline: 同一行为错误反复 (FAIL 占多数) → 恢复基线语义
        - minimal_fix: 同一编译错误反复 → 只允许最小修改, 禁止重写
        - stop_worsening: 错误数持续上升 → 回退 seed, 停止自由发挥
        - narrow_scope: 错误漂移/混合 → 收窄到错误文件
        """
        sigs = [f.error_signature for f in failures]
        counts = [f.err_count for f in failures]
        behavior_n = sum(1 for f in failures if f.is_behavior)
        same_error = len(set(sigs)) == 1 and bool(sigs[0])
        worsening = len(counts) >= 2 and counts[-1] > counts[0]
        if same_error and behavior_n >= max(1, len(failures) // 2):
            strategy = "restore_baseline"
            reason = "同一行为错误反复出现 (FAIL 占多数) — 自由修改无效, 恢复基线语义"
        elif same_error:
            strategy = "minimal_fix"
            reason = "同一编译错误反复出现 — 禁止重写文件, 只做最小修复"
        elif worsening:
            strategy = "stop_worsening"
            reason = "错误数持续上升 — 修改在制造新问题, 回退 seed 基线"
        else:
            strategy = "narrow_scope"
            reason = "错误漂移/混合 — 收窄修改范围到错误涉及文件"
        return {
            "rounds": len(failures),
            "same_error": same_error,
            "worsening": worsening,
            "behavior_count": behavior_n,
            "strategy": strategy,
            "reason": reason,
        }

    def _restore_seed_baseline(self, out_dir: Path) -> int:
        """头脑风暴触发时引擎强制恢复 seed 基线 (内存快照)。

        只恢复快照中存在的文件 (seed 原有的); LLM 本轮新增的文件保留
        (它们是新功能, 不一定是坏的)。返回恢复的文件数。
        """
        if not self._seed_baseline:
            return 0
        restored = 0
        for rel, content in self._seed_baseline.items():
            target = (out_dir / rel).resolve()
            if not str(target).startswith(str(out_dir.resolve())):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            restored += 1
        log.info("Restored %d files to seed baseline (brainstorm)", restored)
        return restored

    @staticmethod
    def _format_brainstorm_context(
        analysis: dict,
        errors: str,
        files: list[GeneratedFile],
        best_state: dict[str, str] | None = None,
        seed_baseline: Optional[dict[str, str]] = None,
    ) -> str:
        """3 次失败后的头脑风暴指令 — 替换普通 repair context。

        明确告诉 LLM: 你已连续失败 N 轮, 引擎分析了失败模式, 已强制
        恢复 seed 基线; 现在按指定策略做**最小修改**, 禁止自由发挥。
        2026-08-18 r21h: 追加 seed 基线代码块 — 策略提示说"恢复 seed 原样"
        但无具体代码时 LLM 仍会整体重写 (r21h window_modes.c (void) 抑制
        4 轮丢失), 必须贴出基线实现。
        """
        rounds = analysis.get("rounds", 0)
        strategy = analysis.get("strategy", "narrow_scope")
        reason = analysis.get("reason", "")
        strategy_hint = {
            "restore_baseline": (
                "你的修改反复引入同一行为回归。磁盘上的 seed 基线就是正确实现。\n"
                "要求: **恢复基线语义** — 不要重写、不要删 guard/启动序列/"
                "状态更新。对照 FAIL 行找到被你改坏的函数, 把实现恢复为 "
                "seed 原样, 只做必要的最小修复。"
            ),
            "minimal_fix": (
                "你已连续多轮无法修复同一编译错误。停止整体重写文件。\n"
                "要求: 逐条对照编译错误, **只修复报错的那几行**, 其余代码 "
                "保持磁盘现状 (引擎已恢复 seed 基线)。一次只输出 1-2 个文件。"
            ),
            "stop_worsening": (
                "你的修改让错误数持续增加。引擎已把文件恢复为 seed 基线。\n"
                "要求: **不要添加新逻辑**。如果无法确定修复方案, 直接重新 "
                "输出 seed 基线文件内容 (磁盘现状), 不要尝试新写法。"
            ),
            "narrow_scope": (
                "错误模式不稳定。引擎已恢复 seed 基线。\n"
                "要求: 只修改错误输出中明确提到的文件, 做最小改动。"
            ),
        }.get(strategy, "")
        listing = "\n".join(f"  - {f.path}" for f in files) or "  - (none)"
        return (
            f"\n\n## 🧠 头脑风暴 — 已连续 {rounds} 轮失败, 策略已切换\n"
            f"引擎分析了失败模式: {reason}\n\n"
            f"{strategy_hint}\n\n"
            f"上一轮输出文件:\n{listing}\n\n"
            "错误输出:\n```\n"
            f"{errors[:4000]}\n```\n\n"
            "**只允许修改与错误直接相关的文件。** 引擎会丢弃白名单外的文件。"
            f"{CodegenEngine._format_seed_hints(seed_baseline, files)}"
        )
    @staticmethod
    def _detect_truncated_files(files: list[GeneratedFile]) -> list[str]:
        """Detect files whose content looks truncated (LLM output cut off).

        2026-08-14 (headlamp dogfood #4): 大项目 (12+ C 文件) 一次输出超过
        max_tokens → 最后一个文件被截断 (如 ``if (resp_len`` 无闭合)。
        Repair 轮同样超限 → 永远修不好。检测特征:

        - ``.c`` / ``.h`` 顶层花括号不平衡 (``{`` != ``}``) — C 编译的
          "expected '}'" / "unexpected EOF" 根源。
        - 以不完整的行结束 (末行不是合法结尾, 且无尾随换行) — 保守特征。

        返回相对路径列表 (仅 C 系语言)。
        """
        truncated: list[str] = []
        for f in files:
            suffix = Path(f.path).suffix.lower()
            if suffix not in (".c", ".h", ".cpp", ".hpp"):
                continue
            content = f.content
            opens = content.count("{")
            closes = content.count("}")
            if opens > closes:
                truncated.append(f.path)
                continue
            # 末行截断启发: 无尾随换行 + 末行包含未闭合的括号/分号
            if not content.endswith("\n"):
                last_line = content.rsplit("\n", 1)[-1].strip()
                if last_line and not last_line.endswith(("}", ")", ";", "#endif", ",", "\"", "'", "*/")):
                    truncated.append(f.path)
        return sorted(set(truncated))

    def _check_seed_contract(self, out_dir: Path) -> str:
        """Check generated code preserves existing public functions (C, 2026-08-16).

        seed_contract: {rel_path: {func_name, ...}} — 现有 src/ 的公共函数
        (非 static, 从头文件声明收集)。生成代码删除既有公共函数 → 判定
        回归 (LLM 全量重写时常整块删除修复逻辑, 编译却通过)。

        Returns error text ("" when ok).
        """
        if not self.seed_contract:
            return ""
        missing_blocks: list[str] = []
        for rel, funcs in sorted(self.seed_contract.items()):
            gen_file = out_dir / rel
            if not gen_file.exists():
                # 整个文件被删 — 由 deploy API 契约闸兜底, 这里只记缺失
                missing_blocks.append(f"  - {rel}: 整个文件缺失")
                continue
            content = gen_file.read_text(encoding="utf-8", errors="replace")
            missing = [f for f in sorted(funcs) if f not in content]
            if missing:
                missing_blocks.append(
                    f"  - {rel}: 缺失公共函数 {', '.join(missing)}"
                )
        if not missing_blocks:
            return ""
        return (
            "## ⚠️ seed 契约破坏 — 生成代码删除了既有公共函数 (2026-08-16)\n"
            "以下函数在现有 src/ 中声明并被测试/harness 依赖, 生成代码不得删除:\n"
            + "\n".join(missing_blocks)
            + "\n请恢复这些函数的完整实现 (可修改内部逻辑, 但签名必须保留)。\n"
        )

    def _check_structural_features(self, out_dir: Path, prior_errors: str = "") -> str:
        """Check generated code preserves project-configured structural features.

        structural_features: {rel_path_glob: [feature_substring, ...]} — 项目
        配置的关键功能路径特征 (如 `window_modes_check_pinch` 调用、反转状态
        入口、G-04 四步序列)。LLM 全量重写时编译通过但删除核心路径是静默
        回归; 行为验证可能因环境 (ARM 链接/缺板卡) 无法执行, 此检查在
        链接之前用纯文本特征拦截, 给 LLM 明确修复指令。

        Returns error text (prior_errors + 新发现的缺失特征), "" when ok.
        """
        if not self.structural_features:
            return prior_errors
        missing_blocks: list[str] = []
        for pattern, features in sorted(self.structural_features.items()):
            if not features:
                continue
            matched = list(out_dir.glob(pattern))
            if not matched:
                missing_blocks.append(
                    f"  - {pattern}: 无匹配文件 (生成代码可能删除了整个文件)"
                )
                continue
            for f in matched:
                if not f.is_file():
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                missing = [feat for feat in features if feat not in content]
                if missing:
                    missing_blocks.append(
                        f"  - {f.relative_to(out_dir)}: 缺失结构特征 "
                        f"{', '.join(missing)}"
                    )
        if not missing_blocks:
            return prior_errors
        new_errors = (
            "## ⚠️ 结构性 smoke 特征缺失 — 生成代码删除了关键功能路径 "
            "(2026-08-17)\n"
            "编译通过但以下文件缺少项目配置的核心功能特征 (防夹检测调用/反转"
            "状态入口/启动序列等)。即使能链接, 功能也静默丢失 — SHALL 恢复:\n"
            + "\n".join(missing_blocks)
            + "\n请恢复这些特征对应的完整功能路径 (可从 seed 基线参考实现)。\n"
        )
        return (prior_errors + "\n" + new_errors).strip() if prior_errors else new_errors

    def _check_forbidden_features(self, out_dir: Path, prior_errors: str = "") -> str:
        """Check generated code does NOT contain forbidden anti-patterns.

        forbidden_features: {rel_path_glob: [禁止出现的子串]} — 链接级/语义级
        反模式 (如 ARM freestanding 的 int64 除法 `(int64_t)` → __aeabi_ldivmod
        未定义)。行为验证能报链接错误, 但错误信息是链接器输出不指代码行,
        4 轮 repair 里 LLM 不理解为啥要改; 这里在链接前直接点名禁止子串,
        修复指令明确可执行。

        Returns error text (prior_errors + 新发现的禁止特征), "" when ok.
        """
        if not self.forbidden_features:
            return prior_errors
        bad_blocks: list[str] = []
        for pattern, forbidden in sorted(self.forbidden_features.items()):
            if not forbidden:
                continue
            matched = list(out_dir.glob(pattern))
            if not matched:
                continue
            for f in matched:
                if not f.is_file():
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                # 2026-08-18 r21o (claude-review): 裸子串匹配会把注释里的
                # 禁止词也命中 — codegen 把 spec/PRD 的禁止措辞复述进注释
                # (如 window_position.c:255 "禁止改用 (int64_t)") 属正常行为,
                # 却导致行为验证被 SKIP → 掩盖生成产物真实语义漂移。
                # 只匹配代码部分 (剥离 /* */ 与 // 注释后再查)。
                code_only = _strip_c_comments(content)
                found = [feat for feat in forbidden if feat in code_only]
                if found:
                    bad_blocks.append(
                        f"  - {f.relative_to(out_dir)}: 禁止出现 "
                        f"{', '.join(found)} (注释内出现不计)"
                    )
        if not bad_blocks:
            return prior_errors
        # 2026-08-18 r21g 复盘: "参考 seed 基线实现" 无具体代码时 LLM 无从
        # 下手 — r21g 4 轮 repair 全部重写回 (int64_t)。有 seed 快照时把
        # 违规文件的基线版本贴进 repair 消息, 让修复有具体模板可抄。
        seed_hints: list[str] = []
        for pattern in sorted(self.forbidden_features):
            for f in sorted(out_dir.glob(pattern)):
                if not f.is_file():
                    continue
                rel = str(f.relative_to(out_dir))
                seed_content = self._seed_baseline.get(rel)
                if seed_content:
                    truncated = len(seed_content) > 6000
                    seed_hints.append(
                        f"\n### {rel} — seed 基线实现 (SHALL 以此为基础做"
                        f"最小修改, 禁止重写回反模式):\n```c\n"
                        f"{seed_content[:6000]}"
                        f"{'... (truncated)' if truncated else ''}\n```\n"
                    )
        new_errors = (
            "## ⚠️ 禁止特征出现 — 生成代码引入了链接级/语义级反模式 "
            "(2026-08-17)\n"
            "以下文件包含项目配置的禁止子串 (如 ARM freestanding 的 int64 "
            "除法会导致 __aeabi_ldivmod 链接失败)。SHALL 移除:\n"
            + "\n".join(bad_blocks)
            + "\n请改用 32 位运算或乘后比较。\n"
            + (("\n".join(seed_hints)) if seed_hints
               else "\n(无 seed 基线快照 — 请以项目 src/ 对应文件为参考)\n")
        )
        return (prior_errors + "\n" + new_errors).strip() if prior_errors else new_errors

    def _final_verify(
        self,
        result: CodegenResult,
        session: PipelineSession,
        out_dir: Path,
        language_hint: Optional[str],
        build_cmd: Optional[list[str]],
        cflags: Optional[list[str]],
    ) -> None:
        """对最终磁盘产物重新执行完整验证链 (2026-08-18, r21j blocker 2/3)。

        循环结束时磁盘产物可能已被 best-state 回滚 / brainstorm seed 恢复
        覆盖 — 循环内记录的 verify 结果对应的是最后一次 verify 时刻的
        产物, 与最终磁盘状态失步。终验保证 report 描述的就是评审/部署
        会看到的精确产物:

        1. compile verify (同一 verifier + cflags, -Werror 编译门)
        2. compile ok → seed 契约 + 结构性 smoke + 禁止特征检查
        3. compile + 契约 ok → behavior verify (真实测试套件临时部署)
        4. 全过 → status 惊喜晋级 verified; 任一失败 → status=failed 且
           last_errors 为最终产物全量失败文本 (不截断)。

        注意: 终验的行为验证会再次临时部署/回滚 src/, 与循环内行为验证
        互不影响 (每次都是独立备份/恢复)。
        """
        verify_files = self._collect_code_files(out_dir)
        if self.verifier is compilers.compile_verify:
            verify = self.verifier(
                verify_files, language=language_hint, build_cmd=build_cmd,
                project_root=getattr(session, "project_dir", None),
                cflags=cflags,
            )
        else:
            verify = self.verifier(
                verify_files, language=language_hint, build_cmd=build_cmd,
                cflags=cflags,
            )
        result.verify = verify
        if not verify.get("ok"):
            result.status = "failed"
            result.last_errors = (
                (verify.get("errors")
                 or f"final verification failed ({verify.get('command')})")
            )
            result.behavior_verify_result = (
                "SKIPPED (final product fails -Werror compile — behavior run "
                "would be invalid)"
            )
            return

        # 编译通过 → 契约链检查
        extra = self._check_seed_contract(out_dir)
        extra = self._check_structural_features(out_dir, extra)
        extra = self._check_forbidden_features(out_dir, extra)
        if extra:
            result.status = "failed"
            result.last_errors = extra
            result.behavior_verify_result = (
                "SKIPPED (final product fails contract checks — behavior run "
                "would be invalid)"
            )
            return

        # 编译 + 契约全过 → 行为验证 (真实测试套件)
        if self.behavior_verify is not None:
            try:
                behavior_errors = self.behavior_verify(out_dir)
                result.behavior_verify_result = (
                    "PASS (临时部署验证: 生成代码暂替 src/ 跑真实测试套件, "
                    "验证后恢复原代码, 0 失败)"
                    if not behavior_errors
                    else f"FAIL ({behavior_errors})"
                )
                if behavior_errors:
                    result.status = "failed"
                    result.last_errors = behavior_errors
            except Exception as e:  # pragma: no cover - defensive
                log.warning("Codegen final behavior verify failed: %s", e)
                result.behavior_verify_result = f"ERROR ({e})"
        else:
            result.behavior_verify_result = (
                "SKIPPED (no behavior_verify configured)"
            )

        if result.status != "failed":
            result.status = "verified"
            result.last_errors = ""
            log.info(
                "Codegen FINAL VERIFY: final product passed all checks — "
                "promoted to verified"
            )

    def _snapshot_files(self, out_dir: Path) -> dict[str, str]:
        snap: dict[str, str] = {}
        for p in self._collect_code_files(out_dir):
            try:
                snap[str(p.relative_to(out_dir))] = p.read_text(encoding="utf-8")
            except OSError:
                continue
        return snap

    def _restore_files(self, out_dir: Path, snapshot: dict[str, str]) -> None:
        """Restore the output dir from a snapshot (rollback to best state)."""
        for rel, content in snapshot.items():
            target = (out_dir / rel).resolve()
            if not str(target).startswith(str(out_dir.resolve())):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        log.info("Restored %d files to best state", len(snapshot))

    @staticmethod
    def _format_seed_hints(
        seed_baseline: Optional[dict[str, str]],
        files: list[GeneratedFile],
        limit: int = 6000,
    ) -> str:
        """构建 repair 消息里的 seed 基线代码块 (2026-08-18 r21h)。

        r21h 复盘: compile-error repair 路径只给编译器输出, 不贴 seed 实现 —
        LLM 4 轮重写 window_modes.c 都丢了 (void)lastCheckTimeMs 抑制
        (G-17 -Werror 编译失败)。错误涉及文件的 seed 基线版本是修复模板,
        必须贴出来让 LLM 有具体代码可抄, 而不是空喊"参考 seed 基线"。
        """
        if not seed_baseline:
            return ""
        hints: list[str] = []
        for f in files:
            content = seed_baseline.get(f.path)
            if not content:
                continue
            truncated = len(content) > limit
            hints.append(
                f"\n### {f.path} — seed 基线实现 (SHALL 以此为基础做最小修改, "
                f"禁止整体重写):\n```c\n{content[:limit]}"
                f"{'... (truncated)' if truncated else ''}\n```\n"
            )
        if not hints:
            return ""
        return (
            "\n\n## 📄 seed 基线实现 (机器提供, 2026-08-18 r21h)\n"
            "以下是你上一轮修改文件的**原始基线版本** — 编译失败/功能丢失的"
            "修复应以它为准, 保留其正确模式 (如 (void) 抑制未用参数、guard "
            "条件、启动序列、防夹区门控):\n"
            + "\n".join(hints)
        )

    @staticmethod
    def _format_repair_context(
        errors: str,
        files: list[GeneratedFile],
        best_state: Optional[dict[str, str]] = None,
        truncated_files: Optional[list[str]] = None,
        seed_baseline: Optional[dict[str, str]] = None,
    ) -> str:
        """Build the compiler-feedback block appended to the next prompt.

        best_state (方案 C): 当前磁盘上错误数最少的版本的文件清单。
        提示模型只输出需要修复的文件 — 未修改文件保留磁盘现状,
        避免全量重发引入新错误。

        truncated_files (2026-08-14, headlamp dogfood #4): LLM 输出被
        max_tokens 截断的文件列表。这些文件必须**完整重发** (当前磁盘
        副本不完整), 但**只重发这些文件** — 避免全量输出再次截断。
        """
        listing = "\n".join(f"  - {f.path}" for f in files) or "  - (none)"
        disk_hint = ""
        if best_state:
            disk_listing = "\n".join(f"  - {rel}" for rel in sorted(best_state))
            disk_hint = (
                "\n\n当前磁盘上已有这些文件 (未修改的基线/上一轮最佳版本):\n"
                f"{disk_listing}\n"
                "**只重新输出你修改的文件** — 未修改的不要重发, 磁盘会保留。"
            )
        trunc_hint = ""
        if truncated_files:
            trunc_listing = "\n".join(f"  - {p}" for p in truncated_files)
            trunc_hint = (
                "\n\n## ✂️ 输出截断警告 — 以下文件被截断 (内容不完整):\n"
                f"{trunc_listing}\n"
                "这些文件必须**完整重新输出** (当前内容缺失/不完整)。\n"
                "**注意**: 一次只输出这些文件, 不要附带其它未修改文件 — "
                "否则会再次超过输出长度限制。"
            )
        # 2026-08-16: behavior-failure repair hint. 编译通过但行为测试失败
        # 时, 错误来自 ctest/行为预检 (FAIL 行) 而非编译器 — LLM 只看到
        # "编译错误" 提示会把好代码越改越坏。必须明确: 失败是**它自己引入
        # 的回归**, seed 基线 (磁盘当前版本) 是正确的, 只做最小修改恢复。
        behavior_hint = ""
        if ("FAIL" in errors) or ("行为" in errors):
            behavior_hint = (
                "\n\n## ⚠️ 行为测试失败 (不是编译错误!) — 你引入了回归\n"
                "编译通过了, 但真实测试套件跑出 FAIL。这些失败几乎都是你"
                "上一轮修改**删掉/改坏了既有正确实现**造成的。\n"
                "要求: **恢复基线实现** — 磁盘上当前版本就是正确的种子代码"
                "(未修改文件保留原样)。请对照 FAIL 行定位被你改坏的函数, "
                "把实现恢复为基线语义 (可做最小修复, 不要整体重写、不要删"
                "既有 guard/启动序列/状态更新)。"
            )
        return (
            "\n\n## 🔧 编译验证失败 — 请修复后重新输出文件\n"
            f"上一轮生成/修改的文件:\n{listing}\n\n"
            "编译错误输出:\n```\n"
            f"{errors[:4000]}\n```\n\n"
            "要求: 修复所有编译错误，重新输出**本次修复涉及的文件** "
            "(不要输出与修复无关的文件)。"
            f"{behavior_hint}"
            f"{disk_hint}"
            f"{CodegenEngine._format_seed_hints(seed_baseline, files)}"
            f"{trunc_hint}"
        )

    # ---- Report --------------------------------------------------------

    def _write_report(self, result: CodegenResult, session: PipelineSession) -> Path:
        """Write the codegen markdown report next to the generated files."""
        out_dir = Path(result.output_dir)
        report = build_codegen_report(result, session)
        path = out_dir / "codegen-report.md"
        path.write_text(report, encoding="utf-8")
        return path


def _strip_c_comments(src: str) -> str:
    """Strip C/C++ comments (/* */ and //) from source, preserving strings.

    2026-08-18 r21o (claude-review): forbidden_features 反模式检查必须只看
    代码不看注释 — codegen 常把 spec/PRD 的禁止措辞复述进注释 (如
    "禁止改用 (int64_t)"), 注释不是反模式本身。朴素 re.sub 会误删
    "http://" 之类字符串, 这里用状态机: 字符串字面量内不剥, 注释剥掉。
    """
    out: list[str] = []
    i = 0
    n = len(src)
    state = "code"  # code | line_comment | block_comment | string | char
    while i < n:
        c = src[i]
        if state == "code":
            if c == "/" and i + 1 < n and src[i + 1] == "/":
                state = "line_comment"
                i += 2
                continue
            if c == "/" and i + 1 < n and src[i + 1] == "*":
                state = "block_comment"
                i += 2
                continue
            if c == '"':
                state = "string"
                out.append(c)
                i += 1
                continue
            if c == "'":
                state = "char"
                out.append(c)
                i += 1
                continue
            out.append(c)
            i += 1
        elif state == "line_comment":
            if c == "\n":
                state = "code"
                out.append("\n")
            i += 1
        elif state == "block_comment":
            if c == "*" and i + 1 < n and src[i + 1] == "/":
                state = "code"
                i += 2
                continue
            i += 1
        elif state == "string":
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if c == '"':
                state = "code"
            i += 1
        elif state == "char":
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if c == "'":
                state = "code"
            i += 1
    return "".join(out)


def build_codegen_report(result: CodegenResult, session: PipelineSession) -> str:
    """Render the codegen report markdown (file list / verify / rounds)."""
    status_icon = {
        "verified": "✅", "generated": "⚠️", "failed": "❌",
        "no-files": "❌", "pending": "⏳",
    }.get(result.status, "❓")
    lines = [
        f"# Code Generation Report: {session.name}",
        "",
        f"> Source spec: {session.spec_path}",
        f"> Status: {status_icon} {result.status}",
        f"> Rounds: {result.rounds} (max retries: {result.max_retries})",
        f"> Started: {result.started_at}",
        f"> Finished: {result.finished_at or '—'}",
        "",
        "## Generated Files",
        "",
    ]
    if result.files:
        lines += [f"- `{f}`" for f in result.files]
    else:
        lines.append("_(no files generated)_")
    lines += ["", "## Verification", ""]
    verify = result.verify or {}
    if verify:
        ok = "✅ PASS" if verify.get("ok") else "❌ FAIL"
        # 2026-08-18 (r21j): status != verified 时 verify 是终验对最终
        # 磁盘产物的结果; verified 时是循环内通过轮的结果 (产物未再变)。
        final_note = (
            "" if result.status == "verified"
            else " *(最终产物终验 — 对应磁盘上实际产物, 非中间迭代)*"
        )
        lines += [
            f"- Result: {ok}{final_note}",
            f"- Language: {verify.get('language', 'unknown')}",
            f"- Command: `{verify.get('command', '')}`",
            f"- Return code: {verify.get('returncode', '?')}",
            "",
            "```",
            (verify.get("output") or "(no output)")[:2000],
            "```",
        ]
    else:
        lines.append("_(verification not run)_")

    # 行为验证结果 (2026-08-17, claude-review blocker 1): 编译通过后
    # behavior_verify 把生成代码部署到项目 → 跑真实测试套件 → 回滚。
    # 报告必须呈现它 — 否则评审只看到 -fsyntax-only 误判"护栏从未执行"。
    lines += ["", "## Behavior Verification (真实测试套件)", ""]
    if result.behavior_verify_result:
        lines.append(f"- Result: {result.behavior_verify_result}")
    else:
        lines.append("_(behavior verification not run)_")

    lines += ["", "## Repair Rounds", ""]
    if result.last_errors:
        lines += [
            f"- Attempts: {result.rounds}",
            f"- Last errors ({len(result.last_errors)} chars, 全量失败清单):",
            "",
            "```",
            result.last_errors[:8000],
            "```",
        ]
    else:
        lines.append(f"- Attempts: {result.rounds} — compiled clean.")
    if result.dropped_files:
        lines += [
            "",
            "## Out-of-Scope Files Dropped (白名单过滤)",
            "",
            "以下文件被引擎丢弃 (不属于错误涉及的修复范围):",
            "",
        ]
        lines += [f"- `{f}`" for f in sorted(result.dropped_files)]
    if result.brainstorm:
        b = result.brainstorm
        lines += [
            "",
            "## 🧠 头脑风暴触发 (3 次失败)",
            "",
            f"- Rounds failed: {b.get('rounds')}",
            f"- Same error repeated: {b.get('same_error')}",
            f"- Worsening: {b.get('worsening')}",
            f"- Behavior failures: {b.get('behavior_count')}",
            f"- Strategy: {b.get('strategy')}",
            f"- Reason: {b.get('reason')}",
        ]
    lines.append("")
    return "\n".join(lines)
