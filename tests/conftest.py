"""pytest configuration for yuleOSH tests."""

import os

import pytest

# Require a test JWT secret so auth modules don't raise at import time.
# The exact value is irrelevant for tests; any non-empty string works.
os.environ.setdefault("YULEOSH_JWT_SECRET", "test-jwt-secret-for-ci-only-not-for-production")

# NOTE (v3.12.x CI 真跑修复): OSH_HOME 不在此全局设置。
# 曾尝试 per-process 隔离 (yuleosh-pytest-<pid>) 防 event_bus 污染 /tmp，
# 但副作用是 test_api.py 等模块用 setdefault 自己设 OSH_HOME=repo 根时
# 被 conftest 抢占，导致 docs/spec.md 相对解析失败（11 errors）。
# /tmp 污染的真正根因已在 loop_engine/event_bus.py 修复：
# EventQueuePersistence 默认路径改为 _default_persistence_path()
# （OSH_HOME 优先，否则 tempfile 隔离目录），不再裸写 /tmp/.yuleosh。


@pytest.fixture(autouse=True)
def _isolate_global_registries():
    """每个测试后恢复单例注册表，防跨测试污染（2026-08-19）。

    背景：RulesetRegistry / ScannerRegistry 是模块级单例，测试内
    register(make_default=True) 会永久改写 _default / _registry，
    泄漏到后续测试。实证案例：test_rulesets.py::test_make_default_overrides
    注册 Second 为默认 → review_misra 的 GSCR 翻译拿到无
    translate_violations 的实例 → gscr-report.json 静默缺失
    （全量回归 -x 才暴露，单独跑单文件全绿）。

    恢复策略：
    - ScannerRegistry：自带 reset()（清空 + 重建 5 个内置适配器）。
    - RulesetRegistry：_instance=None 重建后是空注册表（内置注册只在
      registry.py 模块导入时执行一次），必须显式重注册 4 个内置规则集，
      与 registry.py 模块级 _registry 一致。
    """
    yield
    from yuleosh.ci.rulesets import (
        GscCppRuleSet,
        GscCRuleSet,
        GscrCompositeRuleSet,
        MisraC2023RuleSet,
        RulesetRegistry,
    )
    from yuleosh.ci.scanners import ScannerRegistry

    ScannerRegistry().reset()
    RulesetRegistry._instance = None
    _reg = RulesetRegistry()
    _reg.register(MisraC2023RuleSet)
    _reg.register(GscCRuleSet)
    _reg.register(GscCppRuleSet)
    _reg.register(GscrCompositeRuleSet, make_default=True)


def pytest_collection_modifyitems(config, items):
    """Skip perf-marked tests unless explicitly requested.

    Perf tests (test_kg_performance, test_perf_baseline, test_kb_dedup_perf)
    run benchmarks against the real 28MB knowledge-graph DB and can take
    minutes. They are isolated behind the ``perf`` marker:

      - Default suite:        perf tests are skipped (fast, no hang)
      - Explicit perf run:    pytest -m perf tests/test_kg_performance.py
                              or RUN_PERF=1 pytest tests/...
    """
    if os.environ.get("RUN_PERF"):
        return
    marker_expr = config.getoption("-m", default="")
    if "perf" in (marker_expr or "").split():
        return
    skip_perf = __import__("pytest").mark.skip(
        reason="perf/benchmark test — run with '-m perf' or RUN_PERF=1"
    )
    for item in items:
        if "perf" in item.keywords:
            item.add_marker(skip_perf)
