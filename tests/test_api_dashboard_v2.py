"""Unit tests for yuleosh.api.dashboard_v2 (数据座舱增强聚合 API).

Covers the dashboard-v2 routes offline:
  - routing (4 routes + unknown -> 404, wrong method -> 404)
  - overview: 合规总分五维加权公式 compliance_score = Σ(score*weight)、
    各维度明细、真实覆盖率读取、演示数据回退不泄漏、无数据 0 + note
  - recent-pipelines: 最近 10 条（store.pipelines）/ 空数据 / store 失败 503
  - device-status: DeviceRegistry.list_devices 按状态聚合（2 online 1 busy）
    / 无设备 / registry 失败
  - tests-summary: 三层测试 pass/fail/skip 计数 / 无数据 note
  - 指标加载器: misra jsonl / traceability manifest 三形态 / evidence manifest
"""

# @tests src/yuleosh/api/dashboard.py

import json

import pytest

from yuleosh.api import dashboard as D          # noqa: N812 (OSH_HOME patching)
from yuleosh.api import dashboard_v2 as D2      # noqa: N812
from yuleosh.device.models import DeviceState

# require_auth 注入 current_user 为 kwarg；单测直接调用 wrapped 原函数。
_handle = D2.handle_dashboard_v2.__wrapped__


def _req(method="GET", path="overview", query=None, org_id=1, current_user=None):
    """Call the wrapped handler with an authenticated current_user."""
    if current_user is None:
        current_user = {"user_id": 42, "org_id": org_id,
                        "email": "t@example.com", "role": "admin"}
    return _handle(method, path, {}, query or {}, handler=None,
                   current_user=current_user)


class _FakeStore:
    """Emulate the Store singleton surface used by dashboard_v2."""

    def __init__(self, pipelines=None, ci_runs=None, projects=None):
        self._pipelines = pipelines or []
        self._ci_runs = ci_runs or []
        self._projects = projects or []

    def list_pipelines(self):
        return [dict(p) for p in self._pipelines]

    def list_ci(self, limit=10):
        return [dict(r) for r in self._ci_runs[:limit]]

    def list_org_projects(self, org_id):
        return [dict(p) for p in self._projects if p.get("org_id") == org_id]


class _EmptyRegistry:
    def list_devices(self):
        return []


class _FakeDevice:
    def __init__(self, state):
        self.state = state  # DeviceState enum


def _patch_store(monkeypatch, pipelines=None, ci_runs=None, projects=None):
    store = _FakeStore(pipelines, ci_runs, projects)
    monkeypatch.setattr("yuleosh.store.Store", lambda: store)
    return store


def _patch_devices(monkeypatch, states):
    class FakeRegistry:
        def list_devices(self):
            return [_FakeDevice(s) for s in states]
    monkeypatch.setattr("yuleosh.device.registry.DeviceRegistry", FakeRegistry)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Point both dashboard modules' OSH_HOME at tmp_path and isolate
    store/device-registry behind fakes (offline unit tests)."""
    monkeypatch.setattr(D2, "OSH_HOME", str(tmp_path))
    monkeypatch.setattr(D, "OSH_HOME", str(tmp_path))
    _patch_store(monkeypatch)
    monkeypatch.setattr("yuleosh.device.registry.DeviceRegistry", _EmptyRegistry)
    yield tmp_path


def _write(tmp_path, relpath, content):
    p = tmp_path / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content if isinstance(content, str) else json.dumps(content),
                 encoding="utf-8")
    return p


# ── routing ───────────────────────────────────────────────────────────

class TestRouting:
    def test_unknown_route(self):
        """GIVEN unknown sub-path WHEN handle THEN 404."""
        payload, status = _req("GET", "nope")
        assert status == 404 and payload["ok"] is False

    def test_method_not_allowed(self):
        """GIVEN POST on overview WHEN handle THEN 404."""
        payload, status = _req("POST", "overview")
        assert status == 404 and payload["ok"] is False

    def test_all_routes_ok(self):
        """GIVEN the four dashboard-v2 routes WHEN GET THEN 200."""
        for path in ("overview", "recent-pipelines", "device-status",
                     "tests-summary"):
            payload, status = _req("GET", path)
            assert status == 200, path
            assert payload["ok"] is True, path


# ── overview：合规总分五维加权 ────────────────────────────────────────

class TestOverview:
    def test_compliance_score_weighted_formula(self, monkeypatch):
        """GIVEN 各维分数 WHEN overview THEN compliance_score = Σ(score*weight)。

        权重：coverage 0.30 / test_pass_rate 0.25 / misra 0.20 /
              traceability 0.15 / evidence 0.10
        """
        scores = {
            "coverage": 80.0,
            "test_pass_rate": 70.0,
            "misra": 60.0,          # 8 违规 × 5 分/个 = 40 分扣减
            "traceability": 50.0,
            "evidence": 40.0,
        }
        monkeypatch.setattr(D2, "_load_coverage",
                            lambda: (scores["coverage"], None))
        monkeypatch.setattr(D2, "_load_test_pass_rate",
                            lambda: (scores["test_pass_rate"], None))
        monkeypatch.setattr(D2, "_load_misra_violations", lambda: (8, None))
        monkeypatch.setattr(D2, "_load_traceability_score",
                            lambda: (scores["traceability"], None))
        monkeypatch.setattr(D2, "_load_evidence_score",
                            lambda: (scores["evidence"], None))
        monkeypatch.setattr(D2, "_load_pipelines",
                            lambda: [{"name": "p1", "status": "running"},
                                     {"name": "p2", "status": "passed"}])
        monkeypatch.setattr(D2, "_load_projects_count", lambda org_id: (2, None))
        monkeypatch.setattr(D2, "_load_device_summary", lambda: (
            {"online": 1, "busy": 0, "offline": 0, "fault": 0, "unknown": 0},
            None))

        payload, status = _req("GET", "overview")
        assert status == 200
        data = payload["data"]

        expected = round(
            scores["coverage"] * 0.30 + scores["test_pass_rate"] * 0.25
            + scores["misra"] * 0.20 + scores["traceability"] * 0.15
            + scores["evidence"] * 0.10, 1)
        assert data["compliance_score"] == expected == 65.0

        # 五维明细
        dims = {d["key"]: d for d in data["dimensions"]}
        assert set(dims) == {"coverage", "test_pass_rate", "misra",
                             "traceability", "evidence"}
        assert dims["coverage"]["score"] == 80.0
        assert dims["coverage"]["weight"] == 0.30
        assert dims["misra"]["score"] == 60.0
        assert dims["misra"]["weight"] == 0.20
        assert dims["traceability"]["weight"] == 0.15
        assert dims["evidence"]["weight"] == 0.10

        # 指标卡字段
        assert data["coverage"] == 80.0
        assert data["test_pass_rate"] == 70.0
        assert data["misra_violations"] == 8
        assert data["active_pipelines"] == 1
        assert data["projects_count"] == 2
        assert data["devices_summary"]["online"] == 1
        assert data["generated_at"]

    def test_overview_no_data_zeros_with_note(self, monkeypatch):
        """GIVEN 全部数据源无数据 WHEN overview THEN 0/空 + note，禁止演示数据。"""
        monkeypatch.setattr(D2, "_load_coverage",
                            lambda: (0.0, "覆盖率无真实数据（c-coverage.json 缺失）"))
        monkeypatch.setattr(D2, "_load_test_pass_rate",
                            lambda: (0.0, "无测试运行数据（最近 100 次运行无完成记录）"))
        monkeypatch.setattr(D2, "_load_misra_violations",
                            lambda: (0, "无 MISRA 违规数据"))
        monkeypatch.setattr(D2, "_load_traceability_score",
                            lambda: (0.0, "无需求追溯数据"))
        monkeypatch.setattr(D2, "_load_evidence_score",
                            lambda: (0.0, "无证据完整性数据"))
        monkeypatch.setattr(D2, "_load_pipelines", lambda: [])
        monkeypatch.setattr(D2, "_load_projects_count", lambda org_id: (0, None))
        monkeypatch.setattr(D2, "_load_device_summary", lambda: (
            {"online": 0, "busy": 0, "offline": 0, "fault": 0, "unknown": 0},
            "无设备数据"))

        payload, status = _req("GET", "overview")
        data = payload["data"]
        assert status == 200
        assert data["compliance_score"] == 0.0
        assert data["active_pipelines"] == 0
        assert data["projects_count"] == 0
        assert data["devices_summary"] == {
            "online": 0, "busy": 0, "offline": 0, "fault": 0, "unknown": 0}
        assert data["note"] is not None
        assert "演示" not in json.dumps(data, ensure_ascii=False)

    def test_coverage_from_real_report(self, _isolate):
        """GIVEN 真实 c-coverage.json WHEN overview THEN coverage=line_rate。"""
        _write(_isolate, ".yuleosh/reports/c-coverage.json", {
            "line_rate": 82.4, "branch_rate": 60.0, "function_rate": 90.0,
            "files": []})
        payload, _ = _req("GET", "overview")
        data = payload["data"]
        assert data["coverage"] == 82.4
        dims = {d["key"]: d for d in data["dimensions"]}
        assert dims["coverage"]["score"] == 82.4
        assert dims["coverage"]["status"] == "good"

    def test_coverage_demo_fallback_not_served(self, _isolate):
        """GIVEN 无真实覆盖率报告（dashboard 会回退演示数据）WHEN overview
        THEN coverage=0 + note，演示数据不得泄漏进 v2。"""
        payload, _ = _req("GET", "overview")
        data = payload["data"]
        assert data["coverage"] == 0.0
        assert data["dimensions"][0]["note"] is not None
        assert "演示" not in json.dumps(data, ensure_ascii=False)

    def test_test_pass_rate_from_ci_runs(self, monkeypatch):
        """GIVEN ci_runs 3 完成（2 passed 1 failed）+ 1 running WHEN overview
        THEN test_pass_rate = 2/3 = 66.67。"""
        _patch_store(monkeypatch, ci_runs=[
            {"status": "passed"}, {"status": "failed"},
            {"status": "passed"}, {"status": "running"},
        ])
        payload, _ = _req("GET", "overview")
        data = payload["data"]
        assert data["test_pass_rate"] == 66.67
        dims = {d["key"]: d for d in data["dimensions"]}
        assert dims["test_pass_rate"]["score"] == 66.67
        assert dims["test_pass_rate"]["status"] == "warning"

    def test_dimension_status(self):
        """GIVEN 分数 WHEN _dimension_status THEN 阈值分级。"""
        assert D2._dimension_status(95) == "good"
        assert D2._dimension_status(80) == "good"
        assert D2._dimension_status(65) == "warning"
        assert D2._dimension_status(30) == "critical"


# ── recent-pipelines ──────────────────────────────────────────────────

class TestRecentPipelines:
    def test_recent_10(self, monkeypatch):
        """GIVEN 12 条流水线 WHEN recent-pipelines THEN 最近 10 条。"""
        rows = [
            {"name": f"pipe-{i}", "status": "passed" if i % 2 else "running",
             "created_at": f"2026-08-{i + 1:02d}T00:00:00",
             "updated_at": f"2026-08-{i + 1:02d}T01:00:00"}
            for i in range(12)
        ]
        _patch_store(monkeypatch, pipelines=rows)
        payload, status = _req("GET", "recent-pipelines")
        assert status == 200
        data = payload["data"]
        assert data["count"] == 10
        assert len(data["pipelines"]) == 10
        assert data["pipelines"][0]["name"] == "pipe-0"
        assert data["pipelines"][0]["status"] == "running"
        assert data["note"] is None

    def test_empty(self, monkeypatch):
        """GIVEN 无流水线 WHEN recent-pipelines THEN 空列表 + note。"""
        _patch_store(monkeypatch, pipelines=[])
        payload, _ = _req("GET", "recent-pipelines")
        data = payload["data"]
        assert data["pipelines"] == [] and data["count"] == 0
        assert data["note"] is not None

    def test_store_error_503(self, monkeypatch):
        """GIVEN store 异常 WHEN recent-pipelines THEN 503。"""

        def boom():
            raise RuntimeError("db down")

        monkeypatch.setattr("yuleosh.store.Store", boom)
        payload, status = _req("GET", "recent-pipelines")
        assert status == 503 and payload["ok"] is False


# ── device-status ─────────────────────────────────────────────────────

class TestDeviceStatus:
    def test_aggregates_states(self, monkeypatch):
        """GIVEN 2 online + 1 busy WHEN device-status THEN 按状态聚合。"""
        _patch_devices(monkeypatch,
                       [DeviceState.ONLINE, DeviceState.ONLINE,
                        DeviceState.BUSY])
        payload, status = _req("GET", "device-status")
        assert status == 200
        data = payload["data"]
        assert data["summary"] == {
            "online": 2, "busy": 1, "offline": 0, "fault": 0, "unknown": 0}
        assert data["total"] == 3
        assert data["note"] is None

    def test_all_states_counted(self, monkeypatch):
        """GIVEN 五态设备 WHEN device-status THEN 各状态均计数。"""
        _patch_devices(monkeypatch, [
            DeviceState.ONLINE, DeviceState.BUSY, DeviceState.OFFLINE,
            DeviceState.FAULT, DeviceState.UNKNOWN])
        payload, _ = _req("GET", "device-status")
        assert payload["data"]["summary"] == {
            "online": 1, "busy": 1, "offline": 1, "fault": 1, "unknown": 1}

    def test_no_devices(self, monkeypatch):
        """GIVEN 无设备 WHEN device-status THEN 全 0 + note。"""
        _patch_devices(monkeypatch, [])
        payload, _ = _req("GET", "device-status")
        assert payload["data"]["total"] == 0
        assert payload["data"]["note"] is not None

    def test_registry_error(self, monkeypatch):
        """GIVEN registry 异常 WHEN device-status THEN 全 0 + note。"""

        class Boom:
            def list_devices(self):
                raise RuntimeError("no device.db")

        monkeypatch.setattr("yuleosh.device.registry.DeviceRegistry", Boom)
        payload, status = _req("GET", "device-status")
        assert status == 200
        assert payload["data"]["total"] == 0
        assert payload["data"]["note"] is not None


# ── tests-summary ─────────────────────────────────────────────────────

class TestTestsSummary:
    def test_three_layer_counts(self, monkeypatch):
        """GIVEN ci_runs stages WHEN tests-summary THEN 三层 pass/fail/skip。"""
        _patch_store(monkeypatch, ci_runs=[
            {"status": "passed", "stages": json.dumps([
                {"name": "unit-tests", "status": "passed"},
                {"name": "unit-tests", "status": "passed"},
                {"name": "integration-tests", "status": "failed"},
                {"name": "qualification-tests", "status": "skipped"},
                {"name": "cross-compile", "status": "passed"},  # 非测试层，忽略
            ])},
            {"status": "failed", "stages": json.dumps([
                {"name": "unit-tests", "status": "failed"},
                {"name": "e2e-tests", "status": "passed"},
                {"name": "sil-tests", "status": "skipped"},
            ])},
        ])
        payload, status = _req("GET", "tests-summary")
        assert status == 200
        data = payload["data"]
        assert data["layers"]["unit"] == {"pass": 2, "fail": 1, "skip": 0}
        assert data["layers"]["integration"] == {"pass": 1, "fail": 1, "skip": 1}
        assert data["layers"]["qualification"] == {"pass": 0, "fail": 0, "skip": 1}
        assert data["note"] is None

    def test_no_data(self, monkeypatch):
        """GIVEN 无三层测试 stage WHEN tests-summary THEN 空统计 + note。"""
        _patch_store(monkeypatch, ci_runs=[
            {"status": "passed", "stages": "[]"},
            {"status": "running", "stages": "[]"},
        ])
        payload, _ = _req("GET", "tests-summary")
        data = payload["data"]
        for layer in ("unit", "integration", "qualification"):
            assert data["layers"][layer] == {"pass": 0, "fail": 0, "skip": 0}
        assert data["note"] is not None

    def test_store_error_note(self, monkeypatch):
        """GIVEN store 异常 WHEN tests-summary THEN 空统计 + 加载失败 note。"""

        def boom():
            raise RuntimeError("db down")

        monkeypatch.setattr("yuleosh.store.Store", boom)
        payload, status = _req("GET", "tests-summary")
        assert status == 200
        assert "加载失败" in payload["data"]["note"]


# ── 指标加载器（真实数据源解析）──────────────────────────────────────

class TestMisraLoader:
    def test_misra_score_formula(self):
        """GIVEN 违规数 WHEN _misra_score THEN 每违规扣 5 分、20+ 归零。"""
        assert D2._misra_score(0) == 100.0
        assert D2._misra_score(8) == 60.0
        assert D2._misra_score(20) == 0.0
        assert D2._misra_score(25) == 0.0

    def test_misra_from_trend_file(self, _isolate):
        """GIVEN misra-trend.jsonl WHEN _load_misra_violations THEN 最近违规数。"""
        _write(_isolate, ".yuleosh/reports/misra-trend.jsonl",
               '{"timestamp": "2026-08-01T00:00:00", "total_violations": 12}\n'
               '{"timestamp": "2026-08-02T00:00:00", "total_violations": 9}\n')
        count, note = D2._load_misra_violations()
        assert count == 9 and note is None

    def test_misra_missing_file(self, _isolate):
        """GIVEN 无 misra-trend.jsonl WHEN _load_misra_violations THEN 0 + note。"""
        count, note = D2._load_misra_violations()
        assert count == 0 and note is not None


class TestTraceabilityLoader:
    def test_score_form(self, _isolate):
        _write(_isolate, ".yuleosh/evidence-bundle/audit-manifest.json",
               {"traceability": {"score": 80}})
        score, note = D2._load_traceability_score()
        assert score == 80.0 and note is None

    def test_ratio_form(self, _isolate):
        _write(_isolate, ".yuleosh/evidence-bundle/audit-manifest.json",
               {"traceability": {"ratio": 0.6}})
        score, note = D2._load_traceability_score()
        assert score == 60.0 and note is None

    def test_linked_total_form(self, _isolate):
        _write(_isolate, ".osh/evidence/audit-manifest.json",
               {"traceability": {"linked": 9, "total": 10}})
        score, note = D2._load_traceability_score()
        assert score == 90.0 and note is None

    def test_missing(self, _isolate):
        score, note = D2._load_traceability_score()
        assert score == 0.0 and note is not None


class TestEvidenceLoader:
    def test_artifacts_form(self, _isolate):
        _write(_isolate, ".yuleosh/reports/audit-manifest.json",
               {"integrity": {"total_artifacts": 7}})
        score, note = D2._load_evidence_score()
        assert score == 70.0 and note is None

    def test_artifacts_capped_at_100(self, _isolate):
        _write(_isolate, "reports/audit-manifest.json",
               {"integrity": {"total_artifacts": 42}})
        score, note = D2._load_evidence_score()
        assert score == 100.0 and note is None

    def test_missing(self, _isolate):
        score, note = D2._load_evidence_score()
        assert score == 0.0 and note is not None


class TestCoverageLoader:
    def test_no_report_returns_zero_with_note(self, _isolate):
        """GIVEN 无真实覆盖率报告 WHEN _load_coverage THEN 0 + note（演示回退不泄漏）。"""
        line_rate, note = D2._load_coverage()
        assert line_rate == 0.0 and note is not None
