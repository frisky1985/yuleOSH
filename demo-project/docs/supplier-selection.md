# Supplier Selection（docs/supplier-selection.md）

- 生成时间：2026-11-10T15:31:24+00:00
- 自动识别条目：0
- 扫描来源：glob:procurement/suppliers/*.json、glob:.osh/procurement/suppliers/*.json

## 候选供应商

候选供应商、评估准则与选择结果必须可追溯到来源记录。

- 过程责任人：待指定（人工维护）
- 终态要求：selected 必须提供「评估结论」。

## 评估准则

评估结论由人填写；自动条目在评估前一律标记「待分析」。

1. 识别：按扫描模式收集记录，不臆造条目。
2. 评估：人工填写状态与「评估结论」。
3. 复核：终态缺少「评估结论」即门禁 RED。

## 选择结果

| ID | 条目 | 状态 | 评估结论 | 来源 |
|:---|:---|:---|:---|:---|
| — | （无条目：未检测到供应商选择记录） | — | — | — |

## 数据来源

- `glob:procurement/suppliers/*.json`
- `glob:.osh/procurement/suppliers/*.json`
