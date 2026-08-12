#!/usr/bin/env python3
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
    ):
        self.output_dir = Path(output_dir) if output_dir else None
        self.max_retries = max(0, int(max_retries))
        self.llm_client = llm_client
        self.verifier = verifier or compilers.compile_verify
        self.max_tokens = max_tokens
        # 方案 C seed 增量 (2026-08-12): 项目现有代码基线目录。
        # 提供时 engine 把 src/** 复制到输出目录, LLM 只增量修改。
        self.seed_dir = Path(seed_dir) if seed_dir else None

    # ---- Main entry ---------------------------------------------------

    def generate(
        self,
        session: PipelineSession,
        system_prompt: str,
        user_prompt: str,
        language_hint: Optional[str] = None,
        build_cmd: Optional[list[str]] = None,
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

        repair_context = ""
        best_state: dict[str, str] = {}   # rel_path -> content (错误数最少版本)
        best_error_count: Optional[int] = None
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

            written = self.write_files(files, out_dir)
            result.files = [str(p) for p in written]

            # verify 整个输出目录 (seed 副本 + 本轮修改) — 跨文件引用可被捕获
            verify_files = self._collect_code_files(out_dir)
            # 2026-08-12: 默认 verifier 透传项目根 → 生成的 app 代码可
            # 编译验证宿主项目 HAL API (src/hal/include 等)。自定义
            # verifier 不接收 project_root, 保持旧调用。
            if self.verifier is compilers.compile_verify:
                verify = self.verifier(
                    verify_files, language=language_hint, build_cmd=build_cmd,
                    project_root=getattr(session, "project_dir", None),
                )
            else:
                verify = self.verifier(
                    verify_files, language=language_hint, build_cmd=build_cmd,
                )
            result.verify = verify
            if verify.get("ok"):
                result.status = "verified"
                result.last_errors = ""
                break

            errors = (verify.get("errors") or "").strip()
            result.last_errors = errors or f"verification failed ({verify.get('command')})"
            log.warning(
                "Codegen round %d failed verification: %s",
                round_idx + 1, result.last_errors[:300],
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

            if round_idx < self.max_retries:
                repair_context = self._format_repair_context(
                    result.last_errors, files, best_state,
                )

        result.finished_at = datetime.now().isoformat()
        if result.status == "pending":
            result.status = "failed"

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
        try:
            response = client(system_prompt, prompt, max_tokens=self.max_tokens)
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
        """All ``.c`` / ``.h`` / ``.py`` files under the output dir."""
        exts = {".c", ".h", ".py"}
        return [p for p in sorted(out_dir.rglob("*"))
                if p.is_file() and p.suffix.lower() in exts]

    @staticmethod
    def _error_count(errors: str) -> int:
        """Count compiler error lines (``error:`` / ``Error``) in output."""
        if not errors:
            return 0
        return len(re.findall(r"(?m)^.*\berror\b.*$", errors))

    def _snapshot_files(self, out_dir: Path) -> dict[str, str]:
        """Snapshot the current output dir (rel_path -> content)."""
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
    def _format_repair_context(
        errors: str,
        files: list[GeneratedFile],
        best_state: Optional[dict[str, str]] = None,
    ) -> str:
        """Build the compiler-feedback block appended to the next prompt.

        best_state (方案 C): 当前磁盘上错误数最少的版本的文件清单。
        提示模型只输出需要修复的文件 — 未修改文件保留磁盘现状,
        避免全量重发引入新错误。
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
        return (
            "\n\n## 🔧 编译验证失败 — 请修复后重新输出文件\n"
            f"上一轮生成/修改的文件:\n{listing}\n\n"
            "编译错误输出:\n```\n"
            f"{errors[:4000]}\n```\n\n"
            "要求: 修复所有编译错误，重新输出**本次修复涉及的文件** "
            "(不要输出与修复无关的文件)。"
            f"{disk_hint}"
        )

    # ---- Report --------------------------------------------------------

    def _write_report(self, result: CodegenResult, session: PipelineSession) -> Path:
        """Write the codegen markdown report next to the generated files."""
        out_dir = Path(result.output_dir)
        report = build_codegen_report(result, session)
        path = out_dir / "codegen-report.md"
        path.write_text(report, encoding="utf-8")
        return path


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
        lines += [
            f"- Result: {ok}",
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
    lines += ["", "## Repair Rounds", ""]
    if result.last_errors:
        lines += [
            f"- Attempts: {result.rounds}",
            f"- Last errors:",
            "",
            "```",
            result.last_errors[:2000],
            "```",
        ]
    else:
        lines.append(f"- Attempts: {result.rounds} — compiled clean.")
    lines.append("")
    return "\n".join(lines)
