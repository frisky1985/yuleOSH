# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
ASPICE SWE.4-BP4 — 性能/资源消耗基线测试套件

覆盖模块：
  1. Spec 解析性能     — parse_spec 不同规模 spec.md
  2. 证据包生成性能     — EvidenceCollector 链式操作
  3. CI 配置加载        — load_ci_config / _parse_ci_config
  4. API 响应时间       — auth / subscription / wizard 核心函数
  5. 内存基线           — 关键模块导入后 RSS 增量

运行:
    pytest tests/test_perf_baseline.py -v
    pytest -m perf -v    # 仅 perf 标记
"""

import os
import sys
import time
import tempfile
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

# ---------------------------------------------------------------------------
# 常量与阈值 — 宽松，避免 CI 环境波动导致误报
# ---------------------------------------------------------------------------

# Spec 解析阈值 (秒)
THRESHOLD_SPEC_PARSE_SMALL  = 2.0    # 10 需求
THRESHOLD_SPEC_PARSE_MEDIUM = 3.0    # 100 需求
THRESHOLD_SPEC_PARSE_LARGE  = 5.0    # 500 需求

# Evidence 阈值 (秒)
THRESHOLD_EVIDENCE_INIT     = 0.5
THRESHOLD_EVIDENCE_CHAIN    = 5.0
THRESHOLD_EVIDENCE_COVER    = 2.0
THRESHOLD_TRACEABILITY      = 2.0

# CI 配置阈值 (秒)
THRESHOLD_CI_DEFAULT        = 0.5
THRESHOLD_CI_YAML           = 0.5
THRESHOLD_CI_PARSE_HEAVY    = 1.0
THRESHOLD_CI_CHECKS         = 0.1

# API 阈值 (秒)
THRESHOLD_AUTH_SLUGIFY      = 0.5
THRESHOLD_AUTH_BCRYPT       = 2.0
THRESHOLD_AUTH_JWT          = 1.0
THRESHOLD_SUB_TIER          = 0.2
THRESHOLD_SUB_TOKEN         = 0.2
THRESHOLD_WIZARD_JWT        = 0.5
THRESHOLD_CORE_JSON_OK      = 0.1

# 内存阈值 (MiB)
THRESHOLD_MEM_MODULE        = 200
THRESHOLD_MEM_FULL          = 500

# 集成阈值 (秒)
THRESHOLD_SPEC_TO_EVIDENCE  = 10.0
THRESHOLD_CI_AND_COVER      = 1.0

# 环境
OSH_HOME = os.environ.get("OSH_HOME", os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_spec_file(tmpdir: str, req_count: int,
                    scenario_count: int = 0) -> str:
    """生成包含 req_count 个需求、scenario_count 个场景的 spec.md。

    Uses '## Function Requirements' heading to avoid matching
    the parse_spec regex (which catches '## Requirements').
    """
    path = os.path.join(tmpdir, "perf_spec_baseline.md")
    lines = [
        "# Performance Baseline Spec",
        "",
        f"## Functional Requirements ({req_count} total)",
        "",
    ]
    for i in range(req_count):
        rid = f"RS-{i+1:03d}"
        lines.append(f"### {rid}: Performance requirement {i+1}")
        lines.append("")
        lines.append("**Status:** APPROVED")
        lines.append("")
        lines.append("#### Reason")
        lines.append(
            f"This requirement verifies spec parsing at scale ({req_count} reqs)."
        )
        lines.append("")
        lines.append("#### Specification")
        for j in range(3):
            lines.append(
                f"- The system SHALL handle sub-scenario {j} for Req-{i+1}."
            )
        if i % 2 == 0:
            lines.append(f"- The system SHOULD optimise path {i} under load.")
            lines.append(f"- The system MAY degrade gracefully.")
        lines.append("")

    for i in range(scenario_count):
        lines.append(f"### Scenario: scenario_{i}")
        lines.append(f"- GIVEN condition {i} is met")
        lines.append(f"- WHEN action {i} is triggered")
        lines.append(f"- THEN outcome {i} is observed")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def _make_ci_config(tmpdir: str, layers: list[int] | None = None) -> str:
    """在 tmpdir/.yuleosh/ 下创建 ci-config.yaml。"""
    if layers is None:
        layers = [1, 2, 25, 3]
    config = {
        "ci": {
            "layers": layers,
            "layer_dependencies": {1: [], 2: [1], 25: [1, 2], 3: [1, 2, 25]},
        },
        "coverage": {
            "threshold_line": 85.0,
            "threshold_condition": 80.0,
            "strict": False,
        },
        "hardware_test": {
            "enabled": True,
            "firmware": "build/firmware.elf",
            "mock": True,
        },
    }
    dirpath = os.path.join(tmpdir, ".yuleosh")
    os.makedirs(dirpath, exist_ok=True)
    path = os.path.join(dirpath, "ci-config.yaml")
    import yaml
    with open(path, "w") as f:
        yaml.dump(config, f)
    return path


def _measure_import_mem(module_name: str, rel_src: str = "") -> float:
    """通过 subprocess 测量模块导入的内存增量 (MiB, tracemalloc)。"""
    src_path = os.path.join(OSH_HOME, "src") if not rel_src else rel_src
    code = f"""\
import tracemalloc, gc
gc.collect()
tracemalloc.start()
snap1 = tracemalloc.take_snapshot()
import {module_name}
snap2 = tracemalloc.take_snapshot()
gc.collect()
stats = snap2.compare_to(snap1, 'lineno')
total = sum(s.size_diff for s in stats if s.size_diff > 0)
print(f"{{total / 1024 / 1024:.2f}}")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "PYTHONPATH": src_path},
    )
    if result.returncode != 0:
        return -1.0
    try:
        return float(result.stdout.strip())
    except (ValueError, TypeError):
        return -1.0


# ---------------------------------------------------------------------------
# 1. Spec 解析性能 — parse_spec
# ---------------------------------------------------------------------------

class TestSpecParsePerf:
    """SWE.4-BP4: Spec 解析性能基线 (parse_spec)."""

    @pytest.mark.perf
    def test_spec_parse_10_reqs(self):
        """小规模 spec (10 需求) 解析时间 < 2.0s"""
        from yuleosh.spec.validate import parse_spec

        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = _make_spec_file(tmpdir, 10, scenario_count=5)
            start = time.perf_counter()
            doc = parse_spec(spec_path)
            elapsed = time.perf_counter() - start

        assert len(doc.requirements) >= 10, (
            f"Expected >=10 requirements, got {len(doc.requirements)}"
        )
        assert elapsed < THRESHOLD_SPEC_PARSE_SMALL, (
            f"10-req spec parse took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_SPEC_PARSE_SMALL}s"
        )

    @pytest.mark.perf
    def test_spec_parse_100_reqs(self):
        """中等规模 spec (100 需求) 解析时间 < 3.0s"""
        from yuleosh.spec.validate import parse_spec

        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = _make_spec_file(tmpdir, 100, scenario_count=30)
            start = time.perf_counter()
            doc = parse_spec(spec_path)
            elapsed = time.perf_counter() - start

        assert len(doc.requirements) >= 100
        assert elapsed < THRESHOLD_SPEC_PARSE_MEDIUM, (
            f"100-req spec parse took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_SPEC_PARSE_MEDIUM}s"
        )

    @pytest.mark.perf
    def test_spec_parse_500_reqs(self):
        """大规模 spec (500 需求) 解析时间 < 5.0s"""
        from yuleosh.spec.validate import parse_spec

        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = _make_spec_file(tmpdir, 500, scenario_count=100)
            start = time.perf_counter()
            doc = parse_spec(spec_path)
            elapsed = time.perf_counter() - start

        assert len(doc.requirements) >= 500
        assert elapsed < THRESHOLD_SPEC_PARSE_LARGE, (
            f"500-req spec parse took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_SPEC_PARSE_LARGE}s"
        )

    @pytest.mark.perf
    def test_spec_validate_100_reqs(self):
        """Spec 验证性能 — 100 需求完成验证 < 3.0s"""
        from yuleosh.spec.validate import parse_spec, validate_spec

        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = _make_spec_file(tmpdir, 100, scenario_count=30)
            doc = parse_spec(spec_path)
            start = time.perf_counter()
            issues = validate_spec(doc)
            elapsed = time.perf_counter() - start

        assert elapsed < 3.0, (
            f"100-req spec validation took {elapsed:.3f}s, expected <3.0s"
        )

    @pytest.mark.perf
    def test_spec_diff_perf(self):
        """Spec Diff 性能 — 100→105 需求 < 3.0s"""
        from yuleosh.spec.validate import diff_specs

        with tempfile.TemporaryDirectory() as tmpdir:
            old_path = _make_spec_file(tmpdir, 100, scenario_count=20)
            new_path = _make_spec_file(tmpdir, 105, scenario_count=25)
            start = time.perf_counter()
            delta = diff_specs(old_path, new_path)
            elapsed = time.perf_counter() - start

        assert elapsed < 3.0, (
            f"100→105-req spec diff took {elapsed:.3f}s, expected <3.0s"
        )


# ---------------------------------------------------------------------------
# 2. 证据包生成性能 — EvidenceCollector
# ---------------------------------------------------------------------------

class TestEvidencePerf:
    """SWE.4-BP4: 证据包生成性能基线."""

    @pytest.mark.perf
    def test_evidence_collector_init(self):
        """EvidenceCollector 初始化时间 < 0.5s"""
        from yuleosh.evidence.generator import EvidenceCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            start = time.perf_counter()
            collector = EvidenceCollector(tmpdir)
            elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLD_EVIDENCE_INIT, (
            f"EvidenceCollector init took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_EVIDENCE_INIT}s"
        )

    @pytest.mark.perf
    def test_evidence_collect_requirements_via_spec(self):
        """通过 spec 模块收集需求 < 2.0s (不经过 collection.py 的脆弱 import)"""
        from yuleosh.spec.validate import parse_spec

        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = _make_spec_file(tmpdir, 50, scenario_count=15)
            start = time.perf_counter()
            doc = parse_spec(spec_path)
            reqs = [r.to_dict() for r in doc.requirements]
            scenarios = [s.to_dict() for s in doc.scenarios]
            elapsed = time.perf_counter() - start

        assert len(reqs) >= 50
        assert elapsed < 2.0, (
            f"Spec→requirements took {elapsed:.3f}s, expected <2.0s"
        )

    @pytest.mark.perf
    def test_evidence_full_chain_empty(self):
        """空项目证据链全流程 (直接操作 collector) < 5.0s"""
        from yuleosh.evidence.generator import EvidenceCollector
        from yuleosh.spec.validate import parse_spec

        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = _make_spec_file(tmpdir, 10, scenario_count=3)
            doc = parse_spec(spec_path)

            collector = EvidenceCollector(tmpdir)
            # 直接从 parser 填充 collector，绕开 collection.py 的脆弱 import
            collector.requirements = [r.to_dict() for r in doc.requirements]
            collector.scenarios = [s.to_dict() for s in doc.scenarios]

            start = time.perf_counter()

            tm = collector.generate_traceability_matrix()
            cov = collector.generate_requirement_coverage()
            am = collector.generate_acceptance_matrix()

            elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLD_EVIDENCE_CHAIN, (
            f"Full evidence chain (no CI/SIL) took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_EVIDENCE_CHAIN}s"
        )

    @pytest.mark.perf
    def test_evidence_traceability_matrix(self):
        """Traceability matrix 生成 < 2.0s (50 需求 × 每个 10 个测试引用)"""
        from yuleosh.evidence.generator import EvidenceCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            collector = EvidenceCollector(tmpdir)
            collector.requirements = [
                {"name": f"Req-{i}", "req_id": f"RS-{i:03d}",
                 "level": "SYS", "status": "APPROVED",
                 "shall": ["Do stuff"], "should": [], "may": [],
                 "reason": "Testing", "parent": "",
                 "shall_count": 1, "should_count": 0, "may_count": 0}
                for i in range(50)
            ]
            for i in range(50):
                req_id = f"RS-{i:03d}"
                collector.test_coverage[req_id] = [
                    f"test_{i}_a", f"test_{i}_b",
                    f"test_{i}_c", f"test_{i}_d", f"test_{i}_e",
                ]

            start = time.perf_counter()
            tm = collector.generate_traceability_matrix()
            elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLD_TRACEABILITY, (
            f"Traceability matrix (50 reqs × 5 tests) took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_TRACEABILITY}s"
        )
        assert len(tm) > 0

    @pytest.mark.perf
    def test_evidence_coverage_summary(self):
        """Coverage summary 生成 < 1.0s (含 100% 覆盖数据)"""
        from yuleosh.evidence.generator import EvidenceCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            collector = EvidenceCollector(tmpdir)
            collector.requirements = [
                {"name": f"Req-{i}", "req_id": f"RS-{i:03d}",
                 "level": "SYS", "status": "APPROVED",
                 "shall": ["Do stuff"], "should": [], "may": [],
                 "reason": "Testing", "parent": "",
                 "shall_count": 1, "should_count": 0, "may_count": 0}
                for i in range(50)
            ]
            for i in range(50):
                collector.req_to_tests[f"RS-{i:03d}"] = [
                    f"test_{i}_0", f"test_{i}_1"
                ]
                collector.test_to_reqs[f"test_{i}_0"] = [f"RS-{i:03d}"]
                collector.test_to_reqs[f"test_{i}_1"] = [f"RS-{i:03d}"]

            start = time.perf_counter()
            cov = collector.generate_requirement_coverage()
            elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLD_EVIDENCE_COVER, (
            f"Coverage summary took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_EVIDENCE_COVER}s"
        )


# ---------------------------------------------------------------------------
# 3. CI 配置加载
# ---------------------------------------------------------------------------

class TestCiConfigPerf:
    """SWE.4-BP4: CI 配置加载性能基线."""

    @pytest.mark.perf
    def test_ci_config_load_default(self):
        """CI 配置默认加载 (无文件) < 0.5s"""
        from yuleosh.ci.config import load_ci_config, _clear_ci_config_cache

        _clear_ci_config_cache()
        with tempfile.TemporaryDirectory() as tmpdir:
            start = time.perf_counter()
            cfg = load_ci_config(project_dir=tmpdir)
            elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLD_CI_DEFAULT, (
            f"Default CI config load took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_CI_DEFAULT}s"
        )
        assert cfg.coverage.threshold_line == 85.0

    @pytest.mark.perf
    def test_ci_config_load_from_yaml(self):
        """CI 配置从 YAML 加载 < 0.5s"""
        from yuleosh.ci.config import load_ci_config, _clear_ci_config_cache

        _clear_ci_config_cache()
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_ci_config(tmpdir, layers=[1, 2, 3])
            start = time.perf_counter()
            cfg = load_ci_config(project_dir=tmpdir)
            elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLD_CI_YAML, (
            f"YAML CI config load took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_CI_YAML}s"
        )
        assert cfg.layers == [1, 2, 3]

    @pytest.mark.perf
    def test_ci_config_parse_heavy(self):
        """_parse_ci_config 大配置 (含 20 个模块阈值) < 1.0s"""
        from yuleosh.ci.config import _parse_ci_config

        raw = {
            "ci": {"layers": [1, 2, 25, 3]},
            "coverage": {
                "threshold_line": 85.0,
                "threshold_condition": 80.0,
                "strict": True,
                "module_thresholds": {
                    f"module_{i:03d}": 75.0 + (i % 20)
                    for i in range(20)
                },
            },
            "hardware_test": {
                "enabled": True,
                "firmware": "build/firmware.elf",
                "boot_pattern": "Boot Complete",
                "serial_port": "/dev/ttyUSB0",
                "baud": 115200,
                "test_timeout": 60,
                "mock": True,
            },
        }

        start = time.perf_counter()
        cfg = _parse_ci_config(raw)
        elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLD_CI_PARSE_HEAVY, (
            f"Parse heavy CI config took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_CI_PARSE_HEAVY}s"
        )
        assert len(cfg.coverage.module_thresholds) == 20

    @pytest.mark.perf
    def test_ci_strict_and_misra_checks(self):
        """CI 辅助函数 (is_strict, is_misra_fail_fast) < 0.1s"""
        from yuleosh.ci.config import is_strict, is_misra_fail_fast

        start = time.perf_counter()
        _ = is_strict()
        _ = is_misra_fail_fast()
        elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLD_CI_CHECKS, (
            f"CI check functions took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_CI_CHECKS}s"
        )


# ---------------------------------------------------------------------------
# 4. API 核心函数响应时间
# ---------------------------------------------------------------------------

class TestApiPerf:
    """SWE.4-BP4: API 核心函数响应时间基线."""

    @pytest.mark.perf
    def test_auth_slugify_1000(self):
        """auth._slugify 1000 次调用的总耗时 < 0.5s"""
        from yuleosh.api.auth import _slugify

        inputs = [
            "Hello World",
            "   Trimmed   Text   ",
            "Special!@#Chars$%^",
            "UPPERCASE lowerCASE MiXeD",
            "a-b_c.d/e",
            "Trailing dash --- ",
            "Numbers 123 in text 456",
        ] * 150  # ~1050 calls

        start = time.perf_counter()
        for s in inputs:
            _ = _slugify(s)
        elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLD_AUTH_SLUGIFY, (
            f"1050 slugify calls took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_AUTH_SLUGIFY}s"
        )

    @pytest.mark.perf
    def test_auth_bcrypt_hash_verify(self):
        """bcrypt hash + verify 10 次循环 < 2.0s"""
        import bcrypt

        password = b"TestP@ssword123!Secure"
        start = time.perf_counter()
        for _ in range(10):
            hashed = bcrypt.hashpw(password, bcrypt.gensalt(rounds=6))
            bcrypt.checkpw(password, hashed)
        elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLD_AUTH_BCRYPT, (
            f"10 bcrypt hash+verify cycles took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_AUTH_BCRYPT}s"
        )

    @pytest.mark.perf
    def test_auth_jwt_encode_decode(self):
        """JWT encode/decode 500 次 < 1.0s"""
        import jwt

        secret = "test-secret-key-for-perf-baseline-test"
        payload = {"user_id": 42, "org_id": 1, "role": "admin"}

        start = time.perf_counter()
        for _ in range(500):
            token = jwt.encode(payload, secret, algorithm="HS256")
            _ = jwt.decode(token, secret, algorithms=["HS256"])
        elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLD_AUTH_JWT, (
            f"500 JWT encode/decode cycles took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_AUTH_JWT}s"
        )

    @pytest.mark.perf
    def test_subscription_tier_lookup_10000(self):
        """TIERS 字典查找 10000 次 < 0.2s"""
        from yuleosh.usage import TIERS

        tiers = list(TIERS.keys())
        start = time.perf_counter()
        for _ in range(10000):
            for t in tiers:
                _ = TIERS[t]
        elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLD_SUB_TIER, (
            f"10000 tier lookups took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_SUB_TIER}s"
        )

    @pytest.mark.perf
    def test_subscription_extract_token_5000(self):
        """_extract_token 5000 次 < 0.2s"""
        from yuleosh.api.subscription import _extract_token

        headers_list = [
            {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.dGVzdA.HTUdQ"},
            {"Authorization": "Basic dGVzdDpwYXNz"},
            {},
        ] * 1700  # ~5100 iterations

        start = time.perf_counter()
        for h in headers_list:
            _ = _extract_token(h)
        elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLD_SUB_TOKEN, (
            f"5000 extract_token calls took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_SUB_TOKEN}s"
        )

    @pytest.mark.perf
    def test_wizard_jwt_parse_500(self):
        """Wizard JWT 解析 500 次 < 0.5s"""
        from yuleosh.api.wizard import _get_org_id_from_handler
        import jwt
        import os, secrets

        secret = os.environ.get(
            "YULEOSH_JWT_SECRET",
            secrets.token_urlsafe(32),
        )
        token = jwt.encode(
            {"org_id": 42, "user_id": 1},
            secret,
            algorithm="HS256",
        )

        class MockHandler:
            headers = {"Authorization": f"Bearer {token}"}

        handler = MockHandler()

        start = time.perf_counter()
        for _ in range(500):
            _ = _get_org_id_from_handler(handler)
        elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLD_WIZARD_JWT, (
            f"500 wizard JWT parse calls took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_WIZARD_JWT}s"
        )

    @pytest.mark.perf
    def test_core_json_helpers(self):
        """API json_ok / json_error 1000 次 < 0.1s"""
        from yuleosh.api import json_ok, json_error

        start = time.perf_counter()
        for _ in range(1000):
            _ = json_ok({"status": "ok", "data": {"key": "value"}})
            _ = json_error("Something went wrong", 400)
        elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLD_CORE_JSON_OK, (
            f"1000 json_ok/json_error calls took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_CORE_JSON_OK}s"
        )


# ---------------------------------------------------------------------------
# 5. 内存基线
# ---------------------------------------------------------------------------

class TestMemoryBaseline:
    """SWE.4-BP4: 关键模块导入后 RSS 增量基线."""

    @pytest.mark.perf
    def test_memory_spec_module(self):
        """yuleosh.spec.validate 导入内存增量 < 200 MiB"""
        mem = _measure_import_mem("yuleosh.spec.validate")
        assert mem >= 0, "Failed to measure memory for yuleosh.spec.validate"
        assert mem < THRESHOLD_MEM_MODULE, (
            f"yuleosh.spec.validate import added {mem:.1f} MiB, "
            f"expected <{THRESHOLD_MEM_MODULE} MiB"
        )

    @pytest.mark.perf
    def test_memory_evidence_module(self):
        """yuleosh.evidence.generator 导入内存增量 < 200 MiB"""
        mem = _measure_import_mem("yuleosh.evidence.generator")
        assert mem >= 0
        assert mem < THRESHOLD_MEM_MODULE, (
            f"yuleosh.evidence.generator import added {mem:.1f} MiB, "
            f"expected <{THRESHOLD_MEM_MODULE} MiB"
        )

    @pytest.mark.perf
    def test_memory_ci_config_module(self):
        """yuleosh.ci.config 导入内存增量 < 200 MiB"""
        mem = _measure_import_mem("yuleosh.ci.config")
        assert mem >= 0
        assert mem < THRESHOLD_MEM_MODULE, (
            f"yuleosh.ci.config import added {mem:.1f} MiB, "
            f"expected <{THRESHOLD_MEM_MODULE} MiB"
        )

    @pytest.mark.perf
    def test_memory_api_auth_module(self):
        """yuleosh.api.auth 导入内存增量 < 200 MiB"""
        mem = _measure_import_mem("yuleosh.api.auth")
        assert mem >= 0
        assert mem < THRESHOLD_MEM_MODULE, (
            f"yuleosh.api.auth import added {mem:.1f} MiB, "
            f"expected <{THRESHOLD_MEM_MODULE} MiB"
        )

    @pytest.mark.perf
    def test_memory_api_subscription_module(self):
        """yuleosh.api.subscription 导入内存增量 < 200 MiB"""
        mem = _measure_import_mem("yuleosh.api.subscription")
        assert mem >= 0
        assert mem < THRESHOLD_MEM_MODULE, (
            f"yuleosh.api.subscription import added {mem:.1f} MiB, "
            f"expected <{THRESHOLD_MEM_MODULE} MiB"
        )

    @pytest.mark.perf
    def test_memory_full_yuleosh(self):
        """yuleosh 完整导入内存增量 < 500 MiB"""
        mem = _measure_import_mem("yuleosh")
        assert mem >= 0
        assert mem < THRESHOLD_MEM_FULL, (
            f"yuleosh full import added {mem:.1f} MiB, "
            f"expected <{THRESHOLD_MEM_FULL} MiB"
        )


# ---------------------------------------------------------------------------
# 6. 集成基线 — 组合场景
# ---------------------------------------------------------------------------

class TestIntegrationPerf:
    """SWE.4-BP4: 多模块集成性能基线."""

    @pytest.mark.perf
    def test_spec_to_evidence_chain(self):
        """Spec 解析 → 证据报告生成全链 < 10.0s"""
        from yuleosh.spec.validate import parse_spec
        from yuleosh.evidence.generator import EvidenceCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = _make_spec_file(tmpdir, 25, scenario_count=10)

            start = time.perf_counter()

            # Step 1: Parse
            doc = parse_spec(spec_path)

            # Step 2: Populate collector (避开 collection.py 的脆弱 import)
            collector = EvidenceCollector(tmpdir)
            collector.requirements = [r.to_dict() for r in doc.requirements]
            collector.scenarios = [s.to_dict() for s in doc.scenarios]

            # Step 3: Generate reports
            tm = collector.generate_traceability_matrix()
            cov = collector.generate_requirement_coverage()

            elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLD_SPEC_TO_EVIDENCE, (
            f"Spec→Evidence chain took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_SPEC_TO_EVIDENCE}s"
        )

    @pytest.mark.perf
    def test_ci_config_and_coverage_threshold(self):
        """CI 配置加载 + 阈值检查 < 1.0s"""
        from yuleosh.ci.config import (
            load_ci_config,
            _clear_ci_config_cache,
        )

        _clear_ci_config_cache()
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_ci_config(tmpdir)

            start = time.perf_counter()
            cfg = load_ci_config(project_dir=tmpdir)
            assert cfg.coverage.effective_line >= 75.0
            assert cfg.coverage.effective_condition >= 70.0
            elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLD_CI_AND_COVER, (
            f"CI config + threshold check took {elapsed:.3f}s, "
            f"expected <{THRESHOLD_CI_AND_COVER}s"
        )


# ---------------------------------------------------------------------------
# 7. 元测试 — 验证基线测试框架完整性
# ---------------------------------------------------------------------------

def test_perf_baseline_meta():
    """元测试 — 验证性能基线常量定义完整性。"""
    perf_constants = {
        name: val
        for name, val in globals().items()
        if name.startswith("THRESHOLD_")
    }
    assert len(perf_constants) > 0, "No THRESHOLD_ constants defined"
    for name, val in perf_constants.items():
        assert isinstance(val, (int, float)), (
            f"{name} should be numeric, got {type(val).__name__}"
        )
        assert val > 0, f"{name} should be positive, got {val}"
