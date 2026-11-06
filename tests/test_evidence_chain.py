#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for evidence/chain.py — fail-closed evidence chain + HTML overview."""

import json
from pathlib import Path

from yuleosh.evidence.chain import (
    CHAIN_HTML,
    CHAIN_JSON,
    cmd_evidence_chain,
    collect_chain,
    load_rules,
    render_html,
    validate_chain,
    write_chain,
)
from yuleosh.skills.builtin import builtin_skills


def _make_matrix_project(tmp_path: Path, requirements: list[dict]) -> Path:
    ev = tmp_path / ".osh" / "evidence"
    ev.mkdir(parents=True, exist_ok=True)
    (ev / "traceability-matrix.json").write_text(
        json.dumps({
            "schema": "osh-traceability-v1",
            "generated": "2026-11-07T00:00:00",
            "summary": {},
            "requirements": requirements,
            "sys_trace": {},
            "gap_analysis": {},
        }),
        encoding="utf-8",
    )
    return tmp_path


def _req(req_id: str, code: list[str], tests: list[str], review: bool = False,
         match_method: str = "annotation") -> dict:
    return {
        "req_id": req_id,
        "statement": f"{req_id} shall provide behaviour",
        "section": "2",
        "has_code": bool(code),
        "has_test": bool(tests),
        "has_review": review,
        "code_files": code,
        "test_files": tests,
        "match_method": match_method,
        "status": "Covered" if tests else "Not Covered",
    }


class TestCollectChain:
    def test_collects_nodes_edges_and_passes(self, tmp_path):
        project = _make_matrix_project(tmp_path, [
            _req("SHALL-001", ["src/a.c"], ["tests/test_a.py"]),
            _req("SHALL-002", ["src/b.c"], ["tests/test_b.py"]),
        ])
        chain = collect_chain(str(project))

        assert chain["schema"] == "osh-evidence-chain-v1"
        assert chain["source"] == "traceability-matrix.json"
        ids = {n["id"] for n in chain["nodes"]}
        assert {"SHALL-001", "SHALL-002", "code:src/a.c", "test:tests/test_a.py"} <= ids
        kinds = {e["kind"] for e in chain["edges"]}
        assert {"implement", "verify"} <= kinds
        assert chain["summary"]["status"] == "PASS"
        assert chain["metrics"]["test_coverage_pct"] == 100.0

    def test_rebuilds_matrix_when_missing(self, tmp_path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "spec.md").write_text(
            "# Spec\n\n## Requirements\n\n- **SHALL-001**: The system SHALL start.\n",
            encoding="utf-8",
        )
        chain = collect_chain(str(tmp_path))
        assert chain["source"] == "alm.traceability.write_authoritative_traceability"
        # Matrix is rebuilt so the required evidence artifact exists.
        assert (tmp_path / ".osh" / "evidence" / "traceability-matrix.json").exists()
        assert chain["summary"]["status"] == "FAIL"  # coverage gates fail-closed
        codes = {p["code"] for p in chain["problems"]}
        assert "E-CHAIN-GATE" in codes
        assert "E-CHAIN-ARTIFACT-MISSING" not in codes

    def test_missing_evidence_dir_is_fail_closed(self, tmp_path):
        chain = collect_chain(str(tmp_path))
        assert chain["summary"]["status"] == "FAIL"
        assert chain["metrics"]["requirements"] == 0
        assert any(p["code"] == "E-CHAIN-GATE" for p in chain["problems"])

    def test_duplicate_source_requirement_ids_fail_closed(self, tmp_path):
        project = _make_matrix_project(tmp_path, [
            _req("SHALL-001", ["src/a.c"], ["tests/test_a.py"]),
            _req("SHALL-001", ["src/b.c"], ["tests/test_b.py"]),
        ])
        chain = collect_chain(str(project))
        assert chain["summary"]["status"] == "FAIL"
        assert chain["metrics"]["requirements"] == 1
        assert chain["metrics"]["source_rows"] == 2
        assert chain["source_stats"]["duplicates"] == {"SHALL-001": 2}
        codes = {p["code"] for p in chain["problems"]}
        assert "E-CHAIN-SRC-DUP" in codes
        page = render_html(chain)
        assert "源重复 ID" in page

    def test_empty_source_req_id_is_reported_not_silently_dropped(self, tmp_path):
        project = _make_matrix_project(tmp_path, [
            _req("SHALL-001", ["src/a.c"], ["tests/test_a.py"]),
            _req("", ["src/b.c"], ["tests/test_b.py"]),
        ])
        chain = collect_chain(str(project))
        assert chain["summary"]["status"] == "FAIL"
        assert chain["metrics"]["requirements"] == 1
        assert chain["source_stats"]["dropped"]
        codes = {p["code"] for p in chain["problems"]}
        assert "E-CHAIN-SRC-DROP" in codes


class TestTraceConfidence:
    def test_keyword_code_edge_is_inferred(self, tmp_path):
        project = _make_matrix_project(tmp_path, [
            _req("SHALL-001", ["src/a.c"], ["tests/test_a.py"], match_method="keyword"),
        ])
        chain = collect_chain(str(project))
        implement = [e for e in chain["edges"] if e["kind"] == "implement"]
        assert implement and implement[0]["confidence"] == "inferred"
        assert implement[0]["method"] == "keyword"

    def test_annotation_code_edge_is_exact(self, tmp_path):
        project = _make_matrix_project(tmp_path, [
            _req("SHALL-001", ["src/a.c"], [], match_method="annotation"),
        ])
        chain = collect_chain(str(project))
        implement = [e for e in chain["edges"] if e["kind"] == "implement"]
        assert implement and implement[0]["confidence"] == "exact"

    def test_html_exposes_confidence_filter(self, tmp_path):
        project = _make_matrix_project(tmp_path, [
            _req("SHALL-001", ["src/a.c"], ["tests/test_a.py"], match_method="keyword"),
        ])
        chain = collect_chain(str(project))
        page = render_html(chain)
        assert 'data-confidence="inferred"' in page
        assert 'id="exact-only"' in page


class TestValidateChain:
    def _valid_chain(self, tmp_path):
        project = _make_matrix_project(tmp_path, [
            _req("SHALL-001", ["src/a.c"], ["tests/test_a.py"]),
        ])
        return collect_chain(str(project))

    def test_duplicate_invalid_and_dangling(self, tmp_path):
        chain = self._valid_chain(tmp_path)
        chain["nodes"].append(dict(chain["nodes"][0]))  # duplicate SHALL-001
        chain["nodes"].append({
            "id": "bad id", "type": "code", "title": "bad", "status": "evidence", "refs": [],
        })
        chain["edges"].append({"from": "SHALL-001", "to": "ghost-node", "kind": "verify"})

        codes = {p["code"] for p in validate_chain(chain)}
        assert "E-CHAIN-DUP" in codes
        assert "E-CHAIN-ID" in codes
        assert "E-CHAIN-DANGLING" in codes

    def test_orphan_requirement(self, tmp_path):
        chain = self._valid_chain(tmp_path)
        chain["nodes"].append({
            "id": "SHALL-ORPHAN",
            "type": "requirement",
            "title": "orphan",
            "status": "gap",
            "refs": [],
            "has_code": False,
            "has_test": False,
            "has_review": False,
        })
        codes = {p["code"] for p in validate_chain(chain)}
        assert "E-CHAIN-ORPHAN" in codes

    def test_missing_required_artifact(self, tmp_path):
        chain = self._valid_chain(tmp_path)
        chain["artifacts"] = [a for a in chain["artifacts"]
                              if a["name"] != "traceability-matrix.json"]
        codes = {p["code"] for p in validate_chain(chain)}
        assert "E-CHAIN-ARTIFACT-MISSING" in codes

    def test_empty_sha256_is_fail(self, tmp_path):
        chain = self._valid_chain(tmp_path)
        for artifact in chain["artifacts"]:
            if artifact["name"] == "traceability-matrix.json":
                artifact["sha256"] = ""
        codes = {p["code"] for p in validate_chain(chain)}
        assert "E-CHAIN-ARTIFACT-MISSING" in codes


class TestRenderAndWrite:
    def test_html_contains_data_views_and_deep_links(self, tmp_path):
        project = _make_matrix_project(tmp_path, [
            _req("SHALL-001", ["src/a.c"], ["tests/test_a.py"]),
        ])
        chain = collect_chain(str(project))
        page = render_html(chain)

        assert '<script id="chain-data" type="application/json">' in page
        assert "#/node/" in page
        assert "#/artifact/" in page
        assert "#/gate/" in page
        assert 'id="view-trace"' in page
        assert 'id="view-artifacts"' in page
        assert 'id="view-closure"' in page
        assert "https://" not in page  # offline, no CDN

    def test_html_shows_fail_status(self, tmp_path):
        chain = collect_chain(str(tmp_path))  # empty project → FAIL
        page = render_html(chain)
        assert 'class="badge bad">FAIL' in page

    def test_write_chain_outputs(self, tmp_path):
        project = _make_matrix_project(tmp_path, [
            _req("SHALL-001", ["src/a.c"], ["tests/test_a.py"]),
        ])
        chain = collect_chain(str(project))
        written = write_chain(chain, evidence_dir=str(project / ".osh" / "evidence"))
        assert Path(written["json"]).name == CHAIN_JSON
        assert Path(written["html"]).name == CHAIN_HTML
        saved = json.loads(Path(written["json"]).read_text(encoding="utf-8"))
        assert saved["schema"] == "osh-evidence-chain-v1"


class TestCli:
    def test_exit_code_pass(self, tmp_path, capsys):
        project = _make_matrix_project(tmp_path, [
            _req("SHALL-001", ["src/a.c"], ["tests/test_a.py"]),
        ])
        code = cmd_evidence_chain(str(project), check_only=True)
        assert code == 0
        assert "PASS" in capsys.readouterr().out

    def test_exit_code_fail(self, tmp_path, capsys):
        code = cmd_evidence_chain(str(tmp_path), check_only=True)
        assert code == 1
        assert "FAIL" in capsys.readouterr().out


class TestRulesAndSkill:
    def test_rules_expose_gates_and_thresholds(self):
        rules = load_rules()
        gate_ids = {g["id"] for g in rules["gates"]}
        assert "E-CHAIN-DANGLING" in gate_ids
        assert "min_test_coverage_pct" in rules["thresholds"]
        assert rules["html_contract"]["offline"] is True

    def test_skill_registered(self):
        names = {s.name for s in builtin_skills()}
        assert "aspice-evidence-chain" in names
