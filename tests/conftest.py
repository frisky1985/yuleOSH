"""pytest configuration for yuleOSH tests."""

import os

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
