#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for yuleosh.pipeline.step_handlers.review_power — low-power / energy review."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.review_power import (
    step_review_power,
    _find_power_relevant_files,
    _check_wfi_wfe_usage,
    _check_sleep_on_exit,
    _check_clock_gating,
    _check_low_power_modes,
    _check_power_regulator,
    _check_wakeup_sources,
    _check_dvfs,
    _check_peripheral_power_management,
    _static_power_review,
    _build_power_review_prompt,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_session(tmp_path):
    """Build a minimal PipelineSession with a temp project structure."""
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text("# Test Spec\n## Requirements\nPWR-001: shall support sleep modes\n")
    session = PipelineSession(
        name="test-power",
        spec_path=str(spec_file),
    )
    session.session_dir = tmp_path / ".osh" / "sessions" / "test-power"
    session.session_dir.mkdir(parents=True, exist_ok=True)
    session.token_usage_total = 0
    session.token_usage_steps = []
    return session


def _fake_llm_result(content="# Power Review\n\n## Summary\n\nLow-power OK.",
                      total_tokens=300,
                      prompt_tokens=150) -> dict:
    return {
        "content": content,
        "usage": {
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": total_tokens - prompt_tokens,
        },
        "model": "test-model",
    }


# =============================================================================
# Unit tests — helper functions
# =============================================================================

class TestFindPowerRelevantFiles:
    """Tests for _find_power_relevant_files — power-related file discovery."""

    def test_finds_c_files_with_power_keywords(self, tmp_path):
        """GIVEN a project with C files containing power-related keywords
           WHEN _find_power_relevant_files runs
           THEN it returns those files in c_source."""
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "power.c").write_text('void idle(void) { __WFI(); }\n')
        (src / "main.c").write_text('int main(void) { return 0; }\n')  # no keywords

        categories = _find_power_relevant_files(tmp_path)
        assert len(categories["c_source"]) == 1
        assert "power.c" in str(categories["c_source"][0])

    def test_finds_header_files(self, tmp_path):
        """GIVEN header files with power keywords
           WHEN _find_power_relevant_files runs
           THEN they appear in the header category."""
        (tmp_path / "pwr_config.h").write_text('#define PWR_SLEEP_ON_EXIT\n')
        categories = _find_power_relevant_files(tmp_path)
        assert len(categories["header"]) >= 1

    def test_finds_config_files(self, tmp_path):
        """GIVEN config files with power-related names
           WHEN _find_power_relevant_files runs
           THEN they appear in the config category."""
        (tmp_path / "board.ioc").write_text("some content\n")
        categories = _find_power_relevant_files(tmp_path)
        assert len(categories["config"]) >= 1

    def test_empty_project(self, tmp_path):
        """GIVEN an empty project
           WHEN _find_power_relevant_files runs
           THEN all categories are empty."""
        categories = _find_power_relevant_files(tmp_path)
        assert sum(len(v) for v in categories.values()) == 0


class TestCheckWfiWfeUsage:
    """Tests for _check_wfi_wfe_usage — WFI/WFE instruction detection."""

    def test_no_wfi_wfe(self):
        """GIVEN source content with no WFI or WFE
           WHEN _check_wfi_wfe_usage runs
           THEN it returns a 'major' finding about busy-wait."""
        contents = {"main.c": "int main(void) { while(1); }\n"}
        findings = _check_wfi_wfe_usage(contents)
        majors = [f for f in findings if f["severity"] == "major"]
        assert len(majors) >= 1
        assert "No WFI or WFE" in majors[0]["message"]

    def test_wfi_in_idle_loop(self):
        """GIVEN source with WFI in an idle loop
           WHEN _check_wfi_wfe_usage runs
           THEN it reports WFI used in idle — good practice."""
        contents = {"main.c": "void idle(void) { while (1) { WFI(); } }\n"}
        findings = _check_wfi_wfe_usage(contents)
        infos = [f for f in findings if f["severity"] == "info"]
        good_findings = [f for f in infos if "good power-saving" in f["message"]]
        assert len(good_findings) >= 1

    def test_wfi_and_hal_pwr(self):
        """GIVEN files with both HAL_PWR and WFI
           WHEN _check_wfi_wfe_usage runs
           THEN it reports sleep-on-exit or sleep-now mode usage."""
        contents = {"power.c": "HAL_PWR_EnterSLEEPMode();\nvoid idle(void) { while (1) { WFI(); } }\n"}
        findings = _check_wfi_wfe_usage(contents)
        hal_infos = [f for f in findings if "HAL_PWR and WFI" in f.get("message", "")]
        assert len(hal_infos) >= 1

    def test_wfe_detected(self):
        """GIVEN source with WFE usage
           WHEN _check_wfi_wfe_usage runs
           THEN WFE-related findings are included."""
        contents = {"event.c": "void wait_event(void) { while (1) { WFE(); } }\n"}
        findings = _check_wfi_wfe_usage(contents)
        wfe_findings = [f for f in findings if "WFE event wait" in f.get("message", "")]
        assert len(wfe_findings) >= 1


class TestCheckSleepOnExit:
    """Tests for _check_sleep_on_exit — SLEEPONEXIT configuration."""

    def test_sleep_on_exit_detected(self, tmp_path):
        """GIVEN content with SLEEPONEXIT reference
           WHEN _check_sleep_on_exit runs
           THEN it returns an info finding."""
        content = "SCB->SCR |= SCB_SCR_SLEEPONEXIT;\n"
        f = tmp_path / "startup.c"
        findings = _check_sleep_on_exit(content, f)
        assert len(findings) >= 1
        assert findings[0]["category"] == "sleep_mode"

    def test_deep_sleep_detected(self, tmp_path):
        """GIVEN content with DEEPSLEEP reference
           WHEN _check_sleep_on_exit runs
           THEN it reports deep sleep mode."""
        content = "SCB->SCR |= SCB_SCR_DEEPSLEEP;\n"
        f = tmp_path / "startup.c"
        findings = _check_sleep_on_exit(content, f)
        deep_findings = [f for f in findings if "Deep sleep" in f["message"]]
        assert len(deep_findings) >= 1

    def test_no_sleep_config(self, tmp_path):
        """GIVEN content with no sleep config
           WHEN _check_sleep_on_exit runs
           THEN no findings are returned."""
        content = "int main(void) { return 0; }\n"
        f = tmp_path / "main.c"
        findings = _check_sleep_on_exit(content, f)
        assert len(findings) == 0


class TestCheckClockGating:
    """Tests for _check_clock_gating — clock gate detection."""

    def test_detects_enabled_gates(self):
        """GIVEN content with __HAL_RCC_*_CLK_ENABLE macros
           WHEN _check_clock_gating runs
           THEN it reports enabled clock gates."""
        contents = {"main.c": "__HAL_RCC_USART1_CLK_ENABLE();\n__HAL_RCC_GPIOA_CLK_ENABLE();\n"}
        findings = _check_clock_gating(contents)
        enabled_findings = [f for f in findings if "Clock gates enabled" in f.get("message", "")]
        assert len(enabled_findings) >= 1

    def test_detects_disabled_gates(self):
        """GIVEN content with __HAL_RCC_*_CLK_DISABLE macros
           WHEN _check_clock_gating runs
           THEN it reports disabled clock gates."""
        contents = {"main.c": "__HAL_RCC_USART1_CLK_DISABLE();\n"}
        findings = _check_clock_gating(contents)
        disabled = [f for f in findings if "disabled" in f.get("message", "").lower()
                     and "Clock gates" in f.get("message", "")]
        assert len(disabled) >= 1

    def test_no_disable_macros(self):
        """GIVEN content with no disable macros
           WHEN _check_clock_gating runs
           THEN it returns a 'minor' finding suggesting clock disable."""
        contents = {"main.c": "int main(void) { return 0; }\n"}
        findings = _check_clock_gating(contents)
        minors = [f for f in findings if f["severity"] == "minor"]
        assert len(minors) >= 1
        assert "CLK_DISABLE" in minors[0]["message"]


class TestCheckLowPowerModes:
    """Tests for _check_low_power_modes — sleep/stop/standby detection."""

    def test_detects_sleep_mode(self):
        """GIVEN content with HAL_PWR_EnterSLEEPMode
           WHEN _check_low_power_modes runs
           THEN it reports SLEEP mode usage."""
        contents = {"power.c": "HAL_PWR_EnterSLEEPMode(PWR_MAINREGULATOR_ON, PWR_SLEEPENTRY_WFI);\n"}
        findings = _check_low_power_modes(contents)
        modes = [f for f in findings if "Low-power modes configured" in f.get("message", "")]
        assert len(modes) >= 1
        assert "SLEEP" in modes[0]["message"]

    def test_no_low_power_mode(self):
        """GIVEN content with no power mode entries
           WHEN _check_low_power_modes runs
           THEN it returns a 'major' finding."""
        contents = {"main.c": "int main(void) { return 0; }\n"}
        findings = _check_low_power_modes(contents)
        majors = [f for f in findings if f["severity"] == "major"]
        assert len(majors) >= 1

    def test_standby_without_wakeup(self):
        """GIVEN content with STANDBY mode but no wake-up source
           WHEN _check_low_power_modes runs
           THEN it returns a 'critical' finding."""
        contents = {"power.c": "HAL_PWR_EnterSTANDBYMode();\n"}
        findings = _check_low_power_modes(contents)
        criticals = [f for f in findings if f["severity"] == "critical"]
        assert len(criticals) >= 1
        assert "STANDBY" in criticals[0]["message"]


class TestCheckPowerRegulator:
    """Tests for _check_power_regulator — voltage scaling detection."""

    def test_detects_voltage_scaling(self, tmp_path):
        """GIVEN content with PWR_REGULATOR_VOLTAGE_SCALE references
           WHEN _check_power_regulator runs
           THEN it reports regulator scaling."""
        content = "HAL_PWREx_ConfigVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1);\n"
        f = tmp_path / "power.c"
        findings = _check_power_regulator(content, f)
        assert len(findings) >= 1
        assert "Regulator voltage scaling" in findings[0]["message"]

    def test_basic_pwr_config(self, tmp_path):
        """GIVEN content with PVD/PVMO config but no scaling
           WHEN _check_power_regulator runs
           THEN it reports basic PWR config."""
        content = "HAL_PWR_ConfigPVD(&pvdConfig);\n"
        f = tmp_path / "power.c"
        findings = _check_power_regulator(content, f)
        basic = [f for f in findings if "Basic PWR configuration" in f.get("message", "")]
        assert len(basic) >= 1


class TestCheckWakeupSources:
    """Tests for _check_wakeup_sources — wake-up configuration detection."""

    def test_detects_rtc_wakeup(self):
        """GIVEN content with RTC wake-up references
           WHEN _check_wakeup_sources runs
           THEN it reports RTC as a wake-up source."""
        contents = {"rtc.c": "HAL_RTCEx_SetWakeUpTimer(&hrtc, 5000, RTC_WAKEUPCLOCK_CK_SPRE_16);\n"}
        findings = _check_wakeup_sources(contents)
        sources = [f for f in findings if "Wake-up sources" in f.get("message", "")]
        assert len(sources) >= 1
        assert "RTC" in sources[0]["message"]

    def test_no_wakeup_detected(self):
        """GIVEN content with no wake-up references
           WHEN _check_wakeup_sources runs
           THEN it reports no explicit wake-up source."""
        contents = {"main.c": "int main(void) { return 0; }\n"}
        findings = _check_wakeup_sources(contents)
        assert len(findings) >= 1
        assert "no explicit" in findings[0]["message"].lower()


class TestCheckDvfs:
    """Tests for _check_dvfs — DVFS detection."""

    def test_detects_dvfs(self):
        """GIVEN content with DVFS keyword
           WHEN _check_dvfs runs
           THEN it reports DVFS configuration."""
        contents = {"power.c": "// DVFS (Dynamic Voltage and Frequency Scaling) enabled\n"}
        findings = _check_dvfs(contents)
        dvfs_findings = [f for f in findings if "DVFS" in f.get("message", "")]
        assert len(dvfs_findings) >= 1

    def test_detects_freq_scaling(self):
        """GIVEN content with SystemCoreClockUpdate call
           WHEN _check_dvfs runs
           THEN it reports potential DVFS-like behavior."""
        contents = {"clock.c": "void set_freq(void) { SystemCoreClockUpdate(); }\n"}
        findings = _check_dvfs(contents)
        scaling = [f for f in findings if "frequency changes" in f.get("message", "")]
        assert len(scaling) >= 1

    def test_detects_msi(self):
        """GIVEN content with MSI reference
           WHEN _check_dvfs runs
           THEN it reports MSI oscillator usage."""
        contents = {"clock.c": "MSI_RANGE = RCC_MSIRANGE_6;\n"}
        findings = _check_dvfs(contents)
        msi_findings = [f for f in findings if "MSI oscillator" in f.get("message", "")]
        assert len(msi_findings) >= 1

    def test_no_dvfs(self):
        """GIVEN content with no DVFS or freq scaling
           WHEN _check_dvfs runs
           THEN it reports fixed frequency."""
        contents = {"main.c": "int main(void) { return 0; }\n"}
        findings = _check_dvfs(contents)
        fixed = [f for f in findings if "fixed frequency" in f.get("message", "")]
        assert len(fixed) >= 1


class TestCheckPeripheralPowerManagement:
    """Tests for _check_peripheral_power_management — peripheral power patterns."""

    def test_init_without_deinit(self):
        """GIVEN content with HAL init calls but no deinit
           WHEN _check_peripheral_power_management runs
           THEN it reports peripherals running continuously."""
        contents = {"main.c": "void setup(void) { HAL_UART_Init(&huart); HAL_SPI_Init(&hspi); }\n"}
        findings = _check_peripheral_power_management(contents)
        init_msgs = [f for f in findings if "peripherals initialized" in f.get("message", "")]
        assert len(init_msgs) >= 1

    def test_low_power_apis(self):
        """GIVEN content with HAL low-power API calls
           WHEN _check_peripheral_power_management runs
           THEN it reports low-power API usage."""
        contents = {"main.c": "HAL_UARTEx_EnableStopMode(&huart);\n"}
        findings = _check_peripheral_power_management(contents)
        lp_api = [f for f in findings if "low-power APIs" in f.get("message", "")]
        assert len(lp_api) >= 1

    def test_pwr_macros(self):
        """GIVEN content with __HAL_PWR_ macros
           WHEN _check_peripheral_power_management runs
           THEN it reports low-power macro usage."""
        contents = {"main.c": "__HAL_PWR_CLEAR_FLAG(PWR_FLAG_SB);\n"}
        findings = _check_peripheral_power_management(contents)
        macro_findings = [f for f in findings if "low-power control macro" in f.get("message", "")]
        assert len(macro_findings) >= 1


class TestStaticPowerReview:
    """Tests for _static_power_review — orchestrator of static power checks."""

    def test_empty_project(self, tmp_path):
        """GIVEN an empty project
           WHEN _static_power_review runs
           THEN it returns a 'major' discovery finding."""
        findings = _static_power_review(tmp_path)
        majors = [f for f in findings if f["severity"] == "major"]
        assert len(majors) >= 1
        assert any("No power-management" in f["message"] for f in findings)

    def test_with_power_files(self, tmp_path):
        """GIVEN a project with power-related files
           WHEN _static_power_review runs
           THEN it returns findings from multiple check modules."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "power.c").write_text(
            'void idle(void) { while(1) { __WFI(); } }\n'
            '__HAL_RCC_GPIOA_CLK_ENABLE();\n'
            'HAL_PWR_EnterSLEEPMode(PWR_MAINREGULATOR_ON, PWR_SLEEPENTRY_WFI);\n'
            'HAL_RTCEx_SetWakeUpTimer(&hrtc, 5000, RTC_WAKEUPCLOCK_CK_SPRE_16);\n'
        )
        findings = _static_power_review(tmp_path)
        categories = set(f["category"] for f in findings)
        assert "wfi_wfe" in categories
        assert "low_power_mode" in categories

    def test_no_power_keywords(self, tmp_path):
        """GIVEN a project with files that have no power keywords
           WHEN _static_power_review runs
           THEN it returns the discovery finding."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.c").write_text('int main(void) { return 0; }\n')
        findings = _static_power_review(tmp_path)
        majors = [f for f in findings if f["severity"] == "major"]
        assert len(majors) >= 1


class TestBuildPowerReviewPrompt:
    """Tests for _build_power_review_prompt — LLM prompt construction."""

    def test_returns_prompts(self, tmp_path):
        """GIVEN files with power-related content
           WHEN _build_power_review_prompt runs
           THEN it returns system_prompt and user_prompt strings."""
        (tmp_path / "power.c").write_text(
            'void idle(void) { __WFI(); }\n'
        )
        files = {"c_source": [tmp_path / "power.c"], "header": [], "config": []}
        system_prompt, user_prompt = _build_power_review_prompt(files)
        assert isinstance(system_prompt, str)
        assert len(system_prompt) > 50
        assert isinstance(user_prompt, str)


# =============================================================================
# Integration tests — step_review_power
# =============================================================================

class TestStepReviewPower:
    """Test suite for step_review_power — the pipeline step handler."""

    # ── Happy path ──────────────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_power._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_power.os.environ")
    def test_happy_path(self, mock_environ, mock_call_llm, mock_session, tmp_path):
        """GIVEN a valid session with power-related source files
           WHEN step_review_power runs
           THEN it writes a JSON report and returns the output path."""
        mock_environ.get.return_value = str(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "power.c").write_text(
            'void idle(void) { while(1) { __WFI(); } }\n'
            'HAL_PWR_EnterSLEEPMode(PWR_MAINREGULATOR_ON, PWR_SLEEPENTRY_WFI);\n'
        )
        mock_call_llm.return_value = _fake_llm_result()

        result = step_review_power(mock_session)

        out_path = Path(result)
        assert out_path.exists()
        assert out_path.name == "power-review.json"
        report = json.loads(out_path.read_text())
        assert report["step"] == "review-power"
        assert report["reviewer"] == "小克"
        assert "status" in report
        assert "static_findings" in report
        assert "llm_review" in report

    # ── LLM call fails (non-fatal) ──────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_power._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_power.os.environ")
    def test_llm_failure_is_non_fatal(self, mock_environ, mock_call_llm, mock_session, tmp_path):
        """GIVEN LLM call raises an exception
           WHEN step_review_power runs
           THEN it still succeeds with llm_review set to error message."""
        mock_environ.get.return_value = str(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "power.c").write_text('void idle(void) { __WFI(); }\n')
        mock_call_llm.side_effect = RuntimeError("LLM down")

        result = step_review_power(mock_session)
        report = json.loads(Path(result).read_text())
        assert "(LLM-powered review unavailable)" in report["llm_review"]

    # ── Token usage tracked ─────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_power._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_power.os.environ")
    def test_token_usage_tracked(self, mock_environ, mock_call_llm, mock_session, tmp_path):
        """GIVEN LLM returns usage info
           WHEN step_review_power completes
           THEN session token totals are updated."""
        mock_environ.get.return_value = str(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "power.c").write_text('void idle(void) { __WFI(); }\n')
        mock_call_llm.return_value = _fake_llm_result(total_tokens=350)

        step_review_power(mock_session)

        assert mock_session.token_usage_total > 0
        steps = [s for s in mock_session.token_usage_steps if s["step"] == "review-power"]
        assert len(steps) == 1
        assert steps[0]["usage"]["total_tokens"] == 350

    # ── Status determination ────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_power._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_power.os.environ")
    def test_critical_finding_triggers_failed(self, mock_environ, mock_call_llm,
                                               mock_session, tmp_path):
        """GIVEN a finding with 'critical' severity
           WHEN step_review_power runs
           THEN overall status is 'failed'."""
        mock_environ.get.return_value = str(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        # STANDBY without wakeup triggers critical
        (src / "power.c").write_text(
            'void enter_standby(void) { HAL_PWR_EnterSTANDBYMode(); }\n'
        )
        mock_call_llm.return_value = _fake_llm_result()

        result = step_review_power(mock_session)
        report = json.loads(Path(result).read_text())
        assert report["status"] == "failed"

    # ── Output write error ──────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_power._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_power.os.environ")
    def test_output_write_error_raises(self, mock_environ, mock_call_llm, mock_session, tmp_path):
        """GIVEN output file cannot be written
           WHEN step_review_power runs
           THEN it raises PipelineStepError."""
        mock_environ.get.return_value = str(tmp_path)
        mock_call_llm.return_value = _fake_llm_result()
        import shutil
        shutil.rmtree(mock_session.session_dir)
        mock_session.session_dir.write_text("not_a_dir")

        with pytest.raises(PipelineStepError, match="Cannot write"):
            step_review_power(mock_session)

    # ── No power files ──────────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_power._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_power.os.environ")
    def test_no_power_files(self, mock_environ, mock_call_llm, mock_session, tmp_path):
        """GIVEN a project with no power-relevant files
           WHEN step_review_power runs
           THEN it succeeds with major discovery finding and LLM review is empty."""
        mock_environ.get.return_value = str(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.c").write_text('int main(void) { return 0; }\n')
        mock_call_llm.return_value = _fake_llm_result()

        result = step_review_power(mock_session)
        report = json.loads(Path(result).read_text())
        assert "static_findings" in report
        # No power files → LLM review block not entered → llm_review is empty string
        assert report["llm_review"] == ""
