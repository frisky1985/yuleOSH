# Validation（docs/product-validation.md）

- 生成时间：2026-11-10T15:31:24+00:00
- 自动识别条目：0
- 扫描来源：glob:.osh/evidence/validation/*.json、glob:.osh/ci/validate-*.json

## 确认目标

确认目标、环境与准则须与预期使用场景一致。

- 过程责任人：待指定（人工维护）
- 终态要求：passed 必须提供「执行证据」。

## 确认环境

确认结果只来自显式执行记录；passed 必须带执行证据。

1. 识别：按扫描模式收集记录，不臆造条目。
2. 评估：人工填写状态与「执行证据」。
3. 复核：终态缺少「执行证据」即门禁 RED。

## 确认记录

| ID | 条目 | 状态 | 执行证据 | 来源 |
|:---|:---|:---|:---|:---|
| — | （无条目：未检测到确认执行记录） | — | — | — |

## 数据来源

- `glob:.osh/evidence/validation/*.json`
- `glob:.osh/ci/validate-*.json`
