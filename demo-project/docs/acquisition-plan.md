# Acquisition Preparation（docs/acquisition-plan.md）

- 生成时间：2026-11-10T15:31:24+00:00
- 自动识别条目：0
- 扫描来源：glob:procurement/*.json、glob:.osh/procurement/*.json

## 采购范围

覆盖采购范围、自制/外购决策与验收准则；范围变更须回写本文件。

- 过程责任人：待指定（人工维护）
- 终态要求：approved 必须提供「决策依据」。

## 采购策略

采购输入只来自显式扫描产物，扫描不到时如实记录「无条目」。

1. 识别：按扫描模式收集记录，不臆造条目。
2. 评估：人工填写状态与「决策依据」。
3. 复核：终态缺少「决策依据」即门禁 RED。

## 验收准则

| ID | 条目 | 状态 | 决策依据 | 来源 |
|:---|:---|:---|:---|:---|
| — | （无条目：未检测到采购记录） | — | — | — |

## 数据来源

- `glob:procurement/*.json`
- `glob:.osh/procurement/*.json`
