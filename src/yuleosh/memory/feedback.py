# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH 反馈环 (P3) — 注入埋点 / 步骤结果回采 / 自动归档。

设计 (reflective-distillation-20260819):
    ③ 反馈 Feedback: knowledge_injection._assemble_memory 埋点记录注入的
       fact_ids + step_key（memory_usage_log 表）；步骤结果回采
       （passed → trust+0.05；failed/retry → trust-0.1；封顶 0.95 /
       保底 0.05）；trust < 0.1 自动 archive（可恢复）。

回采幂等：只结算 status='injected'（未结算）的 usage 行，结算后标记为
passed/failed/retry，重复调用不会二次调整。
"""

from __future__ import annotations

import logging

from yuleosh.memory.store import MemoryStore

log = logging.getLogger("yuleosh.memory.feedback")

# 反馈调整参数（设计文档钦定）
FEEDBACK_TRUST_MAX = 0.95
FEEDBACK_TRUST_MIN = 0.05
PASS_DELTA = 0.05
FAIL_DELTA = -0.1
# trust 低于该阈值 → 自动归档（可恢复，不删）
ARCHIVE_TRUST_THRESHOLD = 0.1

VALID_STATUSES = ("passed", "failed", "retry")


def record_injection(fact_ids, step_key: str,
                     store: MemoryStore | None = None) -> int:
    """埋点：记录注入的 fact_ids + step_key（usage_log + last_used_at）。

    由 knowledge_injection._assemble_memory 在每次记忆注入时调用。
    失败非致命（记忆注入链路永不阻断）。

    Returns:
        成功记录的 usage 行数。
    """
    if not fact_ids or not step_key:
        return 0
    store = store or MemoryStore()
    n = 0
    for fid in fact_ids:
        try:
            store.record_usage(int(fid), step=step_key, status="injected")
            n += 1
        except Exception as e:  # noqa: BLE001 — 埋点永不阻断注入
            log.warning("record_injection failed for fact %s (non-fatal): %s",
                        fid, e)
    return n


def apply_step_result(step_key: str, status: str,
                      store: MemoryStore | None = None) -> int:
    """步骤结果回采：调整该 step 注入过的 facts 的 trust。

    passed   → trust + 0.05（封顶 0.95）
    failed / retry → trust - 0.1（保底 0.05）
    每次结算 +1 verified_count；trust < 0.1 → 自动 archive。

    只处理未结算（status='injected'）的 usage 行，结算后标记结果，
    幂等安全。

    Returns:
        结算的 usage 行数。
    """
    if status not in VALID_STATUSES:
        return 0
    store = store or MemoryStore()
    rows = store.list_usage(step=step_key, unsettled_only=True, limit=1000)
    if not rows:
        return 0
    delta = PASS_DELTA if status == "passed" else FAIL_DELTA
    settled = 0
    for row in rows:
        try:
            fact = store.get_fact(row["fact_id"])
            if fact is None:
                store.mark_usage_settled(row["id"], status)
                continue
            new_trust = max(FEEDBACK_TRUST_MIN,
                            min(FEEDBACK_TRUST_MAX,
                                float(fact["trust"]) + delta))
            store.update_trust(fact["id"], new_trust)
            store.increment_verified(fact["id"])
            if new_trust < ARCHIVE_TRUST_THRESHOLD:
                store.archive_fact(fact["id"])
            store.mark_usage_settled(row["id"], status)
            settled += 1
        except Exception as e:  # noqa: BLE001 — 回采失败不致命
            log.warning("apply_step_result failed for usage %s (non-fatal): %s",
                        row["id"], e)
    return settled
