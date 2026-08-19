# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH 反思器 (P2) — 冲突检测 / 来源可靠性解决 / 过时归档。

设计 (reflective-distillation-20260819):
    ② 反思 Reflect: 候选 vs 现有 facts 冲突检测（LLM 判断 + 关键词）；
       冲突解决按来源可靠性分级（human > external > llm）；默认新胜，
       旧记忆 trust > 0.8 时保留旧的并降权新的；过时检测（最近使用为空
       + 超阈值天数 → 降级 archive 不删）。

确定性实现优先（关键词/数字/否定词检测），可选 ``llm_judge`` 增强。
所有归档操作可恢复（``MemoryStore.unarchive_fact``）。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from yuleosh.memory.distill import DistillCandidate, similarity
from yuleosh.memory.store import MemoryStore, normalize_text

log = logging.getLogger("yuleosh.memory.reflect")

# 来源可靠性分级（数字越大越可靠）
RELIABILITY_RANK = {"human": 3, "external": 2, "llm": 1}
# 高信任保留阈值：旧记忆 trust 超过它时新候选降权
KEEP_OLD_TRUST = 0.8
# 降权新候选的信任上限
DOWNGRADE_NEW_TRUST = 0.4
# 过时默认阈值（天）
DEFAULT_MAX_AGE_DAYS = 30

# 否定/冲突信号词（确定性冲突检测）
_NEGATION_MARKERS = ("不", "禁止", "不要", "勿", "无", "非", "失败", "错误", "停止")


def _detect_conflict(cand: DistillCandidate, fact: dict,
                     min_sim: float = 0.5) -> bool:
    """确定性冲突检测：同 entity + 内容相似但数字或否定语义矛盾。

    规则（语义信号优先于重复判定）：
    - 相似度 < min_sim → 无关，非冲突；
    - 数字集合不同（其余相似）→ 冲突；
    - 否定词出现与否翻转（其余相似）→ 冲突；
    - 其余高度相似（≥0.9）→ 纯重复（去重管），非冲突。
    """
    if not cand.entity or not fact.get("entity"):
        return False
    if normalize_text(cand.entity) != normalize_text(str(fact.get("entity", ""))):
        return False
    sim = similarity(cand.content, str(fact.get("content", "")))
    if sim < min_sim:
        return False

    nums_c = set(re.findall(r"\d+(?:\.\d+)?", cand.content))
    nums_f = set(re.findall(r"\d+(?:\.\d+)?", str(fact.get("content", ""))))
    if nums_c and nums_f and nums_c != nums_f:
        return True

    c_neg = any(m in cand.content for m in _NEGATION_MARKERS)
    f_neg = any(m in str(fact.get("content", "")) for m in _NEGATION_MARKERS)
    if c_neg != f_neg:
        return True

    if sim >= 0.9:
        return False  # 纯重复
    return False


def _reliability_rank(value: str | None) -> int:
    return RELIABILITY_RANK.get((value or "llm").lower(), 1)


class Reflector:
    """反思器：候选 vs 现有 facts → 冲突/过时 → 解决动作 → 应用。"""

    def __init__(self, store: MemoryStore | None = None,
                 llm_judge=None, project_dir: str | Path | None = None):
        self._store = store or MemoryStore()
        self._llm_judge = llm_judge  # 可选增强: (cand, fact) -> bool conflict
        self._project_dir = Path(project_dir) if project_dir else Path.cwd()

    # ── 冲突检测 ──────────────────────────────────────────────────────

    def detect_conflicts(self, candidates: list[DistillCandidate],
                         limit: int = 500) -> list[dict]:
        """候选 vs 同 entity 的现有 active facts 冲突对。"""
        conflicts: list[dict] = []
        seen: set = set()
        for cand in candidates:
            if not cand.entity:
                continue
            for f in self._store.list_facts(entity=cand.entity,
                                            include_archived=False,
                                            limit=limit):
                key = (cand.content, f["id"])
                if key in seen:
                    continue
                seen.add(key)
                if _detect_conflict(cand, f):
                    conflicts.append({"candidate": cand, "fact": f})
                    continue
                if self._llm_judge is not None:
                    try:
                        if self._llm_judge(cand, f):
                            conflicts.append({"candidate": cand, "fact": f})
                    except Exception as e:  # noqa: BLE001 — judge 失败不致命
                        log.warning("LLM conflict judge failed (non-fatal): %s", e)
        return conflicts

    # ── 冲突解决 ──────────────────────────────────────────────────────

    def resolve(self, conflicts: list[dict]) -> list[dict]:
        """按来源可靠性 + 信任解决冲突，产出动作列表。

        动作类型:
        - archive_old   : 归档旧 fact（新胜 / 可靠性更高）
        - insert_new    : 插入新候选（新胜路径；由调用方负责插入）
        - downgrade_new : 降权新候选（旧信任高或旧更可靠 → 保留旧）
        """
        actions: list[dict] = []
        for cf in conflicts:
            cand, fact = cf["candidate"], cf["fact"]
            c_rank = _reliability_rank(cand.source_reliability)
            f_rank = _reliability_rank(fact.get("source_reliability"))
            f_trust = float(fact.get("trust", 0.0) or 0.0)
            if c_rank > f_rank:
                actions.append({
                    "type": "archive_old", "fact_id": fact["id"],
                    "reason": f"new reliability {cand.source_reliability} > "
                              f"old {fact.get('source_reliability', 'llm')}",
                })
                actions.append({"type": "insert_new", "candidate": cand,
                                "fact_id_old": fact["id"]})
            elif c_rank == f_rank:
                if f_trust > KEEP_OLD_TRUST:
                    actions.append({
                        "type": "downgrade_new", "candidate": cand,
                        "fact_id_old": fact["id"],
                        "reason": f"old trust {f_trust:.2f} > {KEEP_OLD_TRUST}",
                    })
                else:
                    actions.append({
                        "type": "archive_old", "fact_id": fact["id"],
                        "reason": "default new wins (equal reliability)",
                    })
                    actions.append({"type": "insert_new", "candidate": cand,
                                    "fact_id_old": fact["id"]})
            else:
                actions.append({
                    "type": "downgrade_new", "candidate": cand,
                    "fact_id_old": fact["id"],
                    "reason": f"old reliability {fact.get('source_reliability', 'llm')} "
                              f"> new {cand.source_reliability}",
                })
        return actions

    # ── 过时检测 ──────────────────────────────────────────────────────

    def detect_obsolete(self, max_age_days: int = DEFAULT_MAX_AGE_DAYS,
                        limit: int = 2000) -> list[dict]:
        """最近使用为空 + 超阈值天数 → 归档（不删）。"""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)
                  ).isoformat(timespec="seconds")
        out: list[dict] = []
        for f in self._store.list_facts(include_archived=False, limit=limit):
            if f.get("last_used_at") or int(f.get("recall_count", 0) or 0) > 0:
                continue
            created = f.get("created_at") or ""
            if created and created < cutoff:
                out.append({
                    "type": "archive_obsolete",
                    "fact_id": f["id"],
                    "reason": f"never used, created {created}",
                })
        return out

    # ── 应用 ──────────────────────────────────────────────────────────

    def apply(self, actions: list[dict]) -> dict:
        """执行动作（归档 / 插入新候选 / 降权插入）。"""
        stats = {"archived": 0, "inserted": 0, "downgraded": 0}
        for a in actions:
            t = a["type"]
            if t in ("archive_old", "archive_obsolete"):
                if self._store.archive_fact(a["fact_id"]):
                    stats["archived"] += 1
            elif t == "insert_new":
                cand: DistillCandidate = a["candidate"]
                self._store.remember(
                    content=cand.content,
                    entity=cand.entity,
                    category=cand.category,
                    trust=cand.trust,
                    tags=f"distilled:{cand.kind}",
                    source=cand.source_session,
                    source_reliability=cand.source_reliability,
                    distilled_at=cand.distilled_at,
                )
                stats["inserted"] += 1
            elif t == "downgrade_new":
                cand = a["candidate"]
                self._store.remember(
                    content=cand.content,
                    entity=cand.entity,
                    category=cand.category,
                    trust=min(cand.trust, DOWNGRADE_NEW_TRUST),
                    tags=f"distilled:{cand.kind}:downgraded",
                    source=cand.source_session,
                    source_reliability=cand.source_reliability,
                    distilled_at=cand.distilled_at,
                )
                stats["downgraded"] += 1
        return stats

    # ── 主入口 ────────────────────────────────────────────────────────

    def reflect(self, candidates: list[DistillCandidate],
                max_age_days: int = DEFAULT_MAX_AGE_DAYS,
                dry_run: bool = False) -> dict:
        """执行反思：冲突检测 → 解决 + 过时检测 → 应用（dry_run 不写库）。"""
        conflicts = self.detect_conflicts(candidates)
        actions = self.resolve(conflicts)
        obsolete = self.detect_obsolete(max_age_days=max_age_days)
        all_actions = actions + obsolete
        summary = {
            "conflicts": len(conflicts),
            "obsolete": len(obsolete),
            "actions": len(all_actions),
            "dry_run": dry_run,
            "archived": 0,
            "inserted": 0,
            "downgraded": 0,
        }
        if not dry_run and all_actions:
            applied = self.apply(all_actions)
            summary.update(applied)
        return summary
