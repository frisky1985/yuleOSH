#!/usr/bin/env python3
"""
Mock Data Generator — 模拟 MISRA / UT 报告测试数据

用于端到端集成测试，生成各种场景的模拟数据：
  - cppcheck raw output（多行标准格式 + 跨行上下文）
  - JUnit XML（指定通过/失败/跳过数）
  - lcov 覆盖率文件（指定覆盖率百分比）
  - coverage-trend JSONL 行

边缘场景覆盖：
  - 空输出
  - 巨量违规（性能/批量测试）
  - 极端覆盖率（0%, 100%）
  - 格式异常的 cppcheck 输出行
"""

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

# Pick a seed for reproducible mock data
_SEED = 42
random.seed(_SEED)


# ------------------------------------------------------------------
# MISRA 违规生成
# ------------------------------------------------------------------

_MISRA_RULES = [
    "misra-c2012-10.1",
    "misra-c2012-10.3",
    "misra-c2012-11.4",
    "misra-c2012-12.1",
    "misra-c2012-14.4",
    "misra-c2012-15.5",
    "misra-c2012-16.3",
    "misra-c2012-17.7",
    "misra-c2012-21.3",
    "misra-c2012-21.6",
    "misra-c2012-8.4",
    "misra-c2012-17.8",
]

_SEVERITIES = ["error", "warning", "style", "performance", "portability", "information"]

_SAMPLE_MESSAGES = {
    "misra-c2012-10.1": "Operands shall not be of inappropriate type",
    "misra-c2012-10.3": "Value of expression shall not be assigned to wider essential type",
    "misra-c2012-11.4": "Conversion between pointer and integer shall not be performed",
    "misra-c2012-12.1": "Operands shall not be of inappropriate essential type",
    "misra-c2012-14.4": "The controlling expression of an if statement shall have bool type",
    "misra-c2012-15.5": "Return shall not be used in a function with void return type",
    "misra-c2012-16.3": "Switch shall have a default label",
    "misra-c2012-17.7": "Return value of a function shall be used",
    "misra-c2012-21.3": "Memory shall not be allocated dynamically",
    "misra-c2012-21.6": "The library facilities of stdio.h shall not be used",
    "misra-c2012-8.4": "Functions shall have prototype declarations",
    "misra-c2012-17.8": "A function parameter shall not be modified",
}


def make_misra_violation(
    file: str = "/src/main.c",
    line: int = 42,
    col: int = 5,
    severity: str = "style",
    rule_id: str = "misra-c2012-10.1",
    message: str = "Operands shall not be of inappropriate type",
) -> str:
    """生成单行 cppcheck MISRA 违规输出。

    Parameters
    ----------
    file : str
        源文件路径。
    line : int
        行号。
    col : int
        列号。
    severity : str
        严重级别。
    rule_id : str
        MISRA 规则 ID。
    message : str
        违规描述信息。

    Returns
    -------
    str
        标准 cppcheck 格式的违规行。
    """
    return f"{file}:{line}:{col}: {severity}: {message} [{rule_id}]\n"


def _random_violation_line(file: str, code_line: str) -> tuple[str, str]:
    """生成带上下文代码行的随机违规。

    Returns
    -------
    tuple[str, str]
        (violation_line_raw, context_code_lines)
    """
    rule = random.choice(_MISRA_RULES)
    sev = random.choice(_SEVERITIES)
    line_num = random.randint(1, 200)
    col_num = random.randint(1, 40)
    msg = _SAMPLE_MESSAGES.get(rule, "violation")
    v_line = make_misra_violation(
        file=file,
        line=line_num,
        col=col_num,
        severity=sev,
        rule_id=rule,
        message=msg,
    )
    return v_line, code_line + "\n"


def make_misra_output(
    count: int = 5,
    source_files: Optional[list[str]] = None,
    include_context: bool = True,
) -> str:
    """生成完整的 cppcheck MISRA 输出文本。

    Parameters
    ----------
    count : int
        要生成的违规条目数。
    source_files : list[str], optional
        源文件列表。随机分配违规到这些文件。默认为 ["/src/main.c"]。
    include_context : bool
        是否包含上下文代码行（cppcheck 实际输出特征）。默认 True。

    Returns
    -------
    str
        完整的 cppcheck 输出文本，可用于 parse_cppcheck_output() 测试。
    """
    files = source_files or ["/src/main.c"]

    # Sample code context lines for realism
    _CONTEXT_LINES = [
        '    if (x == 0) {',
        '        return result;',
        '    } else {',
        '        printf("hello world");',
        '    }',
        '    while (*p != NULL) {',
        '        *p = (*p) | 0xFF;',
        '    }',
        '    int *p = (int*)malloc(sizeof(int) * 10);',
        '    return 0;',
        '    // This is a comment',
        '    volatile uint32_t *reg = (volatile uint32_t*)0x40000000;',
        '    *reg = 0x01;',
    ]

    lines = []
    for i in range(count):
        file = random.choice(files)
        code_line = random.choice(_CONTEXT_LINES) if include_context else ""
        v_line, ctx = _random_violation_line(file, code_line)
        lines.append(v_line.strip())
        if include_context and ctx.strip():
            carets = " " * random.randint(0, len(ctx) - 1) + "^"
            lines.append(ctx.strip())
            lines.append(carets)

    # Add a trailing checkersReport line like real cppcheck output
    lines.append("nofile:0:0: information: Active checkers: 309/1056 [checkersReport]")

    return "\n".join(lines) + "\n"


def make_misra_output_empty() -> str:
    """生成空的 cppcheck 输出（无违规）。"""
    return ""


def make_misra_output_only_header() -> str:
    """生成仅有 header 信息的 cppcheck 输出（无违规行）。"""
    return """\
nofile:0:0: information: Active checkers: 309/1056 [checkersReport]
"""


def make_misra_output_malformed() -> str:
    """生成包含格式异常行的 cppcheck 输出。

    包含：
      - 不完整的违规行
      - 缺少 file:line 前缀的上下文行
      - 未知严重级别的行
    """
    return """\
/src/main.c:42:5: style: Violation [misra-c2012-10.1]
    if (x) return;
    ^
(style) standalone message without file/line prefix
/src/utils.c:10:0: unknown_severity: weird format here
/src/main.c:99:1: style:
nofile:0:0: information: Active checkers: 309/1056 [checkersReport]
"""


def make_misra_output_massive(count: int = 1000) -> str:
    """生成大量违规的 cppcheck 输出，用于性能和批量测试。

    Parameters
    ----------
    count : int
        违规数量。默认 1000。

    Returns
    -------
    str
        包含 count 条违规的 cppcheck 输出。
    """
    return make_misra_output(count=count, source_files=["/src/main.c", "/src/utils.c", "/src/driver.c"])


# ------------------------------------------------------------------
# JUnit XML 生成
# ------------------------------------------------------------------


def make_junit_xml(
    total: int = 5,
    passed: int = 3,
    failed: int = 1,
    skipped: int = 1,
    errors: int = 0,
    suite_name: str = "pytest",
    time_seconds: float = 1.234,
) -> str:
    """生成模拟 JUnit XML 测试报告。

    Parameters
    ----------
    total : int
        测试用例总数（应 >= passed + failed + skipped + errors）。
    passed : int
        通过的测试数。
    failed : int
        失败的测试数。
    skipped : int
        跳过的测试数。
    errors : int
        错误的测试数。
    suite_name : str
        测试套件名称。
    time_seconds : float
        总执行时间。

    Returns
    -------
    str
        有效的 JUnit XML 字符串。
    """
    assert total >= passed + failed + skipped + errors, (
        f"total={total} < passed({passed})+failed({failed})+skipped({skipped})+errors({errors})"
    )

    cases = []
    test_index = 0

    for i in range(passed):
        test_index += 1
        cases.append(
            f'    <testcase classname="test_mod" name="test_pass_{i}" '
            f'time="{round(random.uniform(0.01, 0.5), 3)}" />'
        )

    for i in range(failed):
        test_index += 1
        cases.append(
            f'    <testcase classname="test_mod" name="test_fail_{i}" '
            f'time="{round(random.uniform(0.05, 0.3), 3)}">'
        )
        cases.append(
            '      <failure message="AssertionError: assert 1 == 2">'
        )
        cases.append("        def test_fail():")
        cases.append("    &gt;       assert 1 == 2")
        cases.append("    E       assert 1 == 2")
        cases.append("      </failure>")
        cases.append("    </testcase>")

    for i in range(skipped):
        test_index += 1
        cases.append(
            f'    <testcase classname="test_mod" name="test_skip_{i}" '
            f'time="0.000">'
        )
        cases.append('      <skipped message="unimportant" />')
        cases.append("    </testcase>")

    for i in range(errors):
        test_index += 1
        cases.append(
            f'    <testcase classname="test_mod" name="test_error_{i}" '
            f'time="{round(random.uniform(0.1, 0.6), 3)}">'
        )
        cases.append('      <error message="RuntimeError: boom!">')
        cases.append("        raise RuntimeError(\"boom!\")")
        cases.append("      </error>")
        cases.append("    </testcase>")

    # Any remaining tests (if total > sum of above) are passed
    remaining = total - (passed + failed + skipped + errors)
    for i in range(remaining):
        test_index += 1
        cases.append(
            f'    <testcase classname="test_mod" name="test_extra_{i}" '
            f'time="{round(random.uniform(0.01, 0.5), 3)}" />'
        )

    xml = '<?xml version="1.0" encoding="utf-8"?>\n'
    xml += f'<testsuites name="{suite_name} tests">\n'
    xml += f'  <testsuite name="{suite_name}" errors="{errors}" '
    xml += f'failures="{failed}" skipped="{skipped}" tests="{total}" '
    xml += f'time="{time_seconds}">\n'
    xml += "\n".join(cases) + "\n"
    xml += "  </testsuite>\n"
    xml += "</testsuites>\n"

    return xml


def make_junit_xml_with_shall(
    shal_ids: list[str],
    all_passed: bool = True,
) -> str:
    """生成包含 SHALL 测试用例的 JUnit XML。

    Parameters
    ----------
    shal_ids : list[str]
        SHALL ID 列表（如 ["10_1", "17_7"]）。
    all_passed : bool
        是否全部通过。若 False，一半的 SHALL 测试标记为失败。

    Returns
    -------
    str
        JUnit XML 字符串。
    """
    cases = []
    status = "passed" if all_passed else None
    for i, sid in enumerate(shal_ids):
        dur = round(random.uniform(0.05, 0.5), 3)
        if all_passed or i % 2 == 0:
            cases.append(
                f'    <testcase classname="test_mod" name="test_shall_{sid}" '
                f'time="{dur}" />'
            )
        else:
            cases.append(
                f'    <testcase classname="test_mod" name="test_shall_{sid}" '
                f'time="{dur}">'
            )
            cases.append('      <failure message="AssertionError" />')
            cases.append("    </testcase>")

    xml = '<?xml version="1.0" encoding="utf-8"?>\n'
    xml += '<testsuites name="pytest shall tests">\n'
    xml += f'  <testsuite name="pytest" errors="0" '
    xml += f'failures="{0 if all_passed else len(shal_ids)//2}" '
    xml += f'skipped="0" tests="{len(shal_ids)}" time="1.0">\n'
    xml += "\n".join(cases) + "\n"
    xml += "  </testsuite>\n"
    xml += "</testsuites>\n"
    return xml


def make_junit_empty() -> str:
    """生成空的 JUnit XML（无测试用例）。"""
    return """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites name="empty">
  <testsuite name="pytest" errors="0" failures="0" skipped="0" tests="0" time="0.001" />
</testsuites>
"""


def make_junit_malformed() -> str:
    """生成格式损坏的 JUnit XML。"""
    return "not xml at all, this is just text"


# ------------------------------------------------------------------
# lcov 覆盖率文件生成
# ------------------------------------------------------------------


def make_lcov(
    file_paths: Optional[list[str]] = None,
    line_rate: float = 85.0,
    branch_rate: float = 75.0,
) -> str:
    """生成模拟 lcov 覆盖率文件。

    根据指定的行覆盖率和分支覆盖率，生成一个包含指定数量文件的 lcov 输出。
    每个文件包含 DA（行覆盖率）和 BRDA（分支覆盖率）记录。

    Parameters
    ----------
    file_paths : list[str], optional
        要包含的源文件路径列表。默认为 ["/src/main.c", "/src/utils.c"]。
    line_rate : float
        目标行覆盖率百分比 (0-100)。
    branch_rate : float
        目标分支覆盖率百分比 (0-100)。

    Returns
    -------
    str
        lcov 格式的覆盖率文本。
    """
    files = file_paths or ["/src/main.c", "/src/utils.c"]
    lines_total_per_file = 50
    branches_total_per_file = 20

    lcov_str = ""
    for file_idx, file_path in enumerate(files):
        sf_line = f"SF:{file_path}\n"

        # DA records: line_number,execution_count
        da_lines = ""
        hit_lines = 0
        for line_num in range(1, lines_total_per_file + 1):
            exec_count = 1 if random.random() * 100 < line_rate else 0
            if exec_count > 0:
                hit_lines += 1
            da_lines += f"DA:{line_num},{exec_count}\n"

        # BRDA records: file,line_num,block_num,branch_num,taken
        brda_lines = ""
        hit_branches = 0
        for b in range(1, branches_total_per_file + 1):
            block = b // 2
            branch_num = b % 2
            taken = random.choice(["-", "0", "1", "2"])
            if taken != "-" and int(taken) > 0:
                hit_branches += 1
            brda_lines += f"BRDA:{line_num},{block},{branch_num},{taken}\n"

        lcov_str += sf_line
        lcov_str += da_lines
        lcov_str += brda_lines
        lcov_str += f"DA:{lines_total_per_file + 1},0\n"  # dummy
        lcov_str += f"LF:{lines_total_per_file}\n"
        lcov_str += f"LH:{hit_lines}\n"
        lcov_str += f"BRF:{branches_total_per_file}\n"
        lcov_str += f"BRH:{hit_branches}\n"
        lcov_str += "end_of_record\n"

    return lcov_str


def make_lcov_extreme() -> dict:
    """生成多种极端覆盖率场景的 lcov 数据。

    Returns
    -------
    dict
        键为场景名称，值为 lcov 文本。
    """
    return {
        "zero_coverage": make_lcov(
            file_paths=["/src/main.c"],
            line_rate=0.0,
            branch_rate=0.0,
        ),
        "full_coverage": make_lcov(
            file_paths=["/src/main.c"],
            line_rate=100.0,
            branch_rate=100.0,
        ),
        "many_files": make_lcov(
            file_paths=[f"/src/mod{i}.c" for i in range(50)],
            line_rate=80.0,
            branch_rate=70.0,
        ),
    }


def make_lcov_empty() -> str:
    """生成空的 lcov 文件（无记录）。"""
    return ""


# ------------------------------------------------------------------
# 趋势 JSONL 辅助
# ------------------------------------------------------------------


def make_trend_jsonl_entry(
    report_type: str = "misra",
    total_violations: int = 10,
    required: int = 5,
    advisory: int = 3,
    line_rate: float = 85.0,
    branch_rate: float = 75.0,
    commit: str = "",
) -> str:
    """生成单行趋势 JSONL 条目。

    Parameters
    ----------
    report_type : str
        "misra" 或 "coverage"。
    total_violations : int
        总违规数（仅 MISRA）。
    required : int
        Required 违规数（仅 MISRA）。
    advisory : int
        Advisory 违规数（仅 MISRA）。
    line_rate : float
        行覆盖率（仅 coverage）。
    branch_rate : float
        分支覆盖率（仅 coverage）。
    commit : str
        Git commit hash。

    Returns
    -------
    str
        JSON 行（末尾不带 \\n）。
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "commit": commit or f"mock-{random.randint(100000, 999999)}",
    }

    if report_type == "misra":
        entry.update({
            "total_violations": total_violations,
            "required": required,
            "advisory": advisory,
            "files_checked": random.randint(5, 50),
            "is_delta": True,
        })
    elif report_type == "coverage":
        entry["c"] = {
            "line_rate": line_rate,
            "branch_rate": branch_rate,
            "total_files": random.randint(5, 50),
        }

    return json.dumps(entry, ensure_ascii=False) + "\n"


# ------------------------------------------------------------------
# Convenience: write mock data to files
# ------------------------------------------------------------------


def write_mock_misra_output(output_path: str, count: int = 20) -> Path:
    """写入模拟 cppcheck 输出到文件并返回路径。"""
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(make_misra_output(count=count), encoding="utf-8")
    return p


def write_mock_junit(output_path: str, total: int = 10, failed: int = 2) -> Path:
    """写入模拟 JUnit XML 到文件并返回路径。"""
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        make_junit_xml(total=total, passed=total - failed, failed=failed),
        encoding="utf-8",
    )
    return p


def write_mock_lcov(output_path: str) -> Path:
    """写入模拟 lcov 文件并返回路径。"""
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(make_lcov(), encoding="utf-8")
    return p
