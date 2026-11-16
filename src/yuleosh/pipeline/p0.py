#!/usr/bin/env python3

# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""P0 步骤阻断（AUD-ASPICE-001 NC-12）。

``gates.py`` 已把 skipped/not-run 归为 ``unverified``，但整条流水线仍会
"跑完"并输出 UNVERIFIED —— 容易被读成"基本通过"。这里划出**不可降级**
的 P0 集合：需求、架构、代码、单元测试、追溯、最终报告，任一 skipped /
not-run / failed 时运行结论必须为 **failed**。

断点续跑（``--from-step``）显式跳过的前序步骤例外 —— 那是操作者主动声明的
"本段不重复验证"，其证据由被恢复的 artifacts 承担。
"""

from __future__ import annotations

#: 不可降级步骤：缺任一步的证据，本次运行不能宣称任何 ASPICE 结论。
P0_STEPS: frozenset[str] = frozenset({
    # SYS.1/SYS.2 —— 系统需求与架构（确定性，必须产出）
    "sys-requirements",
    "sys-architecture",
    # SWE.1 —— 需求
    "spec-check",
    "prd",
    "prd-review",
    # SWE.2 —— 架构
    "architecture",
    "arch-review",
    # SWE.3/4 —— 设计与实现
    "development",
    "development-review",
    "codegen-deploy",
    # SWE.5/6 —— 测试与追溯
    "verify-loop",
    # 汇总证据
    "final-report",
})

_RESUME_MARKER = "before --from-step"
_NON_EVIDENCE_STATUSES = frozenset({"skipped", "not-run", "failed"})

#: 个别 P0 步骤的失败语义已被上下游显式降级（info 档报告失败不阻断），
#: 这类步骤只把「证据缺失」视为违规，避免与既有的降级契约冲突。
_STATUS_OVERRIDES: dict[str, frozenset[str]] = {
    "final-report": frozenset({"skipped", "not-run"}),
}


def violations(entries) -> list[dict]:
    """返回 P0 违规列表。

    Parameters
    ----------
    entries : iterable of ``(step_key, status, detail)``
    """
    out: list[dict] = []
    for key, status, detail in entries:
        if key not in P0_STEPS:
            continue
        state = str(status or "").strip().lower()
        allowed = _STATUS_OVERRIDES.get(key, _NON_EVIDENCE_STATUSES)
        if state not in allowed:
            continue
        if _RESUME_MARKER in str(detail or ""):
            continue
        out.append({"step": key, "status": state, "detail": str(detail or "")})
    return out


def describe(items: list[dict]) -> str:
    return ", ".join(f"{i['step']}={i['status']}" for i in items)
