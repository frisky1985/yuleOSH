# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for api/spec.py Studio endpoints — projects / list / read / save.

工作区模型：一个工程 = OSH_HOME/projects/<pid>/，规格在该工程的 docs/ 下。
"""

import pytest

import yuleosh.api as api
from yuleosh.api.spec import handle_spec

_USER = {"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"}

VALID_MD = """# Brake Light Spec

### REQ-001: Brake Light Activation

- The system SHALL turn on the brake light within 100ms of pedal press.

#### Reason

Safety signaling to following vehicles.

#### Scenario: normal braking

- GIVEN the vehicle is powered
- WHEN the driver presses the brake pedal
- THEN the brake light turns on within 100ms
"""


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Isolated OSH_HOME; Store 名称映射被打桩（测试不依赖 sqlite）。"""
    monkeypatch.setattr(api, "OSH_HOME", str(tmp_path))
    monkeypatch.setattr("yuleosh.api.spec._project_name_map", lambda: {})
    return tmp_path


@pytest.fixture
def project(home):
    """一个已存在、带 docs/ 的工程工作区，返回 (home, pid)。"""
    pid = "18"
    (home / "projects" / pid / "docs").mkdir(parents=True)
    return home, pid


def _call(method, tail, body=None, query=None):
    return handle_spec(method, tail, body or {}, query or {}, current_user=_USER)


# ── projects（工作区列表） ───────────────────────────────────────────────

def test_projects_empty(home):
    result, code = _call("GET", "projects")
    assert code == 200
    assert result["data"] == {"projects": [], "count": 0}


def test_projects_lists_dirs_with_spec_counts(home, project):
    root, pid = project
    (root / "projects" / pid / "docs" / "spec.md").write_text(VALID_MD, encoding="utf-8")
    other = root / "projects" / "gpio-led"
    (other / "docs").mkdir(parents=True)
    (other / "docs" / "a.md").write_text("# a", encoding="utf-8")
    # 非工程目录（无 docs/）也应出现在列表里，只是 spec_count=0
    (root / "projects" / "empty").mkdir()

    result, code = _call("GET", "projects")
    assert code == 200
    by_id = {p["id"]: p for p in result["data"]["projects"]}
    assert set(by_id) == {pid, "gpio-led", "empty"}
    assert by_id[pid]["spec_count"] == 1
    assert by_id[pid]["has_docs"] is True
    assert by_id[pid]["dir"] == f"projects/{pid}"
    assert by_id["empty"]["spec_count"] == 0
    assert by_id["empty"]["has_docs"] is False


def test_projects_rejects_post(home):
    result, code = _call("POST", "projects")
    assert code == 405


def test_projects_health_ok_for_valid_spec(home, project):
    """健康徽标：符合规范的规格不应产生 ERROR。"""
    root, pid = project
    (root / "projects" / pid / "docs" / "spec.md").write_text(VALID_MD, encoding="utf-8")

    result, code = _call("GET", "projects")
    assert code == 200
    health = {p["id"]: p["health"] for p in result["data"]["projects"]}[pid]
    assert health["errors"] == 0
    assert health["warnings"] >= 0


def test_projects_health_flags_placeholder_spec(home, project):
    """健康徽标：占位/空规格必须报错（与 spec/save 同一套标准）。"""
    root, pid = project
    (root / "projects" / pid / "docs" / "spec.md").write_text(
        "# placeholder\n", encoding="utf-8")

    result, code = _call("GET", "projects")
    assert code == 200
    health = {p["id"]: p["health"] for p in result["data"]["projects"]}[pid]
    # 无需求 + 无场景
    assert health["errors"] >= 2
    # 该文件连需求都没有 → 算「占位规格」，前端不当作写错的规格
    assert health["stubs"] == 1
    assert health["checked"] == 1


def test_projects_health_zero_without_docs(home):
    (home / "projects" / "bare").mkdir(parents=True)
    result, code = _call("GET", "projects")
    assert code == 200
    health = result["data"]["projects"][0]["health"]
    assert health["errors"] == 0
    assert health["warnings"] == 0
    assert health["stubs"] == 0
    assert health["checked"] == 0


# ── list ────────────────────────────────────────────────────────────────

def test_list_requires_project(home):
    result, code = _call("GET", "list")
    assert code == 400


def test_list_rejects_traversal(project):
    _root, _pid = project
    result, code = _call("GET", "list", query={"project": ["../18"]})
    assert code == 403


def test_list_unknown_project(home):
    result, code = _call("GET", "list", query={"project": ["999"]})
    assert code == 404


def test_list_only_docs_dir(home, project):
    root, pid = project
    proj = root / "projects" / pid
    (proj / "docs" / "spec.md").write_text("# s", encoding="utf-8")
    (proj / "root-spec.md").write_text("# r", encoding="utf-8")
    (proj / "specs").mkdir()
    (proj / "specs" / "other.md").write_text("# o", encoding="utf-8")

    result, code = _call("GET", "list", query={"project": [pid]})
    assert code == 200
    assert result["data"]["project"] == pid
    assert [f["path"] for f in result["data"]["files"]] == ["docs/spec.md"]


def test_list_rejects_post(project):
    _root, pid = project
    result, code = _call("POST", "list", query={"project": [pid]})
    assert code == 405


# ── read ────────────────────────────────────────────────────────────────

def test_read_returns_content(home, project):
    root, pid = project
    (root / "projects" / pid / "docs" / "spec.md").write_text(VALID_MD, encoding="utf-8")

    result, code = _call("GET", "read", query={"project": [pid], "path": ["docs/spec.md"]})
    assert code == 200
    assert result["data"]["content"] == VALID_MD
    assert result["data"]["project"] == pid


def test_read_requires_path(project):
    _root, pid = project
    result, code = _call("GET", "read", query={"project": [pid]})
    assert code == 400


def test_read_traversal_rejected(project):
    _root, pid = project
    result, code = _call("GET", "read",
                         query={"project": [pid], "path": ["../../etc/passwd"]})
    assert code == 403


def test_read_missing_file(project):
    _root, pid = project
    result, code = _call("GET", "read", query={"project": [pid], "path": ["docs/nope.md"]})
    assert code == 404


# ── save ────────────────────────────────────────────────────────────────

def test_save_default_path_is_project_docs(home, project):
    root, pid = project
    result, code = _call("POST", "save", body={"project": pid, "markdown": VALID_MD})
    assert code == 200
    target = root / "projects" / pid / "docs" / "spec.md"
    assert target.read_text(encoding="utf-8") == VALID_MD
    assert result["data"]["spec_path"] == str(target)
    assert result["data"]["stats"]["requirements"] == 1
    assert not (target.parent / ".spec.md.studio-tmp").exists()


def test_save_requires_project(home):
    result, code = _call("POST", "save", body={"markdown": VALID_MD})
    assert code == 400


def test_save_rejects_invalid_without_writing(home, project):
    root, pid = project
    result, code = _call("POST", "save", body={
        "project": pid, "path": "docs/bad.md", "markdown": "# nothing here"})
    assert code == 400
    assert not (root / "projects" / pid / "docs" / "bad.md").exists()


def test_save_conflict_then_force(home, project):
    root, pid = project
    target = root / "projects" / pid / "docs" / "spec.md"
    target.write_text("# old", encoding="utf-8")

    result, code = _call("POST", "save", body={"project": pid, "markdown": VALID_MD})
    assert code == 409
    assert target.read_text(encoding="utf-8") == "# old"

    result, code = _call("POST", "save",
                         body={"project": pid, "markdown": VALID_MD, "force": True})
    assert code == 200
    assert target.read_text(encoding="utf-8") == VALID_MD


def test_save_traversal_rejected(home, project):
    _root, pid = project
    result, code = _call("POST", "save", body={
        "project": pid, "path": "../../outside.md", "markdown": VALID_MD})
    assert code == 403


def test_save_creates_nested_docs_dir(home, project):
    root, pid = project
    result, code = _call("POST", "save", body={
        "project": pid, "path": "docs/features/spec.md", "markdown": VALID_MD})
    assert code == 200
    assert (root / "projects" / pid / "docs" / "features" / "spec.md").exists()
