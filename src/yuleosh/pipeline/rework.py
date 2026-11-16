"""rework.py — 评审 → 生产者的返工路由（AUD-ASPICE-001 NC-01）

背景
----
旧行为：评审步骤产出 ``status=retry`` / ``failed`` 后，编排器只会记录错误或
中断整条流水线，**不会**把评审意见回灌给生产者重做。这使「多智能体协同」
退化成「一串一次性调用 + 单向门禁」。

机制
----
1. ``REWORK_ROUTES`` 声明评审步骤 → 生产步骤的返工关系；
2. ``plan_rework`` 读取评审产物中的 major/critical findings，生成一段
   约束指令，写入环境变量 ``OSH_REWORK_FINDINGS``；
3. 编排器在该环境变量存在时重跑生产者，然后重跑评审；
4. 每个评审步骤最多返工 ``MAX_REWORK_ROUNDS`` 轮，超出升级为人工介入。

该模块只做纯逻辑，便于单测；编排器的接入见 ``orchestrator._maybe_rework``。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

#: 评审步骤 → 生产者步骤（键必须是 PIPELINE_STEPS 中真实存在的 step_key）。
#: 值可以是单个 step_key，也可以是按顺序执行的生产链——内部代码评审的
#: 返工对象是「生成 → 部署」两步，只重跑 development 无法把新代码落到 src/。
REWORK_ROUTES: dict[str, str | tuple[str, ...]] = {
    "prd-review": "prd",
    "arch-review": "architecture",
    "development-review": "development",
    # MISRA 违规的修复对象是产生代码的 development 步骤
    "misra-review": "development",
    # 内部代码评审（F-08 真跑暴露）：必须重新生成并部署才有意义。
    "internal-code-review": ("development", "codegen-deploy"),
}

#: 单个评审最多返工轮数（超过则升级人工）
MAX_REWORK_ROUNDS = 2

#: 返工上下文环境变量（生产者的 prompt builder 读取）
REWORK_FINDINGS_ENV = "OSH_REWORK_FINDINGS"


def route_for(review_key: str) -> str | tuple[str, ...] | None:
    """返回评审步骤对应的生产者（单个或链）；无路由返回 None。"""
    return REWORK_ROUTES.get(review_key)


def _iter_findings(payload: dict[str, Any]):
    for key in ("static_findings", "findings", "issues"):
        items = payload.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    yield item


def read_blocking_findings(artifact_path: Path | str) -> list[dict[str, Any]]:
    """从评审产物中提取需要返工的 findings（major / critical）。

    支持 ``static_findings`` / ``findings`` / ``issues`` 三种常见字段。
    非 dict 项、缺少 severity 的项按 major 处理（保守：宁可返工）。
    """
    p = Path(artifact_path)
    if not p.is_file():
        return []
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    out: list[dict[str, Any]] = []
    for item in _iter_findings(payload):
        severity = str(item.get("severity", "major")).lower()
        if severity in ("critical", "major", "error", "high"):
            out.append(item)
    return out


def format_directive(findings: list[dict[str, Any]], round_no: int) -> str:
    """把 findings 渲染成生产者可执行的返工指令。"""
    lines = [
        "## 返工要求（上一轮评审未通过）",
        "",
        f"这是第 {round_no} 轮返工。上一轮产物存在以下问题，必须逐条修正后才能再次提交：",
        "",
    ]
    for idx, f in enumerate(findings, 1):
        rule = f.get("rule") or f.get("code") or f.get("category") or "FINDING"
        msg = f.get("message") or f.get("detail") or ""
        where = f.get("file") or f.get("artifact") or ""
        suffix = f"（位置: {where}）" if where else ""
        lines.append(f"{idx}. [{rule}] {msg}{suffix}")
    lines += [
        "",
        "修正时不得降低既有覆盖范围，也不得删除被评审的章节；"
        "若认为评审有误，必须在产物中给出明确的技术反驳与证据。",
    ]
    return "\n".join(lines)


def plan_rework(session: Any, review_key: str,
                artifact_path: Path | str) -> dict[str, Any] | None:
    """决定是否返工，并返回执行计划；不满足条件返回 None。

    计划字段：
      ``producer``   生产者 step_key（兼容旧调用方；多步时为首步）
      ``producers``  按顺序执行的生产链
      ``round``      本轮序号（1-based）
      ``findings``   阻塞性 findings
      ``env_key``    注入环境变量名
      ``context``    注入内容
    """
    route = route_for(review_key)
    if not route:
        return None
    producers = (route,) if isinstance(route, str) else tuple(route)
    if not producers:
        return None
    rounds = getattr(session, "rework_rounds", None)
    if not isinstance(rounds, dict):
        rounds = {}
        try:
            session.rework_rounds = rounds
        except Exception:  # pragma: no cover - 非 dataclass session
            return None
    used = int(rounds.get(review_key, 0))
    if used >= MAX_REWORK_ROUNDS:
        return None
    findings = read_blocking_findings(artifact_path)
    if not findings:
        return None
    round_no = used + 1
    rounds[review_key] = round_no
    return {
        "review": review_key,
        "producer": producers[0],
        "producers": list(producers),
        "round": round_no,
        "findings": findings,
        "env_key": REWORK_FINDINGS_ENV,
        "context": format_directive(findings, round_no),
    }


def directive() -> str:
    """供 prompt builder 调用：当前返工上下文（无则空串）。"""
    return os.environ.get(REWORK_FINDINGS_ENV, "").strip()


def clear() -> None:
    os.environ.pop(REWORK_FINDINGS_ENV, None)
