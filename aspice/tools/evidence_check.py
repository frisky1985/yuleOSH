#!/usr/bin/env python3
"""evidence_check.py — pipeline 产物 ↔ ASPICE 模板槽位 双向闭合校验（fail-closed）

定位：trace_check.py 的姊妹工具。trace_check 管「文档之间」的需求追溯，
evidence_check 管「pipeline 产物 → 文档槽位」的证据追溯。

核心概念
--------
槽位（slot）: ``文档别名::行键::列名``，例如
    ENG_测试规范::SYS-SEAT-001-TC-01::实际结果
槽位由模板定义（本原型：测试规范「2.测试用例」页第 1 轮的结果列组）。

产物（artifact）: pipeline stage 输出的 Markdown 文件，YAML frontmatter 自声明
（stage 自声明机制，粒度到产物）：

    ---
    artifact: SYS-SEAT-001-TC-01__round1
    stage: test
    verdict: PASS
    fills:
      - ENG_测试规范::SYS-SEAT-001-TC-01::实际结果
      - ENG_测试规范::SYS-SEAT-001-TC-01::测试日志链接
      - ENG_测试规范::SYS-SEAT-001-TC-01::判定结论
    ---

清单（manifest）: evidence_manifest.json，记录每个产物的 sha256。
由 ``--write-manifest`` 在证据基线时生成；此后每次校验逐文件重算哈希，
不一致即判定证据被篡改（ERROR）。

校验规则（fail-closed：任一 ERROR → 退出码 1）
---------------------------------------------
E-SLOT-UNFILLED   模板槽位没有任何产物填充           ERROR
E-SLOT-UNKNOWN    产物声明的槽位在模板中不存在        ERROR（孤儿产物）
E-SLOT-DUP        同一槽位被多个产物填充              WARN（来源歧义）
E-ARTIFACT-EMPTY  产物正文为空（占位造假）            ERROR
E-HASH-MISMATCH   产物当前哈希 ≠ 清单哈希            ERROR（证据被篡改）
E-HASH-MISSING    产物未纳入清单                     ERROR
E-MANIFEST-STALE  清单中的产物已从磁盘消失            ERROR
W-NO-MANIFEST     尚未建立清单，无法校验篡改          WARN

仅依赖 openpyxl（frontmatter 用内置微型解析器，不依赖 pyyaml）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_EVIDENCE_COLUMNS = ("实际结果", "测试日志链接", "判定结论")
DEFAULT_DOC_ALIAS = "ENG_测试规范"
DEFAULT_CASES_SHEET = "2.测试用例"
TC_ID_HEADER = "测试用例ID"
MANIFEST_NAME = "evidence_manifest.json"
MIN_BODY_CHARS = 20  # 产物正文最少字符数，防止空壳占位


# ---------------------------------------------------------------- 数据结构

@dataclass
class Artifact:
    path: Path
    rel_path: str
    sha256: str
    stage: str
    verdict: str
    fills: list[str]
    body_chars: int
    meta: dict = field(default_factory=dict)


@dataclass
class EvidenceAnalysis:
    slots_expected: list[str] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest_path: str | None = None
    manifest_written: bool = False

    def passed(self, strict: bool = False) -> bool:
        if self.errors:
            return False
        return not (strict and self.warnings)

    def filled_slots(self) -> set[str]:
        out: set[str] = set()
        for a in self.artifacts:
            out.update(a.fills)
        return out


# ---------------------------------------------------------------- 工具函数

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """微型 YAML frontmatter 解析器。

    仅支持 ``key: value`` 与 ``key:`` + 缩进 ``- item`` 列表两种形态，
    足够覆盖产物自声明。返回 (meta, body)；无 frontmatter 时 meta 为空 dict。
    """
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return {}, text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text

    meta: dict[str, object] = {}
    current_key: str | None = None
    for raw in lines[1:end]:
        line = raw.rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped.startswith("- ") and current_key:
            lst = meta.setdefault(current_key, [])
            if isinstance(lst, list):
                lst.append(stripped[2:].strip())
            continue
        if ":" in stripped and not line.startswith((" ", "\t")):
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            meta[key] = value if value else []
            current_key = key
    body = "\n".join(lines[end + 1:]).strip()
    return meta, body


# ---------------------------------------------------------------- 槽位规格

def load_slots(slots_path: Path, doc_alias: str) -> dict:
    """读取 slots.yaml，返回指定文档别名的规格（dict）。

    规格即 L0 护栏：sheet/表头定位/行键列/证据列/字段映射/受控词表全部数据化。
    """
    try:
        import yaml
    except ImportError as exc:
        raise ValueError("--slots 需要 pyyaml：python3 -m pip install pyyaml") from exc
    data = yaml.safe_load(slots_path.read_text(encoding="utf-8"))
    docs = (data or {}).get("documents", [])
    for doc in docs:
        if doc.get("alias") == doc_alias:
            for key in ("sheet", "header_locator", "row_key", "evidence_columns"):
                if key not in doc:
                    raise ValueError(f"slots.yaml 中「{doc_alias}」缺少 {key}")
            return doc
    aliases = [d.get("alias") for d in docs]
    raise ValueError(f"slots.yaml 中找不到文档别名「{doc_alias}」（现有：{aliases}）")


# ---------------------------------------------------------------- 槽位发现

def discover_slots(cases_path: Path, sheet_name: str,
                   columns: tuple[str, ...], doc_alias: str,
                   row_key: str = TC_ID_HEADER,
                   locator: str | None = None) -> list[str]:
    """从测试规范 xlsx 枚举证据槽位（第 1 轮结果列组 × 全部用例 ID）。"""
    from openpyxl import load_workbook

    locator = locator or row_key
    wb = load_workbook(cases_path, read_only=True)
    if sheet_name not in wb.sheetnames:
        raise ValueError(f"{cases_path.name} 中找不到工作表「{sheet_name}」")
    ws = wb[sheet_name]

    # 动态定位表头行：前若干行中包含定位串的那一行
    header: list[str] | None = None
    header_row = 0
    for ridx, row in enumerate(ws.iter_rows(min_row=1, max_row=10, values_only=True), 1):
        # 表头单元格常为「中文\n英文」双语：取第一行做规范化匹配
        cells = [str(c).split("\n")[0].strip() if c else "" for c in row]
        if locator in cells:
            header = cells
            header_row = ridx
            break
    if header is None:
        raise ValueError(f"「{sheet_name}」前 10 行内找不到含「{locator}」的表头行")

    tc_col = header.index(row_key) if row_key in header else None
    if tc_col is None:
        raise ValueError(f"表头缺少行键列「{row_key}」")
    # 每类证据列只取第一次出现（第 1 轮列组）
    col_names: list[str] = []
    for want in columns:
        if want in header:
            col_names.append(want)
    if not col_names:
        raise ValueError(f"表头缺少全部证据列：{'/'.join(columns)}")

    slots: list[str] = []
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        tc = row[tc_col]
        if tc is None or str(tc).strip() == "":
            continue
        tc_id = str(tc).strip()
        for col in col_names:
            slots.append(f"{doc_alias}::{tc_id}::{col}")
    wb.close()
    if not slots:
        raise ValueError(f"「{sheet_name}」未发现任何测试用例行")
    return slots


# ---------------------------------------------------------------- 产物扫描

def scan_artifacts(evidence_dir: Path, doc_alias: str) -> tuple[list[Artifact], list[str]]:
    artifacts: list[Artifact] = []
    errors: list[str] = []
    for path in sorted(evidence_dir.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        rel = path.relative_to(evidence_dir.parent).as_posix()
        fills_raw = meta.get("fills", [])
        fills = [str(s).strip() for s in fills_raw] if isinstance(fills_raw, list) else []
        if not fills:
            errors.append(f"E-ARTIFACT-NOFRONT: {rel} 缺少 frontmatter fills 声明")
        artifacts.append(Artifact(
            path=path,
            rel_path=rel,
            sha256=sha256_file(path),
            stage=str(meta.get("stage", "")).strip(),
            verdict=str(meta.get("verdict", "")).strip(),
            fills=fills,
            body_chars=len(body),
            meta=meta,
        ))
    return artifacts, errors


# ---------------------------------------------------------------- 主分析

def analyze(cases_path: Path, evidence_dir: Path, doc_alias: str,
            columns: tuple[str, ...], sheet_name: str,
            manifest_path: Path | None, write_manifest: bool,
            row_key: str = TC_ID_HEADER, locator: str | None = None,
            fields: dict[str, str] | None = None,
            vocab: dict[str, list[str]] | None = None) -> EvidenceAnalysis:
    result = EvidenceAnalysis()
    result.slots_expected = discover_slots(cases_path, sheet_name, columns, doc_alias,
                                           row_key=row_key, locator=locator)

    artifacts, scan_errors = scan_artifacts(evidence_dir, doc_alias)
    result.artifacts = artifacts
    result.errors.extend(scan_errors)

    expected = set(result.slots_expected)

    # --- 双向闭合 ------------------------------------------------
    filled: dict[str, list[str]] = {}
    for a in artifacts:
        for slot in a.fills:
            filled.setdefault(slot, []).append(a.rel_path)
            if not slot.startswith(f"{doc_alias}::"):
                result.errors.append(
                    f"E-SLOT-UNKNOWN: {a.rel_path} 声明的槽位不属于本文档别名：{slot}")
            elif slot not in expected:
                result.errors.append(
                    f"E-SLOT-UNKNOWN: {a.rel_path} 声明的槽位在模板中不存在：{slot}")
        if a.body_chars < MIN_BODY_CHARS:
            result.errors.append(
                f"E-ARTIFACT-EMPTY: {a.rel_path} 正文不足 {MIN_BODY_CHARS} 字符（疑似空壳占位）")
        # 字段与受控词表校验（规格驱动）：产物声明填充某列，就必须带对应字段且值合法
        for slot in a.fills:
            col = slot.rsplit("::", 1)[-1]
            if fields and col in fields:
                value = str(a.meta.get(fields[col], "")).strip()
                if not value:
                    result.errors.append(
                        f"E-FIELD-MISSING: {a.rel_path} 声明填充「{col}」"
                        f"但 frontmatter 缺少字段 {fields[col]}")
                elif vocab and col in vocab and value not in vocab[col]:
                    result.errors.append(
                        f"E-VOCAB: {a.rel_path} 字段 {fields[col]}={value!r}"
                        f" 不在受控词表 {vocab[col]}")

    for slot in result.slots_expected:
        if slot not in filled:
            result.errors.append(f"E-SLOT-UNFILLED: 槽位无产物填充：{slot}")
    for slot, sources in sorted(filled.items()):
        if len(sources) > 1:
            result.warnings.append(
                f"E-SLOT-DUP: 槽位被 {len(sources)} 个产物填充：{slot} ← {', '.join(sources)}")

    # --- 哈希 / 清单 ----------------------------------------------
    manifest_file = manifest_path or (evidence_dir / MANIFEST_NAME)
    result.manifest_path = str(manifest_file)

    if write_manifest:
        data = {
            "version": "0.1",
            "doc_alias": doc_alias,
            "artifacts": [
                {
                    "path": a.rel_path,
                    "sha256": a.sha256,
                    "stage": a.stage,
                    "verdict": a.verdict,
                    "fills": a.fills,
                }
                for a in artifacts
            ],
        }
        manifest_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result.manifest_written = True
    elif manifest_file.exists():
        try:
            data = json.loads(manifest_file.read_text(encoding="utf-8"))
            recorded = {e["path"]: e for e in data.get("artifacts", [])}
        except (json.JSONDecodeError, KeyError) as exc:
            result.errors.append(f"E-MANIFEST-BAD: 清单损坏：{exc}")
            recorded = {}
        on_disk = {a.rel_path: a for a in artifacts}
        for rel, a in on_disk.items():
            entry = recorded.get(rel)
            if entry is None:
                result.errors.append(f"E-HASH-MISSING: 产物未纳入清单：{rel}")
            elif entry.get("sha256") != a.sha256:
                result.errors.append(
                    f"E-HASH-MISMATCH: {rel} 哈希与清单不符（证据疑似被篡改）")
        for rel in recorded:
            if rel not in on_disk:
                result.errors.append(f"E-MANIFEST-STALE: 清单产物已消失：{rel}")
    else:
        result.warnings.append(
            f"W-NO-MANIFEST: 未找到 {manifest_file.name}，无法校验篡改；"
            f"请先以 --write-manifest 建立证据基线")

    return result


# ---------------------------------------------------------------- 输出

def render_console(a: EvidenceAnalysis, strict: bool) -> str:
    lines = [
        "===== evidence_check 结果 =====",
        f"槽位（模板定义）   : {len(a.slots_expected)}",
        f"产物（pipeline 输出）: {len(a.artifacts)}",
        f"已填充槽位         : {len(a.filled_slots() & set(a.slots_expected))}",
        f"ERROR              : {len(a.errors)}",
        f"WARN               : {len(a.warnings)}",
    ]
    if a.manifest_written:
        lines.append(f"清单               : 已写入 {a.manifest_path}")
    elif a.manifest_path:
        lines.append(f"清单               : {a.manifest_path}")
    for e in a.errors:
        lines.append(f"  [ERROR] {e}")
    for w in a.warnings:
        lines.append(f"  [WARN ] {w}")
    lines.append("结论：" + ("PASS ✅" if a.passed(strict) else "FAIL ❌（fail-closed）"))
    return "\n".join(lines)


def analysis_to_dict(a: EvidenceAnalysis, strict: bool) -> dict:
    return {
        "slots_expected": len(a.slots_expected),
        "slots_filled": len(a.filled_slots() & set(a.slots_expected)),
        "artifacts": [
            {"path": x.rel_path, "sha256": x.sha256, "stage": x.stage,
             "verdict": x.verdict, "fills": x.fills}
            for x in a.artifacts
        ],
        "errors": a.errors,
        "warnings": a.warnings,
        "manifest": a.manifest_path,
        "passed": a.passed(strict),
    }


# ---------------------------------------------------------------- 自测

def run_selftest() -> int:
    from openpyxl import Workbook

    def make_cases(path: Path, tc_ids: list[str]) -> None:
        wb = Workbook()
        ws = wb.active
        ws.title = DEFAULT_CASES_SHEET
        ws.append(["测试用例信息"])
        ws.append(["编号", "被测项ID", "需求描述", TC_ID_HEADER, "操作步骤",
                   "期望结果", "实际结果", "测试日志链接", "判定结论"])
        for i, tc in enumerate(tc_ids, 1):
            ws.append([i, f"SYS-X-{i:03d}", "示例需求", tc, "步骤", "期望", None, None, None])
        wb.save(path)

    def make_artifact(directory: Path, name: str, tc: str,
                      cols: tuple[str, ...], body: str = "实测结果与期望一致，日志已归档（示例数据）。") -> Path:
        fills = "\n".join(f"  - {DEFAULT_DOC_ALIAS}::{tc}::{c}" for c in cols)
        p = directory / name
        p.write_text(
            f"---\nartifact: {name}\nstage: test\nverdict: PASS\nfills:\n{fills}\n---\n\n{body}\n",
            encoding="utf-8")
        return p

    cols = ("实际结果", "测试日志链接", "判定结论")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cases = root / "cases.xlsx"
        evd = root / "evidence"
        evd.mkdir()
        manifest = evd / MANIFEST_NAME
        make_cases(cases, ["SYS-X-001-TC-01", "SYS-X-002-TC-01"])

        # 1. 全部填充 + 建清单 → 通过
        make_artifact(evd, "tc1.md", "SYS-X-001-TC-01", cols)
        make_artifact(evd, "tc2.md", "SYS-X-002-TC-01", cols)
        r = analyze(cases, evd, DEFAULT_DOC_ALIAS, cols, DEFAULT_CASES_SHEET, manifest, True)
        assert r.passed(), f"全填充应通过：{r.errors}"
        assert manifest.exists()

        # 2. 基线后复验 → 仍通过
        r = analyze(cases, evd, DEFAULT_DOC_ALIAS, cols, DEFAULT_CASES_SHEET, manifest, False)
        assert r.passed(), f"复验应通过：{r.errors}"

        # 3. 篡改产物 → 哈希 ERROR
        tc1 = evd / "tc1.md"
        tc1.write_text(tc1.read_text(encoding="utf-8") + "追加一行篡改\n", encoding="utf-8")
        r = analyze(cases, evd, DEFAULT_DOC_ALIAS, cols, DEFAULT_CASES_SHEET, manifest, False)
        assert not r.passed() and any("E-HASH-MISMATCH" in e for e in r.errors)

        # 4. 恢复产物，删一条 fills → 槽位未填充 ERROR
        make_artifact(evd, "tc1.md", "SYS-X-001-TC-01", cols)
        make_artifact(evd, "tc2.md", "SYS-X-002-TC-01", cols[:2])  # 少一列
        r = analyze(cases, evd, DEFAULT_DOC_ALIAS, cols, DEFAULT_CASES_SHEET, manifest, True)
        assert not r.passed() and any("E-SLOT-UNFILLED" in e for e in r.errors)

        # 5. 孤儿槽位声明 → E-SLOT-UNKNOWN
        make_artifact(evd, "tc2.md", "SYS-X-002-TC-01", cols)
        bad = make_artifact(evd, "ghost.md", "SYS-X-999-TC-01", cols)
        r = analyze(cases, evd, DEFAULT_DOC_ALIAS, cols, DEFAULT_CASES_SHEET, None, False)
        assert not r.passed() and any("E-SLOT-UNKNOWN" in e for e in r.errors)
        bad.unlink()

        # 6. 空壳产物 → E-ARTIFACT-EMPTY
        make_artifact(evd, "tc1.md", "SYS-X-001-TC-01", cols, body="空")
        r = analyze(cases, evd, DEFAULT_DOC_ALIAS, cols, DEFAULT_CASES_SHEET, None, False)
        assert not r.passed() and any("E-ARTIFACT-EMPTY" in e for e in r.errors)

    print("[SELFTEST PASS] 6 组断言全部通过")
    return 0


# ---------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="evidence_check.py",
        description="pipeline 产物 ↔ ASPICE 模板槽位 双向闭合 + 哈希防篡改校验（单文件，仅依赖 openpyxl）",
    )
    p.add_argument("--cases", type=Path, default=None, help="测试规范 .xlsx")
    p.add_argument("--evidence", type=Path, default=None, help="pipeline 产物目录（递归扫描 *.md）")
    p.add_argument("--manifest", type=Path, default=None,
                   help=f"证据清单路径（默认 <evidence>/{MANIFEST_NAME}）")
    p.add_argument("--write-manifest", action="store_true",
                   help="以当前产物重建证据清单（建立/更新基线）")
    p.add_argument("--slots", type=Path, default=None,
                   help="slots.yaml 模板槽位规格（提供后以此为准，覆盖 --sheet/--columns）")
    p.add_argument("--doc-alias", default=DEFAULT_DOC_ALIAS,
                   help=f"槽位文档别名（默认 {DEFAULT_DOC_ALIAS}）")
    p.add_argument("--sheet", default=DEFAULT_CASES_SHEET,
                   help=f"用例工作表名（默认 {DEFAULT_CASES_SHEET}）")
    p.add_argument("--columns", default=",".join(DEFAULT_EVIDENCE_COLUMNS),
                   help="证据列名，逗号分隔（默认 实际结果,测试日志链接,判定结论）")
    p.add_argument("--json", action="store_true", help="stdout 输出机器可读 JSON")
    p.add_argument("--strict", action="store_true", help="WARN 也视为失败")
    p.add_argument("--selftest", action="store_true", help="运行内置自测（不依赖外部文件）")
    return p


def _fail(message: str) -> int:
    print(f"[ERROR] {message}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.selftest:
        try:
            return run_selftest()
        except AssertionError as exc:
            print(f"[SELFTEST FAILED] {exc}", file=sys.stderr)
            return 1

    if args.cases is None or args.evidence is None:
        return _fail("--cases 与 --evidence 均为必填（--selftest 除外）")
    cases_path = Path(args.cases).expanduser()
    if not cases_path.is_file():
        return _fail(f"找不到 --cases 指定的 .xlsx：{cases_path}")
    evidence_dir = Path(args.evidence).expanduser()
    if not evidence_dir.is_dir():
        return _fail(f"找不到 --evidence 指定的目录：{evidence_dir}")

    columns = tuple(c.strip() for c in args.columns.split(",") if c.strip())
    sheet_name = args.sheet
    row_key, locator = TC_ID_HEADER, None
    fields: dict[str, str] | None = None
    vocab: dict[str, list[str]] | None = None
    if args.slots is not None:
        slots_path = Path(args.slots).expanduser()
        if not slots_path.is_file():
            return _fail(f"找不到 --slots 指定的规格文件：{slots_path}")
        try:
            spec = load_slots(slots_path, args.doc_alias)
        except ValueError as exc:
            return _fail(str(exc))
        sheet_name = spec["sheet"]
        row_key = spec["row_key"]["column"]
        locator = spec["header_locator"]["contains"]
        columns = tuple(c["name"] for c in spec["evidence_columns"])
        fields = {c["name"]: c["field"] for c in spec["evidence_columns"] if c.get("field")}
        vocab = {c["name"]: list(c["vocabulary"])
                 for c in spec["evidence_columns"] if c.get("vocabulary")}
    try:
        result = analyze(cases_path, evidence_dir, args.doc_alias, columns,
                         sheet_name, args.manifest, args.write_manifest,
                         row_key=row_key, locator=locator, fields=fields, vocab=vocab)
    except ValueError as exc:
        return _fail(str(exc))
    except Exception as exc:
        return _fail(f"分析失败：{type(exc).__name__}: {exc}")

    if args.json:
        print(json.dumps(analysis_to_dict(result, args.strict), ensure_ascii=False, indent=2))
        print(render_console(result, args.strict), file=sys.stderr)
    else:
        print(render_console(result, args.strict))
    return 0 if result.passed(args.strict) else 1


if __name__ == "__main__":
    sys.exit(main())
