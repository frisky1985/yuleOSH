# @tests src/yuleosh/evidence/human_report.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""人类可读证据（HTML / Excel / Markdown）与 UI 产物过滤回归。"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from yuleosh.evidence.human_report import write_bundle_evidence, write_human_evidence


def _session(tmp_path: Path, name: str = "sess-abc") -> SimpleNamespace:
    sdir = tmp_path / ".osh" / "sessions" / name
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "gate-summary.json").write_text(
        json.dumps({"schema": "gate-summary-v1", "session": name}),
        encoding="utf-8",
    )
    return SimpleNamespace(
        name=name,
        status="completed",
        project_dir=str(tmp_path),
        session_dir=str(sdir),
        steps=[
            {"name": "spec-parse", "status": "completed",
             "output_path": "docs/spec.md"},
            {"name": "man1-charter", "status": "completed",
             "output_path": ".osh/sessions/sess-abc/man1-charter.json"},
            {"name": "test-unit", "status": "skipped", "output_path": ""},
        ],
        gate_verdict={"outcome": "UNVERIFIED", "reason": "G7 未运行"},
    )


GATE_SUMMARY = {
    "schema": "gate-summary-v1",
    "gates": [
        {"gate": "G0", "name": "Spec Gate", "status": "passed",
         "step_keys": ["spec-parse"], "advisory": False},
        {"gate": "G20", "name": "MAN 管理过程 Gate", "status": "not-run",
         "step_keys": ["man1-charter"], "advisory": False},
    ],
    "worst_gate_status": "not-run",
}


def _prepare_project(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "spec.md").write_text("# 产品\n\n需求可度量。\n",
                                               encoding="utf-8")
    (tmp_path / "docs" / "issue-register.yaml").write_text(
        "records: []\n", encoding="utf-8")


class TestHumanEvidence:
    def test_writes_three_human_formats(self, tmp_path):
        _prepare_project(tmp_path)
        session = _session(tmp_path)
        written = write_human_evidence(session, gate_summary=GATE_SUMMARY)

        assert set(written) == {"markdown", "html", "excel"}
        for path in written.values():
            assert Path(path).is_file()
            assert Path(path).stat().st_size > 0

    def test_html_contains_gate_and_step_details(self, tmp_path):
        _prepare_project(tmp_path)
        session = _session(tmp_path)
        written = write_human_evidence(session, gate_summary=GATE_SUMMARY)
        html = Path(written["html"]).read_text(encoding="utf-8")

        assert "证据摘要" in html
        assert "G20" in html and "not-run" in html
        assert "spec-parse" in html
        assert "UNVERIFIED" in html

    def test_machine_evidence_not_listed_as_artifact(self, tmp_path):
        _prepare_project(tmp_path)
        session = _session(tmp_path)
        written = write_human_evidence(session, gate_summary=GATE_SUMMARY)
        html = Path(written["html"]).read_text(encoding="utf-8")
        md = Path(written["markdown"]).read_text(encoding="utf-8")

        # 人类可读产物被列出；json / yaml 不出现在产物清单里
        assert "docs/spec.md" in html
        assert "man1-charter.json" not in html
        assert "issue-register.yaml" not in html
        assert "docs/spec.md" in md

    def test_excel_has_four_sheets(self, tmp_path):
        openpyxl = pytest.importorskip("openpyxl")
        _prepare_project(tmp_path)
        session = _session(tmp_path)
        written = write_human_evidence(session, gate_summary=GATE_SUMMARY)

        wb = openpyxl.load_workbook(written["excel"])
        assert wb.sheetnames == ["概览", "门禁", "步骤", "人类可读产物"]
        gates = list(wb["门禁"].values)
        assert gates[1][0] == "G0" and gates[2][0] == "G20"

    def test_missing_gate_summary_is_explicit(self, tmp_path):
        _prepare_project(tmp_path)
        session = _session(tmp_path)
        (Path(session.session_dir) / "gate-summary.json").unlink()
        written = write_human_evidence(session, gate_summary=None)
        html = Path(written["html"]).read_text(encoding="utf-8")

        assert "未生成门禁汇总" in html

    def test_rerun_overwrites_same_session_dir(self, tmp_path):
        _prepare_project(tmp_path)
        session = _session(tmp_path)
        first = write_human_evidence(session, gate_summary=GATE_SUMMARY)
        second = write_human_evidence(session, gate_summary=GATE_SUMMARY)

        assert first == second
        evidence_dirs = list((tmp_path / "docs" / "evidence").iterdir())
        assert len(evidence_dirs) == 1


class TestUiArtifactFilter:
    def test_json_and_yaml_are_hidden_from_evidence_list(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        _prepare_project(tmp_path)
        row = {
            "run_id": "run-1",
            "op": "full",
            "mode": "mock",
            "status": "passed",
            "started_at": "",
            "finished_at": "",
            "snapshot": json.dumps({"steps": [
                {"step_id": "spec", "name": "spec", "status": "passed",
                 "output_path": "docs/spec.md"},
                {"step_id": "man1", "name": "charter", "status": "passed",
                 "output_path": ".osh/sessions/sess-abc/man1-charter.json"},
                {"step_id": "sup9", "name": "issues", "status": "passed",
                 "output_path": "docs/issue-register.yaml"},
            ]}),
        }

        from yuleosh.ui.routes.pipeline_routes import _run_evidence

        pkg = _run_evidence(row, str(tmp_path))
        assert [a["path"] for a in pkg["artifacts"]] == ["docs/spec.md"]
        assert pkg["artifact_count"] == 1
        assert pkg["machine_artifact_count"] == 2


class TestBundleEvidence:
    def _manifest(self, tmp_path: Path) -> dict:
        return {
            "bundle": {
                "generated_at": "2026-11-11T10:00:00",
                "project_dir": str(tmp_path),
            },
            "components": {
                "ci-results": {"label": "CI Results", "artifacts": [{"dest": "a"}]},
                "reviews": {"label": "Reviews", "artifacts": []},
            },
            "artifacts": [
                {"type": "ci-results",
                 "dest": str(tmp_path / "bundle" / "b" / "x.json"),
                 "sha256": "a" * 64},
            ],
            "integrity": {"manifest_sha256": "b" * 64},
            "swe_status": {
                "SWE.1": {"name": "SWE.1 软件需求分析", "status": "completed"},
            },
        }

    def test_writes_three_formats(self, tmp_path):
        bundle = tmp_path / "bundle"
        written = write_bundle_evidence(bundle, self._manifest(tmp_path))

        assert (bundle / "bundle-summary.md").is_file()
        assert (bundle / "bundle-summary.html").is_file()
        html_text = (bundle / "bundle-summary.html").read_text(encoding="utf-8")
        assert "CI Results" in html_text and "b" * 64 in html_text
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            assert "excel" not in written
        else:
            assert (bundle / "bundle-manifest.xlsx").is_file()
            assert "excel" in written

    def test_artifact_paths_are_relative_to_bundle(self, tmp_path):
        bundle = tmp_path / "bundle"
        write_bundle_evidence(bundle, self._manifest(tmp_path))
        md = (bundle / "bundle-summary.md").read_text(encoding="utf-8")
        assert "b/x.json" in md
        assert f"`{tmp_path}/b/x.json`" not in md

    def test_pack_emits_human_reports(self, tmp_path):
        from yuleosh.evidence.evidence_check import pack_evidence_bundle

        (tmp_path / ".yuleosh").mkdir()
        (tmp_path / ".yuleosh" / "ci-config.yaml").write_text(
            "stages: [build]\n", encoding="utf-8")
        out = tmp_path / "bundle"

        pack_evidence_bundle(str(tmp_path), output_dir=str(out))

        assert (out / "audit-manifest.json").is_file()
        assert (out / "bundle-summary.md").is_file()
        assert (out / "bundle-summary.html").is_file()
