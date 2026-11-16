#!/usr/bin/env python3

# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""AST 级追溯校验（AUD-ASPICE-001 NC-07）。

注释里的 ``@req SWR-001`` 只是**声明**，不等于实现。本模块解析 C 源码中的
函数定义与注解，并用需求文本做实质比对：

- 注解了某需求、但函数体与函数名都不含该需求任何实质词元 → ``TRACE-UNSUBSTANTIATED``
  （与 RUN-A 中"函数打假标签即可称已实现"是同一类缺陷）；
- 注解的需求 ID 在 spec 中不存在 → ``TRACE-UNKNOWN-REQ``；
- 同时提供 ``impact``：给定需求 ID，列出受影响的函数 / 文件 / 测试，
  供变更影响分析（SUP.10 / D-03）使用。

局限：这是词汇级实质比对，不是语义证明。它只用于**抓住明显造假**，
不用于替评审下"已实现"结论。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("evidence.ast_trace")

ANNOTATION_RE = re.compile(
    r"@(?:req|trace_req|implements)\s+([A-Z][A-Z0-9]*(?:[-_.][A-Z0-9]+)*)"
)
_FUNC_DEF_RE = re.compile(
    r"^[A-Za-z_][\w\s\*]*?\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{", re.MULTILINE
)
_SOURCE_EXTS = (".c", ".cpp", ".cc")
_SKIP_DIRS = {"artifacts", "build", "cmake-build-coverage", "third_party",
              ".git", ".osh", "tests", "node_modules", "docs"}
_CJK_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_STOPWORDS = {
    "the", "and", "for", "with", "via", "all", "any", "are", "not", "but",
    "shall", "should", "may", "must", "can", "system", "this", "that", "from",
    "into", "its", "their", "when", "then", "than", "have", "has", "was",
    "were", "will", "each", "per", "use", "used", "using", "set",
}


@dataclass
class FunctionTrace:
    file: str
    name: str
    line: int
    requirements: list[str] = field(default_factory=list)
    body: str = ""

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "function": self.name,
            "line": self.line,
            "requirements": list(self.requirements),
        }


def _iter_sources(project_dir):
    root = Path(project_dir)
    for path in root.rglob("*"):
        if path.suffix not in _SOURCE_EXTS or not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        yield path, str(rel).replace("\\", "/")


def _brace_body(text: str, start: int) -> str:
    depth = 0
    for idx in range(start, len(text)):
        if text[idx] == "{":
            depth += 1
        elif text[idx] == "}":
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]
    return text[start:]


def scan_source(text: str, rel_path: str) -> list[FunctionTrace]:
    """从单个 C 文件提取「函数 + 紧邻其上的 @req 注解」。"""
    traces: list[FunctionTrace] = []
    pending: list[str] = []
    for match in _FUNC_DEF_RE.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        # 注解可以在签名同一行，也可以在紧邻的注释块中（向上回溯 8 行）
        head = text[max(0, line_start - 600):match.start()]
        pending = [m.upper() for m in ANNOTATION_RE.findall(head)]
        if not pending:
            continue
        name = match.group(1)
        if name in {"if", "for", "while", "switch", "return", "sizeof"}:
            continue
        traces.append(FunctionTrace(
            file=rel_path,
            name=name,
            line=text.count("\n", 0, match.start()) + 1,
            requirements=pending,
            body=_brace_body(text, match.end() - 1),
        ))
        pending = []
    return traces


def scan_project(project_dir) -> list[FunctionTrace]:
    traces: list[FunctionTrace] = []
    for path, rel in _iter_sources(project_dir):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        traces.extend(scan_source(text, rel))
    return traces


def requirement_texts(spec_path) -> dict[str, str]:
    """spec 中 {需求ID: 需求文本}（标题 + SHALL/SHOULD/MAY 语句）。

    除解析器的结构化字段外，还合并小节原文 —— 有些 spec 把 SHALL 写成
    普通段落而非列表项，只靠 ``req.shall`` 会得到空文本，导致实质比对
    退化成"无法判断"。
    """
    if not spec_path or not Path(spec_path).is_file():
        return {}
    try:
        raw_text = Path(spec_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    raw_sections = _raw_sections(raw_text)
    try:
        from yuleosh.spec.validate import parse_spec

        doc = parse_spec(str(spec_path))
    except Exception:  # noqa: BLE001 — 解析失败退回原文
        return raw_sections
    out: dict[str, str] = {}
    for req in doc.requirements:
        rid = (req.req_id or "").strip().upper()
        if not rid:
            continue
        text = " ".join([req.name or ""] + list(req.shall or [])
                        + list(req.should or []) + list(req.may or []))
        raw = raw_sections.get(rid, "")
        if raw:
            text = f"{text} {raw}".strip()
        out[rid] = text
    for rid, raw in raw_sections.items():
        out.setdefault(rid, raw)
    return out


def _raw_sections(spec_text: str) -> dict[str, str]:
    """按 ``### SR-001`` 小节切分原文（用于补齐解析器未取到的语句）。"""
    out: dict[str, list[str]] = {}
    current: str | None = None
    for line in spec_text.splitlines():
        heading = re.match(r"^#{2,4}\s+([A-Za-z][\w-]*-\d[\w.]*)\b", line)
        if heading:
            current = heading.group(1).upper()
            out.setdefault(current, [])
            remainder = line[heading.end():].strip(" :-")
            if remainder:
                out[current].append(remainder)
            continue
        if re.match(r"^#{1,6}\s+", line):
            current = None
            continue
        if current:
            out[current].append(line)
    return {k: " ".join(v).strip() for k, v in out.items()}


def _tokens(text: str) -> set[str]:
    """实质词元：标识符按 ``_`` 拆词 + 中文二元组，去掉停用词。"""
    words: set[str] = set()
    for ident in _IDENT_RE.findall(text or ""):
        for part in ident.split("_"):
            low = part.lower()
            if len(low) >= 3 and low not in _STOPWORDS:
                words.add(low)
    for chunk in _CJK_RE.findall(text or ""):
        words.update(chunk[i:i + 2] for i in range(len(chunk) - 1))
    return words


def validate(project_dir, spec_path=None) -> dict:
    """扫描并校验注解追溯的实质性。

    Returns
    -------
    dict
        ``{"status": passed|failed|not-run, "annotated", "findings", ...}``
    """
    traces = scan_project(project_dir)
    annotated = [t for t in traces if t.requirements]
    if not annotated:
        return {
            "status": "not-run",
            "functions": len(traces),
            "annotated": 0,
            "findings": [],
            "reason": "no @req annotations found in project sources",
        }

    texts = requirement_texts(spec_path)
    findings: list[dict] = []
    for trace in annotated:
        body_tokens = _tokens(trace.name) | _tokens(trace.body)
        for rid in trace.requirements:
            req_text = texts.get(rid)
            if req_text is None:
                findings.append({
                    "rule": "TRACE-UNKNOWN-REQ",
                    "severity": "major",
                    "file": trace.file,
                    "function": trace.name,
                    "requirement": rid,
                    "reason": "annotated requirement not found in spec",
                })
                continue
            req_tokens = _tokens(req_text)
            if not (body_tokens & req_tokens):
                findings.append({
                    "rule": "TRACE-UNSUBSTANTIATED",
                    "severity": "major",
                    "file": trace.file,
                    "function": trace.name,
                    "requirement": rid,
                    "reason": "function body/name shares no term with the requirement",
                })

    return {
        "status": "failed" if findings else "passed",
        "functions": len(traces),
        "annotated": len(annotated),
        "findings": findings,
    }


def impact(requirement_id: str, project_dir, spec_path=None) -> dict:
    """变更影响分析：某需求被哪些函数 / 文件 / 测试引用。"""
    rid = str(requirement_id).strip().upper()
    functions: list[dict] = []
    for trace in scan_project(project_dir):
        if rid in trace.requirements:
            functions.append(trace.to_dict())

    tests: list[str] = []
    root = Path(project_dir)
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in (".py", ".c", ".cpp", ".h"):
            continue
        rel = path.relative_to(root)
        if "tests" not in rel.parts and not rel.name.startswith("test_"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(rid)}(?![A-Za-z0-9])", text):
            tests.append(str(rel).replace("\\", "/"))

    return {
        "requirement": rid,
        "functions": functions,
        "files": sorted({f["file"] for f in functions}),
        "tests": sorted(set(tests)),
        "known_in_spec": rid in requirement_texts(spec_path),
    }
