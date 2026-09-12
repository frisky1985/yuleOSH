"""B1-03 函数级提取测试 (T-011 Q4 sprint).

覆盖：正常函数 / 函数原型 / K&R 老式声明 / 指针·数组参数 / 前导注释 /
存储类(static·inline) / void 无参 / 坏 C·二进制·缺失文件零崩溃。
"""

import os

from yuleosh.knowledge_graph import c_parser


SAMPLE = """
/* 前导注释：加法器 */
static int add(int a, int b) {
    return a + b;
}

/* 仅原型 */
void proto(void);

inline unsigned long compute(const char *buf, size_t n) {
    return n;
}

int main(int argc, char *argv[]) {
    return 0;
}

/* K&R 老式声明 */
int legacy(a, b)
    int a;
    int b;
{
    return a + b;
}
"""


def _by_name(r, name):
    for f in r["functions"]:
        if f["name"] == name:
            return f
    return None


def test_extract_counts():
    r = c_parser.extract_functions(SAMPLE.encode("utf-8"), "sample.c")
    assert r["parse_ok"] is True
    names = {f["name"] for f in r["functions"]}
    assert names == {"add", "proto", "compute", "main", "legacy"}
    assert r["count"] == 5


def test_normal_function():
    r = c_parser.extract_functions(SAMPLE.encode("utf-8"), "sample.c")
    add = _by_name(r, "add")
    assert add["return_type"] == "int"
    assert add["storage_class"] == "static"
    assert add["is_definition"] is True
    assert add["parameters"] == [
        {"name": "a", "type": "int"},
        {"name": "b", "type": "int"},
    ]
    assert add["leading_comment"] is not None
    assert "加法器" in add["leading_comment"]
    # 行区间合法
    assert 1 <= add["start_line"] <= add["end_line"]


def test_prototype_is_not_definition():
    r = c_parser.extract_functions(SAMPLE.encode("utf-8"), "sample.c")
    proto = _by_name(r, "proto")
    assert proto["is_definition"] is False
    assert proto["parameters"] == [{"name": None, "type": "void"}]


def test_pointer_and_array_params():
    r = c_parser.extract_functions(SAMPLE.encode("utf-8"), "sample.c")
    compute = _by_name(r, "compute")
    assert ("buf", "const char *") in [(p["name"], p["type"]) for p in compute["parameters"]]
    main = _by_name(r, "main")
    types = {p["name"]: p["type"] for p in main["parameters"]}
    assert types["argc"] == "int"
    assert "*" in types["argv"] and "[]" in types["argv"]


def test_kr_style_declaration():
    r = c_parser.extract_functions(SAMPLE.encode("utf-8"), "sample.c")
    legacy = _by_name(r, "legacy")
    assert legacy["is_definition"] is True
    # K&R：参数名捕获，类型留空（在外部声明解析）
    names = [p["name"] for p in legacy["parameters"]]
    assert names == ["a", "b"]
    assert all(p["type"] == "" for p in legacy["parameters"])


def test_storage_class_inline():
    r = c_parser.extract_functions(SAMPLE.encode("utf-8"), "sample.c")
    compute = _by_name(r, "compute")
    assert compute["storage_class"] == "inline"


def test_as_dict_keys():
    r = c_parser.extract_functions(SAMPLE.encode("utf-8"), "sample.c")
    f = r["functions"][0]
    assert set(f.keys()) == {
        "name", "return_type", "storage_class", "parameters",
        "is_definition", "start_line", "end_line", "byte_start", "byte_end",
        "leading_comment",
    }


def test_malformed_c_no_crash():
    bad = b"int main( { return ; } void foo(\n"
    r = c_parser.extract_functions(bad, "bad.c")
    assert isinstance(r, dict)
    assert r["count"] >= 0
    # 即便有语法错误，也应成功构建树（容错）
    assert r["parse_ok"] is True
    # 不抛异常即可（允许 0 或若干提取）


def test_binary_input_no_crash():
    binary = bytes(range(256))
    r = c_parser.extract_functions(binary, "binary.bin")
    assert isinstance(r, dict)
    assert r["count"] >= 0


def test_missing_file_no_crash():
    r = c_parser.extract_functions_file("/no/such/file.c")
    assert r["parse_ok"] is False
    assert r["count"] == 0
    assert r["functions"] == []


def test_empty_string():
    r = c_parser.extract_functions(b"", "empty.c")
    assert r["count"] == 0


def test_large_file_no_crash():
    # 5 万行重复函数 —— 验证零崩溃与可接受性能
    lines = ["int fn_%d(int x) { return x + %d; }" % (i, i % 7) for i in range(50000)]
    src = ("\n".join(lines)).encode("utf-8")
    r = c_parser.extract_functions(src, "big.c")
    assert r["parse_ok"] is True
    assert r["count"] == 50000


def test_extract_functions_file_real(tmp_path):
    p = tmp_path / "m.c"
    p.write_text(SAMPLE, encoding="utf-8")
    r = c_parser.extract_functions_file(str(p))
    assert r["parse_ok"] is True
    assert {f["name"] for f in r["functions"]} == {"add", "proto", "compute", "main", "legacy"}
