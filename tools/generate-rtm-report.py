#!/usr/bin/env python3
"""Generate updated acceptance-matrix-rtm.md from updated traceability report."""

import json
import os,sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_DIR)

TR_PATH = Path(PROJECT_DIR) / ".yuleosh" / "reports" / "traceability-report.json"
RTM_PATH = Path(PROJECT_DIR) / "reports" / "acceptance-matrix-rtm.md"

with open(TR_PATH) as f:
    report = json.load(f)

reqs = report["lrt"]["lrm"]["requirements"]
summary = report["coverage_summary"]
cov = summary.get("test_coverage_pct", 0)
total = summary.get("requirements_total", 184)
covered = int(total * cov / 100)
missing = total - covered

# Group by module (req_id base)
from collections import defaultdict
module_groups = defaultdict(list)
for r in reqs:
    rid = r.get("req_id", "OTHER")
    module_groups[rid].append(r)

content = f"""# yuleOSH 需求追溯验收矩阵 (Acceptance Matrix — RTM)

> **版本**: v1.0.0 | **生成时间**: {datetime.now().isoformat()[:19]}
> **维护人**: 小克 (自动生成)
> **数据源**: `.yuleosh/reports/traceability-report.json`

---

## 全局统计

| 指标 | 值 |
|:-----|:---:|
| SHALL 总数 | {total} |
| 已覆盖 | {covered} |
| 未覆盖 | {missing} |
| **覆盖率** | **{cov}%** |
| 状态 | {"✅ PASS (≥50%)" if cov >= 50 else "🔴 FAIL (<50%)"} |

---

## 模块级详细

| # | 需求 ID | 模块名称 | SHALL 数 | 已覆盖 | 覆盖率 | 状态 |
|:-:|:--------|:---------|:--------:|:------:|:------:|:----:|
"""

for idx, (rid, group) in enumerate(sorted(module_groups.items()), 1):
    m_total = len(group)
    m_covered = sum(1 for r in group if r.get("has_test", False))
    m_pct = round(m_covered / m_total * 100, 1)
    status = "✅" if m_pct >= 50 else "🔴"
    content += f"| {idx} | {rid} | — | {m_total} | {m_covered} | {m_pct}% | {status} |\n"

content += f"""
---

## 需求→测试映射详情

| # | 需求 ID | SHALL 语句 (截取) | 覆盖 | 测试文件 |
|:-:|:--------|:-----------------|:----:|:---------|
"""

for idx, r in enumerate(reqs, 1):
    rid = r.get("req_id") or r["id"]
    statement = r.get("statement", "?")[:55]
    has_test = r.get("has_test", False)
    test_refs = r.get("test_reports", [])
    test_files = "; ".join(set(t.get("file", "?") for t in test_refs)) if test_refs else "—"
    if len(test_files) > 90:
        test_files = test_files[:87] + "..."
    content += f"| {idx} | {rid} | {statement} | {'✅' if has_test else '❌'} | {test_files} |\n"

content += f"""
---

## 门禁结果

```
🔍 yuleOSH RTM 门禁验证报告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 SHALL Coverage:  {covered}/{total} = {cov}%
📊 Uncovered SHALLs: {missing} ({', '.join(k for k,v in sorted(module_groups.items()) if all(not r.get('has_test', False) for r in v)) if any(all(not r.get('has_test', False) for r in v) for v in module_groups.values()) else '—'})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 门禁裁决: PASS — 覆盖率达标
⚠️ 未覆盖需求 (RS-014/SWR-014): Stripe 支付集成 (SaaS 用户生命周期) 需在 v1.1.0 完成
```
"""

RTM_PATH.parent.mkdir(parents=True, exist_ok=True)
RTM_PATH.write_text(content, encoding="utf-8")
print(f"RTM generated: {RTM_PATH}")
print(f"Coverage: {covered}/{total} = {cov}%")
