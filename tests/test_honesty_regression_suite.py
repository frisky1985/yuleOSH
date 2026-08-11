"""诚实性回归套件 — 防回退/防假绿（brainstorm-quality-guard-2026-08-08 §1.2）。

8 个自检用例（H1-H8）：故意注入假数据（空报告 / 全 PASS 断言 / 缺失产物 /
过期时间戳 / 覆盖率虚高 / mock 伪装 / 假 skip / 数字不一致），然后断言
**门禁真的会红**（对应 checker 返回 failed，或 ``yuleosh ci run`` 退出码非 0）。

套件自身规则：
- 所有自检通过 = 套件绿；
- 任一注入导致门禁不红（checker 仍 passed） = 套件失败（假绿复发）。

已有单测覆盖的用例（H2/H5/H6/H7）直接引用既有测试文件，不在本套件重复实现
（见各自 docstring 的 reference）。
"""
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from yuleosh.ci.honesty_gate import (  # noqa: E402
    check_empty_evidence,
    check_missing_artifacts,
    check_misra_consistency,
    check_result_freshness,
    run_honesty_gate,
)


def _mkproj(tmp_path: pathlib.Path, with_misra_report: bool = True,
            name: str = "proj") -> pathlib.Path:
    """Minimal project layout that makes the honesty gates non-skipped."""
    proj = tmp_path / name
    (proj / ".osh" / "evidence").mkdir(parents=True)
    (proj / ".yuleosh" / "reports").mkdir(parents=True)
    (proj / ".osh" / "ci").mkdir(parents=True)
    if with_misra_report:
        (proj / ".yuleosh" / "reports" / "misra-report.json").write_text(json.dumps({
            "total_violations": 2,
            "violations_raw": [
                {"rule_id": "Rule 10.1", "file": "a.c", "line": 1},
                {"rule_id": "Rule 10.1", "file": "a.c", "line": 2},
            ],
            "groups": {"Rule 10.1": {"count": 2, "total": 2}},
        }))
    (proj / ".osh" / "evidence" / "manifest.json").write_text(
        json.dumps({"files": [], "total_files": 0})
    )
    return proj


def _fresh_layer_result(proj: pathlib.Path, age_days: int = 0) -> pathlib.Path:
    """Write a layer1 result file with completed_at *age_days* in the past."""
    ts = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
    f = proj / ".osh" / "ci" / "layer1-test.json"
    f.write_text(json.dumps({"layer": 1, "status": "passed", "completed_at": ts}))
    return f


# ═══════════════════════════════════════════════════════════════════════
# H1 空报告注入 — 空自报对象不得撑绿
# ═══════════════════════════════════════════════════════════════════════


class TestH1EmptyReport:
    def test_empty_self_report_red(self, tmp_path):
        """注入 {"type":"review","status":"passed"} 纯自报空对象 → 门禁红。"""
        proj = _mkproj(tmp_path)
        (proj / ".osh" / "evidence" / "review.json").write_text(
            json.dumps({"type": "review", "status": "passed"})
        )
        status, msgs = check_empty_evidence(str(proj))
        assert status == "failed", f"空自报对象必须红，实际 {status}: {msgs}"

    def test_substantive_evidence_green(self, tmp_path):
        """实质证据（title/details/verdict）不误杀。"""
        proj = _mkproj(tmp_path)
        (proj / ".osh" / "evidence" / "review.json").write_text(
            json.dumps({"type": "review", "status": "passed",
                        "title": "SWE.4 review", "details": "real content",
                        "verdict": "approved"})
        )
        status, msgs = check_empty_evidence(str(proj))
        assert status == "passed", msgs

    def test_no_evidence_dir_skips(self, tmp_path):
        """无 evidence 目录 → skip（不是红）。"""
        status, msgs = check_empty_evidence(str(tmp_path))
        assert status == "skipped", msgs


# ═══════════════════════════════════════════════════════════════════════
# H2 全 PASS 断言注入 — reference: tests/test_compliance_no_fake_green.py
# ═══════════════════════════════════════════════════════════════════════

H2_REFERENCE = (
    "H2 已有单测覆盖: tests/test_compliance_no_fake_green.py "
    "(T3 KG covers>=3 + 测试文件 / T4 SRS SHALL 接线, 8 例)"
)


@pytest.mark.skip(reason=H2_REFERENCE)
def test_h2_all_pass_assertions_red():
    """全 PASS 断言测试文件 → compliance_checker 红（已在 reference 覆盖）。"""
    raise AssertionError("unreachable — see test_compliance_no_fake_green.py")


# ═══════════════════════════════════════════════════════════════════════
# H3 缺失产物注入 — 删除 misra-report.json / manifest.json → 红
# ═══════════════════════════════════════════════════════════════════════


class TestH3MissingArtifacts:
    def test_missing_misra_report_red(self, tmp_path):
        """有 reports 结构但缺 misra-report.json → 红（不再静默跳过）。"""
        proj = _mkproj(tmp_path, with_misra_report=False)
        status, msgs = check_missing_artifacts(str(proj))
        assert status == "failed", f"缺产物必须红，实际 {status}: {msgs}"
        assert "misra-report.json" in " ".join(msgs)

    def test_missing_manifest_red(self, tmp_path):
        """缺 manifest.json → 红。"""
        proj = _mkproj(tmp_path)
        (proj / ".osh" / "evidence" / "manifest.json").unlink()
        status, msgs = check_missing_artifacts(str(proj))
        assert status == "failed", f"缺 manifest 必须红，实际 {status}: {msgs}"

    def test_all_present_green(self, tmp_path):
        """产物齐备 → 绿。"""
        proj = _mkproj(tmp_path)
        status, msgs = check_missing_artifacts(str(proj))
        assert status == "passed", msgs

    def test_no_structure_skips(self, tmp_path):
        """无 reports/evidence 结构 → skip（干净目录不误伤）。"""
        status, msgs = check_missing_artifacts(str(tmp_path))
        assert status == "skipped", msgs


# ═══════════════════════════════════════════════════════════════════════
# H4 过期时间戳注入 — 新鲜度 gate（本次新增）
# ═══════════════════════════════════════════════════════════════════════


class TestH4StaleTimestamp:
    def test_stale_result_red(self, tmp_path):
        """completed_at 30 天前 → 新鲜度门禁红。"""
        proj = _mkproj(tmp_path)
        _fresh_layer_result(proj, age_days=30)
        status, msgs = check_result_freshness(str(proj), max_age_days=7)
        assert status == "failed", f"过期时间戳必须红，实际 {status}: {msgs}"

    def test_fresh_result_green(self, tmp_path):
        """刚刚完成 → 绿。"""
        proj = _mkproj(tmp_path)
        _fresh_layer_result(proj, age_days=0)
        status, msgs = check_result_freshness(str(proj), max_age_days=7)
        assert status == "passed", msgs

    def test_started_at_also_checked(self, tmp_path):
        """started_at 过期同样红（不只 completed_at）。"""
        proj = _mkproj(tmp_path)
        ts = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        (proj / ".osh" / "ci" / "layer1-old.json").write_text(
            json.dumps({"layer": 1, "status": "passed", "started_at": ts})
        )
        status, msgs = check_result_freshness(str(proj), max_age_days=30)
        assert status == "failed", msgs

    def test_no_dated_artifacts_skips(self, tmp_path):
        """无带时间戳产物 → skip。"""
        proj = _mkproj(tmp_path)
        status, msgs = check_result_freshness(str(proj), max_age_days=30)
        assert status == "skipped", msgs


# ═══════════════════════════════════════════════════════════════════════
# H5 覆盖率虚高注入 — reference: tests/test_mock_gate_no_fake_pass.py
# ═══════════════════════════════════════════════════════════════════════

H5_REFERENCE = (
    "H5 已有单测覆盖: tests/test_mock_gate_no_fake_pass.py "
    "(mock 报告 passed=False + skipped=True, 3 例) + run_c_coverage_check 阈值门禁"
)


@pytest.mark.skip(reason=H5_REFERENCE)
def test_h5_inflated_coverage_red():
    """c-coverage.json 虚高 → coverage gate 红（已在 reference 覆盖）。"""
    raise AssertionError("unreachable — see test_mock_gate_no_fake_pass.py")


# ═══════════════════════════════════════════════════════════════════════
# H6 mock 产物伪装注入 — reference: tests/test_mock_gate_no_fake_pass.py
# ═══════════════════════════════════════════════════════════════════════

H6_REFERENCE = (
    "H6 已有单测覆盖: tests/test_mock_gate_no_fake_pass.py "
    "(merge_gate/c_coverage_gate mock 报告不得当门禁通过证据)"
)


@pytest.mark.skip(reason=H6_REFERENCE)
def test_h6_mock_disguise_red():
    """mock 报告冒充真实证据 → merge_gate 红（已在 reference 覆盖）。"""
    raise AssertionError("unreachable — see test_mock_gate_no_fake_pass.py")


# ═══════════════════════════════════════════════════════════════════════
# H7 security 假 skip 注入 — reference: tests/test_security.py（T10 已修）
# ═══════════════════════════════════════════════════════════════════════

H7_REFERENCE = (
    "H7 已有单测覆盖: tests/test_security.py (T10 修复 — 假 skip 改真实模块, "
    "35 passed; 回归由该文件锁定)"
)


@pytest.mark.skip(reason=H7_REFERENCE)
def test_h7_security_fake_skip_red():
    """import 不存在的模块 → 永远 skip 被检测（已在 reference 覆盖）。"""
    raise AssertionError("unreachable — see test_security.py")


# ═══════════════════════════════════════════════════════════════════════
# H8 报告数字不一致注入 — total_violations 与 violations_raw 不一致 → 红
# ═══════════════════════════════════════════════════════════════════════


class TestH8NumberInconsistency:
    def test_total_mismatch_raw_red(self, tmp_path):
        """total_violations 与 violations_raw 长度不一致 → 红。"""
        proj = _mkproj(tmp_path)
        report_path = proj / ".yuleosh" / "reports" / "misra-report.json"
        data = json.loads(report_path.read_text())
        data["total_violations"] = 99  # 注入不一致
        report_path.write_text(json.dumps(data))
        status, msgs = check_misra_consistency(str(proj))
        assert status == "failed", f"数字不一致必须红，实际 {status}: {msgs}"
        assert "total_violations" in " ".join(msgs)

    def test_groups_count_mismatch_raw_red(self, tmp_path):
        """groups 计数与 raw 不一致 → 红。"""
        proj = _mkproj(tmp_path)
        report_path = proj / ".yuleosh" / "reports" / "misra-report.json"
        data = json.loads(report_path.read_text())
        data["groups"]["Rule 10.1"]["count"] = 7  # 注入不一致
        report_path.write_text(json.dumps(data))
        status, msgs = check_misra_consistency(str(proj))
        assert status == "failed", msgs

    def test_consistent_green(self, tmp_path):
        """一致报告 → 绿。"""
        proj = _mkproj(tmp_path)
        status, msgs = check_misra_consistency(str(proj))
        assert status == "passed", msgs

    def test_no_report_skips(self, tmp_path):
        """无 misra-report.json → skip。"""
        status, msgs = check_misra_consistency(str(tmp_path))
        assert status == "skipped", msgs


# ═══════════════════════════════════════════════════════════════════════
# 套件自绿：干净项目全绿 + 注入必红（任一注入不红 = 套件失败）
# ═══════════════════════════════════════════════════════════════════════


class TestSuiteSelfConsistency:
    def test_clean_project_all_green(self, tmp_path):
        """干净项目跑完整门禁 → 无 failed（passed/skipped 均可）。"""
        proj = _mkproj(tmp_path)
        _fresh_layer_result(proj, age_days=0)
        (proj / ".osh" / "evidence" / "review.json").write_text(
            json.dumps({"type": "review", "status": "passed",
                        "title": "t", "details": "d", "verdict": "approved"})
        )
        assert run_honesty_gate(str(proj)) is True

    def test_every_injection_turns_red(self, tmp_path):
        """四种注入各自让对应门禁红（防假绿复发的核心不变量）。"""
        # 1) 空报告
        proj = _mkproj(tmp_path)
        (proj / ".osh" / "evidence" / "review.json").write_text(
            json.dumps({"type": "review", "status": "passed"})
        )
        assert check_empty_evidence(str(proj))[0] == "failed"

        # 2) 缺失产物
        proj2 = _mkproj(tmp_path, with_misra_report=False, name="proj2")
        assert check_missing_artifacts(str(proj2))[0] == "failed"

        # 3) 过期时间戳
        proj3 = _mkproj(tmp_path, name="proj3")
        _fresh_layer_result(proj3, age_days=45)
        assert check_result_freshness(str(proj3), max_age_days=30)[0] == "failed"

        # 4) 数字不一致
        proj4 = _mkproj(tmp_path, name="proj4")
        rp = proj4 / ".yuleosh" / "reports" / "misra-report.json"
        d = json.loads(rp.read_text())
        d["total_violations"] = 12345
        rp.write_text(json.dumps(d))
        assert check_misra_consistency(str(proj4))[0] == "failed"


class TestHonestyGateCli:
    """CLI 级验证：注入后 `python -m yuleosh.ci.honesty_gate` 退出码非 0。"""

    _ROOT = str(pathlib.Path(__file__).resolve().parent.parent)

    def _run_cli(self, proj):
        return subprocess.run(
            [sys.executable, "-m", "yuleosh.ci.honesty_gate", str(proj)],
            capture_output=True, text=True, timeout=60,
            cwd=self._ROOT,
            env={"PYTHONPATH": pathlib.Path(self._ROOT, "src").as_posix(),
                 **{k: v for k, v in __import__("os").environ.items()
                    if k not in ("PYTHONPATH",)}},
        )

    def test_cli_exit_code_red_on_injection(self, tmp_path):
        """`python -m yuleosh.ci.honesty_gate` 注入后退出码非 0。"""
        proj = _mkproj(tmp_path)
        (proj / ".osh" / "evidence" / "review.json").write_text(
            json.dumps({"type": "review", "status": "passed"})
        )
        _fresh_layer_result(proj, age_days=60)
        result = self._run_cli(proj)
        assert result.returncode != 0, f"注入后 CLI 必须红:\n{result.stdout}"

    def test_cli_exit_code_zero_on_clean(self, tmp_path):
        """干净项目 CLI 退出码 0。"""
        proj = _mkproj(tmp_path)
        _fresh_layer_result(proj, age_days=0)
        result = self._run_cli(proj)
        assert result.returncode == 0, result.stdout


# ═══════════════════════════════════════════════════════════════════════
# H9 diff 假 skip 注入 — 方向2 (2026-08-11)
# ═══════════════════════════════════════════════════════════════════════
# 攻击向量: diff planner 报告「跳过 X 步骤」，但该步骤实际需要跑
# （文件 glob 误声明 / 空 diff 全跳过 / 跨切面步骤被裁剪）→ 必须红。
# 对应 tests/test_diff_planner.py 的 G1/G3/G5 门槛。


class TestH9FakeSkipInjection:
    def test_fake_skip_block_gate_red(self):
        """注入: block 级门禁被 plan_skips 裁剪 → 必须红。

        review-critical-safety 在 DEFAULT_GATE_POLICY 是 block。
        若 plan_skips 错误地把它裁掉（G5 失效），就是假 skip → 红。
        """
        from yuleosh.ci.diff_planner import plan_skips
        from yuleosh.ci.gate_policy import DEFAULT_GATE_POLICY

        steps = [
            ("review-critical-safety", "小明", "P0 GATE", lambda s: ""),
            ("review-linker", "小克", "链接脚本审查", lambda s: ""),
        ]
        # 空 diff → G1 fail-safe 应不裁剪；若裁剪了任何 block 步骤 = 假 skip
        decisions = plan_skips(steps, [], gate_policy=DEFAULT_GATE_POLICY)
        assert decisions == [], f"H9: 空 diff 不应裁剪任何步骤，实际 {decisions}"

    def test_fake_skip_cross_cutting_red(self):
        """注入: 跨切面步骤被 plan_skips 裁剪 → 必须红。"""
        from yuleosh.ci.diff_planner import CROSS_CUTTING_STEPS, plan_skips

        steps = [
            ("final-report", "小明", "最终报告", lambda s: ""),
            ("merge-gate", "小马", "Merge Gate", lambda s: ""),
            ("review-linker", "小克", "链接脚本审查", lambda s: ""),
        ]
        # 任意 diff —— 跨切面步骤永不裁剪
        decisions = plan_skips(steps, ["src/main.c"], gate_policy={})
        skipped = {d.step_key for d in decisions}
        for step in ["final-report", "merge-gate"]:
            assert step not in skipped, (
                f"H9: 跨切面步骤 {step} 被裁剪！CROSS_CUTTING_STEPS 含: {CROSS_CUTTING_STEPS}"
            )

    def test_fake_skip_invalid_glob_red(self):
        """注入: 需要跑的步骤被错误 glob 裁剪 → 必须红。

        review-linker 关心 *.ld，src/main.c 变更不应裁剪它触发的审查链
        （链接布局影响内存安全——跨切面交叉影响）。
        """
        from yuleosh.ci.diff_planner import plan_skips

        steps = [
            ("review-linker", "小克", "链接脚本审查", lambda s: ""),
        ]
        # 变更 .ld 文件 → review-linker 必须保留
        decisions = plan_skips(steps, ["linker/STM32F4.ld"], gate_policy={})
        assert decisions == [], f"H9: .ld 变更不应裁剪 review-linker，实际 {decisions}"

    def test_fake_skip_non_git_red(self):
        """注入: 非 git checkout 返回空 → plan_skips 不裁剪（G1 fail-safe）。"""
        from yuleosh.ci.diff_planner import collect_changed_files, plan_skips

        # 非 git 目录
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            changed = collect_changed_files(tmp)
            assert changed == [], "非 git checkout 必须返回空（fail-safe）"
            steps = [("review-linker", "小克", "链接脚本审查", lambda s: "")]
            decisions = plan_skips(steps, changed, gate_policy={})
            assert decisions == [], "非 git checkout 不得裁剪任何步骤"
