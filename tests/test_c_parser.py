"""B1-02 容错 C 解析封装测试。

核心断言：parse() / parse_file() 对任何输入都不抛异常，且错误可量化。
"""

import os
import tempfile

import pytest

from yuleosh.knowledge_graph.c_parser import (
    CParseResult,
    parse,
    parse_file,
)

VALID_C = """
#include <stdint.h>

static volatile uint32_t g_counter = 0;

int add(int a, int b) {
    return a + b;
}

void isr_handler(void) {
    g_counter++;
}
""".encode("utf-8")

# 坏 C：缺分号 + 未闭合复合语句
BROKEN_C = b"int main() { int x = 1 return 0; }\nvoid foo(int a) {"


def test_valid_c_no_syntax_error():
    r = parse(VALID_C, filename="valid.c")
    assert isinstance(r, CParseResult)
    assert r.ok is True
    assert r.has_syntax_error is False
    assert r.error_count == 0
    assert r.missing_count == 0
    assert r.root_node is not None
    assert r.total_nodes > 0


def test_broken_c_never_raises_and_counts_errors():
    r = parse(BROKEN_C, filename="broken.c")
    assert r.ok is True  # 树构建成功，但含语法错误
    assert r.has_syntax_error is True
    assert r.error_count > 0
    assert r.missing_count > 0  # 缺 ';' 与未闭合 '}' 应记为 missing
    # error_nodes 含位置信息
    assert any(e.kind == "missing" for e in r.error_nodes)
    assert r.error_rate > 0.0


def test_empty_source_does_not_raise():
    r = parse(b"", filename="empty.c")
    assert r.ok is True
    assert r.byte_length == 0
    # 空翻译单元通常有 1 个根节点、无错误
    assert r.error_count == 0


def test_accepts_str_input():
    r = parse("int main(void) { return 0; }", filename="str.c")
    assert r.ok is True
    assert r.error_count == 0


def test_parse_file_missing_never_raises():
    r = parse_file("/no/such/file_abc.c")
    assert r.ok is False
    assert r.exception is not None
    assert "read failed" in r.exception


def test_parse_file_binary_never_crashes():
    with tempfile.NamedTemporaryFile(suffix=".c", delete=False) as f:
        path = f.name
        f.write(b"\x00\x01\x02\x03int main() {\xff\xfe return 0; }\x00")
    try:
        r = parse_file(path)
        assert isinstance(r, CParseResult)
        # 二进制兜底解码后至少能构建树（不崩溃）
        assert r.ok is True
    finally:
        os.unlink(path)


def test_large_file_no_crash():
    # 生成约 50k 行 C（远超普通单文件），确认零崩溃且耗时可控
    lines = ["int f%d(int x) { return x + %d; }" % (i, i % 7) for i in range(50000)]
    big = ("\n".join(lines)).encode("utf-8")
    r = parse(big, filename="big.c")
    assert r.ok is True
    assert r.total_nodes > 1000
    assert r.has_syntax_error is False


def test_error_rate_quantified():
    r = parse(BROKEN_C, filename="broken.c")
    assert 0.0 <= r.error_rate <= 1.0
    assert r.error_rate == r.error_count / r.total_nodes


def test_as_dict_serializable():
    r = parse(BROKEN_C, filename="broken.c")
    d = r.as_dict()
    assert d["filename"] == "broken.c"
    assert isinstance(d["error_nodes"], list)
    assert set(d.keys()) >= {"ok", "error_count", "missing_count", "error_rate"}


def test_root_node_none_when_failed():
    r = parse_file("/no/such/file.c")
    assert r.root_node is None
