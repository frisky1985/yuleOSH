"""AUD-ASPICE-001 B1 回归：门禁严格化。

覆盖：
* NC-05 架构评审的确定性漂移检查（HAL 缺失 / AUTOSAR 过度设计）
* F-01 覆盖率门禁的「已部署代码 + 构建定义」判定

撤销对应修复（删除 ``_deterministic_drift_findings``、把 ``artifacts`` 从
``_SKIP_DIRS`` 移除）后，本文件的用例会失败。
"""

# @tests src/yuleosh/pipeline/step_handlers/review_arch.py, src/yuleosh/pipeline/step_handlers/c_coverage_gate.py

from pathlib import Path

from yuleosh.pipeline.step_handlers.c_coverage_gate import (
    _asil_level,
    _asil_policy,
    _has_build_definition,
    _has_c_sources,
)
from yuleosh.pipeline.step_handlers.review_arch import (
    _deterministic_drift_findings,
    _mentions_hal,
)


class TestHalDetection:
    def test_shall_does_not_look_like_hal(self):
        """``\\bhal\\b`` 防止 "shall" 被误判为 HAL。"""
        assert _mentions_hal("The system SHALL blink every second.") is False

    def test_hal_tokens_are_detected(self):
        assert _mentions_hal("硬件访问必须通过 HAL 抽象层") is True
        assert _mentions_hal("HAL layer isolates register access") is True


class TestArchDeterministicDrift:
    SPEC = (
        "# LED\n\n## 1. System Requirements\n\n### SR-001\n"
        "- 硬件访问必须通过 HAL 抽象层\n- 周期 1000 ms\n"
    )

    def test_missing_hal_in_architecture_is_major(self):
        arch = "# 架构\n\n模块: main, timer\n"
        findings = _deterministic_drift_findings(self.SPEC, arch)
        rules = {f["rule"] for f in findings}
        assert "ARCH-DRIFT-HAL" in rules
        assert all(f["severity"] == "major" for f in findings)

    def test_autosar_overreach_without_spec_requirement(self):
        arch = (
            "# 架构\n\n使用 HAL 层。\n"
            "组件: LedSwc, Rte_Led, SchM, BSW\n"
        )
        findings = _deterministic_drift_findings(self.SPEC, arch)
        rules = {f["rule"] for f in findings}
        assert "ARCH-DRIFT-AUTOSAR" in rules
        assert "ARCH-DRIFT-HAL" not in rules

    def test_aligned_architecture_has_no_findings(self):
        arch = "# 架构\n\nHAL 层: hal_led_toggle()\n周期 1000 ms\n"
        assert _deterministic_drift_findings(self.SPEC, arch) == []

    def test_empty_inputs_produce_no_findings(self):
        assert _deterministic_drift_findings("", "# arch\nHAL\n") == []
        assert _deterministic_drift_findings(self.SPEC, "") == []


class TestCoverageGateApplicability:
    def test_artifacts_staging_source_is_not_deployed_code(self, tmp_path):
        """codegen 暂存区的 .c 不算工程代码 (RUN-A hard-fail 根因)。"""
        staging = tmp_path / "artifacts" / "generated-code" / "x" / "src"
        staging.mkdir(parents=True)
        (staging / "SchM.c").write_text("int main(void){return 0;}\n")
        assert _has_c_sources(str(tmp_path)) is False

    def test_deployed_source_is_detected(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "led.c").write_text("int led(void){return 0;}\n")
        assert _has_c_sources(str(tmp_path)) is True

    def test_build_definition_requires_root_cmakelists(self, tmp_path):
        assert _has_build_definition(str(tmp_path)) is False
        (tmp_path / "CMakeLists.txt").write_text("project(x C)\n")
        assert _has_build_definition(str(tmp_path)) is True

    def test_makefile_is_not_a_coverage_build_definition(self, tmp_path):
        """覆盖率门禁只会跑 cmake；Makefile-only 工程必须 skip 而非 hard-fail。"""
        (tmp_path / "Makefile").write_text("all:\n\tgcc -o x x.c\n")
        assert _has_build_definition(str(tmp_path)) is False


class TestAsilCoveragePolicy:
    """NC-06：ASIL 分级覆盖率阈值。"""

    def test_default_level_is_qm(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OSH_ASIL_LEVEL", raising=False)
        assert _asil_level(str(tmp_path)) == "QM"
        assert _asil_policy(str(tmp_path)) == (80.0, 70.0)

    def test_env_override_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_ASIL_LEVEL", "ASIL-B")
        assert _asil_level(str(tmp_path)) == "ASIL-B"
        assert _asil_policy(str(tmp_path)) == (100.0, 100.0)

    def test_bare_letter_is_normalised(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_ASIL_LEVEL", "a")
        assert _asil_level(str(tmp_path)) == "ASIL-A"
        assert _asil_policy(str(tmp_path)) == (100.0, 90.0)

    def test_yaml_config_is_honoured(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OSH_ASIL_LEVEL", raising=False)
        (tmp_path / ".yuleosh.yaml").write_text("asil_level: ASIL-C\n")
        assert _asil_level(str(tmp_path)) == "ASIL-C"
        assert _asil_policy(str(tmp_path)) == (100.0, 100.0)

    def test_unknown_level_falls_back_to_qm(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_ASIL_LEVEL", "SIL-9")
        assert _asil_level(str(tmp_path)) == "QM"
