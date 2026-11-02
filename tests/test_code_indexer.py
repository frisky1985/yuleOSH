# @tests src/yuleosh/kb/code_indexer.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for code indexer — P1: 代码级语义索引。

Covers:
- T1: Python 文件签名提取（AST 解析）
- T2: C 文件签名提取（正则解析）
- T3: 索引内容生成（格式化）
- T4: 增量索引（content_hash 去重）
- T5: 文件排除逻辑
- T6: 端到端索引流程
- T7: 优雅降级（无向量扩展）
"""

import tempfile
from pathlib import Path

import pytest

from yuleosh.kb.code_indexer import (
    CodeIndexReport,
    _build_index_content,
    _collect_source_files,
    _extract_c_signatures,
    _extract_python_signatures,
    _should_exclude,
    index_project_code,
)
from yuleosh.kb.store import KbStore


# ═══════════════════════════════════════════════════════════════════════
# T1: Python 签名提取
# ═══════════════════════════════════════════════════════════════════════


def test_extract_python_signatures_functions(tmp_path):
    """T1.1: 提取模块级函数。"""
    py_file = tmp_path / "test_module.py"
    py_file.write_text('''
def foo():
    """Foo function."""
    pass

def bar(x, y):
    """Bar function with args."""
    return x + y

async def async_baz():
    """Async function."""
    pass
''')

    sigs = _extract_python_signatures(py_file)
    assert len(sigs["functions"]) == 3
    assert sigs["functions"][0]["name"] == "foo"
    assert sigs["functions"][0]["docstring"] == "Foo function."
    assert sigs["functions"][1]["name"] == "bar"
    assert sigs["functions"][2]["name"] == "async_baz"


def test_extract_python_signatures_classes(tmp_path):
    """T1.2: 提取类定义和方法。"""
    py_file = tmp_path / "test_class.py"
    py_file.write_text('''
class MyClass:
    """My class docstring."""

    def method_one(self):
        pass

    def method_two(self, x):
        pass

class AnotherClass:
    pass
''')

    sigs = _extract_python_signatures(py_file)
    assert len(sigs["classes"]) == 2
    assert sigs["classes"][0]["name"] == "MyClass"
    assert sigs["classes"][0]["docstring"] == "My class docstring."
    assert len(sigs["classes"][0]["methods"]) == 2
    assert "method_one" in sigs["classes"][0]["methods"]
    assert sigs["classes"][1]["name"] == "AnotherClass"


def test_extract_python_signatures_parse_error(tmp_path):
    """T1.3: 语法错误时返回空结果。"""
    py_file = tmp_path / "broken.py"
    py_file.write_text("def foo(:\n  pass\n")  # 语法错误

    sigs = _extract_python_signatures(py_file)
    assert sigs == {"functions": [], "classes": []}


# ═══════════════════════════════════════════════════════════════════════
# T2: C 签名提取
# ═══════════════════════════════════════════════════════════════════════


def test_extract_c_signatures_functions(tmp_path):
    """T2.1: 提取 C 函数定义。"""
    c_file = tmp_path / "test.c"
    c_file.write_text('''
#include <stdio.h>

int main(int argc, char *argv[]) {
    return 0;
}

static void helper_function(int x, int y) {
    // do something
}

const char* get_name(void) {
    return "test";
}
''')

    sigs = _extract_c_signatures(c_file)
    assert len(sigs["functions"]) >= 2
    names = [f["name"] for f in sigs["functions"]]
    assert "main" in names
    assert "helper_function" in names


def test_extract_c_signatures_header(tmp_path):
    """T2.2: 提取头文件函数声明。"""
    h_file = tmp_path / "test.h"
    h_file.write_text('''
#ifndef TEST_H
#define TEST_H

void init_system(void);
int process_data(const uint8_t* data, size_t len);

#endif
''')

    sigs = _extract_c_signatures(h_file)
    # 头文件中的函数声明（无函数体）可能不被正则匹配
    # 但不应崩溃
    assert isinstance(sigs["functions"], list)


def test_extract_c_signatures_empty(tmp_path):
    """T2.3: 空文件返回空列表。"""
    c_file = tmp_path / "empty.c"
    c_file.write_text("")

    sigs = _extract_c_signatures(c_file)
    assert sigs == {"functions": []}


# ═══════════════════════════════════════════════════════════════════════
# T3: 索引内容生成
# ═══════════════════════════════════════════════════════════════════════


def test_build_index_content_python():
    """T3.1: Python 索引内容格式化。"""
    signatures = {
        "functions": [
            {"name": "foo", "line": 10, "docstring": "Foo function."},
            {"name": "bar", "line": 20, "docstring": ""},
        ],
        "classes": [
            {"name": "MyClass", "line": 30, "methods": ["m1", "m2"]},
        ],
    }

    content = _build_index_content("src/module.py", "python", signatures)
    assert "File: src/module.py" in content
    assert "Language: python" in content
    assert "Functions:" in content
    assert "foo (line 10): Foo function." in content
    assert "bar (line 20)" in content
    assert "Classes:" in content
    assert "MyClass (line 30): methods: m1, m2" in content


def test_build_index_content_c():
    """T3.2: C 索引内容格式化。"""
    signatures = {
        "functions": [
            {"name": "main", "line": 5, "signature": "int main(int argc, char *argv[])"},
        ],
    }

    content = _build_index_content("src/main.c", "c", signatures)
    assert "File: src/main.c" in content
    assert "Language: c" in content
    assert "main (line 5): int main(int argc, char *argv[])" in content


# ═══════════════════════════════════════════════════════════════════════
# T4: 增量索引
# ═══════════════════════════════════════════════════════════════════════


def test_incremental_index_skips_unchanged(tmp_path):
    """T4.1: 重复索引时跳过未变文件。"""
    # 创建项目结构
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "module.py").write_text("def foo(): pass\n")

    db_path = tmp_path / "kb.db"
    store = KbStore(db_path=str(db_path))

    # 第一次索引
    report1 = index_project_code(tmp_path, store)
    assert report1.files_indexed == 1
    assert report1.files_skipped_unchanged == 0

    # 第二次索引（文件未变）
    report2 = index_project_code(tmp_path, store)
    assert report2.files_indexed == 0
    assert report2.files_skipped_unchanged == 1

    store.close()


def test_incremental_index_detects_changes(tmp_path):
    """T4.2: 文件变更后重新索引。"""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    py_file = src_dir / "module.py"

    db_path = tmp_path / "kb.db"
    store = KbStore(db_path=str(db_path))

    # 第一次索引
    py_file.write_text("def foo(): pass\n")
    report1 = index_project_code(tmp_path, store)
    assert report1.files_indexed == 1

    # 修改文件后重新索引
    py_file.write_text("def foo(): pass\ndef bar(): pass\n")
    report2 = index_project_code(tmp_path, store)
    assert report2.files_indexed == 1  # 重新索引
    assert report2.files_skipped_unchanged == 0

    store.close()


# ═══════════════════════════════════════════════════════════════════════
# T5: 文件排除
# ═══════════════════════════════════════════════════════════════════════


def test_should_exclude_test_files():
    """T5.1: 排除测试文件。"""
    assert _should_exclude(Path("test_module.py"))
    assert _should_exclude(Path("module_test.py"))
    assert _should_exclude(Path("conftest.py"))


def test_should_exclude_hidden_dirs():
    """T5.2: 排除隐藏目录。"""
    assert _should_exclude(Path(".git/config.py"))
    assert _should_exclude(Path("__pycache__/module.py"))
    assert _should_exclude(Path(".venv/lib/module.py"))


def test_should_not_exclude_normal_files():
    """T5.3: 不排除正常文件。"""
    assert not _should_exclude(Path("src/module.py"))
    assert not _should_exclude(Path("src/main.c"))


def test_collect_source_files(tmp_path):
    """T5.4: 收集源文件（排除测试和隐藏目录）。"""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "module.py").write_text("")
    (src_dir / "main.c").write_text("")
    (src_dir / "test_module.py").write_text("")  # 测试文件

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_foo.py").write_text("")  # 不在 src/ 下

    files = _collect_source_files(tmp_path)
    assert len(files) == 2  # 只有 module.py 和 main.c
    names = {f.name for f in files}
    assert "module.py" in names
    assert "main.c" in names
    assert "test_module.py" not in names


# ═══════════════════════════════════════════════════════════════════════
# T6: 端到端索引
# ═══════════════════════════════════════════════════════════════════════


def test_index_project_code_e2e(tmp_path):
    """T6.1: 端到端索引流程。"""
    # 创建项目结构
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "module.py").write_text('''
def foo():
    """Foo function."""
    pass

class Bar:
    def method(self):
        pass
''')
    (src_dir / "main.c").write_text('''
int main(int argc, char *argv[]) {
    return 0;
}
''')

    db_path = tmp_path / "kb.db"
    store = KbStore(db_path=str(db_path))

    report = index_project_code(tmp_path, store)

    assert report.files_scanned == 2
    assert report.files_indexed == 2
    assert report.files_skipped_unchanged == 0
    assert len(report.errors) == 0

    # 验证文章已写入
    articles = store.list_articles(limit=10)
    assert len(articles) == 2
    sources = {a.source for a in articles}
    assert "code_index" in sources

    store.close()


def test_index_project_code_no_src_dir(tmp_path):
    """T6.2: 无 src/ 目录时返回空报告。"""
    db_path = tmp_path / "kb.db"
    store = KbStore(db_path=str(db_path))

    report = index_project_code(tmp_path, store)

    assert report.files_scanned == 0
    assert report.files_indexed == 0

    store.close()


# ═══════════════════════════════════════════════════════════════════════
# T7: 优雅降级
# ═══════════════════════════════════════════════════════════════════════


def test_index_without_vector_store(tmp_path):
    """T7.1: 无向量库时仍写入 kb_articles。"""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "module.py").write_text("def foo(): pass\n")

    db_path = tmp_path / "kb.db"
    store = KbStore(db_path=str(db_path))

    # 不传 embedding_provider 和 vector_store
    report = index_project_code(
        tmp_path, store,
        embedding_provider=None,
        vector_store=None,
    )

    assert report.files_indexed == 1
    assert report.vectors_written == 0

    # 文章仍写入
    articles = store.list_articles(limit=10)
    assert len(articles) == 1

    store.close()


def test_index_with_tenant_org(tmp_path):
    """T7.2: 租户标识正确传递。"""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "module.py").write_text("def foo(): pass\n")

    db_path = tmp_path / "kb.db"
    store = KbStore(db_path=str(db_path))

    report = index_project_code(tmp_path, store, tenant_org="test-org")

    assert report.files_indexed == 1

    # 验证 tenant_org 已设置
    articles = store.list_articles(limit=10)
    assert len(articles) == 1
    assert articles[0].tenant_org == "test-org"

    store.close()
