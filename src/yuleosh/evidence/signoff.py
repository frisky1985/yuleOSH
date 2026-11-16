#!/usr/bin/env python3

# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""电子签批（AUD-ASPICE-001 NC-09）。

CL2 评估要求关键基线（需求 / 架构）由**具名责任人**签批，且签批必须绑定
到被签批产物的内容摘要 —— 否则"先签后改"无法被发现。本模块提供：

- ``record_signoff(...)``：记录签批（签批人、角色、决策、时间、产物 SHA-256），
  并可选打 git tag，形成不可否认的时间锚点；
- ``write_recommendation(...)``：独立 agent 的**预审建议**（无放行权）；
- ``verify_signoffs(...)``：校验签批是否仍有效（决策 approved 且产物摘要未变）；
- ``required_signoff_status(...)``：给门禁结论用的 G1/G2 签批状态。

签批记录落盘于 ``<project>/.osh/signoffs/<gate>.json``（追加历史）。缺少签批
时，运行结论为 ``awaiting-signoff``（不是 green，也不是 red）—— 自动化只能
把证据准备到位，放行必须由人完成。

责任分层（2026-11-16）: **agent 有否决权，没有放行权**。
``write_recommendation`` 产出 ``recommend-approve`` / ``recommend-reject``，
人签批时可通过 ``based_on_recommendation`` 引用该文件（记录其 SHA-256，形成
"agent 预审 → 人批准" 的可审计链）。若预审为 reject 而人仍批准，必须填写
``override_reason``；agent 身份前缀（agent:/ai:/bot: …）不得作为签批人。
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("evidence.signoff")

SCHEMA = "yuleosh-signoff/v1"
RECOMMENDATION_SCHEMA = "yuleosh-signoff-recommendation/v1"

#: CL2 必须人工签批的基线门禁
REQUIRED_GATES: tuple[str, ...] = ("G1", "G2")

DECISIONS = ("approved", "rejected", "conditional")
RECOMMENDATION_VERDICTS = ("recommend-approve", "recommend-reject")

#: 不得作为签批人的身份前缀 —— 批准权不可委托（CL2 责任分层）。
AGENT_IDENTITY_PREFIXES = ("agent:", "agent/", "ai:", "ai/", "bot:",
                           "bot/", "llm:", "robot:")


def is_agent_identity(who) -> bool:
    """判定 ``who`` 是否是 agent/工具身份（非人类签批人）。"""
    s = str(who or "").strip().lower()
    return any(s.startswith(p) for p in AGENT_IDENTITY_PREFIXES)


def signoff_dir(project_dir) -> Path:
    return Path(project_dir) / ".osh" / "signoffs"


def artifact_digest(path) -> str:
    """产物内容摘要（SHA-256）。文件不存在时返回空串，由调用方判错。"""
    try:
        p = Path(path)
        if not p.is_file():
            return ""
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def _history_path(project_dir, gate: str) -> Path:
    return signoff_dir(project_dir) / f"{gate}.json"


# ── agent 预审建议（无放行权）────────────────────────────────────────────

def recommendation_dir(project_dir) -> Path:
    return Path(project_dir) / ".osh" / "evidence"


def write_recommendation(project_dir, gate: str, artifacts=(),
                         agent: str = "yuleosh:independent-verifier",
                         verdict: str = "recommend-approve",
                         blocking: Optional[list[str]] = None,
                         residual_risks: Optional[list[str]] = None,
                         independence: str = "none",
                         notes: str = "") -> Path:
    """写一份 agent 预审建议，返回落盘路径。

    文件名带时间戳 + 短随机后缀，**每次调用生成新文件**：人签批引用的是
    "当时那一份"建议，后续运行重新生成不会让已签批记录失效。

    Raises
    ------
    ValueError
        决策非法或 gate 为空。
    """
    gate = str(gate).strip().upper()
    if not gate:
        raise ValueError("gate id is required")
    verdict = str(verdict).strip().lower()
    if verdict not in RECOMMENDATION_VERDICTS:
        raise ValueError(
            f"verdict must be one of {RECOMMENDATION_VERDICTS}, got {verdict!r}")

    entries: list[dict] = []
    missing: list[str] = []
    for path in artifacts or ():
        digest = artifact_digest(path)
        if not digest:
            missing.append(str(path))
            continue
        entries.append({"path": str(path), "sha256": digest})
    blocking_items = [str(b) for b in (blocking or [])]
    blocking_items += [f"artifact missing or unreadable: {p}" for p in missing]
    if blocking_items and verdict == "recommend-approve":
        # 有阻断项却给 approve 是自相矛盾的建议 —— 直接改写为 reject。
        verdict = "recommend-reject"

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = recommendation_dir(project_dir) / (
        f"signoff-recommendation-{gate}-{stamp}-{uuid.uuid4().hex[:6]}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema": RECOMMENDATION_SCHEMA,
        "gate": gate,
        "generated_at": datetime.now().isoformat(),
        "generated_by": str(agent or "yuleosh:independent-verifier"),
        "independence": str(independence or "none"),
        "verdict": verdict,
        "artifacts": entries,
        "blocking_items": blocking_items,
        "residual_risks": [str(r) for r in (residual_risks or [])],
        "notes": str(notes or ""),
        "release_authority": "none",
        "authority_note": ("本文件仅为 agent 预审建议，不构成批准；"
                           "基线放行须由具名责任人电子签批（approved）。"),
    }
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    log.info("Sign-off recommendation written: %s (%s)", path, verdict)
    return path


def recommendation_history(project_dir, gate: str) -> list[Path]:
    """按文件名（即时间）升序列出该门的预审建议文件。"""
    root = recommendation_dir(project_dir)
    if not root.is_dir():
        return []
    return sorted(root.glob(f"signoff-recommendation-{str(gate).upper()}-*.json"))


def latest_recommendation(project_dir, gate: str) -> Optional[Path]:
    items = recommendation_history(project_dir, gate)
    return items[-1] if items else None


def load_recommendation(path) -> dict:
    """读取预审建议；非法 JSON 抛 ``ValueError``。"""
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable recommendation: {p} ({exc})") from exc
    if not isinstance(data, dict) or data.get("schema") != RECOMMENDATION_SCHEMA:
        raise ValueError(f"not a {RECOMMENDATION_SCHEMA} document: {p}")
    return data


def history(project_dir, gate: str) -> list[dict]:
    path = _history_path(project_dir, gate)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def record_signoff(project_dir, gate: str, artifact_path,
                   reviewer: str, role: str = "reviewer",
                   decision: str = "approved", comment: str = "",
                   tag: bool = True,
                   based_on_recommendation=None,
                   override_reason: str = "") -> dict:
    """记录一次签批。返回记录 dict（已落盘）。

    ``based_on_recommendation`` 指向 agent 预审建议文件时，记录会绑定该文件的
    SHA-256（"agent 预审 → 人批准" 的可审计链）；若预审结论为
    ``recommend-reject`` 而人仍批准，必须提供 ``override_reason``。

    Raises
    ------
    ValueError
        缺少签批人、签批人是 agent 身份、决策非法、产物不存在（无法绑定摘要），
        预审建议不可读，或否决后批准却未写理由。
    """
    gate = str(gate).strip().upper()
    if not gate:
        raise ValueError("gate id is required")
    reviewer = str(reviewer).strip()
    if not reviewer:
        raise ValueError("reviewer identity is required for an electronic signature")
    if is_agent_identity(reviewer):
        raise ValueError(
            f"agent identity {reviewer!r} cannot sign a baseline: an electronic "
            "sign-off requires an accountable human. Use write_recommendation() "
            "for the agent pre-review and have a named person approve it.")
    decision = str(decision).strip().lower()
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}, got {decision!r}")

    digest = artifact_digest(artifact_path)
    if not digest:
        raise ValueError(f"artifact not found or unreadable: {artifact_path}")

    basis: Optional[dict] = None
    if based_on_recommendation:
        rec_path = Path(based_on_recommendation)
        rec = load_recommendation(rec_path)  # ValueError on unreadable
        rec_digest = artifact_digest(rec_path)
        if not rec_digest:
            raise ValueError(f"recommendation unreadable: {rec_path}")
        basis = {
            "path": str(rec_path),
            "sha256": rec_digest,
            "verdict": rec.get("verdict", ""),
            "generated_by": rec.get("generated_by", ""),
            "independence": rec.get("independence", ""),
        }
        if rec.get("verdict") == "recommend-reject" and decision == "approved" \
                and not str(override_reason).strip():
            raise ValueError(
                "agent pre-review returned recommend-reject; approving it "
                "requires a non-empty override_reason (risk acceptance)")

    record = {
        "schema": SCHEMA,
        "gate": gate,
        "artifact": str(artifact_path),
        "artifact_sha256": digest,
        "reviewer": reviewer,
        "role": str(role or "reviewer"),
        "decision": decision,
        "comment": str(comment or ""),
        "signed_at": datetime.now().isoformat(),
        "commit": _git_head(project_dir),
        "tag": _create_tag(project_dir, gate, reviewer) if tag else "",
    }
    if basis is not None:
        record["recommendation"] = basis
    if str(override_reason or "").strip():
        record["override_reason"] = str(override_reason).strip()

    path = _history_path(project_dir, gate)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = history(project_dir, gate)
    entries.append(record)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    log.info("Sign-off recorded: %s by %s (%s)", gate, reviewer, decision)
    return record


def latest(project_dir, gate: str) -> Optional[dict]:
    entries = history(project_dir, gate)
    return entries[-1] if entries else None


def verify_gate(project_dir, gate: str, artifact_path=None) -> dict:
    """校验某门的签批是否有效。

    有效 = 存在记录 ∧ 最近一次决策为 approved ∧ 产物摘要与记录一致。
    ``artifact_path`` 省略时用记录中登记的产物路径。
    """
    gate = str(gate).strip().upper()
    record = latest(project_dir, gate)
    if not record:
        return {"gate": gate, "signed": False, "reason": "no sign-off record"}

    if record.get("decision") != "approved":
        return {
            "gate": gate,
            "signed": False,
            "reason": f"latest decision is {record.get('decision')!r}",
            "reviewer": record.get("reviewer"),
        }

    target = artifact_path or record.get("artifact")
    current = artifact_digest(target)
    if not current:
        return {"gate": gate, "signed": False,
                "reason": f"signed artifact missing: {target}"}
    if current != record.get("artifact_sha256"):
        return {
            "gate": gate,
            "signed": False,
            "reason": "artifact changed after sign-off (digest mismatch)",
            "reviewer": record.get("reviewer"),
        }

    # 预审建议是签批的举证基础；被删除或改写即视为证据链断裂 —— 不能拿
    # 一份"人签的是 A、基础却已变成 B"的记录去应付评估。
    basis = record.get("recommendation") or {}
    basis_info: dict = {}
    if basis:
        basis_info = {"path": basis.get("path"),
                      "verdict": basis.get("verdict"),
                      "generated_by": basis.get("generated_by")}
        current_basis = artifact_digest(basis.get("path"))
        if not current_basis:
            return {
                "gate": gate,
                "signed": False,
                "reason": "sign-off basis (agent recommendation) is missing",
                "reviewer": record.get("reviewer"),
                "basis": basis_info,
            }
        if current_basis != basis.get("sha256"):
            return {
                "gate": gate,
                "signed": False,
                "reason": "agent recommendation changed after sign-off "
                          "(digest mismatch)",
                "reviewer": record.get("reviewer"),
                "basis": basis_info,
            }
        basis_info["intact"] = True

    return {
        "gate": gate,
        "signed": True,
        "reason": "approved and digest matches",
        "reviewer": record.get("reviewer"),
        "role": record.get("role"),
        "signed_at": record.get("signed_at"),
        "tag": record.get("tag", ""),
        "basis": basis_info,
        "override_reason": record.get("override_reason", ""),
    }


def required_signoff_status(project_dir,
                            gates: tuple[str, ...] = REQUIRED_GATES) -> dict:
    """返回 ``{gate: verify_gate(...)}``，供门禁结论聚合。"""
    if not project_dir:
        return {g: {"gate": g, "signed": False,
                    "reason": "project directory unknown"} for g in gates}
    return {g: verify_gate(project_dir, g) for g in gates}


def _git_head(project_dir) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(project_dir), capture_output=True, text=True, timeout=10,
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except Exception:  # noqa: BLE001 — 非 git 工程
        return ""


def _create_tag(project_dir, gate: str, reviewer: str) -> str:
    """创建不可否认的时间锚点 tag；失败只告警（非 git 工程/重复 tag）。"""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_reviewer = "".join(ch if ch.isalnum() else "-" for ch in reviewer)[:24]
    name = f"aspice/{gate.lower()}-{stamp}-{safe_reviewer}"
    try:
        proc = subprocess.run(
            ["git", "tag", "-a", name, "-m",
             f"ASPICE {gate} sign-off by {reviewer}"],
            cwd=str(project_dir), capture_output=True, text=True, timeout=15,
        )
        return name if proc.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def _main(argv=None) -> int:
    """CLI：``python -m yuleosh.evidence.signoff record|verify ...``"""
    import argparse

    parser = argparse.ArgumentParser(description="ASPICE electronic sign-off")
    sub = parser.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="record a human sign-off")
    rec.add_argument("--project", required=True)
    rec.add_argument("--gate", required=True)
    rec.add_argument("--artifact", required=True)
    rec.add_argument("--reviewer", required=True)
    rec.add_argument("--role", default="reviewer")
    rec.add_argument("--decision", default="approved", choices=DECISIONS)
    rec.add_argument("--comment", default="")
    rec.add_argument("--no-tag", action="store_true")
    rec.add_argument("--based-on-recommendation", default="",
                     help="agent pre-review JSON this approval is based on")
    rec.add_argument("--override-reason", default="",
                     help="required when overriding a recommend-reject")

    pre = sub.add_parser("recommend",
                         help="agent pre-review (advisory only, no release authority)")
    pre.add_argument("--project", required=True)
    pre.add_argument("--gate", required=True)
    pre.add_argument("--artifact", action="append", default=[])
    pre.add_argument("--agent", default="yuleosh:independent-verifier")
    pre.add_argument("--verdict", default="recommend-approve",
                     choices=RECOMMENDATION_VERDICTS)
    pre.add_argument("--blocking", action="append", default=[])
    pre.add_argument("--risk", action="append", default=[])
    pre.add_argument("--independence", default="none")
    pre.add_argument("--notes", default="")

    ver = sub.add_parser("verify", help="verify sign-offs")
    ver.add_argument("--project", required=True)
    ver.add_argument("--gate", action="append")
    args = parser.parse_args(argv)

    if args.cmd == "record":
        record = record_signoff(
            args.project, args.gate, args.artifact, reviewer=args.reviewer,
            role=args.role, decision=args.decision, comment=args.comment,
            tag=not args.no_tag,
            based_on_recommendation=args.based_on_recommendation or None,
            override_reason=args.override_reason,
        )
        print(json.dumps(record, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "recommend":
        path = write_recommendation(
            args.project, args.gate, artifacts=args.artifact, agent=args.agent,
            verdict=args.verdict, blocking=args.blocking,
            residual_risks=args.risk, independence=args.independence,
            notes=args.notes,
        )
        print(str(path))
        return 0

    gates = tuple(args.gate) if args.gate else REQUIRED_GATES
    status = {g: verify_gate(args.project, g) for g in gates}
    print(json.dumps(status, indent=2, ensure_ascii=False))
    return 0 if all(v.get("signed") for v in status.values()) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
