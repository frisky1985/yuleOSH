# 硬件需求分析（HWE.1）

- 生成时间：2026-11-10T15:31:23+00:00
- 硬件条目数：0

## 硬件条目

| ID | 条目 | 类型 | 来源 | 状态 | 责任人 |
|:---|:---|:---|:---|:---|:---|
| — | （无条目：未检测到硬件范围） | — | — | — | — |

## 范围与扫描来源

硬件范围由以下客观信号识别（零命中亦如实记录）：

- `glob:**/*.ld`
- `glob:**/*.sct`
- `glob:**/*.ioc`
- `glob:**/*.dbc`
- `glob:**/startup_*.s`
- `glob:**/startup_*.S`
- `dir:boards/`
- `dir:board/`

> 本次扫描未命中任何硬件信号，判定为无硬件范围；不做任何硬件条目推断。若项目实际包含硬件，请补充上述信号文件或在登记文件中人工登记（origin: manual）。

## 可追溯性

- 登记文件：`docs/hw-item-register.yaml`（scan_sources 为扫描证据）。
- 硬件设计覆盖见 `docs/hw-design.md`（HWE.2）；验证结论见 `docs/hw-verification-report.md`（HWE.4）。
