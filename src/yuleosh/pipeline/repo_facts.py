"""仓库事实快照 — 文档步骤 (development/test-planning/PRD) 的真实项目基线。

2026-08-18 r21e 复盘: development/test-planning 步骤只喂 spec + 前序文档,
不注入真实仓库状态 → LLM 凭幻觉写计划 (引用不存在的测试文件、把已实现的
nvm_persisted 列为 P0 缺口、把自定义 CHECK harness 误述为 Unity、自造
ASIL_B)。claude-review 是唯一真正读仓库的 agent, 所以它总能抓到错误。

修法: 把 claude-review 的「读仓库」前置——文档步骤共享本模块注入的仓库
事实, 让 LLM 的计划/测试/PRD 建立在真实数据上。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger("pipeline.repo_facts")

# 测试函数识别: C/C++ 静态测试函数 (Unity/自定义 CHECK harness 通用)
_TEST_FUNC_RE = re.compile(
    r"^\s*(?:static\s+)?(?:void|int)\s+test_\w+\s*\(", re.M
)


def count_test_functions(path: Path) -> int:
    """统计 C/C++ 文件里的测试函数数 (test_ 前缀函数)。"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return len(_TEST_FUNC_RE.findall(text))
    except OSError:
        return 0


def detect_test_framework(tests_dir: Path) -> str:
    """探测测试框架: Unity / custom-Check / pytest / unknown。

    2026-08-18 r21e: test-planning 曾把自定义 CHECK 宏 harness 误述为
    'Unity Test Framework v2.5+' — 必须注入真实框架, 否则测试基建配置被误导。
    """
    if not tests_dir.exists():
        return "unknown"
    # 先扫 C 测试文件
    c_files = list(tests_dir.rglob("*.c")) + list(tests_dir.rglob("*.cpp"))
    for f in c_files[:20]:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            if "TEST_ASSERT" in text or "#include \"unity" in text \
                    or "#include <unity" in text:
                return "unity"
            if re.search(r"#\s*define\s+CHECK\b", text):
                return "custom-Check"
        except OSError:
            continue
    # pytest
    py_files = list(tests_dir.rglob("*.py"))
    if py_files:
        for f in py_files[:20]:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                if "import pytest" in text or "def test_" in text:
                    return "pytest"
            except OSError:
                continue
    if c_files:
        return "c-harness"
    if py_files:
        return "python"
    return "unknown"


def _project_asil_from_files(project_dir: Path) -> str:
    """ASIL 来源: yuleosh.yaml asil 字段 → project-context.md / README 正则。

    2026-08-18 r21e: PRD 自造 'ASIL_B (平台配置)' 但项目无 yuleosh.yaml,
    ASIL 纪律段因 project_asil='' 完全未注入 → LLM 自由发挥。来源应扩展
    到项目文档 (project-context.md / README.md 的 ASIL 行), 且纪律段在
    无 ASIL 时也必须注入 (禁止自封)。
    """
    import yaml as _yaml
    for name in ("yuleosh.yaml", ".yuleosh.yaml"):
        p = project_dir / name
        if p.exists():
            try:
                raw = _yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                asil = raw.get("asil")
                if asil:
                    return str(asil)
            except Exception as e:
                log.warning("asil parse failed %s: %s", p, e)
    # 项目文档中的 ASIL 行: "ASIL: ASIL B" / "ASIL B" / "ASIL-B" / "ASIL_D"
    # 2026-08-18 r21e: 分隔符 ([-:_\s]) 吞掉后规范化为 ASIL_<level>, 与
    # yuleosh.yaml asil 字段返回格式一致 (ASIL_B / ASIL_D)。
    asil_re = re.compile(
        r"ASIL[-:_\s]*([A-Za-z][A-Za-z0-9_+\-]*)", re.I
    )
    for name in ("project-context.md", "README.md"):
        p = project_dir / name
        if not p.exists():
            continue
        try:
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                m = asil_re.search(line)
                if m:
                    return "ASIL_" + m.group(1).upper()
        except OSError:
            continue
    return ""


def get_project_asil(project_dir: str | Path) -> str:
    """项目 ASIL 来源 (r21e 扩展): yuleosh.yaml asil → 项目文档正则。"""
    return _project_asil_from_files(Path(project_dir))


def collect_repo_facts(project_dir: str | Path) -> dict:
    """收集文档步骤需要的仓库事实快照。"""
    project_dir = Path(project_dir)
    facts: dict = {}

    # 源文件
    src_files = []
    src_lines = 0
    for pattern in ("src/**/*.c", "src/**/*.h", "src/**/*.cpp",
                    "src/**/*.hpp", "src/**/*.py", "src/**/*.sh"):
        for f in sorted(project_dir.glob(pattern)):
            src_files.append(str(f.relative_to(project_dir)))
            try:
                src_lines += len(f.read_text(encoding="utf-8",
                                             errors="replace").splitlines())
            except OSError:
                pass
    facts["src_file_count"] = len(src_files)
    facts["src_lines"] = src_lines

    # 测试文件 + 函数数
    test_files = []
    test_func_count = 0
    for pattern in ("tests/**/*.c", "tests/**/*.h", "tests/**/*.cpp",
                    "tests/**/*.hpp", "tests/**/*.py"):
        for f in sorted(project_dir.glob(pattern)):
            test_files.append(str(f.relative_to(project_dir)))
            if f.suffix in (".c", ".h", ".cpp", ".hpp"):
                test_func_count += count_test_functions(f)
    facts["test_file_count"] = len(test_files)
    facts["test_files"] = test_files
    facts["test_func_count"] = test_func_count

    # 测试框架
    facts["test_framework"] = detect_test_framework(project_dir / "tests")

    # 覆盖率报告 (最新)
    cov_report = project_dir / ".yuleosh" / "reports" / "c-coverage.json"
    if cov_report.exists():
        try:
            cov = json.loads(cov_report.read_text(encoding="utf-8"))
            totals = cov.get("totals", {}) or {}
            facts["coverage"] = (
                f"line_rate={totals.get('line_rate', '?')} "
                f"branch_rate={totals.get('branch_rate', '?')} "
                f"functions={totals.get('functions', '?')}"
            )
        except (OSError, json.JSONDecodeError):
            facts["coverage"] = ""
    else:
        facts["coverage"] = ""

    # ASIL
    facts["project_asil"] = _project_asil_from_files(project_dir)

    return facts


def format_repo_facts(facts: dict) -> str:
    """把仓库事实快照格式化为 prompt 注入段落。"""
    lines = [
        "# Repository Facts (machine-collected, 2026-08-18 r21e)\n"
        "以下数据由流水线从仓库机器收集 — 开发/测试计划必须以此为准, "
        "不得编造不存在的文件或把已完成工作列为缺口:",
        f"- Source files: {facts.get('src_file_count', 0)} "
        f"({facts.get('src_lines', 0)} lines)",
        f"- Test files ({facts.get('test_file_count', 0)}): "
        + (", ".join(facts.get("test_files", [])[:15]) or "(none)"),
        f"- Test functions: {facts.get('test_func_count', 0)}",
        f"- Test framework: {facts.get('test_framework', 'unknown')}",
        f"- Coverage (latest report): "
        f"{facts.get('coverage') or 'no report'}",
        f"- Project ASIL: {facts.get('project_asil') or '(not declared — do NOT invent one)'}",
    ]
    return "\n".join(lines)
