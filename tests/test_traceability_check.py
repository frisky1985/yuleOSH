import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from yuleosh.alm.traceability import compute_trace_integrity
from yuleosh.audit import AuditLog
from yuleosh.cli.commands.traceability import cmd_traceability_check

# ── fixtures ────────────────────────────────────────────────────────────

OK_LRT = {
    "lrm": {
        "summary": {
            "total": 3,
            "with_code": 3,
            "with_test": 3,
            "with_review": 2,
            "without_code": 0,
            "without_test": 0,
            "without_review": 1,
            "coverage_pct": 100.0,
        },
        "requirements": [
            {"id": "SHALL-1", "req_id": "REQ-A-1", "has_code": True,
             "has_test": True, "has_review": True, "statement": "S1"},
            {"id": "SHALL-2", "req_id": "REQ-A-2", "has_code": True,
             "has_test": True, "has_review": True, "statement": "S2"},
            {"id": "SHALL-3", "req_id": "REQ-A-3", "has_code": True,
             "has_test": True, "has_review": False, "statement": "S3"},
        ],
    },
    "gap_analysis": {"total_gaps": 0, "gaps": []},
    "orphaned_test_files": [],
    "generated_at": "2026-08-07T12:00:00",
}

BROKEN_LRT = {
    "lrm": {
        "summary": {
            "total": 2,
            "with_code": 1,
            "with_test": 1,
            "with_review": 0,
            "without_code": 1,
            "without_test": 1,
            "without_review": 2,
            "coverage_pct": 50.0,
        },
        "requirements": [
            {"id": "SHALL-1", "req_id": "REQ-B-1", "has_code": True,
             "has_test": True, "has_review": False, "statement": "S1"},
            {"id": "SHALL-2", "req_id": "REQ-B-2", "has_code": False,
             "has_test": False, "has_review": False, "statement": "S2"},
        ],
    },
    "gap_analysis": {
        "total_gaps": 3,
        "gaps": [
            {"type": "no_test", "req_id": "REQ-B-2", "statement": "S2"},
            {"type": "no_code", "req_id": "REQ-B-2", "statement": "S2"},
            {"type": "no_review", "req_id": "REQ-B-1", "statement": "S1"},
        ],
    },
    "orphaned_test_files": ["tests/test_orphan_bad.py"],
    "generated_at": "2026-08-07T12:00:00",
}


@pytest.fixture
def ok_lrt():
    with patch("yuleosh.alm.traceability.generate_lrt", return_value=OK_LRT):
        yield OK_LRT


@pytest.fixture
def broken_lrt():
    with patch("yuleosh.alm.traceability.generate_lrt", return_value=BROKEN_LRT):
        yield BROKEN_LRT


# ── 1. compute_trace_integrity 状态判定 ────────────────────────────────

def test_integrity_ok_status(ok_lrt):
    record = compute_trace_integrity("/tmp/proj")
    assert record["status"] == "ok"
    assert record["requirements_total"] == 3
    assert record["test_coverage_pct"] == 100.0
    assert record["broken_links"] == []
    assert record["orphaned_tests"] == []


def test_integrity_broken_status(broken_lrt):
    record = compute_trace_integrity("/tmp/proj")
    assert record["status"] == "broken"
    assert record["test_coverage_pct"] == 50.0
    assert len(record["broken_links"]) == 3
    assert len(record["orphaned_tests"]) == 1


def test_integrity_hash_deterministic(ok_lrt):
    r1 = compute_trace_integrity("/tmp/proj")
    r2 = compute_trace_integrity("/tmp/proj")
    assert r1["integrity_hash"] == r2["integrity_hash"]
    assert len(r1["integrity_hash"]) == 64  # SHA-256 hex


def test_integrity_hash_changes_on_tamper(ok_lrt):
    """事后补链：改报告内容 → 哈希必须变化（防补链）。"""
    r1 = compute_trace_integrity("/tmp/proj")
    # 模拟事后把 REQ-A-3 的 review 从 False 改成 True（补链）
    tampered = json.loads(json.dumps(OK_LRT))
    tampered["lrm"]["summary"]["with_review"] = 3
    tampered["lrm"]["requirements"][2]["has_review"] = True
    with patch("yuleosh.alm.traceability.generate_lrt", return_value=tampered):
        r2 = compute_trace_integrity("/tmp/proj")
    assert r1["integrity_hash"] != r2["integrity_hash"]


def test_integrity_empty_project():
    """空项目：total=0 → ok（无需求即无断链），覆盖率 0。"""
    empty = {
        "lrm": {"summary": {"total": 0, "with_code": 0, "with_test": 0,
                            "with_review": 0, "coverage_pct": 0.0},
                "requirements": []},
        "gap_analysis": {"total_gaps": 0, "gaps": []},
        "orphaned_test_files": [],
        "generated_at": "2026-08-07T12:00:00",
    }
    with patch("yuleosh.alm.traceability.generate_lrt", return_value=empty):
        record = compute_trace_integrity("/tmp/proj")
    assert record["status"] == "ok"
    assert record["test_coverage_pct"] == 0.0


# ── 2. cmd_traceability_check CLI 门禁 ─────────────────────────────────

def _make_args(project_dir="/tmp/proj", data_root=None):
    return SimpleNamespace(
        project_dir=project_dir,
        spec=None,
        data_root=data_root,
        json_output=False,
    )


def test_cmd_check_exit_1_on_broken(broken_lrt, tmp_path):
    args = _make_args(data_root=str(tmp_path / "data"))
    with pytest.raises(SystemExit) as exc:
        cmd_traceability_check(args)
    assert exc.value.code == 1


def test_cmd_check_exit_0_on_ok(ok_lrt, tmp_path):
    args = _make_args(data_root=str(tmp_path / "data"))
    cmd_traceability_check(args)  # 不应抛 SystemExit


def test_cmd_check_json_output(ok_lrt, tmp_path, capsys):
    args = SimpleNamespace(
        project_dir="/tmp/proj", spec=None,
        data_root=str(tmp_path / "data"), json_output=True,
    )
    cmd_traceability_check(args)
    out = capsys.readouterr().out
    assert '"integrity_hash"' in out
    assert '"status": "ok"' in out


# ── 3. audit SHA-256 链写入与验证 ─────────────────────────────────────

def test_cmd_check_writes_audit_chain(ok_lrt, tmp_path):
    data_root = str(tmp_path / "data")
    args = _make_args(data_root=data_root)
    cmd_traceability_check(args)

    log = AuditLog(data_root=data_root)
    events = log.query()
    assert len(events) >= 1
    last = events[-1]
    assert last.action == "traceability.check"
    assert last.actor == "yuleosh-cli"
    detail = last.detail or {}
    assert detail["status"] == "ok"

    # SHA-256 链必须可验证（无篡改）
    result = log.verify()
    assert result["valid"] is True


def test_cmd_check_audit_detail_matches_integrity(ok_lrt, tmp_path):
    """审计 detail 中的 integrity_hash 必须等于 compute 的哈希。"""
    data_root = str(tmp_path / "data")
    args = _make_args(data_root=data_root)
    cmd_traceability_check(args)

    record = compute_trace_integrity("/tmp/proj")
    log = AuditLog(data_root=data_root)
    events = log.query()
    detail = events[-1].detail or {}
    assert detail["integrity_hash"] == record["integrity_hash"]
    assert detail["requirements_total"] == record["requirements_total"]


def test_cmd_check_audit_failure_nonfatal(ok_lrt, tmp_path, capsys):
    """audit 写入失败（如 data_root 不可写）不阻塞门禁本身。"""
    bad_root = str(tmp_path / "no_such_dir" / "deep" / "root")
    args = _make_args(data_root=bad_root)
    # AuditLog 会尝试 mkdir；若失败不应影响 check 的判定（此处目录可创建，
    # 用 monkeypatch 强制 record 抛异常更贴近"审计失败"路径）
    with patch.object(AuditLog, "record", side_effect=OSError("disk full")):
        cmd_traceability_check(args)  # 不应抛异常
    out = capsys.readouterr().out
    assert "追溯完整性检查" in out


def test_broken_status_in_audit(broken_lrt, tmp_path):
    data_root = str(tmp_path / "data")
    args = _make_args(data_root=data_root)
    with pytest.raises(SystemExit):
        cmd_traceability_check(args)
    log = AuditLog(data_root=data_root)
    events = log.query()
    assert (events[-1].detail or {})["status"] == "broken"
