"""Regression tests for call-time ``OSH_HOME`` resolution (2026-09-23).

背景（根因）: ``OSH_HOME`` 在各 api 模块里是 **import 期快照**，而
``os.environ["OSH_HOME"]`` 可以在运行时被改 —— 同一进程里存在**两份真值**。
dashboard 的证据生成把 bundle 位置交给 ``dashboard.OSH_HOME``、把写入目标交给
``api.OSH_HOME``（``evidence.snapshot_bundle`` 内部 ``from . import OSH_HOME``），
两个快照分叉时隔离就失效：测试里生成的证据包落进**仓库** ``.osh/evidence/``。
实测累积 46 个空壳包（33×174B + 13×~890B）外加一个 ``compliance-pack.zip``，
且删掉之后每次跑测试还会再长出来。

修法: ``yuleosh.api.resolve_osh_home(current)`` 在**调用时**解析，并把测试里
长期并存的两套隔离手法都认下来 ——

- ``monkeypatch.setenv("OSH_HOME", tmp)``  → 232 处
- ``monkeypatch.setattr(mod, "OSH_HOME", tmp)`` → 82 处

优先级：本模块常量被显式覆盖 > 运行时 env > import 期快照。
（不能简单地「env 优先」：``tests/test_api.py`` 在**收集期**就用
``os.environ.setdefault`` 把 env 钉在仓库根，此后恒存在，env 优先会反过来
废掉 setattr 那一类隔离 —— 实测 28 项失败。）
"""

# @tests src/yuleosh/api/__init__.py

import zipfile
from pathlib import Path

import pytest

from yuleosh import api as A


REPO_ROOT = Path(__file__).resolve().parents[1]
# 两处都可能是落点：``<repo>/.osh/evidence``（env 指向仓库根时）与
# ``<repo>/src/.osh/evidence``（env 未设时 ``api.PROJECT_ROOT`` 实为 ``src``，
# 因为 ``parent.parent.parent`` 从 ``api/`` 往上三层 —— 这处 09-02 起漏了两周）。
EVIDENCE_ROOTS = (
    REPO_ROOT / ".osh" / "evidence",
    REPO_ROOT / "src" / ".osh" / "evidence",
)


# ── resolve_osh_home 的判定规则 ────────────────────────────────────────


class TestResolveOshHome:
    def test_falls_back_to_import_snapshot(self, monkeypatch):
        """GIVEN 既没改 env 也没覆盖常量 THEN 返回 import 期取值。"""
        monkeypatch.delenv("OSH_HOME", raising=False)
        assert A.resolve_osh_home(A.OSH_HOME) == A._OSH_HOME_AT_IMPORT

    def test_runtime_env_change_wins_when_constant_untouched(
        self, monkeypatch, tmp_path
    ):
        """GIVEN 只改了 env（232 处 setenv 手法）THEN 以 env 为准。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        assert A.resolve_osh_home(A.OSH_HOME) == str(tmp_path)

    def test_explicit_constant_override_wins_over_env(self, monkeypatch, tmp_path):
        """GIVEN 常量被显式覆盖、env 另有其值 THEN 常量赢。

        这是 82 处 ``setattr`` 隔离能继续生效的前提：收集期 test_api.py 已把
        env 钉在仓库根，若让 env 优先，这些测试的隔离会全部失效。
        """
        monkeypatch.setenv("OSH_HOME", str(REPO_ROOT))
        monkeypatch.setattr(A, "OSH_HOME", str(tmp_path))
        assert A.resolve_osh_home(A.OSH_HOME) == str(tmp_path)

    def test_no_argument_is_safe(self, monkeypatch):
        """GIVEN 不传 current THEN 仍返回非空字符串（不抛、不返回 Mock）。"""
        monkeypatch.delenv("OSH_HOME", raising=False)
        result = A.resolve_osh_home()
        assert isinstance(result, str) and result

    def test_non_string_env_is_ignored(self, monkeypatch):
        """GIVEN env 被整体打桩成非字符串（patch os.environ.get 的老写法）
        THEN 退回旧行为，绝不把 Mock 当路径用。"""
        from unittest.mock import MagicMock

        monkeypatch.setattr(A.os.environ, "get", MagicMock(return_value=MagicMock()))
        result = A.resolve_osh_home()
        assert isinstance(result, str)
        assert "<MagicMock" not in result


# ── 证据包写入目标（本次泄漏的现场） ───────────────────────────────────


def _make_bundle(root: Path) -> Path:
    bundle = root / ".yuleosh" / "evidence-bundle"
    bundle.mkdir(parents=True)
    (bundle / "audit-manifest.json").write_text(
        '{"integrity": {"total_artifacts": 1}}', encoding="utf-8"
    )
    return bundle


def _repo_evidence_zips() -> set[str]:
    """仓库内两处 evidence 目录里的包名集合（用于断言「没漏进仓库」）。"""
    found: set[str] = set()
    for root in EVIDENCE_ROOTS:
        if root.is_dir():
            rel = root.relative_to(REPO_ROOT)
            found |= {f"{rel}/{p.name}" for p in root.glob("compliance-pack*.zip")}
    return found


class TestEvidenceWriteTarget:
    def test_snapshot_bundle_honours_env_redirect(self, monkeypatch, tmp_path):
        """GIVEN env 指向 tmp（旧写法下无效）THEN 包落在 tmp，不再漏进仓库。

        这是原始缺陷的最小复现：修复前 ``snapshot_bundle`` 读 import 期常量，
        ``setenv`` 隔离形同虚设，包写进仓库 ``.osh/evidence/``。
        """
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        before = _repo_evidence_zips()

        from yuleosh.api.evidence import snapshot_bundle

        version = snapshot_bundle(str(_make_bundle(tmp_path)))

        assert version is not None
        assert (tmp_path / ".osh" / "evidence" / version).is_file()
        assert _repo_evidence_zips() == before, "证据包漏进了仓库 .osh/evidence/"

    def test_snapshot_bundle_honours_explicit_osh_home(self, monkeypatch, tmp_path):
        """GIVEN 调用方显式传 osh_home THEN 写入目标完全由它决定。

        dashboard 必须把自己的 ``OSH_HOME`` 传下来，否则 bundle 来源与写入
        目标各读一份快照 → 分叉。
        """
        other = tmp_path / "elsewhere"
        other.mkdir()
        monkeypatch.setenv("OSH_HOME", str(REPO_ROOT))  # env 指向仓库也不该被用

        from yuleosh.api.evidence import snapshot_bundle

        version = snapshot_bundle(str(_make_bundle(tmp_path)), osh_home=str(tmp_path))

        assert version is not None
        assert (tmp_path / ".osh" / "evidence" / version).is_file()
        assert not (other / ".osh").exists()

    def test_dashboard_worker_never_writes_into_repo(self, monkeypatch, tmp_path):
        """GIVEN 只有 dashboard.OSH_HOME 被隔离、env 反指仓库根
        THEN 后台生成仍把包写进隔离目录（跨模块同源）。

        这是 2026-09-23 的真实事故路径：
        ``test_api_dashboard_unit`` 只 patch ``D.OSH_HOME``，而
        ``snapshot_bundle`` 内部读 ``api.OSH_HOME``（= 仓库根）→ 包落仓库。
        """
        from unittest.mock import MagicMock

        from yuleosh.api import dashboard as D

        monkeypatch.setenv("OSH_HOME", str(REPO_ROOT))  # 收集期被钉死的 env
        monkeypatch.setattr(D, "OSH_HOME", str(tmp_path))
        D._ev_tasks.clear()

        _make_bundle(tmp_path)  # worker 会读 <project_dir>/.yuleosh/evidence-bundle

        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "ok"
        proc.stderr = ""
        monkeypatch.setattr(D.subprocess, "run", lambda *a, **kw: proc)

        before = _repo_evidence_zips()
        D._ev_tasks["t-osh"] = {"task_id": "t-osh", "status": "running"}
        D._run_evidence_task("t-osh", str(tmp_path))

        task = D._ev_tasks["t-osh"]
        assert task["status"] == "completed", task.get("error")
        assert (tmp_path / ".osh" / "evidence").is_dir()
        assert _repo_evidence_zips() == before, "证据包漏进了仓库 .osh/evidence/"


class TestEvidenceReadPaths:
    def test_list_files_reads_redirected_root(self, monkeypatch, tmp_path):
        """GIVEN env 重定向 THEN 列表读的是重定向后的目录。"""
        ev = tmp_path / ".osh" / "evidence"
        ev.mkdir(parents=True)
        (ev / "traceability-matrix.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv("OSH_HOME", str(tmp_path))

        from yuleosh.api.evidence import _list_evidence_files

        payload, status = _list_evidence_files()
        assert status == 200
        assert [f["name"] for f in payload["data"]["files"]] == ["traceability-matrix.json"]

    def test_generate_guard_accepts_redirected_root(self, monkeypatch, tmp_path):
        """GIVEN env 重定向 THEN 守卫用同一个根判定 project_dir。"""
        from yuleosh.api.evidence import _generate_evidence

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        payload, status = _generate_evidence({"project_dir": "/etc"})
        assert status == 403
        assert "inside OSH_HOME" in payload["error"]


class TestPackIsRealZip:
    def test_snapshot_zip_contains_bundle(self, monkeypatch, tmp_path):
        """GIVEN bundle 有内容 THEN 快照 zip 真含该内容（不是空壳）。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        bundle = _make_bundle(tmp_path)
        (bundle / "hil-report.md").write_text("# HIL", encoding="utf-8")

        from yuleosh.api.evidence import snapshot_bundle

        version = snapshot_bundle(str(bundle))
        with zipfile.ZipFile(tmp_path / ".osh" / "evidence" / version) as z:
            names = z.namelist()
        assert "audit-manifest.json" in names
        assert "hil-report.md" in names


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_env_is_treated_as_unset(monkeypatch, value):
    """GIVEN env 是空白串 THEN 视同未设置（不返回空路径）。"""
    monkeypatch.setenv("OSH_HOME", value)
    result = A.resolve_osh_home()
    assert result.strip()
