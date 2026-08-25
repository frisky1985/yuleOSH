"""Change Proposal (CP) — spec evolution management tests.

Covers the OpenSpec spec evolution mechanism (RULES §13):
- directory structure + templates
- propose / validate / status machine / archive
- blocking gate semantics (approved-but-not-implemented)
"""

# @tests src/yuleosh/spec/changes.py

from __future__ import annotations

import pytest
from pathlib import Path

from yuleosh.spec.changes import (
    ChangeProposal,
    archive_change,
    find_changes_dir,
    get_blocking_cps,
    list_changes,
    load_proposal,
    mark_implemented,
    propose_change,
    set_status,
    validate_proposal,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path / "proj"


def test_propose_creates_directory_with_templates(project: Path):
    """GIVEN empty project WHEN propose THEN creates proposal.md + tasks.md."""
    cp_dir = propose_change(project, "cp-001", title="Make threshold configurable")
    assert (cp_dir / "proposal.md").exists()
    assert (cp_dir / "tasks.md").exists()
    assert (project / ".osh" / "changes" / "cp-001") == cp_dir

    cp = load_proposal(project, "cp-001")
    assert cp is not None
    assert cp.status == "proposed"
    assert cp.title == "Make threshold configurable"
    assert cp.affects == ["core"]
    assert len(cp.tasks) >= 1


def test_propose_rejects_duplicate_and_bad_id(project: Path):
    """GIVEN existing cp WHEN propose same id THEN FileExistsError; bad id ValueError."""
    propose_change(project, "cp-001", title="x")
    with pytest.raises(FileExistsError):
        propose_change(project, "cp-001", title="y")
    with pytest.raises(ValueError):
        propose_change(project, "../escape", title="bad")


def test_validate_accepts_template(project: Path):
    """GIVEN template proposal WHEN validate THEN valid (warnings only)."""
    propose_change(project, "cp-001", title="x", affects="cap-a")
    result = validate_proposal(project, "cp-001")
    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_rejects_missing_title(project: Path):
    """GIVEN proposal without title frontmatter WHEN validate THEN invalid."""
    cp_dir = propose_change(project, "cp-001", title="x")
    text = (cp_dir / "proposal.md").read_text(encoding="utf-8")
    text = text.replace("title: x\n", "")
    (cp_dir / "proposal.md").write_text(text, encoding="utf-8")
    result = validate_proposal(project, "cp-001")
    assert result["valid"] is False
    assert any("title" in e for e in result["errors"])


def test_status_machine_transitions(project: Path):
    """GIVEN proposed cp WHEN approve/implement THEN status advances; illegal blocked."""
    propose_change(project, "cp-001", title="x")
    # illegal jump proposed → implemented
    with pytest.raises(ValueError):
        set_status(project, "cp-001", "implemented")
    # legal chain
    set_status(project, "cp-001", "approved")
    assert load_proposal(project, "cp-001").status == "approved"
    set_status(project, "cp-001", "implemented")
    assert load_proposal(project, "cp-001").status == "implemented"
    # illegal re-approve
    with pytest.raises(ValueError):
        set_status(project, "cp-001", "approved")


def test_archive_moves_to_archive_dir(project: Path):
    """GIVEN implemented cp WITH evidence WHEN archive THEN moves to archive/."""
    propose_change(project, "cp-001", title="x")
    set_status(project, "cp-001", "approved")
    mark_implemented(project, "cp-001", "run-abc123")
    target = archive_change(project, "cp-001")
    assert "archive" in str(target)
    assert (target / "proposal.md").exists()
    assert load_proposal(project, "cp-001") is None
    assert list_changes(project) == []


def test_archive_rejects_missing_evidence(project: Path):
    """GIVEN implemented WITHOUT evidence WHEN archive THEN ValueError (fail-closed)."""
    propose_change(project, "cp-001", title="x")
    set_status(project, "cp-001", "approved")
    set_status(project, "cp-001", "implemented")  # no evidence
    with pytest.raises(ValueError) as exc:
        archive_change(project, "cp-001")
    assert "evidence" in str(exc.value).lower()


def test_mark_implemented_requires_evidence_and_approved(project: Path):
    """GIVEN approved cp WHEN mark_implemented THEN evidence written; guards enforced."""
    propose_change(project, "cp-001", title="x")
    with pytest.raises(ValueError):
        mark_implemented(project, "cp-001", "")  # empty evidence
    with pytest.raises(ValueError):
        mark_implemented(project, "cp-001", "run-1")  # not approved yet
    set_status(project, "cp-001", "approved")
    cp = mark_implemented(project, "cp-001", "run-abc123")
    assert cp.status == "implemented"
    assert cp.implemented_by == "run-abc123"
    assert cp.has_implementation_evidence is True


def test_mark_implemented_persists_across_reload(project: Path):
    """GIVEN mark_implemented THEN reload sees evidence in frontmatter."""
    propose_change(project, "cp-001", title="x")
    set_status(project, "cp-001", "approved")
    mark_implemented(project, "cp-001", "run-xyz789")
    cp = load_proposal(project, "cp-001")
    assert cp is not None
    assert cp.implemented_by == "run-xyz789"


def test_mark_implemented_recovery_after_manual_implemented(project: Path):
    """GIVEN manually implemented (no evidence) WHEN mark_implemented THEN evidence attached."""
    propose_change(project, "cp-001", title="x")
    set_status(project, "cp-001", "approved")
    set_status(project, "cp-001", "implemented")  # manual, no evidence
    cp = mark_implemented(project, "cp-001", "run-recovery-1")
    assert cp.implemented_by == "run-recovery-1"
    archive_change(project, "cp-001")  # now allowed


def test_mark_implemented_rejects_overwrite(project: Path):
    """GIVEN implemented WITH evidence WHEN mark_implemented again THEN ValueError."""
    propose_change(project, "cp-001", title="x")
    set_status(project, "cp-001", "approved")
    mark_implemented(project, "cp-001", "run-first")
    with pytest.raises(ValueError):
        mark_implemented(project, "cp-001", "run-second")


def test_archive_rejects_non_implemented(project: Path):
    """GIVEN approved (not implemented) cp WHEN archive THEN ValueError."""
    propose_change(project, "cp-001", title="x")
    set_status(project, "cp-001", "approved")
    with pytest.raises(ValueError):
        archive_change(project, "cp-001")


def test_blocking_cps_only_approved(project: Path):
    """GIVEN proposed + approved cps WHEN get_blocking_cps THEN only approved."""
    propose_change(project, "cp-001", title="proposed one")
    propose_change(project, "cp-002", title="approved one")
    set_status(project, "cp-002", "approved")
    blocking = get_blocking_cps(project)
    assert [b.change_id for b in blocking] == ["cp-002"]
    assert blocking[0].is_blocking is True


def test_list_changes_sorted_and_empty_ok(project: Path):
    """GIVEN no changes THEN empty list; GIVEN two changes THEN sorted by id."""
    assert list_changes(project) == []
    propose_change(project, "cp-002", title="b")
    propose_change(project, "cp-001", title="a")
    ids = [c.change_id for c in list_changes(project)]
    assert ids == ["cp-001", "cp-002"]


def test_change_proposal_is_blocking_property():
    """GIVEN status approved THEN is_blocking True; others False."""
    assert ChangeProposal(change_id="x", path=Path("."), status="approved").is_blocking is True
    assert ChangeProposal(change_id="x", path=Path("."), status="proposed").is_blocking is False
    assert ChangeProposal(change_id="x", path=Path("."), status="implemented").is_blocking is False


def test_find_changes_dir_creates_nothing(project: Path):
    """GIVEN empty project WHEN find_changes_dir THEN path returned without creating dirs."""
    d = find_changes_dir(project)
    assert str(d).endswith(".osh/changes")
    assert not d.exists()
