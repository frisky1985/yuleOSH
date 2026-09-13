#!/usr/bin/env python3

# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for ``yuleosh reverse scan`` CLI (B1-11)."""

import json

import pytest

from yuleosh.cli.commands.reverse import cmd_reverse_scan, _build_report, _confidence_distribution


def _write_sample_project(tmp_path):
    """写一个最小 C 工程，覆盖函数/全局/对象宏/函数式宏/调用。"""
    (tmp_path / "app.c").write_text(
        """
#include <stdint.h>

#define MAX_LEN 128
#define MIN(a,b) ((a) < (b) ? (a) : (b))

volatile uint32_t g_counter = 0;

void isr_handler(void) {
    g_counter++;
}

void app_task(void) {
    int x = MIN(1, 2);
    isr_handler();
}
""",
        encoding="utf-8",
    )
    # 第二文件：包含一个完整函数 + 一处语法错误，用于置信度 0.5 分桶
    (tmp_path / "broken.c").write_text(
        "int ok_func(int a) { return a; }\n"
        "int broken = ;  // syntax error\n",
        encoding="utf-8",
    )
    return tmp_path


def _make_args(tmp_path, json_out=True):
    class _Args:
        path = str(tmp_path)
        json = json_out
        save = None
    return _Args()


def test_reverse_scan_json_report(capsys, tmp_path):
    """reverse scan 输出 JSON 报告且实体计数正确。"""
    proj = _write_sample_project(tmp_path)
    rc = cmd_reverse_scan(_make_args(proj, json_out=True))
    assert rc == 0
    out = capsys.readouterr().out
    report = json.loads(out)

    stats = report["scan_stats"]
    assert stats["files_scanned"] == 2
    assert stats["code_files"] == 2

    counts = report["entity_counts"]
    # app.c: app_task + isr_handler = 2；broken.c: ok_func = 1
    assert counts["CFunction"] == 3
    # app.c: g_counter；broken.c: broken（声明被识别，初始化器含错）
    assert counts["CGlobalVar"] == 2
    # MAX_LEN(object) + MIN(function) = 2
    assert counts["CMacro"] == 2

    edges = report["edges"]
    # contains 边 = 全部 C 实体节点（CFunction/CGlobalVar/CMacro/ISR）之和
    expected_contains = (
        counts["CFunction"] + counts["CGlobalVar"] + counts["CMacro"] + counts["ISR"]
    )
    assert edges["contains"] == expected_contains
    # app_task -> isr_handler 是已解析的 calls 边
    assert edges["calls"] >= 1


def test_reverse_scan_text_report(capsys, tmp_path):
    """reverse scan 文本报告含扫描统计与置信度分桶。"""
    proj = _write_sample_project(tmp_path)
    rc = cmd_reverse_scan(_make_args(proj, json_out=False))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Scan Statistics" in out
    assert "Confidence Distribution" in out
    assert "CFunction" in out
    assert "CMacro" in out


def test_reverse_scan_confidence_distribution_buckets(tmp_path):
    """置信度分桶：干净文件 0.9，含错文件 0.5；函数式宏 0.35。"""
    from yuleosh.knowledge_graph.store import KGStore
    from yuleosh.knowledge_graph.c_code_scanner import scan_directory
    import tempfile, os

    proj = _write_sample_project(tmp_path)
    tmp = tempfile.NamedTemporaryFile(prefix="rev-test-", suffix=".db", delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        store = KGStore(tmp_path)
        summary = scan_directory(store, str(proj))
        dist = _confidence_distribution(store)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    # 干净函数 2 + 含错函数 1 → 0.9×2, 0.5×1
    fn_buckets = dist["CFunction"]
    assert fn_buckets.get(0.9, 0) == 2
    assert fn_buckets.get(0.5, 0) == 1
    # 函数式宏 MIN → 0.35；对象宏 MAX_LEN 在干净文件 → 0.9
    macro_buckets = dist["CMacro"]
    assert macro_buckets.get(0.35, 0) == 1
    assert macro_buckets.get(0.9, 0) == 1


def test_reverse_scan_missing_path(capsys):
    """路径不存在时报错并退出码 2。"""
    class _Args:
        path = "/nonexistent/path/xyz"
        json = False
        save = None
    rc = cmd_reverse_scan(_Args())
    assert rc == 2
