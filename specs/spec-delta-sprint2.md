# Sprint 2: E2E集成测试 + 模块重构

> **Version**: 1.0.0-draft
> **基于**: Sprint 1 完成（覆盖率80.59%, CI gate 80%）
> **格式**: SHALL / SHOULD / MAY

---

## 背景

Sprint 1 完成分支覆盖攻坚后，代码覆盖率已达到80.59%。
Sprint 2 聚焦两个核心问题：
1. E2E集成测试缺失 — 无端到端的全流程验证
2. 部分模块过大 — `pipeline/run.py`(938行) 和 `ci/run.py`(895行) 超800行阈值

---

## S2-REQ-001: E2E 全流程集成测试

- The system **SHALL** provide a fully-mocked E2E test that exercises the pipeline from spec ingestion to evidence pack generation.
- The E2E test **SHALL** mock all external dependencies (LLM, subprocess, file system I/O).
- The E2E test **SHOULD** cover at least 80% of pipeline steps in a single end-to-end run.
- The E2E test **MAY** use pytest fixtures for test isolation.

### GIVEN/WHEN/THEN

**GIVEN** a valid OpenSpec file as input  
**WHEN** the pipeline runs end-to-end with mocked dependencies  
**THEN** the pipeline SHALL produce a result indicating success or failure for each step

**GIVEN** a test spec configured for all 3 CI layers  
**WHEN** the CI runner executes Layer 1, 2, and 3  
**THEN** each layer SHALL report a pass/fail status

**GIVEN** a completed pipeline session  
**WHEN** the evidence pack step is triggered  
**THEN** an evidence summary SHALL be generated

---

## S2-REQ-002: pipeline/run.py 模块拆分

- The system **SHALL** split `pipeline/run.py` into at least 3 modules: `orchestrator.py`, `steps.py`, `session.py`.
- Each resulting module **SHALL** be under 500 lines of code.
- The public API **SHOULD** remain backward compatible.
- The split **MAY** preserve existing import paths via re-exports.

### GIVEN/WHEN/THEN

**GIVEN** the existing pipeline/run.py (938 lines)  
**WHEN** it is split into orchestrator/steps/session  
**THEN** all existing tests SHALL continue to pass without modification

---

## S2-REQ-003: ci/run.py 模块拆分

- The system **SHALL** split `ci/run.py` into at least 3 modules: `runner.py`, `layers.py`, `config.py`.
- Each resulting module **SHALL** be under 500 lines of code.
- Layer-specific logic **SHOULD** be isolated in `layers.py`.

### GIVEN/WHEN/THEN

**GIVEN** the existing ci/run.py (895 lines)  
**WHEN** it is split into runner/layers/config  
**THEN** all existing CI tests SHALL continue to pass without modification

---

## 验收标准

| ID | 条件 | 优先级 | 负责人 |
|----|------|--------|--------|
| AC-01 | E2E测试运行通过且覆盖率≥80% | P0 | 小克 |
| AC-02 | pipeline/run.py ≤500行/模块 | P1 | 小克 |
| AC-03 | ci/run.py ≤500行/模块 | P1 | 小克 |
| AC-04 | 所有现有测试不退化 | P0 | 小克 |
