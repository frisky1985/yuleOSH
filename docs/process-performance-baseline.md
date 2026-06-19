# 过程性能基线报告 (Process Performance Baseline)

**文档 ID**: MP-14
**版本**: v1.0.1
**生成日期**: 2026-06-19
**生成脚本**: yuleOSH KPI 基线采集引擎 + C Coverage Runner
**数据周期**: 30 次构建 (2026-06-19 及历史数据)
**审计分类**: PA 2.2 MP — 过程测量

---

## 1. 概述

本基线文档记录 yuleOSH CI/CD 流水线的四项过程稳定性 KPI：
1. **构建成功率** (Build Success Rate) — §21.1
2. **回归触发率** (Regression Trigger Rate) — §21.2
3. **违规修复时效** (Violation Fix Timeliness) — §21.4
4. **缺陷逃逸率** (Defect Escape Rate) — Sprint E 新增

并补充了 Sprint E 新增的以下基线数据：
- **C 代码覆盖率** (C Code Coverage) — 基于 gcovr 实测
- **Profile 变更审计** (Profile Change Audit) — 变更可追溯
- **工具版本变更审批** (Tool Version Change Approval)

这些 KPI 满足 ASPICE CL2 PA 2.2 MP 的过程测量要求，用于：
- 衡量过程稳定性趋势
- 设定门禁阈值基线
- 支持审计师交叉验证

---

## 2. KPI 基线数据

### 2.1 构建成功率 (Build Success Rate)

| 指标 | 值 |
|:-----|:----|
| 总构建次数 | 30 |
| 成功次数 | 29 |
| 失败次数 | 1 |
| **成功率** | **96.7%** |
| 阈值 | 95% |
| 判定 | ✅ PASS (≥95%) |

**趋势分析**: 构建成功率反映流水线稳定性。≥95% 表示流水线处于健康状态。

### 2.2 回归触发率 (Regression Trigger Rate)

| 指标 | 值 |
|:-----|:----|
| 回归触发次数 | 1 |
| **回归触发率** | **3.3%** |
| 阈值 | 5% |
| 判定 | ✅ PASS (≤5%) |

**回归定义**: 构建失败且通过的阶段数 < 总阶段数。

### 2.3 违规修复时效 (Required Violation Fix Timeliness)

| 指标 | 值 |
|:-----|:----|
| 新增 Required 违规总数 | 60 |
| 带 Required 违规的构建占比 | 100.0% |
| Required 修复时限 | 48h |
| Advisory 修复时限 | 15d |

**说明**: Required 违规需在 48 小时内修复或提交偏差申请。Advisory 违规需在 15 天内处理。

### 2.4 构建时长统计

| 指标 | 值 |
|:-----|:-----|
| 均值 | 31.5s |
| 标准差 | 10.0s |
| P50 (中位数) | 33.0s |
| P90 | 43.5s |
| UCL (上控制限) | 61.5s |
| LCL (下控制限) | 1.5s |
| 最长时间 | 48.0s |
| 最短时间 | 15.0s |

### 2.5 缺陷逃逸率 (Defect Escape Rate) — Sprint E 新增

| 指标 | 值 |
|:-----|:----|
| 总缺陷数 | 50 (样例数据) |
| 逃逸缺陷数 | 3 |
| **缺陷逃逸率** | **6.0%** |
| 阈值 | ≤15% |
| 判定 | ✅ PASS |

**数据来源**: `yuleosh kpi defect-escape record` 命令记录
**存储文件**: `.yuleosh/reports/defect-escape.jsonl`
**采集方式**: 从 tech-debt.md 和缺陷追踪中分析

### 2.6 C 代码覆盖率 — Sprint E 新增

| 指标 | 值 |
|:-----|:----|
| **Line 覆盖率** | **99.2%** |
| Branch 覆盖率 | 71.0% |
| Function 覆盖率 | 100.0% |
| 测量文件数 | 7 |
| 阈值 | ≥60% |
| 判定 | ✅ PASS |

**覆盖文件**:
- `src/yuleosh/cross/hello.c` — 100%
- `src/yuleosh/cross/hal_mock/gpio_mock.h` — 100%
- `src/yuleosh/cross/hal_mock/i2c_mock.h` — 100%
- `src/yuleosh/cross/hal_mock/mock_core.h` — 97.2%
- `src/yuleosh/cross/hal_mock/spi_mock.h` — 100%
- `src/yuleosh/cross/hal_mock/timer_mock.h` — 100%
- `src/yuleosh/cross/hal_mock/uart_mock.h` — 100%

**数据来源**: gcovr (Python 覆盖率工具)
**采集脚本**: `scripts/run_c_coverage.py`
**门禁命令**: `make c-coverage-gate` 或 `python3 scripts/run_c_coverage.py --fail-under=60`

---

## 3. 关联证据数据

### 3.1 MISRA 违规趋势

- 趋势文件: `.yuleosh/reports/misra-trend.jsonl`
- 总记录数: **100** 条
- 门禁要求: ≥90 条

### 3.2 代码覆盖率趋势

- 趋势文件: `.yuleosh/reports/coverage-trend.jsonl`
- 总记录数: **≥60** 条
- 门禁要求: ≥20 条
- 包含: C 和 Python 覆盖率趋势

### 3.3 构建元数据

- 元数据文件: `.yuleosh/metrics/build-metadata.jsonl`
- 每条记录包含: build_id, timestamp, commit, status, layer, tool_versions, files_changed

### 3.4 缺陷逃逸数据 — Sprint E 新增

- 数据文件: `.yuleosh/reports/defect-escape.jsonl`
- 每条记录包含: timestamp, total_defects, escaped_defects, escape_rate, stage

### 3.5 Profile 变更审计 — Sprint E 新增

- 审计日志: `.yuleosh/reports/profile-audit.jsonl`
- 每次变更记录: timestamp, user, old_profile, new_profile, commit, reason
- 查询命令: `yuleosh config profile audit`

### 3.6 工具版本记录 — Sprint E 更新

- 版本文件: `.yuleosh/config/tools-version.yaml`
- 新增 `approval` 字段: level, date, approver, pr
- 变更流程文档: `docs/tool-version-change-process.md`

---

## 4. 门禁判别

| 判定项 | 要求 | 数据来源 | 状态 |
|:-------|:-----|:---------|:-----|
| 构建成功率 ≥95% | PA 2.2 MP, §21.1 | process-kpi.jsonl | ✅ |
| 回归触发率 ≤5% | PA 2.2 MP, §21.2 | process-kpi.jsonl | ✅ |
| Required 违规 ≤48h 修复 | PA 2.2 MP, §21.4 | misra-trend.jsonl | ⚠️ 待处理 |
| 缺陷逃逸率 ≤15% | Sprint E | defect-escape.jsonl | ✅ |
| C 代码覆盖率 ≥60% | CL2-E03 | c-coverage.json | ✅ |
| 趋势数据 ≥90 条 | MP-01 | misra-trend.jsonl | ✅ |
| 构建元数据 ≥20 条 | MP-04/MP-08 | build-metadata.jsonl | ✅ |
| 工具版本变更审批 | RI-04 | tools-version.yaml | ✅ |
| Profile 变更可追溯 | G-33 | profile-audit.jsonl | ✅ |

**总体判定**: ✅ 全部门禁通过（除 Required 违规修复时效需持续跟踪）

---

## 5. 异常点说明

| # | 日期 | 异常类型 | 描述 | 根因 | 修复状态 |
|:-:|:----:|:---------|:-----|:-----|:---------|
| 1 | — | 构建失败 | 构建失败记录 (共 1) | 见 CI 日志 | ✅ |
| 2 | — | 回归触发 | 回归触发 (共 1) | 代码引入缺陷或配置问题 | ✅ |

> **说明**: 具体异常点需在逐次构建的 CI 日志中定位。本基线仅记录统计概要。

---

## 6. 数据采集范围

- **最早数据点**: 2026-05-20T15:10
- **最新数据点**: 2026-06-18T10:10
- **总数据点数**: 30
- **采集工具**: yuleOSH CI KPI 引擎 (`src/yuleosh/ci/kpi.py`)、C Coverage Runner (`scripts/run_c_coverage.py`)、Profile Audit (`src/yuleosh/ci/profile.py`)
- **存储格式**: JSONL/JSON/YAML

---

## 7. 维护说明

- **更新周期**: 每次 PR 合并或 CI 运行后自动更新
- **KPI 更新**: `python3 -m yuleosh.ci.kpi` (记录过程稳定性) + `python3 scripts/run_c_coverage.py` (C 覆盖率)
- **基线重置**: 当流程发生重大变化时 (如工具链升级、流水线重构)，需重新建立基线
- **版本管理**: 本文件纳入 Git 版本管理，变更记录可在 Git log 中追溯

---

*本文档由 yuleOSH KPI 基线引擎 + C Coverage Runner 生成，满足 ASPICE CL2 PA 2.2 MP 过程测量要求及 Sprint E 修复要求。*
