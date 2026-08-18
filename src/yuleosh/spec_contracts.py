#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Spec contract extraction & integrity checking (方案 A: 契约抽取器).

2026-08-16: 长 spec 固定截断导致下游 LLM 看不到尾部契约 (window-anti-pinch
连续 3 轮 RED: codegen PRD[:4000] 只见头部 FR, claude-review artifacts[:8000]
只见 FR-041 之前). 治本方案 = 把「契约」从叙述性 spec 中抽取为机器可读
JSON, 供:

  1. spec-check 步骤做确定性完整性校验 (护栏条数/接口数/参数数/NVM 布局),
     不通过直接 RED — 防回归从 LLM 人审迁移到机器检查;
  2. codegen/PRD/评审 prompt 注入全量契约 (契约永不随 spec 正文增长丢失).

抽取规则 (约定式, spec 中「声明了契约节就必须完整」):
  - §1.5 接口契约: `### <name>.h` 标题 + ```c``` 块 → 头文件 + 函数签名
  - §2.5 行为护栏: `| G-xx | ... |` 表格行
  - SW-008 参数边界: 列头含 参数/默认/min/max 的表格行
  - SW-006 NVM 布局: `magic=`/`version=`/`maxClosePulses`/`maxOpenPulses`
  - 需求覆盖: `### SR-xxx` / `### SW-xxx` 段存在性
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger("yuleosh.spec_contracts")

# ------------------------------------------------------------------
# 抽取器
# ------------------------------------------------------------------


def extract_contracts(spec_path: str) -> dict:
    """Extract machine-readable contracts from a spec markdown file.

    Returns a dict with keys: interfaces, guardrails, params, nvm_layout,
    requirements, spec_size. Never raises on malformed specs — extraction
    is best-effort; integrity is judged by validate_contracts().
    """
    path = Path(spec_path)
    if not path.exists():
        return {"error": f"spec not found: {spec_path}"}

    content = path.read_text(encoding="utf-8", errors="ignore")
    lines = content.split("\n")

    return {
        "spec_size": len(content),
        "interfaces": _extract_interfaces(content, lines),
        "guardrails": _extract_guardrails(lines),
        "params": _extract_params(lines),
        "nvm_layout": _extract_nvm_layout(content),
        "requirements": _extract_requirement_ids(lines),
    }


def _extract_interfaces(content: str, lines: list[str]) -> list[dict]:
    """Extract header-file contract blocks (`### name.h` + ```c```)."""
    interfaces: list[dict] = []
    current_header: str | None = None
    in_c_block = False
    c_lines: list[str] = []

    header_re = re.compile(r"^#{2,4}\s+([A-Za-z0-9_]+\.h)\b")
    for line in lines:
        stripped = line.strip()
        m = header_re.match(stripped)
        if m:
            # flush previous
            if current_header and c_lines:
                interfaces.append({
                    "header": current_header,
                    "signatures": _signatures_from_c_block(c_lines),
                })
            current_header = m.group(1)
            c_lines = []
            in_c_block = False
            continue
        if stripped.startswith("```"):
            if in_c_block:
                # flush block for current header
                if current_header and c_lines:
                    interfaces.append({
                        "header": current_header,
                        "signatures": _signatures_from_c_block(c_lines),
                    })
                in_c_block = False
                c_lines = []
            else:
                in_c_block = True
            continue
        if in_c_block and current_header:
            c_lines.append(line)

    # flush trailing
    if current_header and c_lines:
        interfaces.append({
            "header": current_header,
            "signatures": _signatures_from_c_block(c_lines),
        })
    return interfaces


def _signatures_from_c_block(c_lines: list[str]) -> list[str]:
    """Extract function-signature-like lines from a C block.

    Accepts lines starting with a C type keyword and ending with ';' or ')'.
    Drops preprocessor directives, comments, and pure declarations.
    """
    sigs: list[str] = []
    for raw in c_lines:
        line = raw.strip()
        if not line or line.startswith(("#", "//", "/*", "*")):
            continue
        # join multi-line signatures up to ';'
        if not line.endswith(";") and not line.endswith(")"):
            continue
        if line.startswith(("typedef", "struct", "enum", "#define")):
            # keep enum/typedef names only when they look like API contracts
            if not line.startswith(("typedef enum", "typedef struct")):
                continue
        sigs.append(line.rstrip(";").strip())
    return sigs


def _extract_guardrails(lines: list[str]) -> list[str]:
    """Extract guardrail IDs (`| G-01 | ... |`) from markdown tables."""
    guardrails: list[str] = []
    guardrail_re = re.compile(r"^\|\s*(G-\d{2})\s*\|")
    for line in lines:
        m = guardrail_re.match(line.strip())
        if m:
            guardrails.append(m.group(1))
    return sorted(set(guardrails))


def _extract_params(lines: list[str]) -> list[dict]:
    """Extract config parameter rows from a bounds table.

    Table is detected by a header row containing 参数 + min + max (or
    English equivalents). Rows: `| name | default | min | max |`.
    Guardrail tables (§2.5, `| G-xx |`) are excluded.
    """
    params: list[dict] = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|"):
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if not in_table:
                joined = " ".join(cols).lower()
                if ("min" in joined and "max" in joined
                        and ("参数" in joined or "default" in joined or "默认" in joined)):
                    in_table = True
                continue
            if len(cols) >= 4 and cols[0] and not cols[0].startswith(":"):
                # Skip guardrail rows (`| G-01 | ... |`) — they are §2.5
                # behavioral guardrails, not config bounds
                if re.match(r"^G-\d{2}$", cols[0]):
                    continue
                params.append({
                    "name": cols[0],
                    "default": cols[1] if len(cols) > 1 else "",
                    "min": cols[2] if len(cols) > 2 else "",
                    "max": cols[3] if len(cols) > 3 else "",
                })
        else:
            in_table = False
    return params


def _extract_nvm_layout(content: str) -> dict:
    """Extract NVM calibration record layout markers from spec content."""
    layout: dict = {}
    magic = re.search(r"magic\s*=\s*(0x[0-9A-Fa-f]+)", content)
    version = re.search(r"\[4\]\s*version\s*=\s*(\d+)", content)
    max_close = re.search(r"maxClosePulses", content)
    max_open = re.search(r"maxOpenPulses", content)
    byte_count = re.search(r"共\s*(\d+)\s*字节", content)
    if magic:
        layout["magic"] = magic.group(1)
    if version:
        layout["version"] = version.group(1)
    if max_close:
        layout["maxClosePulses"] = True
    if max_open:
        layout["maxOpenPulses"] = True
    if byte_count:
        layout["record_bytes"] = int(byte_count.group(1))
    return layout


def _extract_requirement_ids(lines: list[str]) -> list[str]:
    """Extract requirement section IDs (`### SR-001` / `### SW-004`)."""
    ids: list[str] = []
    req_re = re.compile(r"^#{2,4}\s+([A-Za-z]{2,4}-\d+)\b")
    for line in lines:
        m = req_re.match(line.strip())
        if m:
            ids.append(m.group(1))
    return ids


# ------------------------------------------------------------------
# 完整性校验
# ------------------------------------------------------------------

# 约定式最低标准: spec 声明了契约节就必须满足 (2026-08-16 契约化)
MIN_INTERFACES = 8          # hal_hall/hal_motor/hal_timer/hal_nvm + 4 应用头文件
MIN_GUARDRAILS = 1          # 声明了 §2.5 就至少 1 条 (window-anti-pinch 12 条)
MIN_PARAMS = 1              # 声明了边界表就至少 1 参数


def validate_contracts(contracts: dict, required: dict | None = None) -> dict:
    """Validate extracted contracts against integrity expectations.

    required: optional override — e.g. {"guardrails": 12, "interfaces": 8,
    "params": 14, "nvm": true}. When absent, uses presence-based defaults:
    if a contract category is present in the spec, it must meet the minimum.

    Returns {"passed": bool, "missing": [...], "details": {...}}.
    """
    if "error" in contracts:
        return {"passed": False, "missing": [contracts["error"]], "details": {}}

    missing: list[str] = []
    details: dict = {}

    interfaces = contracts.get("interfaces", [])
    guardrails = contracts.get("guardrails", [])
    params = contracts.get("params", [])
    nvm = contracts.get("nvm_layout", {})

    # 接口契约: 声明了 §1.5 就必须有完整头文件集合
    if required:
        want_iface = required.get("interfaces", MIN_INTERFACES)
        details["interfaces"] = {"found": len(interfaces), "want": want_iface,
                                 "headers": [i["header"] for i in interfaces]}
        if len(interfaces) < want_iface:
            missing.append(
                f"interface contracts: {len(interfaces)}/{want_iface} headers "
                f"({[i['header'] for i in interfaces]})"
            )
    else:
        details["interfaces"] = {"found": len(interfaces),
                                 "headers": [i["header"] for i in interfaces]}
        if interfaces and len(interfaces) < MIN_INTERFACES:
            missing.append(
                f"interface contracts: {len(interfaces)} < {MIN_INTERFACES} "
                f"({[i['header'] for i in interfaces]})"
            )

    # 行为护栏: 声明了 §2.5 就必须逐条存在 (无合并/省略)
    want_guardrails = required.get("guardrails", len(guardrails)) if required else len(guardrails)
    details["guardrails"] = {"found": len(guardrails), "want": want_guardrails,
                             "ids": guardrails}
    if guardrails and len(guardrails) < want_guardrails:
        missing.append(f"guardrails: {len(guardrails)}/{want_guardrails} ({guardrails})")
    if required and "guardrail_ids" in required:
        want_ids = set(required["guardrail_ids"])
        have_ids = set(guardrails)
        absent = sorted(want_ids - have_ids)
        if absent:
            missing.append(f"guardrails missing: {absent}")

    # 参数边界表
    want_params = required.get("params", len(params)) if required else len(params)
    details["params"] = {"found": len(params), "want": want_params,
                         "names": [p["name"] for p in params]}
    if params and len(params) < want_params:
        missing.append(f"config params: {len(params)}/{want_params} ({[p['name'] for p in params]})")
    if required and "param_names" in required:
        want_pnames = set(required["param_names"])
        have_pnames = set(p["name"] for p in params)
        absent = sorted(want_pnames - have_pnames)
        if absent:
            missing.append(f"config params missing: {absent}")

    # NVM 布局
    details["nvm_layout"] = nvm
    if required and required.get("nvm"):
        nvm_want = {"magic", "version", "maxClosePulses", "maxOpenPulses"}
        absent = sorted(nvm_want - set(nvm.keys()))
        if absent:
            missing.append(f"NVM layout missing: {absent}")
    elif nvm and not nvm.get("record_bytes"):
        # 有 NVM 契约但没写字节数 → 视为不完整 (13 字节是 SW-006 契约)
        missing.append("NVM layout missing record byte count")

    return {
        "passed": len(missing) == 0,
        "missing": missing,
        "details": details,
    }


def contracts_check(spec_path: str, required: dict | None = None) -> dict:
    """One-shot extraction + validation, ready for spec-check step output."""
    contracts = extract_contracts(spec_path)
    validation = validate_contracts(contracts, required=required)
    return {
        "contracts": contracts,
        "validation": validation,
    }


def extract_contracts_dir(spec_dir: str) -> dict:
    """Extract contracts from an OpenSpec directory (all capability specs).

    Aggregates ``<dir>/*/spec.md`` (OpenSpec capability layout) or flat
    ``*.md`` fallback, merging interfaces/guardrails/params/requirements
    across files. Returns the same shape as :func:`extract_contracts` with
    ``files`` listing the aggregated sources.

    Never raises on malformed specs — extraction is best-effort.
    """
    from yuleosh.spec.validate import find_spec_files

    files = find_spec_files(spec_dir)
    if not files:
        return {
            "error": f"no spec files found under directory: {spec_dir}",
            "files": [],
        }

    merged: dict = {
        "spec_size": 0,
        "interfaces": [],
        "guardrails": [],
        "params": [],
        "nvm_layout": {},
        "requirements": [],
        "files": files,
    }

    seen_guardrails: set[str] = set()
    seen_params: set[str] = set()
    seen_reqs: set[str] = set()

    for f in files:
        contracts = extract_contracts(f)
        if "error" in contracts:
            continue
        merged["spec_size"] += contracts.get("spec_size", 0)
        merged["interfaces"].extend(contracts.get("interfaces", []))
        for g in contracts.get("guardrails", []):
            gid = g.get("id") or str(g)
            if gid not in seen_guardrails:
                seen_guardrails.add(gid)
                merged["guardrails"].append(g)
        for p in contracts.get("params", []):
            pname = p.get("name") or str(p)
            if pname not in seen_params:
                seen_params.add(pname)
                merged["params"].append(p)
        for r in contracts.get("requirements", []):
            if r not in seen_reqs:
                seen_reqs.add(r)
                merged["requirements"].append(r)

        nvm = contracts.get("nvm_layout") or {}
        if nvm and not merged["nvm_layout"]:
            merged["nvm_layout"] = nvm

    return merged


def contracts_check_dir(spec_dir: str, required: dict | None = None) -> dict:
    """One-shot directory extraction + validation for spec-check step output."""
    contracts = extract_contracts_dir(spec_dir)
    validation = validate_contracts(contracts, required=required)
    return {
        "contracts": contracts,
        "validation": validation,
        "mode": "directory",
    }


def main(argv: list[str] | None = None) -> int:
    """CLI: python -m yuleosh.spec_contracts <spec.md> [--json]"""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Extract & validate spec contracts")
    parser.add_argument("spec_path", help="Path to spec.md")
    parser.add_argument("--json", action="store_true", help="Output raw JSON (no exit-code semantics)")
    parser.add_argument("--required", default="", help="JSON string with required overrides")
    args = parser.parse_args(argv)

    required = None
    if args.required:
        try:
            required = json.loads(args.required)
        except json.JSONDecodeError:
            print(f"invalid --required JSON: {args.required}", file=sys.stderr)
            return 2

    if Path(args.spec_path).is_dir():
        result = contracts_check_dir(args.spec_path, required=required)
    else:
        result = contracts_check(args.spec_path, required=required)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    v = result["validation"]
    print(f"Contracts check: {'PASS' if v['passed'] else 'FAIL'}")
    print(f"  spec size: {result['contracts'].get('spec_size', 0)} chars")
    iface = v["details"].get("interfaces", {})
    print(f"  interfaces: {iface.get('found', 0)} headers {iface.get('headers', [])}")
    gr = v["details"].get("guardrails", {})
    print(f"  guardrails: {gr.get('found', 0)} {gr.get('ids', [])}")
    pm = v["details"].get("params", {})
    print(f"  params: {pm.get('found', 0)} {pm.get('names', [])}")
    print(f"  nvm_layout: {v['details'].get('nvm_layout', {})}")
    if v["missing"]:
        print("  MISSING:")
        for m in v["missing"]:
            print(f"    - {m}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
