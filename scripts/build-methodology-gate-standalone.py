#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Build standalone methodology gate — 从 src 提取生成零依赖单文件引擎.

L3 B 部分: 任何项目无需安装 yuleosh 即可运行方法论门禁。
生成物 `dist/methodology-gate.py` 是自包含脚本:
  - 仅标准库 import（logging / re / pathlib / typing）
  - 包含 methodology_gate.py 全部核心检查函数
  - main 入口: python3 methodology-gate.py <project_dir> [--json]
    退出码: 0 = 通过/跳过, 1 = hard 违反

单一实现: 生成物由 src/yuleosh/ci/stages/methodology_gate.py 派生，
生成器保证同步（CI 一致性测试验证行为等价），不维护两份手写副本。

用法:
    python3 scripts/build-methodology-gate-standalone.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "src" / "yuleosh" / "ci" / "stages" / "methodology_gate.py"
DIST_DIR = REPO_ROOT / "dist"
OUTPUT = DIST_DIR / "methodology-gate.py"

# 需要提取的顶层函数/变量（按源码顺序）。_CliCI 是 CLI 模块里的，standalone 自建。
EXPORT_NAMES = [
    "_find_files",
    "_find_spec_files",
    "_check_grilling",
    "_check_domain_model",
    "_check_two_axis_review",
    "_check_tight_loop",
    "_check_vertical_slices",
    "_check_handoff",
    "CHECKS",
    "_is_methodology_project",
    "run_methodology_gate",
]

# standalone main 入口（追加到提取代码之后）
MAIN_SNIPPET = '''

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
        _out.write(msg + "\\n")

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
        _log(f"\\n📐 methodology gate 结果: {'PASS' if passed else 'FAIL'}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
'''


def _extract_source(src_path: Path, names: list[str]) -> str:
    """用 AST 提取顶层定义，保持源码顺序与 docstring。"""
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    wanted = set(names)
    chunks: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Assign, ast.AnnAssign)):
            target_names: list[str] = []
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        target_names.append(t.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                target_names.append(node.target.id)
            else:
                target_names.append(node.name)
            if any(n in wanted for n in target_names):
                chunk = ast.get_source_segment(src_path.read_text(encoding="utf-8"), node)
                if chunk:
                    chunks.append(chunk)
    return "\n\n".join(chunks)


def _build() -> str:
    source_text = SOURCE.read_text(encoding="utf-8")
    core = _extract_source(SOURCE, EXPORT_NAMES)

    header = f'''#!/usr/bin/env python3
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

'''

    return header + core + MAIN_SNIPPET


def main() -> int:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    output = _build()
    OUTPUT.write_text(output, encoding="utf-8")
    OUTPUT.chmod(0o755)
    print(f"✅ 已生成 {OUTPUT} ({len(output)} bytes, {output.count(chr(10))} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
