# 测量计划 (MAN.6)

## 测量目标

- 以可量化指标评价过程与产品质量，支撑管理决策。
- 度量项与阈值复用 `ci.kpi` 的单一事实来源，避免文档与代码漂移。
- 每个度量项都必须能追溯到具体数据文件与采集时点。

## 度量项定义

| 度量ID | 度量项 | 数据来源 | 采集频率 | 阈值与判据 |
|:-------|:-------|:---------|:---------|:-----------|
| M-001 | MISRA 总违规数 | `.yuleosh/reports/misra-trend.jsonl` | 每次流水线 | ≤ 50 count |
| M-002 | MISRA Required 违规数 | `.yuleosh/reports/misra-trend.jsonl` | 每次流水线 | ≤ 5 count |
| M-003 | C 语言行覆盖率 | `.yuleosh/reports/coverage-trend.jsonl` | 每次流水线 | ≥ 80.0 % |
| M-004 | Python 行覆盖率 | `.yuleosh/reports/coverage-trend.jsonl` | 每次流水线 | ≥ 85.0 % |
| M-005 | 构建成功率 | `.yuleosh/reports/process-kpi.jsonl` | 每次流水线 | ≥ 95.0 % |
| M-006 | 回归触发率 | `.yuleosh/reports/process-kpi.jsonl` | 每次流水线 | ≤ 5.0 % |
| M-007 | 缺陷逃逸率 | `.yuleosh/reports/defect-escape.jsonl` | 每次流水线 | ≤ 15.0 % |
| M-008 | KG 需求覆盖率 | `.yuleosh/knowledge_graph.db` | 每次流水线 | ≥ 80.0 % |

## 测量规程

- **采集**：由流水线在对应步骤产出后写入 `.yuleosh/reports/`，不手工补数。
- **存储**：原始数据保留在项目内，测量报告只做汇总与判定。
- **分析**：PASS/FAIL 由阈值判定；无数据项标注「无数据」，不得推断。
- **通报与措施**：FAIL 项须在测量报告中给出原因分析与纠正措施。

## 可追溯性

- 度量项 ↔ 阈值: `ci.kpi.kpi_state.DEFAULT_THRESHOLDS`。
- 度量项 ↔ 数据文件: 见「度量项定义」表的数据来源列。
- 测量结果支撑 MAN.3 项目管理与 MAN.5 风险管理决策。
