#!/usr/bin/env python3
"""yuleOSH 全量覆盖率回归 — 纯 python3 单进程（绕过 rtk 包装器）。

用法: python3 scripts/run_coverage_full.py
输出: 全量 pytest 结果 + 覆盖率百分比（B2-5 门禁验证）。
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("YULEOSH_JWT_SECRET", "test-jwt-secret-for-ci-only-not-for-production")
# 清理可能残留的 OSH_HOME 污染
os.environ.pop("OSH_HOME", None)

sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)

import coverage

# 独立 data_file：绕开与 pytest-cov 对 .coverage 的并发写（sqlite schema 冲突
# 会报 "no such table: arc"）。写 /tmp 而非项目根，避免污染仓库。
_cov_file = f"/tmp/yuleosh-cov-{os.getpid()}.coverage"
cov = coverage.Coverage(branch=True, source=["yuleosh"], data_file=_cov_file)
cov.erase()
cov.start()

import pytest

args = [
    "tests/",
    "-q",
    "--no-header",
    "-x",
    "--ignore=tests/test_server_integration.py",
    "-o", "addopts=",   # 清掉 pytest.ini 自带的 --cov 参数
    "-p", "no:cov",     # 彻底禁用 pytest-cov 插件（否则会话结束会再写一次 .coverage）
]
rc = pytest.main(args)

cov.stop()
cov.save()

report = cov.json_report(outfile=str(Path(ROOT) / ".coverage-report.json"))
with open(Path(ROOT) / ".coverage-report.json") as _f:
    t = json.load(_f)["totals"]
pct = (t["covered_lines"] + t["covered_branches"]) / (
    t["num_statements"] + t["num_branches"]
) * 100
print(f"\n=== COVERAGE: {pct:.2f}% ===")
print(
    f"= ({t['covered_lines']}+{t['covered_branches']})/"
    f"({t['num_statements']}+{t['num_branches']})"
)
sys.exit(rc)
