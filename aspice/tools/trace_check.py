#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ASPICE 4.0 CL2 需求追踪表机械校验工具（单文件，仅依赖 openpyxl）。

校验对象为《亚远景_ENG_TP_需求追踪表_V1.0.xlsx》的 9 张清单
（涉众需求 → 网络安全需求 → 系统需求 → 系统架构元素 → 硬件需求 →
硬件设计元素 → 软件需求 → 软件架构元素 → 软件详设），可选叠加
《亚远景_ENG_TP_测试规范_V1.0.xlsx》的「2.测试用例」页校验用例引用。

用法示例：
    python3 trace_check.py --trace 需求追踪表.xlsx
    python3 trace_check.py --trace 需求追踪表.xlsx --cases 测试规范.xlsx \\
        --out reports/trace_report.md --json --strict
    python3 trace_check.py --selftest

退出码：0 通过；1 存在 ERROR（--strict 时 WARN 也失败）；2 输入/读取错误。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:
    import openpyxl
except ImportError:  # pragma: no cover - 环境已安装 openpyxl
    print("[ERROR] 缺少依赖 openpyxl，请先执行: python3 -m pip install openpyxl",
          file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# 常量与默认路径
# ---------------------------------------------------------------------------

SCRIPT_PATH = Path(__file__).resolve()
TOOLS_DIR = SCRIPT_PATH.parent
ASPICE_DIR = TOOLS_DIR.parent

DEFAULT_TRACE = (
    ASPICE_DIR
    / "_source_templates"
    / "工程域模版"
    / "ASPICE 4.0 -工程V左"
    / "亚远景_ENG_TP_需求追踪表_V1.0.xlsx"
)
DEFAULT_CASES = (
    ASPICE_DIR
    / "_source_templates"
    / "工程域模版"
    / "ASPICE 4.0 -工程V右"
    / "亚远景_ENG_TP_测试规范_V1.0.xlsx"
)

DEFAULT_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_.\-]{2,}$"
# 推荐用例ID形态：<需求ID>-TC-01
CASE_SUFFIX_PATTERN = r"-TC-\d{2}"
GENERIC_CASE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-]*?-TC-\d{2}$")

# 下游元素 / 上游元素的多值分隔符：英文/中文逗号、分号、斜杠、顿号、换行
SPLIT_RE = re.compile(r"[,;，；/、\r\n]+")

# 语义占位符：不视为“有下游引用”，也不报断链
PLACEHOLDERS = {
    "", "-", "—", "–", "…", "...", "/",
    "na", "n/a", "none", "null", "tbd", "待定", "无", "暂无", "不适用",
}

TAIL_SHEET_KEYWORDS = ("详设", "详细设计", "测试用例")

HEADER_SCAN_ROWS = 20

ID_KEYWORDS = ("id", "标识", "编号", "编码", "identifier")
DOWNSTREAM_KEYWORDS = ("下游", "downstream")
TESTCASE_KEYWORDS = ("测试用例", "testcase", "test case")
UPSTREAM_KEYWORDS = ("上游", "upstream")
SOURCE_KEYWORDS = ("来源", "source")
TITLE_KEYWORDS = ("标题", "title")
GENERIC_HEADER_KEYWORDS = (
    "需求", "描述", "description", "类型", "type", "状态", "status",
    "备注", "remark",
)
HEADER_KEYWORDS = (
    ID_KEYWORDS + DOWNSTREAM_KEYWORDS + TESTCASE_KEYWORDS + UPSTREAM_KEYWORDS
    + SOURCE_KEYWORDS + TITLE_KEYWORDS + GENERIC_HEADER_KEYWORDS
)

SEVERITY_ORDER = {"ERROR": 0, "WARN": 1, "INFO": 2}


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    severity: str
    sheet: str
    row: int | None
    cell: str
    ident: str
    message: str
    suggestion: str


@dataclass
class Record:
    sheet: str
    sheet_index: int
    row: int
    ident: str
    refs_raw: str
    refs: list[str]
    testcase_raw: str
    upstream_raw: str
    source_raw: str


@dataclass
class SheetInfo:
    title: str
    index: int
    header_row: int | None = None
    id_col: int | None = None
    id_header: str = ""
    downstream_col: int | None = None
    downstream_header: str = ""
    testcase_col: int | None = None
    testcase_header: str = ""
    upstream_col: int | None = None
    upstream_header: str = ""
    source_col: int | None = None
    source_header: str = ""
    status: str = "analyzed"          # analyzed / skipped_no_header / skipped_no_id
    data_rows: int = 0                # 表头之后的非空行
    valid_rows: int = 0               # ID 非空行
    rows_with_downstream: int = 0
    coverage: float | None = None
    ids: list[str] = field(default_factory=list)


@dataclass
class CaseSheetInfo:
    path: str
    sheet: str
    header_row: int | None
    id_col: int | None
    total_rows: int
    ids: list[str]
    warning: str = ""


@dataclass
class Analysis:
    trace_file: str
    cases_file: str | None
    strict: bool
    id_pattern: str
    sheets: list[SheetInfo]
    issues: list[Issue]
    records: list[Record]
    global_ids: dict[str, list[tuple[str, int]]]
    broken_links: int
    total_downstream_refs: int
    orphans: int
    invalid_ids: int
    duplicate_groups: int
    cross_sheet_duplicates: int
    testcase_nonempty_cells: int
    testcase_noncompliant_cells: int
    testcase_samples: list[str]
    unresolved_case_refs: int
    unresolved_case_samples: list[str]
    case_info: CaseSheetInfo | None
    bidirectional: bool = False

    # 派生统计 -----------------------------------------------------------
    def counts(self) -> dict[str, int]:
        c = {"ERROR": 0, "WARN": 0, "INFO": 0}
        for issue in self.issues:
            c[issue.severity] = c.get(issue.severity, 0) + 1
        return c

    def totals(self) -> dict[str, int]:
        valid = sum(s.valid_rows for s in self.sheets)
        refs = sum(s.rows_with_downstream for s in self.sheets)
        return {
            "sheets": len(self.sheets),
            "analyzed_sheets": sum(1 for s in self.sheets if s.status == "analyzed"),
            "skipped_sheets": sum(1 for s in self.sheets if s.status != "analyzed"),
            "data_rows": sum(s.data_rows for s in self.sheets),
            "valid_rows": valid,
            "rows_with_downstream": refs,
        }

    def passed(self) -> bool:
        c = self.counts()
        if c["ERROR"] > 0:
            return False
        if self.strict and c["WARN"] > 0:
            return False
        return True

    def referenced_case_ids(self) -> set[str]:
        """追踪表“测试用例”单元格中符合 `<ID>-TC-两位序号` 形态的用例 ID 集合。"""
        tokens: set[str] = set()
        for rec in self.records:
            if rec.ident and rec.testcase_raw:
                for token in split_refs(rec.testcase_raw):
                    if GENERIC_CASE_PATTERN.match(token):
                        tokens.add(token)
        return tokens


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def norm_text(value: Any) -> str:
    """表头归一化：去所有空白（含换行）、小写，用于关键词模糊匹配。"""
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value)).lower()


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, _dt.datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, _dt.date):
        return value.isoformat()
    return str(value).strip()


def split_refs(value: Any) -> list[str]:
    text = as_text(value)
    if not text:
        return []
    parts = SPLIT_RE.split(text)
    out: list[str] = []
    for part in parts:
        token = part.strip().strip("\"'“”‘’")
        if token:
            out.append(token)
    return out


def is_placeholder(token: str) -> bool:
    return token.strip().lower() in PLACEHOLDERS


def col_letter(col: int | None) -> str:
    if not col:
        return ""
    return openpyxl.utils.get_column_letter(col)


def make_issue(severity: str, sheet: str, row: int | None, col: int | None,
               ident: str, message: str, suggestion: str = "") -> Issue:
    return Issue(
        severity=severity,
        sheet=sheet,
        row=row,
        cell=col_letter(col),
        ident=ident,
        message=message,
        suggestion=suggestion,
    )


def header_has(normalized: str, keywords: Iterable[str]) -> bool:
    return any(kw in normalized for kw in keywords)


def detect_header_row(ws) -> int | None:
    """在前 20 行中找最可能的表头行：命中关键词的单元格数最多。"""
    best_score = 0
    best_nonempty = 0
    best_row: int | None = None
    max_row = min(ws.max_row or 0, HEADER_SCAN_ROWS)
    max_col = ws.max_column or 0
    for row in range(1, max_row + 1):
        score = 0
        nonempty = 0
        for col in range(1, max_col + 1):
            value = ws.cell(row=row, column=col).value
            if value is None or not str(value).strip():
                continue
            nonempty += 1
            if header_has(norm_text(value), HEADER_KEYWORDS):
                score += 1
        if score >= 2 and nonempty >= 2 and (score, nonempty) > (best_score, best_nonempty):
            best_score, best_nonempty, best_row = score, nonempty, row
    return best_row


def find_column(ws, header_row: int, predicate, max_col: int,
                exclude_any: tuple[str, ...] = ()) -> int | None:
    for col in range(1, max_col + 1):
        normalized = norm_text(ws.cell(row=header_row, column=col).value)
        if not normalized:
            continue
        if header_has(normalized, exclude_any):
            continue
        if predicate(normalized):
            return col
    return None


def is_id_header(normalized: str) -> bool:
    if header_has(normalized, UPSTREAM_KEYWORDS + SOURCE_KEYWORDS
                  + DOWNSTREAM_KEYWORDS + TESTCASE_KEYWORDS):
        return False
    return header_has(normalized, ID_KEYWORDS)


def is_downstream_header(normalized: str) -> bool:
    return header_has(normalized, DOWNSTREAM_KEYWORDS)


def is_testcase_header(normalized: str) -> bool:
    return header_has(normalized, TESTCASE_KEYWORDS) or "动态测试" in normalized


def is_upstream_header(normalized: str) -> bool:
    return header_has(normalized, UPSTREAM_KEYWORDS)


def is_source_header(normalized: str) -> bool:
    return header_has(normalized, SOURCE_KEYWORDS)


def row_is_blank(ws, row: int, max_col: int) -> bool:
    for col in range(1, max_col + 1):
        value = ws.cell(row=row, column=col).value
        if value is not None and str(value).strip():
            return False
    return True


def load_workbook(path: Path):
    return openpyxl.load_workbook(path, data_only=True)


# ---------------------------------------------------------------------------
# 列映射与数据抽取
# ---------------------------------------------------------------------------

def build_sheet_info(ws, index: int) -> tuple[SheetInfo, list[Record]]:
    info = SheetInfo(title=ws.title, index=index)
    records: list[Record] = []

    header_row = detect_header_row(ws)
    info.header_row = header_row
    if header_row is None:
        info.status = "skipped_no_header"
        return info, records

    max_col = ws.max_column or 0
    info.id_col = find_column(ws, header_row, is_id_header, max_col)
    if info.id_col is None:
        info.status = "skipped_no_id"
        # 仍记录其它列映射，便于报告解释为何跳过
        info.downstream_col = find_column(ws, header_row, is_downstream_header, max_col)
        info.testcase_col = find_column(ws, header_row, is_testcase_header, max_col)
        info.upstream_col = find_column(ws, header_row, is_upstream_header, max_col)
        info.source_col = find_column(ws, header_row, is_source_header, max_col,
                                      exclude_any=DOWNSTREAM_KEYWORDS)
        for header, attr in (
            (info.downstream_col, "downstream_header"),
            (info.testcase_col, "testcase_header"),
            (info.upstream_col, "upstream_header"),
            (info.source_col, "source_header"),
        ):
            if header:
                setattr(info, attr, as_text(ws.cell(row=header_row, column=header).value))
        info.id_header = ""
        return info, records

    info.id_header = as_text(ws.cell(row=header_row, column=info.id_col).value)
    info.downstream_col = find_column(ws, header_row, is_downstream_header, max_col)
    info.testcase_col = find_column(ws, header_row, is_testcase_header, max_col)
    info.upstream_col = find_column(ws, header_row, is_upstream_header, max_col)
    info.source_col = find_column(
        ws, header_row, is_source_header, max_col,
        exclude_any=DOWNSTREAM_KEYWORDS + TESTCASE_KEYWORDS + UPSTREAM_KEYWORDS,
    )

    for header, attr in (
        (info.downstream_col, "downstream_header"),
        (info.testcase_col, "testcase_header"),
        (info.upstream_col, "upstream_header"),
        (info.source_col, "source_header"),
    ):
        if header:
            setattr(info, attr, as_text(ws.cell(row=header_row, column=header).value))

    for row in range(header_row + 1, (ws.max_row or 0) + 1):
        if row_is_blank(ws, row, max_col):
            continue
        info.data_rows += 1
        ident = as_text(ws.cell(row=row, column=info.id_col).value) if info.id_col else ""
        refs_raw = as_text(ws.cell(row=row, column=info.downstream_col).value) \
            if info.downstream_col else ""
        testcase_raw = as_text(ws.cell(row=row, column=info.testcase_col).value) \
            if info.testcase_col else ""
        upstream_raw = as_text(ws.cell(row=row, column=info.upstream_col).value) \
            if info.upstream_col else ""
        source_raw = as_text(ws.cell(row=row, column=info.source_col).value) \
            if info.source_col else ""

        refs = split_refs(refs_raw)
        meaningful_refs = [r for r in refs if not is_placeholder(r)]

        if ident:
            info.valid_rows += 1
            info.ids.append(ident)
            if meaningful_refs:
                info.rows_with_downstream += 1

        records.append(Record(
            sheet=ws.title,
            sheet_index=index,
            row=row,
            ident=ident,
            refs_raw=refs_raw,
            refs=meaningful_refs,
            testcase_raw=testcase_raw,
            upstream_raw=upstream_raw,
            source_raw=source_raw,
        ))

    info.coverage = (info.rows_with_downstream / info.valid_rows) if info.valid_rows else None
    return info, records


# ---------------------------------------------------------------------------
# 测试用例表读取
# ---------------------------------------------------------------------------

CASE_ID_KEYWORDS = ("测试用例id", "用例id", "testcaseid", "caseid")


def find_case_header(ws) -> tuple[int | None, int | None]:
    max_row = min(ws.max_row or 0, HEADER_SCAN_ROWS)
    max_col = ws.max_column or 0
    for row in range(1, max_row + 1):
        for col in range(1, max_col + 1):
            normalized = norm_text(ws.cell(row=row, column=col).value)
            if normalized and header_has(normalized, CASE_ID_KEYWORDS):
                return row, col
    return None, None


def load_cases(path: Path) -> CaseSheetInfo:
    wb = load_workbook(path)
    sheet = None
    if "2.测试用例" in wb.sheetnames:
        sheet = wb["2.测试用例"]
    else:
        for name in wb.sheetnames:
            if "测试用例" in name and "选择" not in name:
                sheet = wb[name]
                break
    if sheet is None:
        return CaseSheetInfo(str(path), "", None, None, 0, [],
                             "未找到「2.测试用例」页（或名称含“测试用例”的页）")

    header_row, id_col = find_case_header(sheet)
    if header_row is None or id_col is None:
        return CaseSheetInfo(str(path), sheet.title, None, None, 0, [],
                             f"「{sheet.title}」页未识别到“测试用例ID”列")

    ids: list[str] = []
    max_col = sheet.max_column or 0
    for row in range(header_row + 1, (sheet.max_row or 0) + 1):
        if row_is_blank(sheet, row, max_col):
            continue
        ident = as_text(sheet.cell(row=row, column=id_col).value)
        if ident:
            ids.append(ident)
    return CaseSheetInfo(str(path), sheet.title, header_row, id_col,
                         len(ids), ids)


# ---------------------------------------------------------------------------
# 核心分析
# ---------------------------------------------------------------------------

def analyze(trace_path: Path, cases_path: Path | None = None,
            id_pattern: str = DEFAULT_ID_PATTERN, strict: bool = False,
            bidirectional: bool = False) -> Analysis:
    wb = load_workbook(trace_path)
    issues: list[Issue] = []
    sheet_infos: list[SheetInfo] = []
    records: list[Record] = []

    for index, ws in enumerate(wb.worksheets):
        if ws.sheet_state != "visible":
            continue
        info, recs = build_sheet_info(ws, index)
        sheet_infos.append(info)
        records.extend(recs)

        if info.status == "skipped_no_header":
            issues.append(make_issue(
                "WARN", ws.title, None, None, "",
                "未识别到表头行（前 20 行缺少 ID/下游/测试用例等关键词），该清单已跳过",
                "确认表头是否位于前 20 行，或手工检查列名是否含“ID/标识/下游元素”等关键词",
            ))
        elif info.status == "skipped_no_id":
            issues.append(make_issue(
                "WARN", ws.title, info.header_row, None, "",
                "未识别到 ID 列（表头无 ID/标识/编号关键词），该清单无法建立索引，已跳过",
                "补充明确的标识列（如“XXX标识 / XXX ID”），否则无法机械校验追溯",
            ))
        elif info.downstream_col is None:
            issues.append(make_issue(
                "WARN", ws.title, info.header_row, None, "",
                "未识别到“下游元素 / Downstream Element”列，无法校验其出边（按链尾处理）",
                "若非链尾清单，请补充“下游元素”列并填写下游 ID",
            ))

    # 表头缺失 / ID 缺失的清单无法继续；其余参与校验 ---------------------
    analyzed_sheets = [s for s in sheet_infos if s.status == "analyzed"]
    valid_records = [r for r in records if r.ident]

    # 全库 ID 索引 -------------------------------------------------------
    global_ids: dict[str, list[tuple[str, int]]] = {}
    for rec in valid_records:
        global_ids.setdefault(rec.ident, []).append((rec.sheet, rec.row))

    # 规则1a：清单内重复 ID ---------------------------------------------
    duplicate_groups = 0
    for info in analyzed_sheets:
        groups: dict[str, list[Record]] = {}
        for rec in valid_records:
            if rec.sheet == info.title:
                groups.setdefault(rec.ident, []).append(rec)
        for ident, group in groups.items():
            if len(group) > 1:
                duplicate_groups += 1
                rows = [r.row for r in group]
                issues.append(make_issue(
                    "ERROR", info.title, group[1].row, info.id_col, ident,
                    f"清单内 ID 重复，共出现 {len(group)} 次（行 {', '.join(map(str, rows))}）",
                    "为每个条目分配唯一 ID；重复行需合并或改号",
                ))

    # 规则1b：清单内空 ID（聚合为一条，避免刷屏） ------------------------
    for info in analyzed_sheets:
        empty_rows = [
            r.row for r in records
            if r.sheet == info.title and not r.ident
        ]
        if empty_rows:
            sample = ", ".join(map(str, empty_rows[:5]))
            more = "" if len(empty_rows) <= 5 else f" 等 {len(empty_rows)} 行"
            issues.append(make_issue(
                "WARN", info.title, empty_rows[0], info.id_col, "",
                f"存在 {len(empty_rows)} 行 ID 为空但整行并非全空（行 {sample}{more}）",
                "补全 ID；若为下拉示例/占位残留，请清空数据行或移入模板说明页",
            ))

    # 规则1c：跨清单重复 ID ---------------------------------------------
    cross_sheet_duplicates = 0
    for ident, locations in global_ids.items():
        sheets = {s for s, _ in locations}
        if len(sheets) > 1:
            cross_sheet_duplicates += 1
            first_sheet, first_row = locations[0]
            issues.append(make_issue(
                "WARN", first_sheet, first_row, None, ident,
                f"同一 ID 出现在多张清单：{'、'.join(sorted(sheets))}（通常为误用或编号域未隔离）",
                "按清单设置 ID 前缀/编号空间，确保一个 ID 只属于一个层级",
            ))

    # 规则2：ID 命名规范（每个清单聚合一条） ------------------------------
    try:
        id_re = re.compile(id_pattern)
    except re.error as exc:
        raise ValueError(f"--id-pattern 不是合法正则: {exc}") from exc

    invalid_ids = 0
    for info in analyzed_sheets:
        bad = []
        for rec in valid_records:
            if rec.sheet == info.title and not id_re.match(rec.ident):
                bad.append(rec)
        if bad:
            invalid_ids += len(bad)
            samples = "、".join(f"行{r.row}:{r.ident}" for r in bad[:3])
            issues.append(make_issue(
                "WARN", info.title, bad[0].row, info.id_col, bad[0].ident,
                f"{len(bad)} 个 ID 不符合命名规范 {id_pattern}（样本：{samples}）",
                "统一为字母开头、仅含字母/数字/下划线/点/短横线、长度 ≥3 的 ID",
            ))

    # 规则3：下游引用可解析 -------------------------------------------------
    broken_links = 0
    total_downstream_refs = 0
    inbound_ids: set[str] = set()
    for rec in valid_records:
        for token in rec.refs:
            total_downstream_refs += 1
            if token in global_ids:
                inbound_ids.add(token)
            else:
                broken_links += 1
                issues.append(make_issue(
                    "ERROR", rec.sheet, rec.row, None, rec.ident,
                    f"下游引用无法解析：`{token}` 不在全库 ID 索引中（断链）",
                    "核对下游 ID 拼写/层级；若下游条目尚未建立，先建条目再引用",
                ))

    # 规则4a：孤儿/未被上游引用（叶子且入度为 0，非链尾） --------------------
    orphans = 0
    for info in analyzed_sheets:
        if info.downstream_col is None:
            continue
        is_tail = header_has(norm_text(info.title), TAIL_SHEET_KEYWORDS)
        if is_tail:
            continue
        per_sheet: list[Record] = []
        seen: set[str] = set()
        for rec in valid_records:
            if rec.sheet != info.title or rec.ident in seen:
                continue
            seen.add(rec.ident)
            if not rec.refs and rec.ident not in inbound_ids:
                per_sheet.append(rec)
        if per_sheet:
            orphans += len(per_sheet)
            samples = "、".join(r.ident for r in per_sheet[:3])
            issues.append(make_issue(
                "WARN", info.title, per_sheet[0].row, info.id_col, samples,
                f"{len(per_sheet)} 个叶子节点从未被任何下游引用（可能未被上游引用；样本：{samples}）",
                "在上一层的“下游元素”中补引用；若确为并行/独立条目，请在备注说明",
            ))

    # 规则4b：上游列/来源列与严格闭环 ---------------------------------------
    root_index = min((s.index for s in analyzed_sheets), default=None)
    for info in analyzed_sheets:
        if info.upstream_col is None:
            note = "当前仅有下游列，无法机械举证向上追溯"
            if info.source_col is not None:
                note = "仅识别到“来源 / Source”列（属来源说明，非上游需求 ID）"
            if info.index == root_index:
                note += "；该页为链首，可豁免强制上游，但建议明确来源"
            issues.append(make_issue(
                "INFO", info.title, info.header_row, None, "",
                "未识别到“上游元素 / Upstream Element”列，建议补列以支持严格双向闭环校验",
                f"新增“上游元素”列并与上一层 ID 对齐；{note}",
            ))

        # 上游引用：严格校验
        if info.upstream_col is not None:
            missing_upstream: list[Record] = []
            for rec in valid_records:
                if rec.sheet != info.title:
                    continue
                if not rec.upstream_raw:
                    if info.index != root_index:
                        missing_upstream.append(rec)
                    continue
                for token in split_refs(rec.upstream_raw):
                    if is_placeholder(token):
                        continue
                    if token not in global_ids:
                        issues.append(make_issue(
                            "ERROR", info.title, rec.row, info.upstream_col, rec.ident,
                            f"上游引用无法解析：`{token}` 不在全库 ID 索引中",
                            "核对上游 ID；或在上层清单补建该条目",
                        ))
            if missing_upstream:
                samples = "、".join(f"行{r.row}:{r.ident}" for r in missing_upstream[:3])
                issues.append(make_issue(
                    "WARN", info.title, missing_upstream[0].row, info.upstream_col, "",
                    f"{len(missing_upstream)} 行缺少上游引用（样本：{samples}）",
                    "为每个非链首条目填写至少一个上游 ID，形成双向闭合",
                ))

        # 来源列：仅对“看起来像 ID”的值做存在性校验，自由文本来源不报错
        if info.source_col is not None:
            for rec in valid_records:
                if rec.sheet != info.title:
                    continue
                for token in split_refs(rec.source_raw):
                    if is_placeholder(token) or not id_re.match(token):
                        continue
                    if token not in global_ids:
                        issues.append(make_issue(
                            "WARN", info.title, rec.row, info.source_col, rec.ident,
                            f"来源列中的 ID 无法解析：`{token}`",
                            "若“来源”列用于记录需求来源文档，请改为文档名；若作为上游链接，请补建条目",
                        ))

    # 规则4c：严格双向闭环（可选 --bidirectional） -------------------------
    if bidirectional:
        first_record: dict[str, Record] = {}
        for rec in valid_records:
            first_record.setdefault(rec.ident, rec)
        downstream_edges: dict[tuple[str, str], Record] = {}
        for rec in valid_records:
            for token in rec.refs:
                if token in global_ids:
                    downstream_edges.setdefault((rec.ident, token), rec)
        upstream_edges: dict[tuple[str, str], Record] = {}
        for rec in valid_records:
            for token in split_refs(rec.upstream_raw):
                if is_placeholder(token) or token not in global_ids:
                    continue
                upstream_edges.setdefault((token, rec.ident), rec)

        for source, target in downstream_edges:
            if (source, target) in upstream_edges:
                continue
            target_rec = first_record.get(target)
            issues.append(make_issue(
                "ERROR",
                target_rec.sheet if target_rec else downstream_edges[(source, target)].sheet,
                target_rec.row if target_rec else None, None, target,
                f"双向不一致：`{source}` 的“下游元素”引用了 `{target}`，"
                f"但 `{target}` 的“上游元素”未回指 `{source}`",
                f"在 `{target}` 行补填上游 ID `{source}`，或删除 `{source}` 行中的该下游引用",
            ))
        for source, target in upstream_edges:
            if (source, target) in downstream_edges:
                continue
            source_rec = first_record.get(source)
            issues.append(make_issue(
                "ERROR",
                source_rec.sheet if source_rec else upstream_edges[(source, target)].sheet,
                source_rec.row if source_rec else None, None, source,
                f"双向不一致：`{target}` 的“上游元素”引用了 `{source}`，"
                f"但 `{source}` 的“下游元素”未回指 `{target}`",
                f"在 `{source}` 行补填下游 ID `{target}`，或删除 `{target}` 行中的该上游引用",
            ))

    # 规则5：测试用例 ID 规范 ------------------------------------------------
    testcase_nonempty_cells = 0
    testcase_noncompliant_cells = 0
    testcase_samples: list[str] = []
    referenced_case_tokens: set[str] = set()
    for info in analyzed_sheets:
        if info.testcase_col is None:
            continue
        per_sheet_nonempty = 0
        per_sheet_bad = 0
        first_bad_row: int | None = None
        per_sheet_samples: list[str] = []
        for rec in valid_records:
            if rec.sheet != info.title or not rec.testcase_raw:
                continue
            per_sheet_nonempty += 1
            tokens = split_refs(rec.testcase_raw)
            expected = re.compile("^" + re.escape(rec.ident) + CASE_SUFFIX_PATTERN + "$")
            ok = bool(tokens) and all(expected.match(tok) for tok in tokens)
            if not ok:
                per_sheet_bad += 1
                if first_bad_row is None:
                    first_bad_row = rec.row
                sample = f"行{rec.row}:{rec.testcase_raw[:40]}"
                if len(testcase_samples) < 3:
                    testcase_samples.append(sample)
                if len(per_sheet_samples) < 3:
                    per_sheet_samples.append(sample)
            for tok in tokens:
                if GENERIC_CASE_PATTERN.match(tok):
                    referenced_case_tokens.add(tok)
        testcase_nonempty_cells += per_sheet_nonempty
        testcase_noncompliant_cells += per_sheet_bad
        if per_sheet_bad:
            ratio = per_sheet_bad / per_sheet_nonempty if per_sheet_nonempty else 0.0
            issues.append(make_issue(
                "WARN", info.title, first_bad_row, info.testcase_col, "",
                f"测试用例列 {per_sheet_bad}/{per_sheet_nonempty} 个非空单元格不合规"
                f"（{ratio:.1%}），未满足 `<本行需求ID>-TC-两位序号` 形态；"
                f"样本：{'；'.join(per_sheet_samples)}",
                "将自由文本改为“<本行需求ID>-TC-两位序号>”，多值用英文逗号分隔",
            ))

    # 用例引用存在性 -------------------------------------------------------
    unresolved_case_refs = 0
    unresolved_case_samples: list[str] = []
    case_info: CaseSheetInfo | None = None
    if cases_path is not None:
        case_info = load_cases(cases_path)
        case_set = set(case_info.ids)
        if case_set:
            for token in sorted(referenced_case_tokens):
                if token not in case_set:
                    unresolved_case_refs += 1
                    if len(unresolved_case_samples) < 3:
                        unresolved_case_samples.append(token)
            if unresolved_case_refs:
                issues.append(make_issue(
                    "WARN", "（测试用例表）", None, None, "",
                    f"{unresolved_case_refs} 个被追踪表引用的用例 ID 在用例表中不存在"
                    f"（样本：{'、'.join(unresolved_case_samples)}）",
                    "在「2.测试用例」页补建用例，或修正追踪表中的用例 ID",
                ))

    return Analysis(
        trace_file=str(trace_path),
        cases_file=str(cases_path) if cases_path else None,
        strict=strict,
        id_pattern=id_pattern,
        sheets=sheet_infos,
        issues=issues,
        records=records,
        global_ids=global_ids,
        broken_links=broken_links,
        total_downstream_refs=total_downstream_refs,
        orphans=orphans,
        invalid_ids=invalid_ids,
        duplicate_groups=duplicate_groups,
        cross_sheet_duplicates=cross_sheet_duplicates,
        testcase_nonempty_cells=testcase_nonempty_cells,
        testcase_noncompliant_cells=testcase_noncompliant_cells,
        testcase_samples=testcase_samples,
        unresolved_case_refs=unresolved_case_refs,
        unresolved_case_samples=unresolved_case_samples,
        case_info=case_info,
        bidirectional=bidirectional,
    )


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------

def md_cell(value: Any) -> str:
    text = as_text(value).replace("\n", " ").replace("|", "\\|")
    if len(text) > 100:
        text = text[:97] + "..."
    return text


def pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1%}"


def issue_sort_key(issue: Issue, sheet_order: dict[str, int]) -> tuple:
    return (
        SEVERITY_ORDER.get(issue.severity, 9),
        sheet_order.get(issue.sheet, 999),
        issue.row if issue.row is not None else 999999,
        issue.message,
    )


def render_markdown(analysis: Analysis) -> str:
    counts = analysis.counts()
    totals = analysis.totals()
    sheet_order = {s.title: s.index for s in analysis.sheets}
    ordered = sorted(analysis.issues, key=lambda i: issue_sort_key(i, sheet_order))
    passed = analysis.passed()

    lines: list[str] = []
    lines.append("# ASPICE 需求追踪校验报告")
    lines.append("")
    lines.append(f"- 生成时间：{_dt.datetime.now().astimezone().isoformat(timespec='seconds')}")
    lines.append(f"- 追踪表：`{analysis.trace_file}`")
    if analysis.cases_file:
        lines.append(f"- 测试用例表：`{analysis.cases_file}`")
    else:
        lines.append("- 测试用例表：未提供（跳过用例存在性与覆盖率校验）")
    lines.append(f"- 校验模式：{'--strict（WARN 也判失败）' if analysis.strict else '基线（仅 ERROR 判失败）'}")
    if analysis.bidirectional:
        lines.append("- 双向闭环：开启（下游→上游与上游→下游必须互为引用）")
    lines.append(
        f"- 判定：**{'✅ 通过' if passed else '❌ 不通过'}**"
        f"（ERROR {counts['ERROR']} / WARN {counts['WARN']} / INFO {counts['INFO']}）"
    )
    lines.append("")

    # 概览 ---------------------------------------------------------------
    lines.append("## 1. 概览")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("| --- | --- |")
    lines.append(f"| 清单数 | {totals['sheets']}（已分析 {totals['analyzed_sheets']} / 跳过 {totals['skipped_sheets']}） |")
    lines.append(f"| 数据行（表头后非空行） | {totals['data_rows']} |")
    lines.append(f"| 有效行（ID 非空） | {totals['valid_rows']} |")
    lines.append(f"| 全库唯一 ID 数 | {len(analysis.global_ids)} |")
    lines.append(f"| 下游引用（非占位 ID 计数） | {analysis.total_downstream_refs} |")
    lines.append(f"| 断链（无法解析的下游引用） | {analysis.broken_links} |")
    lines.append(f"| 孤儿节点（叶子且入度为 0） | {analysis.orphans} |")
    lines.append(f"| ID 命名不合规数 | {analysis.invalid_ids} |")
    lines.append(f"| 清单内重复 ID 组数 | {analysis.duplicate_groups} |")
    lines.append(f"| 跨清单重复 ID 组数 | {analysis.cross_sheet_duplicates} |")
    if analysis.testcase_nonempty_cells:
        ratio = analysis.testcase_noncompliant_cells / analysis.testcase_nonempty_cells
        case_ratio_text = pct(ratio)
    else:
        case_ratio_text = "N/A"
    lines.append(
        f"| 测试用例列非空单元格 / 不合规 | "
        f"{analysis.testcase_nonempty_cells} / {analysis.testcase_noncompliant_cells}（{case_ratio_text}） |"
    )
    if analysis.case_info is not None:
        ci = analysis.case_info
        if ci.warning:
            lines.append(f"| 用例表读取 | {md_cell(ci.warning)} |")
        else:
            covered = len(set(ci.ids) & analysis.referenced_case_ids())
            total_cases = len(set(ci.ids))
            coverage = (covered / total_cases) if total_cases else None
            lines.append(
                f"| 用例覆盖率（被引用/用例总数） | {covered}/{total_cases}（{pct(coverage)}） |"
            )
    lines.append("")

    # 列映射 -------------------------------------------------------------
    lines.append("## 2. 列映射（识别结果）")
    lines.append("")
    lines.append("| # | 清单 | 表头行 | ID 列 | 下游元素列 | 测试用例列 | 上游/来源列 | 状态 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for info in analysis.sheets:
        if info.status == "skipped_no_header":
            status = "跳过（未识别表头）"
        elif info.status == "skipped_no_id":
            status = "跳过（未识别 ID 列）"
        elif info.downstream_col is None:
            status = "已分析（无下游列，按链尾）"
        else:
            status = "已分析"

        def show(col: int, header: str) -> str:
            if not col:
                return "—"
            return f"{col_letter(col)}: {md_cell(header)}"

        upstream = show(info.upstream_col, info.upstream_header)
        if info.source_col:
            src = show(info.source_col, info.source_header)
            upstream = src if upstream == "—" else f"{upstream}；来源 {src}"
        lines.append(
            f"| {info.index + 1} | {md_cell(info.title)} | {info.header_row or '—'} | "
            f"{show(info.id_col, info.id_header)} | "
            f"{show(info.downstream_col, info.downstream_header)} | "
            f"{show(info.testcase_col, info.testcase_header)} | "
            f"{upstream} | {status} |"
        )
    lines.append("")

    # 问题明细 -----------------------------------------------------------
    lines.append("## 3. 问题明细")
    lines.append("")
    if not ordered:
        lines.append("未发现问题。")
    else:
        lines.append("| 严重度 | 清单 | 行号 | 单元格 | ID | 问题 | 建议 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        MAX_ROWS = 300
        for issue in ordered[:MAX_ROWS]:
            lines.append(
                f"| {issue.severity} | {md_cell(issue.sheet)} | "
                f"{issue.row if issue.row is not None else '—'} | "
                f"{issue.cell or '—'} | {md_cell(issue.ident) or '—'} | "
                f"{md_cell(issue.message)} | {md_cell(issue.suggestion)} |"
            )
        if len(ordered) > MAX_ROWS:
            lines.append(f"| … | … | … | … | … | 其余 {len(ordered) - MAX_ROWS} 条已省略 | … |")
    lines.append("")

    # 覆盖率 -------------------------------------------------------------
    lines.append("## 4. 覆盖率")
    lines.append("")
    lines.append("口径：有效行 = ID 非空；有下游引用 = 该行“下游元素”至少含 1 个非占位 ID；"
                 "覆盖率 = 有下游引用行 / 有效行。")
    lines.append("")
    lines.append("| 清单 | 有效行 | 有下游引用行 | 覆盖率 |")
    lines.append("| --- | --- | --- | --- |")
    total_valid = 0
    total_refs = 0
    for info in analysis.sheets:
        if info.status != "analyzed":
            continue
        total_valid += info.valid_rows
        total_refs += info.rows_with_downstream
        lines.append(
            f"| {md_cell(info.title)} | {info.valid_rows} | "
            f"{info.rows_with_downstream} | {pct(info.coverage)} |"
        )
    overall = (total_refs / total_valid) if total_valid else None
    lines.append(f"| **合计** | **{total_valid}** | **{total_refs}** | **{pct(overall)}** |")
    lines.append("")

    lines.append("### 4.1 测试用例")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("| --- | --- |")
    lines.append(f"| 追踪表测试用例列非空单元格 | {analysis.testcase_nonempty_cells} |")
    lines.append(f"| 其中不符合 `<需求ID>-TC-两位序号` 形态 | {analysis.testcase_noncompliant_cells} |")
    lines.append(f"| 用例列不合规比例 | {case_ratio_text} |")
    if analysis.case_info is None:
        lines.append("| 用例表 | 未提供 |")
    else:
        ci = analysis.case_info
        if ci.warning:
            lines.append(f"| 用例表 | 读取异常：{md_cell(ci.warning)} |")
        else:
            unique_cases = len(set(ci.ids))
            referenced = len(set(ci.ids) & analysis.referenced_case_ids())
            cov = (referenced / unique_cases) if unique_cases else None
            lines.append(f"| 用例表 ID 数（去重） | {unique_cases} |")
            lines.append(f"| 被追踪表引用的用例 ID 数 | {referenced} |")
            lines.append(f"| 用例引用覆盖率 | {pct(cov)} |")
            lines.append(f"| 引用不存在的用例 ID | {analysis.unresolved_case_refs} |")
    lines.append("")

    # 结论 ---------------------------------------------------------------
    lines.append("## 5. 结论与建议")
    lines.append("")
    if counts["ERROR"]:
        lines.append(f"- **断链 {analysis.broken_links} 处**：下游引用指向了不存在的 ID，"
                     "V 模型链在该处不可机械举证，需优先修复（见问题明细 ERROR 行）。")
    elif analysis.total_downstream_refs:
        lines.append(f"- 未发现断链；{analysis.total_downstream_refs} 条下游引用均可解析到全库 ID 索引。")
    else:
        lines.append("- 当前没有任何下游引用可校验，“无断链”仅表示本轮没有可检数据，不代表链路健康。")
    if totals["valid_rows"] == 0:
        lines.append("- **当前追踪表没有有效 ID 行**：文件仅含表头与占位/下拉示例值，"
                     "无法证明任何追溯关系；需先按模板补全各层 ID 与下游引用后再评估。")
    upstream_missing = sum(
        1 for s in analysis.sheets
        if s.status == "analyzed" and s.upstream_col is None
    )
    if upstream_missing:
        lines.append(f"- **{upstream_missing} 张已分析清单缺少“上游元素”列**："
                     "只能单向向下引用，向上追溯无法机械校验；建议九张清单统一补列。")
    skipped = [s.title for s in analysis.sheets if s.status != "analyzed"]
    if skipped:
        lines.append(f"- 被跳过的清单：{'、'.join(skipped)}；跳过原因见第 2 节列映射表。")
    if analysis.testcase_nonempty_cells:
        lines.append(f"- 测试用例列不合规比例 {case_ratio_text}："
                     "自由文本用例无法与需求建立稳定外键，建议统一 ID 规范。")
    elif analysis.testcase_nonempty_cells == 0:
        lines.append("- 测试用例列存在但无有效数据，用例覆盖率无法举证。")
    lines.append("")
    lines.append("> 本报告由 `trace_check.py` 自动生成，仅对输入文件做只读分析。")
    lines.append("")
    return "\n".join(lines)


def analysis_to_dict(analysis: Analysis) -> dict[str, Any]:
    counts = analysis.counts()
    totals = analysis.totals()
    case_stats: dict[str, Any] | None = None
    if analysis.case_info is not None:
        ci = analysis.case_info
        unique_cases = len(set(ci.ids))
        referenced = len(set(ci.ids) & analysis.referenced_case_ids())
        case_stats = {
            "sheet": ci.sheet,
            "header_row": ci.header_row,
            "id_col": col_letter(ci.id_col) or None,
            "total_cases": unique_cases,
            "referenced_cases": referenced,
            "coverage": (referenced / unique_cases) if unique_cases else None,
            "warning": ci.warning or None,
        }
    return {
        "tool": "trace_check.py",
        "version": "1.0",
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "trace_file": analysis.trace_file,
        "cases_file": analysis.cases_file,
        "strict": analysis.strict,
        "bidirectional": analysis.bidirectional,
        "id_pattern": analysis.id_pattern,
        "passed": analysis.passed(),
        "counts": {
            "error": counts["ERROR"],
            "warn": counts["WARN"],
            "info": counts["INFO"],
        },
        "totals": totals,
        "global_unique_ids": len(analysis.global_ids),
        "broken_links": analysis.broken_links,
        "total_downstream_refs": analysis.total_downstream_refs,
        "orphans": analysis.orphans,
        "invalid_ids": analysis.invalid_ids,
        "duplicate_groups": analysis.duplicate_groups,
        "cross_sheet_duplicates": analysis.cross_sheet_duplicates,
        "testcase": {
            "nonempty_cells": analysis.testcase_nonempty_cells,
            "noncompliant_cells": analysis.testcase_noncompliant_cells,
            "noncompliance_ratio": (
                analysis.testcase_noncompliant_cells / analysis.testcase_nonempty_cells
                if analysis.testcase_nonempty_cells else None
            ),
            "unresolved_refs": analysis.unresolved_case_refs,
        },
        "case_stats": case_stats,
        "sheets": [
            {
                "title": s.title,
                "index": s.index,
                "status": s.status,
                "header_row": s.header_row,
                "id_column": (
                    {"letter": col_letter(s.id_col), "header": s.id_header}
                    if s.id_col else None
                ),
                "downstream_column": (
                    {"letter": col_letter(s.downstream_col), "header": s.downstream_header}
                    if s.downstream_col else None
                ),
                "testcase_column": (
                    {"letter": col_letter(s.testcase_col), "header": s.testcase_header}
                    if s.testcase_col else None
                ),
                "upstream_column": (
                    {"letter": col_letter(s.upstream_col), "header": s.upstream_header}
                    if s.upstream_col else None
                ),
                "source_column": (
                    {"letter": col_letter(s.source_col), "header": s.source_header}
                    if s.source_col else None
                ),
                "data_rows": s.data_rows,
                "valid_rows": s.valid_rows,
                "rows_with_downstream": s.rows_with_downstream,
                "coverage": s.coverage,
            }
            for s in analysis.sheets
        ],
        "issues": [
            {
                "severity": i.severity,
                "sheet": i.sheet,
                "row": i.row,
                "cell": i.cell,
                "id": i.ident,
                "message": i.message,
                "suggestion": i.suggestion,
            }
            for i in analysis.issues
        ],
    }


def render_console(analysis: Analysis, report_path: Path | None, limit: int = 20) -> str:
    counts = analysis.counts()
    totals = analysis.totals()
    sheet_order = {s.title: s.index for s in analysis.sheets}
    ordered = sorted(analysis.issues, key=lambda i: issue_sort_key(i, sheet_order))
    lines: list[str] = []
    lines.append(f"需求追踪校验：{Path(analysis.trace_file).name}")
    lines.append(
        f"清单 {totals['sheets']}（分析 {totals['analyzed_sheets']} / 跳过 {totals['skipped_sheets']}）"
        f" · 有效行 {totals['valid_rows']} · 断链 {analysis.broken_links}"
        f" · ERROR {counts['ERROR']} / WARN {counts['WARN']} / INFO {counts['INFO']}"
        f" · {'PASS' if analysis.passed() else 'FAIL'}"
        + (" · 双向闭环" if analysis.bidirectional else "")
    )
    if analysis.case_info is not None:
        if analysis.case_info.warning:
            lines.append(f"用例表：{analysis.case_info.warning}")
        else:
            unique_cases = len(set(analysis.case_info.ids))
            referenced = len(set(analysis.case_info.ids) & analysis.referenced_case_ids())
            cov = (referenced / unique_cases) if unique_cases else None
            lines.append(
                f"用例：{referenced}/{unique_cases} 被引用（{pct(cov)}）"
                f" · 用例列不合规 {analysis.testcase_noncompliant_cells}"
                f"/{analysis.testcase_nonempty_cells}"
            )
    lines.append("[列映射]")
    for info in analysis.sheets:
        if info.status == "skipped_no_header":
            lines.append(f"  {info.index + 1}. {info.title}：跳过（未识别表头）")
            continue
        if info.status == "skipped_no_id":
            lines.append(f"  {info.index + 1}. {info.title}：跳过（未识别 ID 列）")
            continue
        parts = [f"表头{info.header_row}", f"ID={col_letter(info.id_col) or '—'}",
                 f"下游={col_letter(info.downstream_col) or '—'}",
                 f"用例={col_letter(info.testcase_col) or '—'}"]
        upstream = col_letter(info.upstream_col)
        if upstream:
            parts.append(f"上游={upstream}")
        source = col_letter(info.source_col)
        if source:
            parts.append(f"来源={source}")
        lines.append(f"  {info.index + 1}. {info.title}：" + " ".join(parts))
    if ordered:
        lines.append("-" * 78)
        for issue in ordered[:limit]:
            row = f"行{issue.row}" if issue.row is not None else "—"
            ident = f" [{issue.ident}]" if issue.ident else ""
            lines.append(f"{issue.severity:<5} {issue.sheet} {row}{ident}：{issue.message}")
        if len(ordered) > limit:
            lines.append(f"… 其余 {len(ordered) - limit} 条见报告")
    if report_path:
        lines.append(f"报告已写入：{report_path}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 自测：现场构造工作簿并断言各类问题均被检出
# ---------------------------------------------------------------------------

def _write_fixture(path: Path) -> None:
    wb = openpyxl.Workbook()

    ws1 = wb.active
    ws1.title = "系统需求清单"
    headers1 = [
        "系统需求标识\nSystem Requirement ID",
        "标题\nTitle",
        "下游元素\nDownstream Element",
        "测试用例\nTest Case",
    ]
    for col, value in enumerate(headers1, start=2):
        ws1.cell(row=1, column=col, value=value)
    rows1 = [
        ["SYS_REQ_001", "调光", "SYS_ARCH_001, SYS_ARCH_002", "SYS_REQ_001-TC-01"],
        ["SYS_REQ_002", "寻址", "SYS_MISSING_001", "验证寻址功能"],
        ["SYS_REQ_001", "重复条目", "SYS_ARCH_001", "SYS_REQ_001-TC-02"],
        ["", "空 ID 但整行非空", "SYS_ARCH_001", ""],
        [None, None, None, None],
        ["bad id", "非法命名", "SYS_ARCH_001", ""],
    ]
    for r, values in enumerate(rows1, start=2):
        for c, value in enumerate(values, start=2):
            if value is not None:
                ws1.cell(row=r, column=c, value=value)

    ws2 = wb.create_sheet("系统架构元素清单")
    headers2 = ["系统架构元素标识\nID", "标题\nTitle",
                "下游元素\nDownstream", "测试用例\nTest Case"]
    for col, value in enumerate(headers2, start=2):
        ws2.cell(row=3, column=col, value=value)
    rows2 = [
        ["SYS_ARCH_001", "架构1", "SW_DD_001", "SYS_ARCH_001-TC-01"],
        ["SYS_ARCH_002", "架构2", "", ""],
        ["SYS_ARCH_003", "架构3", "", ""],
        ["SYS_REQ_001", "误用跨层 ID", "", ""],
    ]
    for r, values in enumerate(rows2, start=4):
        for c, value in enumerate(values, start=2):
            if value is not None:
                ws2.cell(row=r, column=c, value=value)

    ws3 = wb.create_sheet("软件详设清单")
    headers3 = ["软件详设标识\nID", "标题\nTitle", "测试用例\nTest Case"]
    for col, value in enumerate(headers3, start=2):
        ws3.cell(row=1, column=col, value=value)
    rows3 = [["SW_DD_001", "详设1", "SW_DD_001-TC-01"]]
    for r, values in enumerate(rows3, start=2):
        for c, value in enumerate(values, start=2):
            if value is not None:
                ws3.cell(row=r, column=c, value=value)

    wb.save(path)


def _write_bidir_fixture(path: Path) -> None:
    """双向闭环自测用最小工作簿：含一处单向下游、一处单向上游。"""
    wb = openpyxl.Workbook()

    ws1 = wb.active
    ws1.title = "系统需求清单"
    headers = ["系统需求标识\nID", "标题\nTitle",
               "上游元素\nUpstream Element", "下游元素\nDownstream Element"]
    for col, value in enumerate(headers, start=2):
        ws1.cell(row=1, column=col, value=value)
    ws1.cell(row=2, column=2, value="REQ_001")
    ws1.cell(row=2, column=5, value="ARCH_001")
    ws1.cell(row=3, column=2, value="REQ_002")

    ws2 = wb.create_sheet("系统架构元素清单")
    headers2 = ["系统架构元素标识\nID", "标题\nTitle",
                "上游元素\nUpstream Element", "下游元素\nDownstream Element"]
    for col, value in enumerate(headers2, start=2):
        ws2.cell(row=1, column=col, value=value)
    ws2.cell(row=2, column=2, value="ARCH_001")
    ws2.cell(row=3, column=2, value="ARCH_002")
    ws2.cell(row=3, column=4, value="REQ_002")

    wb.save(path)


def run_selftest() -> int:
    print("== trace_check.py 自测 ==")
    with tempfile.TemporaryDirectory(prefix="trace_check_selftest_") as tmp:
        fixture = Path(tmp) / "fixture.xlsx"
        _write_fixture(fixture)
        analysis = analyze(fixture, cases_path=None, strict=False)
        bidir_fixture = Path(tmp) / "bidir.xlsx"
        _write_bidir_fixture(bidir_fixture)
        baseline = analyze(bidir_fixture)
        bidir = analyze(bidir_fixture, bidirectional=True)
        print(f"fixture analysis: ERROR={analysis.counts()['ERROR']} "
              f"WARN={analysis.counts()['WARN']} INFO={analysis.counts()['INFO']} "
              f"broken={analysis.broken_links} orphans={analysis.orphans} "
              f"valid={analysis.totals()['valid_rows']}")

    issues = analysis.issues
    errors = [i for i in issues if i.severity == "ERROR"]
    warns = [i for i in issues if i.severity == "WARN"]
    infos = [i for i in issues if i.severity == "INFO"]

    # 1) 列映射：3 张清单均识别；第 2 张表头在第 3 行
    assert len(analysis.sheets) == 3, "应识别 3 张清单"
    assert [s.status for s in analysis.sheets] == ["analyzed"] * 3, "三张清单均应可分析"
    assert analysis.sheets[1].header_row == 3, "第 2 张清单表头应在第 3 行"
    assert analysis.sheets[2].downstream_col is None, "软件详设应无下游列"

    # 2) 计数：清单内重复 1 组 + 断链 1 处 = ERROR 2
    assert len(errors) == 2, f"ERROR 应为 2，实际 {len(errors)}: {[e.message for e in errors]}"
    assert analysis.duplicate_groups == 1, "应检出 1 组清单内重复 ID"
    assert analysis.broken_links == 1, "应检出 1 处断链"
    assert any("SYS_MISSING_001" in e.message for e in errors), "断链应指向 SYS_MISSING_001"

    # 3) 空 ID 聚合 1 + 命名 1 + 跨清单重复 1 + 孤儿 1 + 用例 1 + 无下游 1 = WARN 6
    assert len(warns) == 6, f"WARN 应为 6，实际 {len(warns)}: {[w.message for w in warns]}"
    assert any("ID 为空" in w.message for w in warns), "应检出空 ID 行"
    assert any("不符合命名规范" in w.message for w in warns), "应检出非法命名"
    assert any("出现在多张清单" in w.message for w in warns), "应检出跨清单重复"
    assert any("叶子节点" in w.message for w in warns), "应检出孤儿节点"
    assert any("测试用例列" in w.message for w in warns), "应检出用例列不合规"
    assert any("下游元素" in w.message for w in warns), "应提示缺少下游列"
    assert analysis.orphans == 2, f"孤儿应为 2，实际 {analysis.orphans}"
    assert analysis.cross_sheet_duplicates == 1, "跨清单重复应为 1"

    # 4) 测试用例：5 个非空（4 合规 + 1 自由文本），1 个不合规
    assert analysis.testcase_nonempty_cells == 5, \
        f"用例非空单元格应为 5，实际 {analysis.testcase_nonempty_cells}"
    assert analysis.testcase_noncompliant_cells == 1, \
        f"用例不合规应为 1，实际 {analysis.testcase_noncompliant_cells}"

    # 5) 有效行：sheet1 4 + sheet2 4 + sheet3 1 = 9
    assert analysis.totals()["valid_rows"] == 9, \
        f"有效行应为 9，实际 {analysis.totals()['valid_rows']}"

    # 6) 上游列缺失 INFO：3 张
    assert len(infos) == 3, f"INFO 应为 3，实际 {len(infos)}"

    # 7) 报告渲染不崩溃，且含关键小节
    report = render_markdown(analysis)
    assert "## 2. 列映射" in report and "## 3. 问题明细" in report

    # 8) 严格双向模式：仅单向引用记 ERROR；默认模式不启用
    assert not [i for i in baseline.issues if "双向不一致" in i.message], \
        "默认模式不应产生双向不一致 ERROR"
    bidir_errors = [i for i in bidir.issues if i.severity == "ERROR"]
    assert len(bidir_errors) == 2, \
        f"双向不一致 ERROR 应为 2，实际 {len(bidir_errors)}: {[e.message for e in bidir_errors]}"
    assert all("双向不一致" in i.message for i in bidir_errors)
    assert any("REQ_001" in i.message and "ARCH_001" in i.message for i in bidir_errors)
    assert any("REQ_002" in i.message and "ARCH_002" in i.message for i in bidir_errors)

    print("PASS: 列映射/表头偏移识别")
    print("PASS: 空 ID、重复 ID、跨清单重复、非法命名")
    print("PASS: 断链、孤儿节点、缺少上游列 INFO")
    print("PASS: 测试用例自由文本不合规计数")
    print("PASS: 严格双向闭环（缺失回指计 ERROR）")
    print("PASS: 报告渲染")
    print("SELFTEST OK")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trace_check.py",
        description="ASPICE 4.0 CL2 需求追踪表机械校验（单文件，仅依赖 openpyxl）",
    )
    parser.add_argument(
        "--trace", type=Path, default=DEFAULT_TRACE,
        help=f"需求追踪表 .xlsx（默认：{DEFAULT_TRACE}）",
    )
    parser.add_argument(
        "--cases", type=Path, default=None,
        help="测试规范 .xlsx（读取「2.测试用例」页做用例引用校验）",
    )
    parser.add_argument("--out", type=Path, default=None, help="Markdown 报告输出路径")
    parser.add_argument(
        "--json", action="store_true",
        help="输出机器可读 JSON：指定 --out 时写入同名 .json；未指定时向 stdout 输出纯 JSON",
    )
    parser.add_argument(
        "--strict", action="store_true", help="WARN 也视为失败（退出码 1）",
    )
    parser.add_argument(
        "--bidirectional", action="store_true",
        help="严格双向闭环：下游引用与上游回指必须互为一致（不一致计 ERROR）",
    )
    parser.add_argument(
        "--id-pattern", default=DEFAULT_ID_PATTERN,
        help=f"ID 命名正则（默认：{DEFAULT_ID_PATTERN}）",
    )
    parser.add_argument(
        "--selftest", action="store_true", help="运行内置自测（不依赖外部文件）",
    )
    return parser


def _fail(message: str) -> int:
    print(f"[ERROR] {message}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.selftest:
        try:
            return run_selftest()
        except AssertionError as exc:
            print(f"[SELFTEST FAILED] {exc}", file=sys.stderr)
            return 1
        except Exception as exc:  # 自测期间的非断言异常
            print(f"[SELFTEST ERROR] {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1

    trace_path = Path(args.trace).expanduser()
    if not trace_path.exists():
        return _fail(f"找不到 --trace 指定的文件：{trace_path}")
    if trace_path.is_dir():
        return _fail(f"--trace 指向的是目录而不是 .xlsx 文件：{trace_path}")

    cases_path = Path(args.cases).expanduser() if args.cases else None
    if cases_path is not None:
        if not cases_path.exists():
            return _fail(f"找不到 --cases 指定的文件：{cases_path}")
        if cases_path.is_dir():
            return _fail(f"--cases 指向的是目录而不是 .xlsx 文件：{cases_path}")

    try:
        analysis = analyze(trace_path, cases_path, args.id_pattern, args.strict,
                           args.bidirectional)
    except ValueError as exc:
        return _fail(str(exc))
    except PermissionError:
        return _fail(f"没有读取权限：{trace_path}")
    except (OSError, KeyError, TypeError) as exc:
        return _fail(f"读取工作簿失败：{type(exc).__name__}: {exc}")
    except Exception as exc:
        # openpyxl 对损坏文件抛出多种异常；给出清晰信息，不打印 traceback
        name = type(exc).__name__
        if name in {"BadZipFile", "InvalidFileException"} or "zip" in str(exc).lower():
            return _fail(f"文件不是有效的 .xlsx（可能已损坏或为旧版 .xls）：{trace_path}")
        return _fail(f"分析失败：{name}: {exc}")

    report: str | None = None
    report_path: Path | None = None
    json_path: Path | None = None
    try:
        report = render_markdown(analysis)
        if args.out:
            report_path = Path(args.out).expanduser()
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(report, encoding="utf-8")
        if args.json and report_path is not None:
            json_path = report_path.with_suffix(".json")
            json_path.write_text(
                json.dumps(analysis_to_dict(analysis), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    except OSError as exc:
        return _fail(f"写入报告失败：{exc}")

    console = render_console(analysis, report_path)
    if args.json and report_path is None:
        # stdout 保持纯 JSON 供 CI 解析，人读摘要写到 stderr
        print(json.dumps(analysis_to_dict(analysis), ensure_ascii=False, indent=2))
        print(console, file=sys.stderr)
    else:
        print(console)
        if json_path is not None:
            print(f"JSON 已写入：{json_path}")

    return 0 if analysis.passed() else 1


if __name__ == "__main__":
    sys.exit(main())
