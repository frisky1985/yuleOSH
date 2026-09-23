"""pytest configuration for yuleOSH tests."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

# Require a test JWT secret so auth modules don't raise at import time.
# The exact value is irrelevant for tests; any non-empty string works.
os.environ.setdefault("YULEOSH_JWT_SECRET", "test-jwt-secret-for-ci-only-not-for-production")

# NOTE (v3.12.x CI 真跑修复): OSH_HOME 不在此全局设置。
# 曾尝试 per-process 隔离 (yuleosh-pytest-<pid>) 防 event_bus 污染 /tmp，
# 但副作用是 test_api.py 等模块用 setdefault 自己设 OSH_HOME=repo 根时
# 被 conftest 抢占，导致 docs/spec.md 相对解析失败（11 errors）。
# /tmp 污染的真正根因已在 loop_engine/event_bus.py 修复：
# EventQueuePersistence 默认路径改为 _default_persistence_path()
# （OSH_HOME 优先，否则 tempfile 隔离目录），不再裸写 /tmp/.yuleosh。


# ---------------------------------------------------------------------------
# Sessions-root isolation (2026-09-23)
# ---------------------------------------------------------------------------
# 每次 pipeline run 会在 sessions 根下建一个目录。该根原为
# ``<OSH_HOME>/.osh/sessions``，而 test_api.py 在模块导入期就用 setdefault
# 把 OSH_HOME 钉到仓库根（进程级）—— 于是每个构造过 PipelineSession 的测试
# 都往仓库自己的 ``.osh/sessions`` 里漏一个目录。实测代价：3611 个残留目录，
# 占历史上出现过的全部 session 的 99.6%（字节数可忽略，但拖慢
# api/artifacts.py 的 O(N) 扫描）。
#
# 这里用 ``OSH_SESSIONS_DIR`` 单独重定向 sessions 根，**不动 OSH_HOME**，
# 所以 test_api.py 依赖的相对路径解析不受影响（上次直接抢占 OSH_HOME 的
# 尝试坏掉了 11 个测试）。临时根保持 ``<project>/.osh/sessions`` 的层级形态，
# 因为 PipelineSession.to_dict 会向上追溯三层反推 project_dir。
_SESSIONS_TMP: str | None = None
if not os.environ.get("OSH_SESSIONS_DIR", "").strip():
    _SESSIONS_TMP = tempfile.mkdtemp(prefix="yuleosh-pytest-sessions-")
    os.environ["OSH_SESSIONS_DIR"] = str(
        Path(_SESSIONS_TMP) / "project" / ".osh" / "sessions"
    )
    Path(os.environ["OSH_SESSIONS_DIR"]).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Mock-path tripwire (2026-09-23)
# ---------------------------------------------------------------------------
# 背景：``api/pipeline.py::_run_orchestrator_job`` 把 project_dir 导出为
# **进程级** ``os.environ["OSH_HOME"]``。当 project_dir 来自被 patch 掉的
# ``yuleosh.api.pipeline.Path``（测试里常见写法 ``return_value=MagicMock()``）
# 时，它的 ``str()`` 就是 ``<MagicMock name='mock.resolve().parent.parent' id=...>``，
# 随后 ``store.py`` 的 ``Path(db).parent.mkdir(parents=True, exist_ok=True)``
# 会在 CWD 真建出同名目录。实测累计 **100+ 个**（仓库根 89 + projects/ 12），
# 污染 ``projects/`` 的项目发现与磁盘扫描，且随每次跑测试再生。
#
# 这里不改变任何测试行为，只**记录**「往真实文件系统写 MagicMock 路径」的调用，
# 并在会话末尾按测试归因打印，把静默污染变成可见信息。
# 设 ``OSH_ALLOW_MOCK_PATHS=1`` 可完全关闭（不包装，无开销）。
_MOCK_PATH_HITS: list = []
_MOCK_PATH_SILENT = bool(os.environ.get("OSH_ALLOW_MOCK_PATHS"))
_MOCK_PATH_ORIG: dict = {}


def _install_mock_path_tripwire() -> None:
    """Wrap FS-creating calls so a MagicMock-derived path is never silent."""
    if _MOCK_PATH_SILENT:
        return

    import functools
    import pathlib
    import traceback

    orig_mkdir = pathlib.Path.mkdir
    if getattr(orig_mkdir, "_yuleosh_mock_guard", False):
        return
    orig_touch = pathlib.Path.touch
    orig_makedirs = os.makedirs
    _MOCK_PATH_ORIG.update(mkdir=orig_mkdir, touch=orig_touch, makedirs=orig_makedirs)

    def _note(target, kind: str) -> None:
        frames = [
            f for f in traceback.format_stack()[:-3]
            if "/tests/" in f or "/src/" in f
        ]
        _MOCK_PATH_HITS.append(
            (
                os.environ.get("PYTEST_CURRENT_TEST", "<no-test>").split(" (")[0],
                f"[{kind}] {target}",
                "".join(frames[-3:]),
            )
        )

    @functools.wraps(orig_mkdir)
    def _mkdir(self, *a, **k):
        if "<MagicMock" in str(self):
            _note(self, "Path.mkdir")
        return orig_mkdir(self, *a, **k)

    @functools.wraps(orig_touch)
    def _touch(self, *a, **k):
        if "<MagicMock" in str(self):
            _note(self, "Path.touch")
        return orig_touch(self, *a, **k)

    @functools.wraps(orig_makedirs)
    def _makedirs(name, *a, **k):
        if "<MagicMock" in str(name):
            _note(name, "os.makedirs")
        return orig_makedirs(name, *a, **k)

    _mkdir._yuleosh_mock_guard = True
    pathlib.Path.mkdir = _mkdir
    pathlib.Path.touch = _touch
    os.makedirs = _makedirs


def _report_mock_path_hits() -> None:
    """Print (and warn about) MagicMock paths that reached the real FS."""
    if _MOCK_PATH_ORIG.get("mkdir") is not None:
        import pathlib

        pathlib.Path.mkdir = _MOCK_PATH_ORIG["mkdir"]
        pathlib.Path.touch = _MOCK_PATH_ORIG["touch"]
        os.makedirs = _MOCK_PATH_ORIG["makedirs"]

    if not _MOCK_PATH_HITS:
        return
    by_test: dict = {}
    for tid, path, stack in _MOCK_PATH_HITS:
        by_test.setdefault(tid, []).append((path, stack))

    print("\n" + "=" * 78)
    print(f"[mock-path] 检测到 {len(_MOCK_PATH_HITS)} 次「MagicMock 路径落盘」"
          f"，来自 {len(by_test)} 个测试")
    print("=" * 78)
    for tid, entries in sorted(by_test.items()):
        print(f"\n● {tid}  ({len(entries)} 次)")
        seen = set()
        for path, _ in entries:
            if path in seen:
                continue
            seen.add(path)
            print(f"    {path}")
        print("    调用栈:")
        for line in entries[0][1].strip().splitlines():
            print("      " + line.strip())
    print("\n修法见 tests/conftest.py 注释；确需静默：OSH_ALLOW_MOCK_PATHS=1")
    print("=" * 78)


_install_mock_path_tripwire()


# ---------------------------------------------------------------------------
# Evidence-pack leak guard (2026-09-23)
# ---------------------------------------------------------------------------
# 背景：``OSH_HOME`` 在同一进程里有**两份真值** —— 模块级常量（import 期快照）
# 与 ``os.environ["OSH_HOME"]``（运行时可改）。dashboard 的证据生成把 bundle
# 位置交给 ``dashboard.OSH_HOME``、把写入目标交给 ``api.OSH_HOME``，两个快照
# 一旦分叉，测试隔离就失效：生成的证据包落进**仓库**。实测两处落点：
#
#   - ``.osh/evidence/``      ：env 指向仓库根时（收集期 test_api.py 会这样钉）
#   - ``src/.osh/evidence/``  ：env 未设时（``api.PROJECT_ROOT`` 实为 ``src``）
#
# 累计 46 个空壳包（174B / ~890B）外加 ``compliance-pack.zip``；``src`` 那处
# 自 09-02 起漏了两周。根因已在 ``yuleosh.api.resolve_osh_home`` 修掉（隔离
# 现在真正生效），这里只再加一道**自愈网**：会话开始记录两处目录的包集合，
# 结束时把**本会话新增**的包清掉并逐条打印。
#
# 判据是「跑测试期间新出现在源码仓库里的 compliance-pack」—— 合法证据包只会
# 落在项目目录或服务端 OSH_HOME，不可能在跑测试时落进源码树。设
# ``OSH_ALLOW_EVIDENCE_WRITES=1`` 可关闭（不记录、不清扫，零开销）。
_REPO_ROOT_DIR = Path(__file__).resolve().parent.parent
_EVIDENCE_ROOTS = (
    _REPO_ROOT_DIR / ".osh" / "evidence",
    _REPO_ROOT_DIR / "src" / ".osh" / "evidence",
)
_EVIDENCE_GUARD_OFF = bool(os.environ.get("OSH_ALLOW_EVIDENCE_WRITES"))
_EVIDENCE_BEFORE: dict = {}


def _snapshot_repo_evidence() -> dict:
    return {
        root: ({p.name for p in root.glob("compliance-pack*.zip")} if root.is_dir() else set())
        for root in _EVIDENCE_ROOTS
    }


def pytest_configure(config):
    """Record the repo's evidence-pack inventory before any test runs."""
    if not _EVIDENCE_GUARD_OFF:
        _EVIDENCE_BEFORE.update(_snapshot_repo_evidence())


def _sweep_evidence_leaks() -> list:
    """Delete packs that *this session* wrote into the source tree."""
    if _EVIDENCE_GUARD_OFF or not _EVIDENCE_BEFORE:
        return []
    removed = []
    for root, before in _EVIDENCE_BEFORE.items():
        for name in sorted(_snapshot_repo_evidence().get(root, set()) - before):
            try:
                (root / name).unlink()
                removed.append(str((root / name).relative_to(_REPO_ROOT_DIR)))
            except OSError:
                pass
    return removed


def _sweep_mock_path_pollution() -> int:
    """删除本会话（及历史遗留）落在仓库里的 ``<MagicMock ...>`` 目录。

    只匹配名字以 ``<MagicMock`` 开头的目录，且限定在仓库根与 ``projects/``
    两处（实测只有这两处出现过）。这是**自愈**措施：即便某个测试仍然把
    Mock 的 repr 当路径落盘，跑完也不会留在仓库里。
    """
    if _MOCK_PATH_SILENT:
        return 0
    repo_root = Path(__file__).resolve().parent.parent
    removed = 0
    for parent in (repo_root, repo_root / "projects"):
        if not parent.is_dir():
            continue
        for child in parent.glob("<MagicMock*"):
            if child.name.startswith("<MagicMock") and child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
    return removed


def pytest_sessionfinish(session, exitstatus):
    """Drop the throwaway sessions root once the run is over."""
    _report_mock_path_hits()
    swept = _sweep_mock_path_pollution()
    if swept:
        print(f"[mock-path] 已自动清扫 {swept} 个 <MagicMock ...> 污染目录")
    leaked = _sweep_evidence_leaks()
    if leaked:
        print(f"[evidence-leak] 已自动清扫 {len(leaked)} 个漏进仓库的证据包：" + ", ".join(leaked))
    if _SESSIONS_TMP:
        shutil.rmtree(_SESSIONS_TMP, ignore_errors=True)


@pytest.fixture(autouse=True)
def _isolate_global_registries():
    """每个测试后恢复单例注册表，防跨测试污染（2026-08-19）。

    背景：RulesetRegistry / ScannerRegistry 是模块级单例，测试内
    register(make_default=True) 会永久改写 _default / _registry，
    泄漏到后续测试。实证案例：test_rulesets.py::test_make_default_overrides
    注册 Second 为默认 → review_misra 的 GSCR 翻译拿到无
    translate_violations 的实例 → gscr-report.json 静默缺失
    （全量回归 -x 才暴露，单独跑单文件全绿）。

    恢复策略：
    - ScannerRegistry：自带 reset()（清空 + 重建 5 个内置适配器）。
    - RulesetRegistry：_instance=None 重建后是空注册表（内置注册只在
      registry.py 模块导入时执行一次），必须显式重注册 4 个内置规则集，
      与 registry.py 模块级 _registry 一致。
    """
    yield
    from yuleosh.ci.rulesets import (
        GscCppRuleSet,
        GscCRuleSet,
        GscrCompositeRuleSet,
        MisraC2023RuleSet,
        RulesetRegistry,
    )
    from yuleosh.ci.scanners import ScannerRegistry

    ScannerRegistry().reset()
    RulesetRegistry._instance = None
    _reg = RulesetRegistry()
    _reg.register(MisraC2023RuleSet)
    _reg.register(GscCRuleSet)
    _reg.register(GscCppRuleSet)
    _reg.register(GscrCompositeRuleSet, make_default=True)

    # Store / KGStore 单例清理（2026-08-25）: 单例 key 是 db_path 或 "default"，
    # db 路径来自 OSH_HOME env。全量随机序下，其他测试写入 OSH_HOME 后
    # Store() 会缓存指向临时 db 的实例，泄漏到后续测试（实证:
    # test_v380_a6_dashboard_f2 全量失败、单独通过）。此处每测试后重置，
    # 与 test_coverage_phase9_billing_user.py 的手动清理模式一致。
    try:
        from yuleosh.store import Store
        Store._instances = {}
    except Exception:  # noqa: BLE001 — store 可选，清理失败不阻断
        pass
    try:
        from yuleosh.knowledge_graph.store import KGStore
        KGStore._instances = {}
    except Exception:  # noqa: BLE001
        pass


def pytest_collection_modifyitems(config, items):
    """Skip perf-marked tests unless explicitly requested.

    Perf tests (test_kg_performance, test_perf_baseline, test_kb_dedup_perf)
    run benchmarks against the real 28MB knowledge-graph DB and can take
    minutes. They are isolated behind the ``perf`` marker:

      - Default suite:        perf tests are skipped (fast, no hang)
      - Explicit perf run:    pytest -m perf tests/test_kg_performance.py
                              or RUN_PERF=1 pytest tests/...
    """
    if os.environ.get("RUN_PERF"):
        return
    marker_expr = config.getoption("-m", default="")
    if "perf" in (marker_expr or "").split():
        return
    skip_perf = __import__("pytest").mark.skip(
        reason="perf/benchmark test — run with '-m perf' or RUN_PERF=1"
    )
    for item in items:
        if "perf" in item.keywords:
            item.add_marker(skip_perf)
