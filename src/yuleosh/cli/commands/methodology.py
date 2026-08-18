# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH CLI — methodology hosting commands (L3 方法论宿主平台化).

L3 目标: 把 yuleOSH 方法论资产（L1 行为约束 + L2 门禁）抽成可复用宿主包，
任何项目（yuleDKCS / yuleASR / 新项目）可一键挂载 + 独立运行门禁。

命令:
  yuleosh methodology init [dir]     — 生成 .yuleosh/agents/ 六件套 + CONTEXT.md + ci-config 片段
  yuleosh methodology check [dir]    — 在任意项目运行 methodology gate（复用 methodology_gate.py）

SHALL-A5.5 纪律: 本模块不 import cli.main（避免循环依赖），_osh_home() 延迟解析。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

_TEMPLATE_NAME = "methodology"


def _osh_home() -> str:
    try:
        import yuleosh.cli.main as _m
        return _m.OSH_HOME
    except Exception:
        return os.environ.get("OSH_HOME", os.getcwd())


def _template_dir() -> Path:
    """定位方法论宿主模板目录（内置优先级）。"""
    from yuleosh.templates import get_template_dir, resolve_template

    tpl = resolve_template(_TEMPLATE_NAME)
    if tpl is None:
        return Path(__file__).resolve().parent.parent.parent / "templates" / _TEMPLATE_NAME
    d = get_template_dir(tpl)
    if d is None:
        raise SystemExit(f"Error: methodology 模板目录解析失败")
    return Path(d)


def _render(content: str, project_name: str, project_desc: str = "") -> str:
    """替换模板占位符 {{PROJECT_NAME}} / {{PROJECT_DESC}}。"""
    return (
        content.replace("{{PROJECT_NAME}}", project_name)
        .replace("{{PROJECT_DESC}}", project_desc)
    )


def cmd_methodology_init(project_dir: str = ".", force: bool = False) -> None:
    """在任意项目生成方法论宿主骨架（幂等：不覆盖已有文件）。"""
    root = Path(project_dir).resolve()
    if not root.is_dir():
        print(f"Error: 目录不存在: {root}")
        sys.exit(1)

    tpl = _template_dir()
    if not tpl.is_dir():
        print(f"Error: 方法论模板缺失: {tpl}")
        sys.exit(1)

    project_name = root.name
    agents_dir = root / ".yuleosh" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    # 1) .yuleosh/agents/ 六件套（四件套 + 第一准则 PRIME-DIRECTIVE + TEST-INTEGRITY）
    created: list[str] = []
    skipped: list[str] = []
    for fname in ("AGENTS.md", "METHODOLOGY.md", "RULES.md", "HOOKS.md", "PRIME-DIRECTIVE.md", "TEST-INTEGRITY.md"):
        src = tpl / ".yuleosh" / "agents" / fname
        dst = agents_dir / fname
        if dst.exists() and not force:
            skipped.append(f".yuleosh/agents/{fname}")
            continue
        rendered = _render(src.read_text(encoding="utf-8"), project_name)
        dst.write_text(rendered, encoding="utf-8")
        created.append(f".yuleosh/agents/{fname}")

    # 2) CONTEXT.md（统一语言模板）
    ctx_src = tpl / "CONTEXT.md"
    ctx_dst = root / "CONTEXT.md"
    if ctx_src.exists():
        if ctx_dst.exists() and not force:
            skipped.append("CONTEXT.md")
        else:
            ctx_dst.write_text(_render(ctx_src.read_text(encoding="utf-8"), project_name), encoding="utf-8")
            created.append("CONTEXT.md")

    # 3) ci-config 门禁片段（仅提示，不覆盖已有配置）
    cfg_src = tpl / "ci-config.methodology.yaml"
    if cfg_src.exists():
        cfg_dst = root / ".yuleosh" / "ci-config.yaml"
        if cfg_dst.exists() and not force:
            skipped.append(".yuleosh/ci-config.yaml (已存在，请手动合并 methodology 段)")
        else:
            cfg_dst.parent.mkdir(parents=True, exist_ok=True)
            cfg_dst.write_text(_render(cfg_src.read_text(encoding="utf-8"), project_name), encoding="utf-8")
            created.append(".yuleosh/ci-config.yaml")

    # 4) OpenSpec 规范骨架（.osh/specs/README + 示例 capability，幂等）
    specs_tpl = tpl / ".osh" / "specs"
    if specs_tpl.exists():
        specs_dst = root / ".osh" / "specs"
        specs_dst.mkdir(parents=True, exist_ok=True)
        readme_dst = specs_dst / "README.md"
        if readme_dst.exists() and not force:
            skipped.append(".osh/specs/README.md")
        else:
            readme_dst.write_text((specs_tpl / "README.md").read_text(encoding="utf-8"), encoding="utf-8")
            created.append(".osh/specs/README.md")
        ex_src = specs_tpl / "example" / "spec.md"
        ex_dst = specs_dst / "example" / "spec.md"
        if ex_src.exists():
            if ex_dst.exists() and not force:
                skipped.append(".osh/specs/example/spec.md")
            else:
                ex_dst.parent.mkdir(parents=True, exist_ok=True)
                ex_dst.write_text(_render(ex_src.read_text(encoding="utf-8"), project_name), encoding="utf-8")
                created.append(".osh/specs/example/spec.md")

    print(f"✅ 方法论宿主包已挂载到 {root}")
    for c in created:
        print(f"   ✍️  创建: {c}")
    for s in skipped:
        print(f"   ⏭️  跳过(已存在): {s}")
    if not created and not skipped:
        print("   （无变更）")
    print("\n下一步:")
    print("  1. 编辑 CONTEXT.md 填充项目领域术语")
    print("  2. 运行 yuleosh methodology check 验证门禁")
    print("  3. 在 CI 中接入 methodology gate（Layer 1 stage）")


class _CliCI:
    """CLI 用的最小 CI 记录器（适配 run_methodology_gate 的 ci.add_stage 接口）。"""

    def __init__(self) -> None:
        self.stages: list[tuple[str, str, str]] = []

    def add_stage(self, name: str, status: str, msg: str = "") -> None:
        self.stages.append((name, status, msg))


def cmd_methodology_check(project_dir: str = ".", json_out: bool = False) -> None:
    """在任意项目独立运行 methodology gate。

    退出码: 0 = 通过/跳过（soft 警告不阻断）; 1 = hard 违反阻断。

    --json 模式: stdout 只输出 JSON（人类可读日志走 stderr），
    保证 stdout 可被 json.loads 直接消费（CI 管道友好）。
    """
    from yuleosh.ci.stages.methodology_gate import run_methodology_gate

    _out = sys.stderr if json_out else sys.stdout

    def _log(msg: str = "") -> None:
        _out.write(msg + "\n")

    root = str(Path(project_dir).resolve())
    ci = _CliCI()
    passed = run_methodology_gate(root, ci, log_fn=_log)

    if json_out:
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

    sys.exit(0 if passed else 1)


def build_parser(sub) -> None:
    """构建 methodology 子命令 parser（供 cli/main.py _build_parser 调用）。"""
    p = sub.add_parser("methodology", help="方法论宿主包管理 (L3): init / check")
    msub = p.add_subparsers(dest="methodology_sub", help="Methodology 子命令")

    p_init = msub.add_parser("init", help="挂载方法论宿主包到项目（生成 .yuleosh/agents/ + CONTEXT.md）")
    p_init.add_argument("dir", nargs="?", default=".", help="目标项目目录 (默认: 当前目录)")
    p_init.add_argument("--force", action="store_true", help="覆盖已存在的文件（默认幂等跳过）")

    p_check = msub.add_parser("check", help="运行 methodology gate（六维检查，hard 违反阻断）")
    p_check.add_argument("dir", nargs="?", default=".", help="目标项目目录 (默认: 当前目录)")
    p_check.add_argument("--json", action="store_true", help="JSON 输出")
