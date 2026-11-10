# 风险报告（MAN.5）

- 生成时间：2026-11-10T15:31:23+00:00
- 扫描来源：MAN.6/KPI、pipeline/session
- 风险总数：2（critical 0 / high 2 / medium 0 / low 0）
- 开放高风险：2
- 待分级高风险：2

## 风险清单

| ID | 标题 | 类别 | L | I | 分值 | 等级 | 状态 | 责任人 | 应对 | 评审日 |
|:---|:---|:---|:--|:--|:--|:---|:---|:---|:---|:---|
| RISK-KPI-KG-COVERAGE-PCT | 度量项未达标: KG 需求覆盖率 | 质量 | 4 | 3 | 12 | high | open | 待指定 | mitigate | — |
| RISK-STEP-SESSION | 流程步骤历史失败: session | 进度 | 3 | 4 | 12 | high | open | 待指定 | mitigate | — |

## 升级项

- **RISK-KPI-KG-COVERAGE-PCT**（high, 12）责任人 待指定，到期 未设置：度量项未达标: KG 需求覆盖率（自动识别，待分级）
- **RISK-STEP-SESSION**（high, 12）责任人 待指定，到期 未设置：流程步骤历史失败: session（自动识别，待分级）

## 可追溯性

- 评分方法与阈值见 `docs/risk-management-plan.md`。
- 自动风险来源：`docs/measurement-report.md` 的 FAIL 度量项与流水线失败记录。
- 登记明细：`docs/risk-register.yaml`。
