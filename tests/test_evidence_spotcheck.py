# @tests src/yuleosh/evidence/spotcheck.py
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Semantic spot-check sampling tests."""

import json

from yuleosh.evidence.spotcheck import (
    load_requirements,
    render_checklist,
    sample_requirements,
)


def _rows(n=5):
    return [
        {"req_id": f"SHALL-{i}", "statement": f"Requirement {i}"}
        for i in range(1, n + 1)
    ]


def test_sample_is_deterministic_and_limited():
    first = sample_requirements(_rows(10), 3)
    second = sample_requirements(_rows(10), 3)

    assert [r["req_id"] for r in first] == [r["req_id"] for r in second]
    assert len(first) == 3


def test_sample_count_zero_returns_empty():
    assert sample_requirements(_rows(5), 0) == []


def test_load_requirements_reads_matrix(tmp_path):
    matrix = tmp_path / "matrix.json"
    matrix.write_text(
        json.dumps({"requirements": [{"req_id": "SHALL-1", "statement": "x"}, {}]}),
        encoding="utf-8",
    )

    assert [r["req_id"] for r in load_requirements(matrix)] == ["SHALL-1"]


def test_checklist_marks_annotation_presence(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "annotated.py").write_text("# @req SHALL-1\nx = 1\n", encoding="utf-8")

    content = render_checklist(
        [{"req_id": "SHALL-1", "statement": "Do x",
          "code_files": ["src/annotated.py", "src/missing.py"]}],
        tmp_path,
        count=1,
    )

    assert "src/annotated.py` ✓" in content
    assert "src/missing.py` —" in content
    assert "语义匹配" in content
