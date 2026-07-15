# Phase 1 — 覆盖率提升 11% → 60%

## 当前状态

| 模块 | 语句数 | 估计覆盖率 | 状态 |
|------|--------|-----------|------|
| `evidence/` | ~2,068 | <5% | 有测试但覆盖面不足 |
| `preview/` | ~506 | 0% | 有测试文件但未正确覆盖 |
| `ci/kpi/` | ~200 | 0% | 有测试文件但未正确覆盖 |
| `review/` | ~2,000 | <10% | 有大量测试但缺口多 |
| `report/` | ~544 | 0% | 有测试文件 |

## 任务

### Wave 1: evidence + preview
- `tests/test_evidence_engine.py` → 覆盖 evidence 核心
- `tests/test_preview_*.py` → 覆盖 preview 全模块
- 目标：每个子文件 > 60%

### Wave 2: ci/kpi + review + report  
- `tests/test_kpi.py` → 覆盖 ci/kpi
- `tests/test_review_*.py` → 覆盖 review 全模块
- `tests/test_report_*.py` → 覆盖 report 全模块

## 方法
- 优先给 0% 模块补测试
- 优先补核心业务逻辑（跳过 LLM/硬件相关代码）
- 使用 mock 避免需要真实硬件/LLM
- 每个测试文件运行 `--cov=模块名` 验证覆盖率

## 验收标准
- 每个模块覆盖率 ≥ 60%
- 所有测试通过
- coverage-trend CI job 自动采集
