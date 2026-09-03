#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0
"""回归测试: critical-safety 扫描器的跨行块注释假阳性修复。

2026-09-03: ``_strip_comment_and_strings`` 仅做单行剥离, 不跟踪跨行
/* ... */ 块注释状态。多行块注释内残留的示例代码(如 ``RCC->APB2ENR``)
会被 NULL 解引用正则误判为 CRIT-NULL-001, 阻断 GPIO 等嵌入式 demo 的
pipeline。本测试锁定:
  - ``_strip_block_comments`` 正确剥离跨行块注释且保留行数;
  - 跨行块注释内的寄存器访问不再触发 CRIT-NULL-001;
  - 真正的 malloc 后未判空解引用仍被检出(修复不弱化真实检查)。
"""

import tempfile
from pathlib import Path

from yuleosh.pipeline.step_handlers.review_critical_safety import (
    CriticalSafetyScanner,
    _strip_block_comments,
)


def test_strip_block_comments_multiline_preserves_line_count():
    lines = [
        "void f(void) {",
        "    /* 目标侧示例(注释):",
        "     * RCC->APB2ENR |= 1;",
        "     * GPIOA->CRL = 0x22222222;",
        "     */",
        "    int x = 1;",
        "}",
    ]
    out = _strip_block_comments(lines)
    assert len(out) == len(lines), "行数必须保持不变"
    joined = "\n".join(out)
    assert "RCC->APB2ENR" not in joined, "块注释内代码应被剥离"
    assert "GPIOA->CRL" not in joined, "块注释内代码应被剥离"
    # 注释外的真实代码不受影响
    assert "int x = 1;" in out[5]
    # 行长度不变(注释字符替换为空格)
    for a, b in zip(lines, out):
        assert len(a) == len(b)


def test_strip_block_comments_keeps_string_literals():
    lines = [
        'char* s = "a /* not a comment */ b";',
        "/* real comment with -> arrow */",
        "int y = 2;",
    ]
    out = _strip_block_comments(lines)
    assert '"a /* not a comment */ b"' in out[0], "字符串内的 /* */ 不当作注释"
    assert "real comment" not in out[1]
    assert "int y = 2;" in out[2]


def test_multiline_comment_not_flagged_as_null_deref():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "src").mkdir()
        (p / "src" / "main.c").write_text(
            "#include <stdint.h>\n"
            "volatile uint32_t* RCC;\n"
            "void init(void) {\n"
            "    /* 目标侧示例(注释):\n"
            "     * RCC->APB2ENR |= 1;\n"
            "     * GPIOA->CRL = 0x22222222;\n"
            "     */\n"
            "    RCC = (volatile uint32_t*)0x40021000;\n"
            "}\n"
        )
        scanner = CriticalSafetyScanner(p)
        violations = scanner.scan_all(["**/*.c"])
        null_violations = [v for v in violations if v.rule_id == "CRIT-NULL-001"]
        assert not null_violations, f"跨行块注释假阳性: {null_violations}"


def test_real_malloc_deref_still_flagged():
    # 注意: 扫描器的 malloc 检查用 re.match 锚定行首 (``var = malloc(...)``),
    # 类型前缀声明 (``int* p = malloc``) 当前不在其匹配范围; 这里用独立赋值行
    # 复现真实解引用场景, 验证修复未弱化既有检测。
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "src").mkdir()
        (p / "src" / "main.c").write_text(
            "#include <stdlib.h>\n"
            "void f(void) {\n"
            "    void* buf;\n"
            "    buf = malloc(16);\n"
            "    ((char*)buf)[0] = 0;  /* malloc 后未判空即解引用 */\n"
            "}\n"
        )
        scanner = CriticalSafetyScanner(p)
        violations = scanner.scan_all(["**/*.c"])
        assert any(v.rule_id == "CRIT-NULL-001" for v in violations), \
            "真实 malloc 后未判空解引用必须仍被检出"
