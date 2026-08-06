#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Methodology Gate (L2) — 零依赖 standalone 版。

由 scripts/build-methodology-gate-standalone.py 从
src/yuleosh/ci/stages/methodology_gate.py 自动生成，请勿手改。
改逻辑请改源文件后重新生成（CI 一致性测试会校验行为等价）。

用法:
    python3 methodology-gate.py <project_dir> [--json]

退出码: 0 = 通过/跳过（soft 警告不阻断）; 1 = hard 违反阻断。
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Callable

log = logging.getLogger("ci.stages.methodology_gate")

def _find_files(project_dir: str, globs: list[str]) -> list[Path]:
    """在项目目录下按 glob 找文件（排除 .git/node_modules/.yuleosh 内部缓存）。"""
    root = Path(project_dir)
    found: list[Path] = []
    for g in globs:
        for p in sorted(root.glob(g)):
            parts = p.parts
            if ".git" in parts or "node_modules" in parts:
                continue
            if ".yuleosh" in parts and "agents" not in parts:
                continue
            found.append(p)
    return found

def _find_spec_files(project_dir: str) -> list[Path]:
    """找 spec 文件（grilling 检查用）。

    优先 OpenSpec 结构化目录（.osh/specs/*/spec.md），其次 docs/spec*.md
    及 docs/spec/、docs/specs/ 子目录（常见 spec 组织方式），再其次
    specs/ 下**文件名含 spec 字样**的文档，最后退路: 项目根下
    *spec*.md（如 spec-contract.md / spec.md）。排除需求追溯表
    （module-requirements.md）、验收矩阵（*acceptance-matrix*.md）等
    非 spec 文档——那些是项目通用文档，不需要 grilling 决策记录。
    """
    found = _find_files(project_dir, [
        ".osh/specs/*/spec.md",
        "docs/spec*.md",
        "docs/spec/*.md",
        "docs/specs/*.md",
        "docs/specification/*.md",
    ])
    if found:
        return found
    # 退路: specs/ 下文件名含 'spec' 的（排除 misra/requirements/matrix）
    for p in _find_files(project_dir, ["specs/*.md"]):
        name = p.name.lower()
        if "spec" in name and "matrix" not in name and "requirement" not in name and "misra" not in name:
            found.append(p)
    if found:
        return found
    # 第三退路: 项目根下 *spec*.md（如 spec-contract.md / spec.md）
    # 排除 docs/ specs/ 等已扫描目录中的文件（避免重复）
    for p in _find_files(project_dir, ["*spec*.md", "*spec*.markdown"]):
        rel = p.relative_to(project_dir)
        if rel.parts and rel.parts[0] in (".git", "node_modules", "docs", "specs", "spec", ".yuleosh"):
            continue
        name = p.name.lower()
        if "matrix" in name or "requirement" in name or "misra" in name:
            continue
        if "acceptance" in name:
            continue
        found.append(p)
    return found

def _check_grilling(project_dir: str) -> tuple[bool, str]:
    """§1 grilling 对齐：最新 spec 必须含决策记录/澄清痕迹。

    语义分层（存量项目 vs 活跃 OpenSpec 流程）:
      - 项目有 .osh/specs/（活跃 OpenSpec 目录，新 spec 在此编写）→ hard:
        最新 spec 必须含决策记录，否则违反（阻断）。
      - 项目只有 docs/spec*.md / specs/*spec*.md（存量后补规范文档，
        无 .osh/specs/ 结构）→ soft: 存量 spec 无法追溯对齐过程，
        提示补充决策记录但不阻断（渐进式方法论落地）。
    """
    root = Path(project_dir)
    active_openspec = bool(_find_files(project_dir, [".osh/specs/*/spec.md"]))
    specs = _find_spec_files(project_dir)
    if not specs:
        return False, "no spec file found (.osh/specs/*/spec.md or docs/spec*.md)"
    latest = sorted(specs, key=lambda p: p.stat().st_mtime)[-1]
    try:
        content = latest.read_text(errors="replace")
    except OSError as e:
        return False, f"cannot read {latest}: {e}"
    markers = [
        "决策记录", "Decision Log", "grilling", "Grilling",
        "澄清", "对齐", "recommended answer", "推荐答案",
    ]
    hits = [m for m in markers if m in content]
    if hits:
        return True, f"{latest.name} 含决策记录: {', '.join(hits[:3])}"
    if not active_openspec:
        return True, (
            f"{latest.name} 无决策记录 — 存量项目降级（无 .osh/specs/ 活跃流程，"
            "建议后续新 spec 补充 Grilling 记录，不阻断）"
        )
    return False, f"{latest.name} 无 grilling/决策记录痕迹（应含 '决策记录' 或 'Grilling'）"

def _check_domain_model(project_dir: str) -> tuple[bool, str]:
    """§2 domain-modeling：CONTEXT.md 存在且不含实现细节关键词。"""
    ctx = Path(project_dir) / "CONTEXT.md"
    if not ctx.exists():
        # 允许 CONTEXT-MAP.md 多上下文模式
        ctx_map = Path(project_dir) / "CONTEXT-MAP.md"
        if not ctx_map.exists():
            return False, "CONTEXT.md / CONTEXT-MAP.md 缺失（统一语言未建立）"
        return True, "CONTEXT-MAP.md 存在（多上下文模式）"
    content = ctx.read_text(errors="replace")
    impl_markers = ["def ", "class ", "import ", "#include", "```python", "```c", ".cpp"]
    leaks = [m for m in impl_markers if m in content]
    if leaks:
        return False, f"CONTEXT.md 含实现细节（应为纯术语表）: {', '.join(leaks[:3])}"
    return True, "CONTEXT.md 存在且为纯术语表"

def _check_two_axis_review(project_dir: str) -> tuple[bool, str]:
    """§3 双轴评审：至少一份评审报告含 Standards + Spec 两轴。"""
    reports = _find_files(project_dir, ["reports/*.md", "expert-review/*.md", ".yuleosh/reports/*.md"])
    if not reports:
        return False, "无评审报告（reports/*.md）可检查双轴"
    for r in sorted(reports, key=lambda p: p.stat().st_mtime, reverse=True):
        content = r.read_text(errors="replace")
        has_standards = bool(re.search(r"Standards|标准轴|规范轴", content))
        has_spec = bool(re.search(r"Spec\b|规格轴|契约轴|Spec 轴", content))
        if has_standards and has_spec:
            return True, f"{r.name} 含双轴（Standards+Spec）"
    # 所有报告均缺双轴之一（例如纯 MISRA 报告）——软检查
    latest = sorted(reports, key=lambda p: p.stat().st_mtime)[-1]
    return False, f"最近报告 {latest.name} 缺双轴之一（应含 Standards + Spec 两节）"

def _check_tight_loop(project_dir: str) -> tuple[bool, str]:
    """§4 tight-loop 调试：至少一份调试/修复记录含复现回路证据。"""
    docs = _find_files(project_dir, ["reports/*rca*.md", "reports/*debug*.md", "reports/*fix*.md", "reports/*diagnos*.md"])
    if not docs:
        # 没有调试类报告 → 无法验证，软检查（不阻断）
        return True, "无调试/修复报告（跳过，软检查）"
    markers = ["复现", "repro", "red-capable", "回路", "feedback loop", "复现步骤", "Reproduce", "reproduce"]
    for d in sorted(docs, key=lambda p: p.stat().st_mtime, reverse=True):
        content = d.read_text(errors="replace")
        hits = [m for m in markers if m in content]
        if hits:
            return True, f"{d.name} 含回路证据: {', '.join(hits[:3])}"
    latest = sorted(docs, key=lambda p: p.stat().st_mtime)[-1]
    return False, f"{latest.name} 无复现回路证据（应含复现步骤/回路描述）"

def _check_vertical_slices(project_dir: str) -> tuple[bool, str]:
    """§5 垂直切片：plan 文件含 blocking edges / 切片结构。"""
    plans = _find_files(project_dir, [".osh/plans/*.md", "plans/*.md"])
    if not plans:
        return True, "无 plan 文件（跳过，软检查）"
    latest = sorted(plans, key=lambda p: p.stat().st_mtime)[-1]
    content = latest.read_text(errors="replace")
    markers = ["Blocked by", "blocking", "依赖", "blockers", "frontier", "切片", "tracer bullet"]
    hits = [m for m in markers if m in content]
    if not hits:
        return False, f"{latest.name} 无切片/依赖结构（应含 Blocked by / 依赖）"
    return True, f"{latest.name} 含切片结构: {', '.join(hits[:3])}"

def _check_handoff(project_dir: str) -> tuple[bool, str]:
    """§6 交接纪律：交接文档引用 artifact 而非复制。"""
    handoffs = _find_files(project_dir, ["**/handoff*.md", "**/HANDOFF*.md", "sessions/*handover*.md"])
    if not handoffs:
        return True, "无交接文档（跳过，软检查）"
    latest = sorted(handoffs, key=lambda p: p.stat().st_mtime)[-1]
    content = latest.read_text(errors="replace")
    has_suggested = "suggested skills" in content or "建议技能" in content
    has_refs = bool(re.search(r"\[.*\]\(.*\)|`[^`]+\.md`|\.osh/|\.yuleosh/", content))
    if has_suggested and has_refs:
        return True, f"{latest.name} 引用 artifact + 建议技能"
    return False, f"{latest.name} 缺建议技能段或 artifact 引用"

CHECKS: dict[str, tuple[str, str, CheckFn]] = {
    "grilling-alignment": ("§1 grilling 对齐", "hard", _check_grilling),
    "domain-model":       ("§2 统一语言", "hard", _check_domain_model),
    "two-axis-review":    ("§3 双轴评审", "soft", _check_two_axis_review),
    "tight-loop-debug":   ("§4 调试回路", "soft", _check_tight_loop),
    "vertical-slices":    ("§5 垂直切片", "soft", _check_vertical_slices),
    "handoff":            ("§6 交接纪律", "soft", _check_handoff),
}

def _is_methodology_project(project_dir: str) -> bool:
    """检测项目是否走方法论流程。

    判定依据（任一）:
      - .osh/specs/ 或 .osh/plans/ 存在（OpenSpec 流程产物）
      - .yuleosh/agents/ 存在（agent 约束）
      - CONTEXT.md / CONTEXT-MAP.md 存在（统一语言）

    仅 docs/spec.md、specs/misra-*.md 等通用文档不算——那是任意项目
    都有的文档，不是方法论流程标志。临时测试项目不会误伤。
    """
    root = Path(project_dir)
    has_spec = bool(_find_files(project_dir, [".osh/specs/*/spec.md"]))
    has_ctx = (root / "CONTEXT.md").exists() or (root / "CONTEXT-MAP.md").exists()
    has_agents = (root / ".yuleosh" / "agents").is_dir()
    has_specs_dir = (root / ".osh" / "specs").is_dir() or (root / ".osh" / "plans").is_dir()
    return has_spec or has_ctx or has_agents or has_specs_dir

def run_methodology_gate(project_dir: str, ci, log_fn=None) -> bool:
    """Run the methodology gate. Returns True if pipeline should continue.

    Hard violations → stage failed → return False (block).
    Soft violations → stage warning → return True (non-blocking).

    非方法论项目（无 spec/CONTEXT/.yuleosh）→ 全部降级为跳过，不阻断。

    log_fn: 可选日志回调 log_fn(msg: str) -> None。默认用 print（stdout）。
         传入 stderr 写入函数可在 --json 模式下把人类日志与 JSON 分离。
         注意参数名不用 log——避免遮蔽模块级 logging logger。
    """
    out = log_fn if log_fn is not None else print
    out("  📐 CI: methodology gate (L2 方法论契约门禁)...")

    if not _is_methodology_project(project_dir):
        msg = "非方法论项目（无 spec/CONTEXT/.yuleosh）— 门禁跳过"
        ci.add_stage("methodology-gate", "skipped", msg)
        out(f"    ⏭️  {msg}")
        return True

    hard_failures: list[str] = []
    soft_failures: list[str] = []
    passes: list[str] = []

    for key, (label, severity, fn) in CHECKS.items():
        try:
            ok, msg = fn(project_dir)
        except Exception as e:  # pragma: no cover - defensive
            ok, msg = False, f"check crashed: {e}"
            log.exception("methodology gate %s crashed", key)  # 模块级 logger，不依赖 log 回调

        if ok:
            passes.append(f"{label}: {msg}")
            ci.add_stage(f"methodology-{key}", "passed", msg)
            out(f"    ✅ {label}: {msg}")
        elif severity == "hard":
            hard_failures.append(f"{label}: {msg}")
            ci.add_stage(f"methodology-{key}", "failed", msg)
            out(f"    ❌ {label}: {msg}")
        else:
            soft_failures.append(f"{label}: {msg}")
            ci.add_stage(f"methodology-{key}", "warning", msg)
            out(f"    ⚠️  {label}: {msg}")

    summary = (
        f"{len(passes)} pass, {len(soft_failures)} soft, {len(hard_failures)} hard"
    )
    ci.add_stage("methodology-gate", "passed" if not hard_failures else "failed", summary)
    out(f"  📐 methodology gate: {summary}")

    if hard_failures:
        out("    ❌ 硬性违反（阻断）:")
        for f in hard_failures:
            out(f"      - {f}")
        return False

    return True

class _CliCI:
    """最小 CI 记录器（适配 run_methodology_gate 的 ci.add_stage 接口）。"""

    def __init__(self) -> None:
        self.stages: list[tuple[str, str, str]] = []

    def add_stage(self, name: str, status: str, msg: str = "") -> None:
        self.stages.append((name, status, msg))


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(
        prog="methodology-gate",
        description="yuleOSH Methodology Gate (L2) — 零依赖 standalone 版",
    )
    parser.add_argument("project_dir", nargs="?", default=".", help="目标项目目录")
    parser.add_argument("--json", action="store_true", help="JSON 输出（stdout 纯 JSON，日志走 stderr）")
    args = parser.parse_args(argv)

    _out = sys.stderr if args.json else sys.stdout

    def _log(msg: str = "") -> None:
        _out.write(msg + "\n")

    root = str(Path(args.project_dir).resolve())
    ci = _CliCI()
    passed = run_methodology_gate(root, ci, log_fn=_log)

    if args.json:
        payload = {
            "project_dir": root,
            "passed": passed,
            "stages": [
                {"name": n, "status": s, "message": m}
                for (n, s, m) in ci.stages
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _log(f"\n📐 methodology gate 结果: {'PASS' if passed else 'FAIL'}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
