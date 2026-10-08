#!/usr/bin/env python3
"""V 模型左半（SYS.1~SYS.5）合规审计 —— 可复现实跑脚本。

用途: 替代临时探针（/tmp/*.py），对指定工程跑合规引擎并逐 BP 输出判定，
供审计/复核直接取用。左半修复（SYS-REQ-001~006）的改善前后对比即以此脚本
对同一工程、不同代码版本各跑一次得出。

用法:
    PYTHONPATH=src python3 scripts/vmodel_left_branch_audit.py <project_dir>
    # 同时对比另一份代码树的判定（A/B）:
    PYTHONPATH=src python3 scripts/vmodel_left_branch_audit.py <project_dir> \
        --baseline-src /path/to/other/src

输出: 逐 BP 明细 + 汇总（unknown check type 数、no substantive 数、BP ✅ 数）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _run_once(project_dir: str) -> dict:
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    from yuleosh.compliance.profile import load_profile

    out: dict = {"profiles": {}}
    for prof_name in ("aspice_sys_v3.1", "aspice_v3.1"):
        try:
            profile = load_profile(prof_name)
        except Exception as exc:  # noqa: BLE001
            out["profiles"][prof_name] = {"error": str(exc)}
            continue
        checker = ComplianceChecker(project_dir=project_dir, profile=profile)
        report = checker.run()
        bps = []
        for sec_key, sec in report.get("swe_sections", {}).items():
            for bp in sec.get("base_practices", []):
                bps.append({
                    "area": sec_key,
                    "id": bp.get("id"),
                    "status": bp.get("status"),
                    "details": bp.get("details", []),
                })
        out["profiles"][prof_name] = {"bps": bps}
    return out


def _summarize(result: dict) -> dict:
    stats: dict = {}
    for prof, data in result.get("profiles", {}).items():
        bps = data.get("bps", [])
        details = [d for bp in bps for d in bp["details"]]
        stats[prof] = {
            "total_bps": len(bps),
            "passed_bps": sum(1 for bp in bps if bp["status"] == "✅"),
            "unknown_check_type": sum(1 for d in details
                                      if "unknown check type" in d),
            "no_substantive_traceability": sum(
                1 for d in details if "no substantive traceability matrix" in d),
            "no_substantive_arch": sum(
                1 for d in details if "no substantive architecture doc found" in d),
        }
    return stats


def _print(label: str, result: dict) -> None:
    print("=" * 72)
    print(f"AUDIT: {label}")
    print("=" * 72)
    for prof, data in result.get("profiles", {}).items():
        if "error" in data:
            print(f"\n[{prof}] ERROR: {data['error']}")
            continue
        print(f"\n[{prof}]")
        for bp in data.get("bps", []):
            print(f"  {bp['id']:<14} {bp['status']}")
            for d in bp["details"]:
                print(f"      {d.strip()}")
    print("\n-- SUMMARY --")
    for prof, s in _summarize(result).items():
        print(f"  {prof}: {s}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("project_dir")
    ap.add_argument("--baseline-src", default=None,
                    help="另一份代码树的 src 路径（A/B 对比用）")
    args = ap.parse_args()

    proj = str(Path(args.project_dir).resolve())
    here_src = str(Path(__file__).resolve().parent.parent / "src")

    sys.path.insert(0, here_src)
    _print(f"CURRENT  (src={here_src})", _run_once(proj))

    if args.baseline_src:
        # 子进程方式切换到另一份 src，避免同进程模块串味。
        # 注意: 必须把脚本**复制到基线树内**再执行 —— 本脚本按 __file__ 定位
        # src，若直接运行当前树的脚本，无论 PYTHONPATH 怎么设都会加载当前
        # src，导致 "基线" 与 "当前" 输出完全相同（假 A/B）。
        import os
        import shutil
        import subprocess
        base = str(Path(args.baseline_src).resolve())
        base_root = Path(base).parent
        target_dir = base_root / "scripts"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_script = target_dir / Path(__file__).name
        shutil.copyfile(Path(__file__).resolve(), target_script)
        proc = subprocess.run(
            [sys.executable, str(target_script), proj],
            cwd=str(base_root), env={**os.environ, "PYTHONPATH": base},
            capture_output=True, text=True)
        print("\n" + "=" * 72)
        print(f"BASELINE (src={base})")
        print("=" * 72)
        body = proc.stdout.split("-- SUMMARY --")[0]
        print(body)
        if proc.returncode != 0:
            print(f"[baseline stderr] {proc.stderr[-2000:]}")
        # 基线汇总需重算，这里只取文本里的 SUMMARY
        if "-- SUMMARY --" in proc.stdout:
            print("-- SUMMARY --" + proc.stdout.split("-- SUMMARY --", 1)[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
