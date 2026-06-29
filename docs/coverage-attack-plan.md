# yuleOSH 覆盖攻击计划

> **目标**: 15% → 60%+ 覆盖率 (3-5天)
> **当前基线**: 33.49% (819 tests passing, 2 known failures)

---

## 攻击策略

### 优先级（按影响排序）

| 批次 | 目标模块 | 预估覆盖提升 | 预估测试数 | 复杂度 |
|------|---------|-------------|-----------|-------|
| **Wave 1** | Pipeline step handlers (~6K LOC) | +12-15% | ~200-300 | ⭐⭐⭐⭐⭐ |
| **Wave 2** | API 模块 (~3.5K LOC) | +7-10% | ~100-150 | ⭐⭐⭐⭐ |
| **Wave 3** | Evidence + ALM + Preview (~4K LOC) | +5-8% | ~100-150 | ⭐⭐⭐ |
| **Wave 4** | CI/Compliance 剩余模块 (~3K LOC) | +3-5% | ~80-120 | ⭐⭐⭐ |
| **Wave 5** | Store + Report + Review 补漏 (~2K LOC) | +2-4% | ~60-80 | ⭐⭐ |

### Wave 1: Pipeline Step Handlers

**文件列表**:
- `pipeline/step_handlers/review_selftest.py` (1,365 lines)
- `pipeline/step_handlers/review_bsp.py` (1,261 lines)
- `pipeline/step_handlers/review_build.py` (850 lines)
- `pipeline/step_handlers/review_memory.py` (813 lines)
- `pipeline/step_handlers/review_startup.py` (778 lines)
- `pipeline/step_handlers/review_mmio.py` (741 lines)
- `pipeline/step_handlers/review_rtos.py` (739 lines)
- `pipeline/step_handlers/review_power.py` (735 lines)
- `pipeline/step_handlers/review_linker.py` (731 lines)
- `pipeline/step_handlers/execution.py` (499 lines)
- `pipeline/step_handlers/review_devplan.py` (536 lines)
- `pipeline/step_handlers/review_stack.py` (516 lines)
- `pipeline/step_handlers/review_test_coverage.py` (490 lines)

**测试策略**: 每个 handler 遵循相同的模式——输入 spec/代码 → 输出审查结果。Mock LLM 调用，测试各种边界条件。

### Wave 2: API 模块

**文件列表**:
- `api/demo_wow.py` (692 lines) - Demo API
- `api/preview.py` (549 lines) - Preview analysis API
- `api/ci.py` - CI orchestration API
- `api/pipeline.py` - Pipeline management API
- `api/evidence.py` - Evidence management API
- `api/auth.py` - Authentication API
- `api/subscription.py` - Subscription API
- `api/webhooks.py` - Webhook handling
- `api/spec.py` - Spec management API
- `api/project.py` - Project management API

### Wave 3: Evidence + ALM + Preview

**文件列表**:
- `evidence/excel_writer.py` (815 lines)
- `evidence/evidence_check.py` (593 lines)
- `alm/traceability.py` (821 lines)
- `alm/polarion.py` (521 lines)
- `preview/score_engine.py` (154 lines)
- `preview/code_parser.py` (156 lines)
- `preview/analyzer.py` (27 lines, wrapper)
- `preview/compliance_analyzer.py` (77 lines)

### Wave 4: CI/Compliance 剩余

- `ci/misra_report/core.py` (1,160 lines, partially tested)
- `ci/config.py` (582 lines)
- `ci/misra_fusion.py` (535 lines)
- `ci/agent_traceability.py` (521 lines)
- `ci/kpi/report.py` (509 lines)
- `ci/layers.py` (469 lines)
- `ci/build_metadata.py` (487 lines)

### Wave 5: 补漏

- `report/card_generator.py` (151 lines, ~6%)
- `report/trend_exporter.py` (90 lines, ~0%)
- `report/feishu_notifier.py` (50 lines, ~25%)
- `review/run.py` (464 lines, ~8%)
- `review/c_review.py` (462 lines)

---

## 执行流水线

```
Day 1: Fix broken tests → Wave 1 (Pipeline handlers) → 合并+验证
Day 2: Wave 2 (API) + Wave 3 (Evidence/ALM/Preview) → 并行
Day 3: Wave 4 (CI) + Wave 5 (补漏) → 并行
Day 4: 集成回归 → 修复 → 专家评审准备
Day 5: 最终验证 → 专家评审 → 量产
```

## 测试风格

每个新测试遵循以下模式:

```python
"""Test module for yuleosh.pipeline.step_handlers.review_selftest."""

import pytest
from unittest import mock

# 1. GIVEN: 设置测试数据
# 2. WHEN: 调用目标函数
# 3. THEN: 验证输出/副作用

# 边界条件:
# - 空输入
# - 异常输入
# - 正常路径
# - 错误路径
# - LLM mock 返回不同场景
```

## 验证标准

- 每批完成后运行: `pytest --cov=yuleosh --cov-config=.coveragerc tests/ -q`
- 新测试不得破坏现有 819+ tests
- 每批目标覆盖率提升: +3-5%
