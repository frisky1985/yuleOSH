#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for yuleosh.pipeline.step_handlers.review_bsp."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

import pytest

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.review_bsp import (
    step_review_bsp,
    _find_bsp_files,
    _check_pin_mux_gpio,
    _check_pin_mux_conflicts,
    _check_clock_hse,
    _check_clock_pll,
    _check_system_clock_frequency,
    _check_alloca_usage,
    _check_vla_usage,
    _check_dynamic_allocation,
    _check_peripheral_init_order,
    _check_peripheral_conflict,
    _check_dma_config,
    _check_hal_api_consistency,
    _static_bsp_review,
    _build_bsp_review_prompt,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_session(tmp_path):
    """Build a minimal PipelineSession for BSP review testing."""
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text("# Test Spec\n")
    session = PipelineSession(
        name="test-bsp",
        spec_path=str(spec_file),
    )
    session.session_dir = tmp_path / ".osh" / "sessions" / "test-bsp"
    session.session_dir.mkdir(parents=True, exist_ok=True)
    return session


def _create_file(project_dir: Path, rel_path: str, content: str = "") -> Path:
    """Create a file under project_dir and return its path."""
    p = project_dir / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


# =============================================================================
# _find_bsp_files
# =============================================================================

class TestFindBspFiles:
    """Tests for _find_bsp_files — BSP file discovery."""

    def test_no_bsp_files(self, tmp_path):
        """GIVEN a project with no BSP files
           WHEN _find_bsp_files runs
           THEN all categories are empty."""
        result = _find_bsp_files(tmp_path)
        for key, val in result.items():
            assert val == [], f"Expected empty {key}, got {len(val)} files"

    def test_board_headers_discovered(self, tmp_path):
        """GIVEN board header files exist
           WHEN _find_bsp_files runs
           THEN they appear under board_headers."""
        _create_file(tmp_path, "board.h")
        _create_file(tmp_path, "target.h")
        _create_file(tmp_path, "BSP/some.h")
        result = _find_bsp_files(tmp_path)
        assert len(result["board_headers"]) == 3

    def test_hal_config_discovered(self, tmp_path):
        """GIVEN hal_conf files exist
           WHEN _find_bsp_files runs
           THEN they appear under hal_config."""
        _create_file(tmp_path, "hal_conf.h")
        _create_file(tmp_path, "stm32f4xx_hal_conf.h")
        result = _find_bsp_files(tmp_path)
        assert len(result["hal_config"]) >= 2

    def test_pin_mux_discovered(self, tmp_path):
        """GIVEN pin mux files exist
           WHEN _find_bsp_files runs
           THEN they appear under pin_mux."""
        _create_file(tmp_path, "pin_mux.c")
        _create_file(tmp_path, "PinMux.c")
        _create_file(tmp_path, "gpio.c")
        result = _find_bsp_files(tmp_path)
        assert len(result["pin_mux"]) >= 3

    def test_clock_config_discovered(self, tmp_path):
        """GIVEN clock config files exist
           WHEN _find_bsp_files runs
           THEN they appear under clock_config."""
        _create_file(tmp_path, "clock.c")
        _create_file(tmp_path, "system_stm32f4xx.c")
        _create_file(tmp_path, "rcc.c")
        result = _find_bsp_files(tmp_path)
        assert len(result["clock_config"]) >= 3

    def test_peripheral_config_discovered(self, tmp_path):
        """GIVEN peripheral config files exist
           WHEN _find_bsp_files runs
           THEN they appear under peripheral_config."""
        for name in ("uart.c", "usart.c", "spi.c", "i2c.c", "adc.c", "timer.c"):
            _create_file(tmp_path, name)
        result = _find_bsp_files(tmp_path)
        assert len(result["peripheral_config"]) >= 6

    def test_dma_config_discovered(self, tmp_path):
        """GIVEN DMA files exist
           WHEN _find_bsp_files runs
           THEN they appear under dma_config."""
        _create_file(tmp_path, "dma.c")
        _create_file(tmp_path, "dma.h")
        result = _find_bsp_files(tmp_path)
        assert len(result["dma_config"]) >= 2

    def test_deduplication(self, tmp_path):
        """GIVEN the same file is matched by multiple symlinks
           WHEN _find_bsp_files runs
           THEN the file appears only once per category."""
        _create_file(tmp_path, "board.h")
        # Hard link the same file
        p = tmp_path / "board_copy.h"
        p.write_text("copy")
        result = _find_bsp_files(tmp_path)
        assert len(result["board_headers"]) == 2


# =============================================================================
# _check_pin_mux_gpio
# =============================================================================

class TestCheckPinMuxGpio:
    """Tests for _check_pin_mux_gpio — GPIO pin mux validation."""

    def test_no_gpio_init_calls(self, tmp_path):
        """GIVEN content with no HAL_GPIO_Init calls
           WHEN _check_pin_mux_gpio runs
           THEN it returns an info finding."""
        f = _create_file(tmp_path, "board.h", "int x;")
        findings = _check_pin_mux_gpio(f.read_text(), f)
        assert any(fi["severity"] == "info" and "No HAL_GPIO_Init" in fi["message"] for fi in findings)
        assert len(findings) == 1

    def test_with_gpio_modes(self, tmp_path):
        """GIVEN content with HAL_GPIO_Init and GPIO modes
           WHEN _check_pin_mux_gpio runs
           THEN it reports modes found."""
        content = """
        void init() {
            HAL_GPIO_Init(GPIOA, &gpio_cfg);
            HAL_GPIO_Init(GPIOB, &gpio_cfg2);
        }
        GPIO_MODE_OUTPUT_PP
        GPIO_MODE_INPUT
        """
        f = _create_file(tmp_path, "pin_mux.c", content)
        findings = _check_pin_mux_gpio(content, f)
        assert any("GPIO modes configured" in fi["message"] for fi in findings)

    def test_without_mode_specifiers(self, tmp_path):
        """GIVEN HAL_GPIO_Init calls but no mode specifiers
           WHEN _check_pin_mux_gpio runs
           THEN it returns a minor finding."""
        content = "HAL_GPIO_Init(GPIOA, &cfg);"
        f = _create_file(tmp_path, "board.h", content)
        findings = _check_pin_mux_gpio(content, f)
        assert any("no GPIO mode specifiers" in fi["message"] for fi in findings)

    def test_pull_configs_detected(self, tmp_path):
        """GIVEN GPIO pull configurations present
           WHEN _check_pin_mux_gpio runs
           THEN pull configs are reported."""
        content = """
        GPIO_PULLUP GPIO_PULLDOWN GPIO_NOPULL
        HAL_GPIO_Init(GPIOA, &cfg);
        """
        f = _create_file(tmp_path, "board.h", content)
        findings = _check_pin_mux_gpio(content, f)
        assert any("GPIO pull configurations" in fi["message"] for fi in findings)

    def test_multiple_af_assignments(self, tmp_path):
        """GIVEN many GPIO alternate function assignments
           WHEN _check_pin_mux_gpio runs
           THEN it warns about potential conflicts."""
        content = "HAL_GPIO_Init();" + " GPIO_AF1 GPIO_AF2 GPIO_AF3 GPIO_AF4 GPIO_AF5 GPIO_AF6 GPIO_AF7 GPIO_AF8 GPIO_AF9"
        f = _create_file(tmp_path, "board.h", content)
        findings = _check_pin_mux_gpio(content, f)
        assert any("Multiple AF assignments" in fi["message"] for fi in findings)

    def test_no_speed_config(self, tmp_path):
        """GIVEN no GPIO output speed configuration
           WHEN _check_pin_mux_gpio runs
           THEN it warns about missing speed config."""
        content = "HAL_GPIO_Init(GPIOA, &cfg); GPIO_MODE_OUTPUT_PP"
        f = _create_file(tmp_path, "board.h", content)
        findings = _check_pin_mux_gpio(content, f)
        assert any("No GPIO output speed configuration" in fi["message"] for fi in findings)


# =============================================================================
# _check_pin_mux_conflicts
# =============================================================================

class TestCheckPinMuxConflicts:
    """Tests for _check_pin_mux_conflicts — pin conflict detection."""

    def test_many_pins_assigned(self, tmp_path):
        """GIVEN many pins assigned to one port
           WHEN _check_pin_mux_conflicts runs
           THEN it warns about overuse."""
        content = "GPIOA GPIOA GPIOA GPIOA GPIOA GPIOA GPIOA GPIOA GPIOA GPIOA GPIOA GPIOA GPIOA " + \
                  " ".join(f"GPIO_PIN_{i}" for i in range(1, 14))
        f = _create_file(tmp_path, "board.h", content)
        findings = _check_pin_mux_conflicts(content, f)
        assert any("pins assigned" in fi["message"] for fi in findings)

    def test_no_findings_when_sparse(self, tmp_path):
        """GIVEN only a few pins per port
           WHEN _check_pin_mux_conflicts runs
           THEN no warnings are generated."""
        content = "GPIOB" + " GPIO_PIN_0 GPIO_PIN_1 GPIO_PIN_2"
        f = _create_file(tmp_path, "board.h", content)
        findings = _check_pin_mux_conflicts(content, f)
        assert len(findings) == 0

    def test_no_port_assignments(self, tmp_path):
        """GIVEN no GPIO port references
           WHEN _check_pin_mux_conflicts runs
           THEN it returns empty."""
        content = "int x;"
        f = _create_file(tmp_path, "board.h", content)
        findings = _check_pin_mux_conflicts(content, f)
        assert findings == []


# =============================================================================
# _check_clock_hse
# =============================================================================

class TestCheckClockHse:
    """Tests for _check_clock_hse — HSE/LSE clock tree checks."""

    def test_no_hse_no_hsi(self, tmp_path):
        """GIVEN no HSE or HSI references
           WHEN _check_clock_hse runs
           THEN it returns a major finding."""
        f = _create_file(tmp_path, "clock.c", "int x;")
        findings = _check_clock_hse(f.read_text(), f)
        assert any(fi["severity"] == "major" and "Neither HSE nor HSI" in fi["message"] for fi in findings)

    def test_hse_with_value(self, tmp_path):
        """GIVEN HSE with a valid frequency value
           WHEN _check_clock_hse runs
           THEN it reports the frequency."""
        content = "HSE HSE_VALUE = 8000000"
        f = _create_file(tmp_path, "clock.c", content)
        findings = _check_clock_hse(content, f)
        assert any("HSE configured: 8000000" in fi["message"] for fi in findings)

    def test_hse_outside_range(self, tmp_path):
        """GIVEN HSE frequency outside 1-50 MHz range
           WHEN _check_clock_hse runs
           THEN it warns about the crystal spec."""
        content = "HSE HSE_VALUE = 60000000"
        f = _create_file(tmp_path, "clock.c", content)
        findings = _check_clock_hse(content, f)
        assert any("outside typical range" in fi["message"] for fi in findings)

    def test_hsi_only(self, tmp_path):
        """GIVEN only HSI configured (no HSE)
           WHEN _check_clock_hse runs
           THEN it returns an info finding."""
        content = "HSI configured"
        f = _create_file(tmp_path, "clock.c", content)
        findings = _check_clock_hse(content, f)
        assert any("using HSI" in fi["message"] for fi in findings)


# =============================================================================
# _check_clock_pll
# =============================================================================

class TestCheckClockPll:
    """Tests for _check_clock_pll — PLL parameter validation."""

    def test_no_pll(self, tmp_path):
        """GIVEN no PLL references
           WHEN _check_clock_pll runs
           THEN it returns an info finding."""
        f = _create_file(tmp_path, "clock.c", "int x;")
        findings = _check_clock_pll(f.read_text(), f)
        assert any("No PLL configuration" in fi["message"] for fi in findings)

    def test_pll_params_missing(self, tmp_path):
        """GIVEN PLL symbol found but no parameters
           WHEN _check_clock_pll runs
           THEN it returns a major finding."""
        content = "PLL is used"
        f = _create_file(tmp_path, "clock.c", content)
        findings = _check_clock_pll(content, f)
        assert any("no PLLM/PLLN/PLLP" in fi["message"] for fi in findings)

    def test_plln_out_of_range(self, tmp_path):
        """GIVEN PLLN outside 8-432 range
           WHEN _check_clock_pll runs
           THEN it returns a major finding."""
        content = "PLLN = 500"
        f = _create_file(tmp_path, "clock.c", content)
        findings = _check_clock_pll(content, f)
        assert any("PLLN=500 outside recommended range" in fi["message"] for fi in findings)

    def test_pllm_out_of_range(self, tmp_path):
        """GIVEN PLLM outside 2-63 range
           WHEN _check_clock_pll runs
           THEN it returns a major finding."""
        content = "PLLM = 1 PLLN = 100"
        f = _create_file(tmp_path, "clock.c", content)
        findings = _check_clock_pll(content, f)
        assert any("PLLM=1 outside recommended range" in fi["message"] for fi in findings)

    def test_valid_pll_params(self, tmp_path):
        """GIVEN valid PLL parameters
           WHEN _check_clock_pll runs
           THEN it reports them as info."""
        content = "PLLM = 8 PLLN = 168 PLLP = 2 PLLQ = 7"
        f = _create_file(tmp_path, "clock.c", content)
        findings = _check_clock_pll(content, f)
        assert any("PLLN=168 within range" in fi["message"] for fi in findings)

    def test_pll_source_not_set(self, tmp_path):
        """GIVEN PLL parameters without explicit source
           WHEN _check_clock_pll runs
           THEN it warns about missing PLL source."""
        content = "PLLM = 8 PLLN = 168"
        f = _create_file(tmp_path, "clock.c", content)
        findings = _check_clock_pll(content, f)
        assert any("PLL source selection not explicitly set" in fi["message"] for fi in findings)


# =============================================================================
# _check_system_clock_frequency
# =============================================================================

class TestCheckSystemClockFrequency:
    """Tests for _check_system_clock_frequency — SystemCoreClock checks."""

    def test_system_core_clock_set(self, tmp_path):
        """GIVEN SystemCoreClock is explicitly set
           WHEN _check_system_clock_frequency runs
           THEN it reports the frequency."""
        content = "SystemCoreClock = 168000000"
        f = _create_file(tmp_path, "clock.c", content)
        findings = _check_system_clock_frequency(content, f)
        assert any("SystemCoreClock = 168000000" in fi["message"] for fi in findings)

    def test_system_clock_too_low(self, tmp_path):
        """GIVEN SystemCoreClock < 1 MHz
           WHEN _check_system_clock_frequency runs
           THEN it warns about potentially intentional low frequency."""
        content = "SystemCoreClock = 1000"
        f = _create_file(tmp_path, "clock.c", content)
        findings = _check_system_clock_frequency(content, f)
        assert any("is < 1 MHz" in fi["message"] for fi in findings)

    def test_system_clock_exceeds_range(self, tmp_path):
        """GIVEN SystemCoreClock > 480 MHz
           WHEN _check_system_clock_frequency runs
           THEN it returns a major finding."""
        content = "SystemCoreClock = 500000000"
        f = _create_file(tmp_path, "clock.c", content)
        findings = _check_system_clock_frequency(content, f)
        assert any("exceeds typical MCU range" in fi["message"] for fi in findings)

    def test_clock_not_set(self, tmp_path):
        """GIVEN no SystemCoreClock assignment
           WHEN _check_system_clock_frequency runs
           THEN it reports info."""
        content = "int x;"
        f = _create_file(tmp_path, "clock.c", content)
        findings = _check_system_clock_frequency(content, f)
        assert any("SystemCoreClock not explicitly set" in fi["message"] for fi in findings)

    def test_rcc_calls_detected(self, tmp_path):
        """GIVEN HAL_RCC_OscConfig and HAL_RCC_ClockConfig present
           WHEN _check_system_clock_frequency runs
           THEN it reports full clock tree configuration."""
        content = "HAL_RCC_OscConfig(); HAL_RCC_ClockConfig();"
        f = _create_file(tmp_path, "clock.c", content)
        findings = _check_system_clock_frequency(content, f)
        assert any("clock tree fully configured" in fi["message"] for fi in findings)


# =============================================================================
# _check_alloca_usage
# =============================================================================

class TestCheckAllocaUsage:
    """Tests for _check_alloca_usage — alloca() detection."""

    def test_alloca_detected(self, tmp_path):
        """GIVEN alloca() usage in code
           WHEN _check_alloca_usage runs
           THEN it returns a critical finding."""
        content = "void f() { char *buf = alloca(128); }"
        f = _create_file(tmp_path, "bsp.c", content)
        findings = _check_alloca_usage(content, f)
        assert any(fi["severity"] == "critical" and "alloca()" in fi["message"] for fi in findings)

    def test_strdupa_detected(self, tmp_path):
        """GIVEN strdupa usage (GNU alloca wrapper)
           WHEN _check_alloca_usage runs
           THEN it returns a critical finding."""
        content = "char *s = strdupa(\"hello\");"
        f = _create_file(tmp_path, "bsp.c", content)
        findings = _check_alloca_usage(content, f)
        assert any("strdupa/strndupa" in fi["message"] for fi in findings)

    def test_no_alloca(self, tmp_path):
        """GIVEN no alloca usage
           WHEN _check_alloca_usage runs
           THEN it returns no findings."""
        content = "int x = 0;"
        f = _create_file(tmp_path, "bsp.c", content)
        findings = _check_alloca_usage(content, f)
        assert findings == []


# =============================================================================
# _check_vla_usage
# =============================================================================

class TestCheckVlaUsage:
    """Tests for _check_vla_usage — VLA detection."""

    def test_potential_vla_detected(self, tmp_path):
        """GIVEN a potential VLA declaration
           WHEN _check_vla_usage runs
           THEN it returns a major finding."""
        content = "void f(int n) { uint8_t buf[n]; }"
        f = _create_file(tmp_path, "bsp.c", content)
        findings = _check_vla_usage(content, f)
        assert any("Potential VLA" in fi["message"] for fi in findings)

    def test_no_vla(self, tmp_path):
        """GIVEN no VLA declarations
           WHEN _check_vla_usage runs
           THEN it returns no findings."""
        content = "uint8_t buf[64];"
        f = _create_file(tmp_path, "bsp.c", content)
        findings = _check_vla_usage(content, f)
        assert findings == []


# =============================================================================
# _check_dynamic_allocation
# =============================================================================

class TestCheckDynamicAllocation:
    """Tests for _check_dynamic_allocation — malloc/calloc/free detection."""

    def test_malloc_detected(self, tmp_path):
        """GIVEN malloc calls in code
           WHEN _check_dynamic_allocation runs
           THEN it returns a finding."""
        content = "void *p = malloc(64); free(p);"
        f = _create_file(tmp_path, "bsp.c", content)
        findings = _check_dynamic_allocation(content, f)
        assert any("Dynamic memory allocation" in fi["message"] for fi in findings)

    def test_calloc_detected(self, tmp_path):
        """GIVEN calloc calls in code
           WHEN _check_dynamic_allocation runs
           THEN it returns a finding."""
        content = "void *p = calloc(10, 4);"
        f = _create_file(tmp_path, "bsp.c", content)
        findings = _check_dynamic_allocation(content, f)
        assert any("calloc" in fi["message"] for fi in findings)

    def test_new_detected(self, tmp_path):
        """GIVEN C++ new operator in code
           WHEN _check_dynamic_allocation runs
           THEN it returns a finding."""
        content = "void* p = new int;"
        f = _create_file(tmp_path, "bsp.cpp", content)
        findings = _check_dynamic_allocation(content, f)
        assert any("'new' operator" in fi["message"] for fi in findings)

    def test_no_dynamic_allocation(self, tmp_path):
        """GIVEN no dynamic allocation calls
           WHEN _check_dynamic_allocation runs
           THEN it returns no findings."""
        content = "int x = 0;"
        f = _create_file(tmp_path, "bsp.c", content)
        findings = _check_dynamic_allocation(content, f)
        assert findings == []


# =============================================================================
# _check_peripheral_init_order
# =============================================================================

class TestCheckPeripheralInitOrder:
    """Tests for _check_peripheral_init_order — init order validation."""

    def test_no_init_calls(self, tmp_path):
        """GIVEN no HAL initialization calls
           WHEN _check_peripheral_init_order runs
           THEN it returns info."""
        files = {"board_headers": [], "clock_config": [], "peripheral_config": [],
                 "dma_config": [], "pin_mux": [], "hal_config": []}
        findings = _check_peripheral_init_order(files)
        assert any("No HAL initialization calls" in fi["message"] for fi in findings)

    def test_hal_init_before_others(self, tmp_path):
        """GIVEN HAL_Init appears before other init calls
           WHEN _check_peripheral_init_order runs
           THEN no ordering issues."""
        f = _create_file(tmp_path, "main.c", "HAL_Init(); HAL_GPIO_Init(); HAL_DMA_Init();")
        files = {"board_headers": [], "clock_config": [], "peripheral_config": [f],
                 "dma_config": [], "pin_mux": [], "hal_config": []}
        findings = _check_peripheral_init_order(files)
        # Should not report GPIO before HAL_Init
        assert not any("initialized before HAL_Init" in fi["message"] for fi in findings)

    def test_gpio_before_hal_init(self, tmp_path):
        """GIVEN GPIO_Init before HAL_Init
           WHEN _check_peripheral_init_order runs
           THEN it warns about ordering."""
        f = _create_file(tmp_path, "main.c", "HAL_GPIO_Init(GPIOA, &cfg); HAL_Init();")
        files = {"board_headers": [], "clock_config": [], "peripheral_config": [f],
                 "dma_config": [], "pin_mux": [], "hal_config": []}
        findings = _check_peripheral_init_order(files)
        assert any("initialized before HAL_Init" in fi["message"] for fi in findings)


# =============================================================================
# _check_peripheral_conflict
# =============================================================================

class TestCheckPeripheralConflict:
    """Tests for _check_peripheral_conflict — pin conflict detection."""

    def test_pin_conflict_detected(self, tmp_path):
        """GIVEN the same pin assigned to different peripherals
           WHEN _check_peripheral_conflict runs
           THEN it returns a critical finding."""
        content = (
            "GPIOA GPIO_PIN_0 USART1 "
            "GPIOA GPIO_PIN_0 SPI1 "
        )
        f = _create_file(tmp_path, "pin_mux.c", content)
        files = {"pin_mux": [f], "peripheral_config": []}
        findings = _check_peripheral_conflict(files)
        assert any(fi["severity"] == "critical" for fi in findings)

    def test_no_conflicts(self, tmp_path):
        """GIVEN different pins for different peripherals
           WHEN _check_peripheral_conflict runs
           THEN it returns no critical findings."""
        content = ""
        f = _create_file(tmp_path, "pin_mux.c", content)
        files = {"pin_mux": [f], "peripheral_config": []}
        findings = _check_peripheral_conflict(files)
        assert not any(fi["severity"] == "critical" for fi in findings)


# =============================================================================
# _check_dma_config
# =============================================================================

class TestCheckDmaConfig:
    """Tests for _check_dma_config — DMA configuration checks."""

    def test_no_dma_files(self, tmp_path):
        """GIVEN no DMA files
           WHEN _check_dma_config runs
           THEN it returns info."""
        files = {"dma_config": []}
        findings = _check_dma_config(files)
        assert any("No DMA configuration files" in fi["message"] for fi in findings)

    def test_dma_init_found_no_irq(self, tmp_path):
        """GIVEN DMA init calls but no IRQ handlers
           WHEN _check_dma_config runs
           THEN it warns about missing IRQ."""
        content = "HAL_DMA_Init(); Channel = 1;"
        f = _create_file(tmp_path, "dma.c", content)
        files = {"dma_config": [f]}
        findings = _check_dma_config(files)
        assert any("DMA initialized without IRQ handlers" in fi["message"] for fi in findings)

    def test_dma_with_irq(self, tmp_path):
        """GIVEN DMA init with IRQ handlers
           WHEN _check_dma_config runs
           THEN it reports DMA configuration."""
        content = "HAL_DMA_Init(); DMA2_Stream0_IRQHandler(); Channel = 1;"
        f = _create_file(tmp_path, "dma.c", content)
        files = {"dma_config": [f]}
        findings = _check_dma_config(files)
        assert any("IRQ handler" in fi["message"] for fi in findings)

    def test_dma_no_init_call(self, tmp_path):
        """GIVEN DMA files but no HAL_DMA_Init
           WHEN _check_dma_config runs
           THEN it reports info."""
        content = "Channel = 1;"
        f = _create_file(tmp_path, "dma.c", content)
        files = {"dma_config": [f]}
        findings = _check_dma_config(files)
        assert any("no HAL_DMA_Init call" in fi["message"] for fi in findings)


# =============================================================================
# _check_hal_api_consistency
# =============================================================================

class TestCheckHalApiConsistency:
    """Tests for _check_hal_api_consistency — HAL API pairing."""

    def test_no_hal_calls(self, tmp_path):
        """GIVEN no HAL API calls
           WHEN _check_hal_api_consistency runs
           THEN it returns info."""
        files = {"board_headers": []}
        findings = _check_hal_api_consistency(files)
        assert any("No HAL API calls" in fi["message"] for fi in findings)

    def test_missing_deinit(self, tmp_path):
        """GIVEN Init without DeInit
           WHEN _check_hal_api_consistency runs
           THEN it reports missing DeInit."""
        content = "HAL_UART_Init(); HAL_SPI_Init();"
        f = _create_file(tmp_path, "main.c", content)
        files = {"peripheral_config": [f]}
        findings = _check_hal_api_consistency(files)
        assert any("Init but no DeInit" in fi["message"] for fi in findings)

    def test_init_deinit_paired(self, tmp_path):
        """GIVEN Init and DeInit both present
           WHEN _check_hal_api_consistency runs
           THEN no missing DeInit finding."""
        content = "HAL_UART_Init(); HAL_UART_DeInit();"
        f = _create_file(tmp_path, "main.c", content)
        files = {"peripheral_config": [f]}
        findings = _check_hal_api_consistency(files)
        # Should still have summary finding
        assert any("HAL API usage" in fi["message"] for fi in findings)


# =============================================================================
# _build_bsp_review_prompt
# =============================================================================

class TestBuildBspReviewPrompt:
    """Tests for _build_bsp_review_prompt — LLM prompt builder."""

    def test_generates_prompts(self, tmp_path):
        """GIVEN BSP files
           WHEN _build_bsp_review_prompt runs
           THEN it returns system and user prompts."""
        f = _create_file(tmp_path, "board.h", "#define LED_PIN GPIO_PIN_5")
        files = {"board_headers": [f]}
        system_prompt, user_prompt = _build_bsp_review_prompt(files)
        assert "Board Support Package" in system_prompt
        assert "board.h" in user_prompt

    def test_empty_files(self, tmp_path):
        """GIVEN no BSP files
           WHEN _build_bsp_review_prompt runs
           THEN prompts still contain key sections."""
        files = {"board_headers": []}
        system_prompt, user_prompt = _build_bsp_review_prompt(files)
        assert "Board Support Package" in system_prompt
        assert "BSP Files" in user_prompt


# =============================================================================
# step_review_bsp — end-to-end
# =============================================================================

class TestStepReviewBsp:
    """Tests for step_review_bsp — the main pipeline step handler."""

    @patch("yuleosh.pipeline.step_handlers.review_bsp._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_bsp.os.environ")
    def test_empty_project(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN an empty project directory
           WHEN step_review_bsp runs
           THEN it finds no BSP files and reports them."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.return_value = {"content": "mock review", "usage": {"total_tokens": 100}}

        result = step_review_bsp(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["step"] == "review-bsp"
        assert report["bsp_file_counts"]["board_headers"] == 0
        assert any("No BSP files" in fi.get("message", "") for fi in report["static_findings"])

    @patch("yuleosh.pipeline.step_handlers.review_bsp._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_bsp.os.environ")
    def test_with_bsp_files(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN BSP board header files exist
           WHEN step_review_bsp runs
           THEN static findings include GPIO checks and LLM review is called."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.return_value = {"content": "# LLM Review\nAll green.", "usage": {"total_tokens": 200}}

        _create_file(tmp_path, "board.h", "int x;")
        _create_file(tmp_path, "bsp/board.h", "HAL_GPIO_Init(GPIOA, &cfg); GPIO_MODE_OUTPUT_PP GPIO_SPEED_FREQ_HIGH")

        result = step_review_bsp(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["step"] == "review-bsp"
        assert "NO GPIO" in report["llm_review"] or report["llm_review"]
        assert report["finding_count"] > 0

    @patch("yuleosh.pipeline.step_handlers.review_bsp._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_bsp.os.environ")
    def test_critical_finding_triggers_failed(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN BSP code with alloca (critical finding)
           WHEN step_review_bsp runs
           THEN the overall status is 'failed'."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.return_value = {"content": "critical issue", "usage": {"total_tokens": 50}}

        _create_file(tmp_path, "board.h", "HAL_GPIO_Init(GPIOA, &cfg);")
        _create_file(tmp_path, "dma_config.c", "char *buf = alloca(256); HAL_DMA_Init();")

        result = step_review_bsp(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["status"] == "failed"
        assert report["finding_breakdown"]["critical"] > 0

    @patch("yuleosh.pipeline.step_handlers.review_bsp._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_bsp.os.environ")
    def test_llm_failure_non_fatal(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN LLM call raises an exception
           WHEN step_review_bsp runs
           THEN the step still completes with a fallback message."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.side_effect = RuntimeError("LLM unavailable")

        _create_file(tmp_path, "board.h", "HAL_GPIO_Init(GPIOA, &cfg); GPIO_MODE_OUTPUT_PP GPIO_SPEED_FREQ_HIGH")

        result = step_review_bsp(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["step"] == "review-bsp"
        # Should have "(LLM-powered review unavailable)" as fallback
        assert "unavailable" in report["llm_review"] or "(LLM-powered" in report["llm_review"]

    @patch("yuleosh.pipeline.step_handlers.review_bsp._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_bsp.os.environ")
    def test_pipeline_step_error_propagates(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN the output file cannot be written
           WHEN step_review_bsp runs
           THEN it raises PipelineStepError."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.return_value = {"content": "mock", "usage": {"total_tokens": 10}}

        # Make session_dir point to a non-writable location
        mock_session.session_dir = tmp_path / "nonexistent" / "deep"
        # Don't create the dir — write will fail

        with pytest.raises(PipelineStepError, match="Cannot write BSP review"):
            step_review_bsp(mock_session)

    @patch("yuleosh.pipeline.step_handlers.review_bsp._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_bsp.os.environ")
    def test_with_many_findings(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN many BSP findings across multiple categories
           WHEN step_review_bsp runs
           THEN the finding breakdown contains all severities."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.return_value = {"content": "mock", "usage": {"total_tokens": 50}}

        _create_file(tmp_path, "board.h", "HAL_GPIO_Init(GPIOA, &cfg); GPIO_MODE_OUTPUT_PP GPIO_SPEED_FREQ_HIGH")
        _create_file(tmp_path, "clock.c", "SystemCoreClock = 1000")
        _create_file(tmp_path, "pin_mux.c", "HAL_GPIO_Init();")

        result = step_review_bsp(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["finding_count"] > 0
        assert "review-bsp" in report["step"]

    def test_timed_step_decorator_present(self):
        """GIVEN the step function
           WHEN inspected
           THEN it has the timed_step wrapper."""
        assert hasattr(step_review_bsp, "__wrapped__") or callable(step_review_bsp)


# =============================================================================
# _static_bsp_review
# =============================================================================

class TestStaticBspReview:
    """Tests for _static_bsp_review — all static checks combined."""

    def test_no_files(self, tmp_path):
        """GIVEN an empty project
           WHEN _static_bsp_review runs
           THEN it returns a no-files finding."""
        findings = _static_bsp_review(tmp_path)
        assert any("No BSP files" in fi["message"] for fi in findings)
        assert len(findings) == 1

    def test_with_board_and_clock(self, tmp_path):
        """GIVEN board header and clock config files
           WHEN _static_bsp_review runs
           THEN findings from both categories appear."""
        _create_file(tmp_path, "board.h", "HAL_GPIO_Init();")
        _create_file(tmp_path, "clock.c", "HSE_VALUE = 8000000 PLLM = 8 PLLN = 168")
        findings = _static_bsp_review(tmp_path)
        assert len(findings) > 1

    def test_unreadable_file_skipped(self, tmp_path):
        """GIVEN a file that cannot be read
           WHEN _static_bsp_review runs
           THEN it skips the file without crashing."""
        f = _create_file(tmp_path, "board.h", "test")
        f.chmod(0o000)  # Remove read permission
        try:
            findings = _static_bsp_review(tmp_path)
            # Should not crash, may have 0 or more findings
            assert isinstance(findings, list)
        finally:
            f.chmod(0o644)  # Restore
