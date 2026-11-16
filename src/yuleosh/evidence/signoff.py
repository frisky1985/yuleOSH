#!/usr/bin/env python3

# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""电子签批（AUD-ASPICE-001 NC-09）。

CL2 评估要求关键基线（需求 / 架构）由**具名责任人**签批，且签批必须绑定
到被签批产物的内容摘要 —— 否则"先签后改"无法被发现。本模块提供：

- ``record_signoff(...)``：记录签批（签批人、角色、决策、时间、产物 SHA-256），
  并可选打 git tag，形成不可否认的时间锚点；
- ``verify_signoffs(...)``：校验签批是否仍有效（决策 approved 且产物摘要未变）；
- ``required_signoff_status(...)``：给门禁结论用的 G1/G2 签批状态。

签批记录落盘于 ``<project>/.osh/signoffs/<gate>.json``（追加历史）。缺少签批
时，运行结论为 ``awaiting-signoff``（不是 green，也不是 red）—— 自动化只能
把证据准备到位，放行必须由人完成。
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("evidence.signoff")

SCHEMA = "yuleosh-signoff/v1"

#: CL2 必须人工签批的基线门禁
REQUIRED_GATES: tuple[str, ...] = ("G1", "G2")

DECISIONS = ("approved", "rejected", "conditional")


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
                   tag: bool = True) -> dict:
    """记录一次签批。返回记录 dict（已落盘）。

    Raises
    ------
    ValueError
        缺少签批人、决策非法，或产物不存在（无法绑定摘要）。
    """
    gate = str(gate).strip().upper()
    if not gate:
        raise ValueError("gate id is required")
    reviewer = str(reviewer).strip()
    if not reviewer:
        raise ValueError("reviewer identity is required for an electronic signature")
    decision = str(decision).strip().lower()
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}, got {decision!r}")

    digest = artifact_digest(artifact_path)
    if not digest:
        raise ValueError(f"artifact not found or unreadable: {artifact_path}")

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
    return {
        "gate": gate,
        "signed": True,
        "reason": "approved and digest matches",
        "reviewer": record.get("reviewer"),
        "role": record.get("role"),
        "signed_at": record.get("signed_at"),
        "tag": record.get("tag", ""),
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

    ver = sub.add_parser("verify", help="verify sign-offs")
    ver.add_argument("--project", required=True)
    ver.add_argument("--gate", action="append")
    args = parser.parse_args(argv)

    if args.cmd == "record":
        record = record_signoff(
            args.project, args.gate, args.artifact, reviewer=args.reviewer,
            role=args.role, decision=args.decision, comment=args.comment,
            tag=not args.no_tag,
        )
        print(json.dumps(record, indent=2, ensure_ascii=False))
        return 0

    gates = tuple(args.gate) if args.gate else REQUIRED_GATES
    status = {g: verify_gate(args.project, g) for g in gates}
    print(json.dumps(status, indent=2, ensure_ascii=False))
    return 0 if all(v.get("signed") for v in status.values()) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
