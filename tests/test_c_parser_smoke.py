"""B1-04 冒烟基准测试。

递归扫描仓库 ``benchmark/``（含 ``legacy-cases/`` 三固件脱敏样例与 ``misra-fp-cases/``）
全部 ``.c`` 文件，断言 C AST 扫描器**对真实固件惯用法零崩溃**：

- ``parse_file`` 与所有 ``extract_*_file`` 入口**永不抛异常**；
- 三固件脱敏样例（valid C）``parse_ok is True``；
- 汇总解析成功率与错误率，供 B1-08 / B1-12 门禁趋势监控。

运行：``pytest tests/test_c_parser_smoke.py -o addopts= -p no:cacheprovider``
"""

import os
from pathlib import Path

import pytest

from yuleosh.knowledge_graph.c_parser import (
    extract_call_graph_file,
    extract_functions_file,
    extract_globals_file,
    extract_isrs_file,
    extract_macros_file,
    parse_file,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = REPO_ROOT / "benchmark"


def _discover_c_files():
    if not BENCHMARK_DIR.exists():
        return []
    return sorted(BENCHMARK_DIR.rglob("*.c"))


C_FILES = _discover_c_files()


def _assert_no_crash(path):
    """六个提取入口依次调用，任一抛异常即失败（零崩溃硬要求）。"""
    results = {}
    # parse_file
    results["parse"] = parse_file(str(path))
    # 各 extract_* 入口
    results["functions"] = extract_functions_file(str(path))
    results["call_graph"] = extract_call_graph_file(str(path))
    results["globals"] = extract_globals_file(str(path))
    results["isrs"] = extract_isrs_file(str(path))
    results["macros"] = extract_macros_file(str(path))
    return results


@pytest.mark.skipif(not C_FILES, reason="benchmark/ 下未找到 .c 文件")
def test_benchmark_files_present():
    # 至少存在 misra-fp-cases 与 legacy-cases 的样例
    assert len(C_FILES) >= 1


@pytest.mark.parametrize("path", C_FILES, ids=lambda p: os.path.relpath(str(p), REPO_ROOT))
def test_all_benchmark_c_parse_without_crash(path):
    """每个 benchmark .c 经全部提取入口解析，绝不抛异常。"""
    try:
        _assert_no_crash(path)
    except Exception as exc:  # pragma: no cover - 零崩溃契约
        pytest.fail(f"{path} 解析抛异常（违反零崩溃契约）：{exc!r}")


@pytest.mark.skipif(not C_FILES, reason="benchmark/ 下未找到 .c 文件")
def test_legacy_firmware_samples_parse_ok():
    """三固件脱敏样例（valid C）必须 parse_ok=True。"""
    legacy = [p for p in C_FILES if "legacy-cases" in p.parts]
    assert legacy, "benchmark/legacy-cases/ 下应有三固件样例"
    for path in legacy:
        res = parse_file(str(path))
        assert res.ok is True, f"{path} 应为合法 C（parse_ok=False）"


@pytest.mark.skipif(not C_FILES, reason="benchmark/ 下未找到 .c 文件")
def test_smoke_report():
    """汇总解析成功率与错误率（趋势监控，不硬性失败）。"""
    total = len(C_FILES)
    ok = 0
    err_sum = 0.0
    for path in C_FILES:
        res = parse_file(str(path))
        if res.ok:
            ok += 1
        err_sum += res.error_rate
    rate = ok / total if total else 0.0
    avg_err = err_sum / total if total else 0.0
    # 打印供 CI 日志 / kpi_trends 采集
    print(f"\n[smoke] benchmark .c 文件数={total} parse_ok={ok} 成功率={rate:.2%} 平均错误率={avg_err:.4f}")
    # 硬门槛：全部文件不得崩溃（已在 parametrize 用例覆盖）；此处仅记录。
    assert total >= 1
