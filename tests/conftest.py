"""pytest configuration for yuleOSH tests."""

import os
import tempfile

# Require a test JWT secret so auth modules don't raise at import time.
# The exact value is irrelevant for tests; any non-empty string works.
os.environ.setdefault("YULEOSH_JWT_SECRET", "test-jwt-secret-for-ci-only-not-for-production")

# Isolate OSH_HOME per pytest process so modules that default to
# OSH_HOME (e.g. loop_engine.event_bus EventQueuePersistence) write to a
# private temp dir instead of polluting /tmp/.yuleosh.
#
# Why: pytest's tmp_path on CI lives under /tmp/pytest-of-runner/..., so its
# ancestor chain includes /tmp. If any earlier test creates /tmp/.yuleosh
# (the old OSH_HOME=/tmp default), test_hooks.py::test_no_project_marker
# wrongly detects a yuleosh project and fails. Setting OSH_HOME to a
# per-process temp dir keeps the whole suite hermetic.
_PID = os.getpid()
os.environ.setdefault("OSH_HOME", os.path.join(tempfile.gettempdir(), f"yuleosh-pytest-{_PID}"))


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
