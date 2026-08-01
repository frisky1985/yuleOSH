"""pytest configuration for yuleOSH tests."""

import os

# Require a test JWT secret so auth modules don't raise at import time.
# The exact value is irrelevant for tests; any non-empty string works.
os.environ.setdefault("YULEOSH_JWT_SECRET", "test-jwt-secret-for-ci-only-not-for-production")


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
