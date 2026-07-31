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
    ):
        self.output_dir = Path(output_dir) if output_dir else None
        self.max_retries = max(0, int(max_retries))
        self.llm_client = llm_client
        self.verifier = verifier or compilers.compile_verify
        self.max_tokens = max_tokens

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
        """
        result = CodegenResult(max_retries=self.max_retries)
        out_dir = self.output_dir or default_output_dir(
            session.project_dir, session.name
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        result.output_dir = str(out_dir)

        repair_context = ""
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

            verify = self.verifier(written, language=language_hint, build_cmd=build_cmd)
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
            if round_idx < self.max_retries:
                repair_context = self._format_repair_context(result.last_errors, files)

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

    @staticmethod
    def _format_repair_context(errors: str, files: list[GeneratedFile]) -> str:
        """Build the compiler-feedback block appended to the next prompt."""
        listing = "\n".join(f"  - {f.path}" for f in files) or "  - (none)"
        return (
            "\n\n## 🔧 编译验证失败 — 请修复后重新输出全部文件\n"
            f"上一轮生成的文件:\n{listing}\n\n"
            "编译错误输出:\n```\n"
            f"{errors[:4000]}\n```\n\n"
            "要求: 修复所有编译错误，重新以相同格式输出 **全部** 文件 "
            "(不要省略未出错的文件)。"
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
