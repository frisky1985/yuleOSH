"""Unit tests for yuleosh.api.loops — Loop Engineering Dashboard API (v3.4.2 Wave 1).

Covers:
  - Time helpers (_now_iso/_hours_ago/_days_ago)
  - get_loop1_data..get_loop4_data: structure/content of each widget payload
  - get_loop_data(): dispatcher, unknown loop, exception fallback
  - get_all_loops_data(): summary payload
"""

# @tests src/yuleosh/api/pipeline.py

import os
import sys
from datetime import datetime, timezone

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src

from yuleosh.api import loops as L


# ── Time helpers ──────────────────────────────────────────────────────

class TestTimeHelpers:
    def test_now_iso_utc(self):
        """GIVEN _now_iso WHEN called THEN returns ISO string with tz."""
        s = L._now_iso()
        dt = datetime.fromisoformat(s)
        assert dt.tzinfo is not None

    def test_hours_ago(self):
        """GIVEN _hours_ago WHEN called THEN time is in the past."""
        s = L._hours_ago(5)
        dt = datetime.fromisoformat(s)
        assert dt <= datetime.now(timezone.utc)

    def test_days_ago(self):
        """GIVEN _days_ago WHEN called THEN ~24h*d in the past."""
        s = L._days_ago(3)
        dt = datetime.fromisoformat(s)
        assert dt <= datetime.now(timezone.utc)


# ── Loop 1: 缺陷→需求回溯 ────────────────────────────────────────────

class TestLoop1:
    def test_structure(self):
        """GIVEN get_loop1_data WHEN called THEN full widget payload."""
        d = L.get_loop1_data()
        assert d["ok"] is True
        assert d["loop_id"] == 1
        assert "label" in d and "emoji" in d
        assert d["last_updated"]

    def test_events_nodes_edges(self):
        """GIVEN loop1 payload THEN events/nodes/edges populated."""
        d = L.get_loop1_data()
        assert len(d["events"]) == 9
        assert all("event_id" in e and "event_type" in e for e in d["events"])
        assert len(d["nodes"]) == 6
        assert len(d["edges"]) == 4
        # edges reference existing node ids
        node_ids = {n["id"] for n in d["nodes"]}
        for e in d["edges"]:
            assert e["from"] in node_ids and e["to"] in node_ids

    def test_metrics_and_charts(self):
        """GIVEN loop1 payload THEN metrics + 7d chart present."""
        d = L.get_loop1_data()
        assert d["metrics"]["total_ci_failures_24h"] == 3
        chart = d["charts"]["traceability_7d"]
        assert len(chart) == 7
        assert chart[0]["date"] == "07-21"
        assert all("ci_failures" in row for row in chart)


# ── Loop 2: 现场→FMEA ────────────────────────────────────────────────

class TestLoop2:
    def test_structure(self):
        """GIVEN get_loop2_data WHEN called THEN widget payload."""
        d = L.get_loop2_data()
        assert d["ok"] is True
        assert d["loop_id"] == 2

    def test_impact_chain(self):
        """GIVEN loop2 payload THEN impact chain has root + children."""
        d = L.get_loop2_data()
        chain = d["impact_chain"]
        assert chain["root"]["name"] == "FIELD_DEFECT"
        assert len(chain["children"]) == 4
        # nested children exist
        assert chain["children"][0]["children"][0]["name"].startswith("FMEA:")

    def test_fmea_entries(self):
        """GIVEN loop2 payload THEN fmea entries with RPN values."""
        d = L.get_loop2_data()
        entries = d["fmea_entries"]
        assert len(entries) == 5
        rpns = [e["rpn"] for e in entries]
        assert max(rpns) == 378
        statuses = {e["status"] for e in entries}
        assert statuses == {"active", "mitigated", "closed"}

    def test_safety_reports_and_trend(self):
        """GIVEN loop2 payload THEN safety reports + monthly trend."""
        d = L.get_loop2_data()
        assert len(d["safety_reports"]) == 2
        assert d["safety_reports"][0]["impact"] == "ASIL D"
        trend = d["charts"]["monthly_trend"]
        assert len(trend) == 6
        assert trend[-1]["month"] == "2026-07"


# ── Loop 3: KPI→RCA→改进 ─────────────────────────────────────────────

class TestLoop3:
    def test_structure(self):
        """GIVEN get_loop3_data WHEN called THEN widget payload."""
        d = L.get_loop3_data()
        assert d["ok"] is True
        assert d["loop_id"] == 3

    def test_rca_records(self):
        """GIVEN loop3 payload THEN RCA records with breach metrics."""
        d = L.get_loop3_data()
        records = d["rca_records"]
        assert len(records) == 4
        assert records[0]["id"] == "RCA-001"
        assert records[0]["breach"] == -12.7
        statuses = {r["status"] for r in records}
        assert statuses == {"in_progress", "resolved", "new"}

    def test_improvement_tickets(self):
        """GIVEN loop3 payload THEN tickets link to RCA ids."""
        d = L.get_loop3_data()
        tickets = d["improvement_tickets"]
        assert len(tickets) == 4
        rca_ids = {r["id"] for r in d["rca_records"]}
        assert tickets[0]["rca_id"] in rca_ids

    def test_metrics_and_charts(self):
        """GIVEN loop3 payload THEN metrics + kpi/closure charts."""
        d = L.get_loop3_data()
        assert d["metrics"]["active_rca_count"] == 3
        assert len(d["charts"]["kpi_trend"]) == 14
        assert len(d["charts"]["closure_trend"]) == 4


# ── Loop 4: KG 自进化 ────────────────────────────────────────────────

class TestLoop4:
    def test_structure(self):
        """GIVEN get_loop4_data WHEN called THEN widget payload."""
        d = L.get_loop4_data()
        assert d["ok"] is True
        assert d["loop_id"] == 4

    def test_confidence_buckets(self):
        """GIVEN loop4 payload THEN histogram buckets sum to ~100%."""
        d = L.get_loop4_data()
        buckets = d["confidence_buckets"]
        assert len(buckets) == 5
        assert buckets[0]["range"] == "0.0-0.2"
        assert sum(b["pct"] for b in buckets) == pytest.approx(100.0)

    def test_low_confidence_items(self):
        """GIVEN loop4 payload THEN low confidence items flagged review."""
        d = L.get_loop4_data()
        items = d["low_confidence_items"]
        assert len(items) == 5
        assert all(i["needs_review"] for i in items)
        assert all(i["confidence"] < 0.3 for i in items)

    def test_trend_and_metrics(self):
        """GIVEN loop4 payload THEN trend + metrics present."""
        d = L.get_loop4_data()
        assert len(d["charts"]["confidence_trend"]) == 14
        assert d["metrics"]["total_kg_entries"] == 200
        assert d["metrics"]["avg_confidence"] == pytest.approx(0.56)


# ── Dispatcher ────────────────────────────────────────────────────────

class TestDispatcher:
    def test_get_loop_data_valid_ids(self):
        """GIVEN each valid loop id WHEN get_loop_data THEN ok payload."""
        for loop_id in (1, 2, 3, 4):
            d = L.get_loop_data(loop_id)
            assert d["ok"] is True
            assert d["loop_id"] == loop_id

    def test_get_loop_data_unknown(self):
        """GIVEN unknown loop id WHEN get_loop_data THEN error payload."""
        d = L.get_loop_data(99)
        assert d["ok"] is False
        assert "not found" in d["error"]

    def test_get_loop_data_exception(self, monkeypatch):
        """GIVEN underlying func raising WHEN get_loop_data THEN error dict."""
        def boom():
            raise RuntimeError("kaboom")
        monkeypatch.setitem(L.LOOP_FUNCS, 1, boom)
        d = L.get_loop_data(1)
        assert d["ok"] is False
        assert d["error"] == "kaboom"

    def test_get_all_loops_data(self):
        """GIVEN get_all_loops_data WHEN called THEN summary for 4 loops."""
        d = L.get_all_loops_data()
        assert d["ok"] is True
        for i in (1, 2, 3, 4):
            key = f"loop_{i}"
            assert key in d
            assert "label" in d[key]
