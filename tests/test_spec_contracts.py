"""Tests for yuleosh.spec_contracts — spec 契约抽取与完整性校验 (方案 A).

2026-08-16: 长 spec 固定截断导致下游 LLM 看不到尾部契约 (window-anti-pinch
连续 3 轮 RED). 本模块把契约从叙述性 spec 抽取为机器可读 JSON, 供 spec-check
步骤确定性校验 + codegen prompt 全量注入.
"""

# @tests src/yuleosh/spec/validate.py

import json
import os
import subprocess
import sys

import pytest

from yuleosh.spec_contracts import (
    contracts_check,
    extract_contracts,
    main as contracts_main,
    validate_contracts,
)

# window-anti-pinch 真实 spec 的缩略版 (覆盖契约节结构)
SAMPLE_SPEC = """# 车窗防夹模块

> Version: 1.1.6

## 1. System Requirements

### SR-001: 硬件抽象
- The system SHALL provide HAL abstraction

## 1.5 接口契约

### hal_hall.h (霍尔传感器)
```c
void hal_hall_init(void);
uint32_t hal_hall_get_count(void);
```

### hal_motor.h (电机)
```c
void hal_motor_init(void);
void hal_motor_set_speed(uint16_t duty);
```

### hal_timer.h (定时)
```c
void hal_timer_init(void);
uint32_t hal_timer_get_ms(void);
```

### hal_nvm.h (存储)
```c
bool hal_nvm_load(uint32_t sector, uint32_t offset, uint8_t *buf, size_t len);
bool hal_nvm_store(uint32_t sector, uint32_t offset, const uint8_t *buf, size_t len);
```

### window_config.h (配置)
```c
void window_config_init(void);
void window_config_set_all(const WindowConfig *config);
```

### window_position.h (位置)
```c
void window_position_init(WindowPosition *pos);
void window_position_update(WindowPosition *pos, uint32_t hallCount, uint32_t timeMs);
```

### window_modes.h (模式)
```c
void window_modes_init(WindowModeContext *ctx);
WindowModeResult window_modes_manual(WindowModeContext *ctx, bool commandActive, bool direction,
                                     const WindowPosition *pos, const WindowConfig *config, uint32_t timeMs);
```

### window_control.h (状态机)
```c
typedef enum { WINDOW_CONTROL_IDLE = 0 } WindowControlState;
void window_control_init(WindowControlContext *ctx);
void window_control_reset(WindowControlContext *ctx);
```

## 2.5 行为护栏 → 需求映射

| # | 行为护栏 | 对应需求 |
|:-:|:-----|:-----|
| G-01 | set_all 逐字段 clamp | SW-008 |
| G-02 | 反置防夹区回退默认值 | SW-008 |
| G-03 | 位置推进增量取 \\|delta\\| | SW-004 |

## 3. Acceptance Scenarios

### Scenario: 手动下降
- GIVEN IDLE
- WHEN manual down
- THEN motor runs
"""

SAMPLE_SPEC_PARAMS = """
## SW-008: 配置参数

| 参数 | 默认 | min | max |
|:-----|:----:|:---:|:---:|
| pinchSpeedDropThreshold | 30 | 1 | 100 |
| reversalDistanceMm | 100 | 10 | 500 |
| stallTimeoutMs | 500 | 100 | 5000 |
"""


@pytest.fixture
def sample_spec(tmp_path):
    p = tmp_path / "spec.md"
    p.write_text(SAMPLE_SPEC, encoding="utf-8")
    return str(p)


@pytest.fixture
def sample_spec_full(tmp_path):
    p = tmp_path / "spec.md"
    p.write_text(SAMPLE_SPEC + SAMPLE_SPEC_PARAMS, encoding="utf-8")
    return str(p)


class TestExtractContracts:
    def test_extracts_requirements(self, sample_spec):
        c = extract_contracts(sample_spec)
        assert "SR-001" in c["requirements"]

    def test_extracts_interfaces(self, sample_spec):
        c = extract_contracts(sample_spec)
        headers = {i["header"] for i in c["interfaces"]}
        assert headers == {"hal_hall.h", "hal_motor.h", "hal_timer.h", "hal_nvm.h",
                           "window_config.h", "window_position.h", "window_modes.h",
                           "window_control.h"}
        by_name = {i["header"]: i for i in c["interfaces"]}
        assert "void hal_motor_set_speed(uint16_t duty)" in by_name["hal_motor.h"]["signatures"]
        assert "void window_control_reset(WindowControlContext *ctx)" in by_name["window_control.h"]["signatures"]

    def test_extracts_guardrails(self, sample_spec):
        c = extract_contracts(sample_spec)
        assert c["guardrails"] == ["G-01", "G-02", "G-03"]

    def test_extracts_params_excludes_guardrail_rows(self, sample_spec_full):
        c = extract_contracts(sample_spec_full)
        names = [p["name"] for p in c["params"]]
        assert "pinchSpeedDropThreshold" in names
        assert "G-01" not in names  # guardrail table must not leak into params
        assert len(c["params"]) == 3

    def test_extracts_nvm_layout(self, tmp_path):
        p = tmp_path / "spec.md"
        p.write_text(
            "# spec\n\n### SW-006: 标定\n"
            "- 布局 `[0..3] magic=0xC411B40C, [4] version=1, "
            "[5..8] maxClosePulses, [9..12] maxOpenPulses` 共 13 字节\n",
            encoding="utf-8",
        )
        c = extract_contracts(str(p))
        assert c["nvm_layout"]["magic"] == "0xC411B40C"
        assert c["nvm_layout"]["version"] == "1"
        assert c["nvm_layout"]["maxClosePulses"] is True
        assert c["nvm_layout"]["maxOpenPulses"] is True
        assert c["nvm_layout"]["record_bytes"] == 13

    def test_missing_spec_returns_error(self, tmp_path):
        c = extract_contracts(str(tmp_path / "nope.md"))
        assert "error" in c


class TestValidateContracts:
    def test_passes_complete(self, sample_spec_full):
        c = extract_contracts(sample_spec_full)
        v = validate_contracts(c)
        assert v["passed"] is True
        assert v["missing"] == []

    def test_fails_missing_guardrails(self, sample_spec):
        c = extract_contracts(sample_spec)
        # 要求 12 条但只有 3 条 → 失败
        v = validate_contracts(c, required={"guardrails": 12})
        assert v["passed"] is False
        assert any("guardrails" in m for m in v["missing"])

    def test_required_guardrail_ids(self, sample_spec):
        c = extract_contracts(sample_spec)
        v = validate_contracts(c, required={"guardrail_ids": ["G-01", "G-02", "G-03", "G-12"]})
        assert v["passed"] is False
        assert any("G-12" in m for m in v["missing"])

    def test_required_params(self, sample_spec_full):
        c = extract_contracts(sample_spec_full)
        v = validate_contracts(c, required={"param_names": ["pinchSpeedDropThreshold", "stallTimeoutMs"]})
        assert v["passed"] is True

    def test_required_nvm(self, tmp_path):
        p = tmp_path / "spec.md"
        p.write_text("# spec\n### SW-006\nmagic=0xDEADBEEF\n", encoding="utf-8")
        c = extract_contracts(str(p))
        v = validate_contracts(c, required={"nvm": True})
        assert v["passed"] is False
        assert any("NVM" in m for m in v["missing"])


class TestContractsCheck:
    def test_roundtrip(self, sample_spec_full):
        r = contracts_check(sample_spec_full)
        assert r["validation"]["passed"] is True
        assert "contracts" in r

    def test_missing_file(self, tmp_path):
        r = contracts_check(str(tmp_path / "nope.md"))
        assert r["validation"]["passed"] is False


class TestCli:
    def test_cli_pass(self, sample_spec_full):
        code = contracts_main([sample_spec_full])
        assert code == 0

    def test_cli_fail(self, tmp_path):
        # 声明了契约节但抽取不完整 → FAIL (比如 NVM 有 magic 但无字节数)
        p = tmp_path / "spec.md"
        p.write_text("# spec\n### SW-006\nmagic=0xDEADBEEF\n", encoding="utf-8")
        code = contracts_main([str(p)])
        assert code == 1

    def test_cli_json(self, sample_spec_full):
        code = contracts_main([sample_spec_full, "--json"])
        assert code == 0
