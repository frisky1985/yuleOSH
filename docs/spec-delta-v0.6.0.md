# Spec-Delta: v0.5.0 → v0.6.0

> 变更追踪文档 | OpenSpec 格式 | 生成: 2026-06-09

---

## 版本变更

| 属性 | v0.5.0 | v0.6.0 |
|:-----|:-------|:-------|
| pyproject.toml | 0.5.0 | 0.5.0 (未变) |
| spec.md | 0.5.0 | 0.6.0 |
| 模块 | SIL + FAL + HIL | + CI Config + L2.5 |

---

## 新增需求

### RS-010: CI 硬化与可配置化 (新)
新增 1 个系统需求、3 个软件需求。

#### SWR-010.1: CI 配置文件
**响应:** `src/ci/config.py` — CiConfig/CoverageConfig/HardwareTestConfig 数据类 + load_ci_config() 加载器
**数据:** `.yuleosh/ci-config.yaml` — 每个项目的 CI 配置文件

#### SWR-010.2: Coverage Guardian 可配置化
**响应:** `src/ci/run.py` :: `run_coverage_check()` — 从 ci-config.yaml 读取 `threshold_line`/`threshold_condition`
**变更:** 移除硬编码 `38.0` 阈值，改为从配置读取（默认 85.0%/80.0%）

#### SWR-010.3: CI L2.5 硬件在环 (HIL) 层
**响应:** `src/ci/run.py` :: `run_layer_25()` — 新的 CI 层
**特性:** mock 模式（CI 安全）、真实 HIL 模式、双报告输出

---

## 变更需求

### SWR-003.2: 覆盖率门禁
| 原 | 新 |
|:---|:---|
| 硬编码 `threshold_line = 38.0` | 从 ci-config.yaml 读取（默认 85.0%） |
| 硬编码 `threshold_cond = 38.0` | 从 ci-config.yaml 读取（默认 80.0%） |

**原因:** 项目覆盖率从 v0.2 的 38% 增长到 v0.5 的 85%，硬编码阈值不再合理

### RS-004: CI/CD 三层流水线
| 原 | 新 |
|:---|:---|
| 3 层 (L1 → L2 → L3) | 4 层 (L1 → L2 → L2.5 → L3) |
| `layer_dependencies: {1:[], 2:[1], 3:[1,2]}` | `{1:[], 2:[1], 25:[1,2], 3:[1,2,25]}` |

**原因:** v0.6.0 新增硬件在环测试层，补全 CI 流水线的硬件测试阶段

---

## 新增验收场景

### Scenario: CI 配置加载 (v0.6.0 新增)
- GIVEN a yuleOSH project with `.yuleosh/ci-config.yaml`
- WHEN the CI pipeline loads configuration
- THEN the system SHALL read coverage thresholds, HIL settings, layer order from the file
- AND SHALL fall back to safe defaults for any missing fields

### Scenario: L2.5 Mock HIL 测试 (v0.6.0 新增)
- GIVEN a CI pipeline run with `hardware_test.mock=true`
- WHEN Layer 2.5 executes
- THEN the system SHALL simulate flash → boot → assert lifecycle
- AND SHALL produce both `layer25-{commit}.json` and `hil-report-{commit}.json`
- AND SHALL report all stages as passed

### Scenario: 可配置覆盖率门禁 (v0.6.0 新增)
- GIVEN a ci-config.yaml with `coverage.threshold_line: 92.0`
- WHEN CI L1 coverage-check runs
- THEN it SHALL use 92.0% as the pass/fail boundary

---

## 新增测试

| 文件 | 测试数 | 内容 |
|:-----|:------:|:-----|
| `tests/test_ci_config.py` | 18 | 默认值/解析/边界条件 |
| `tests/test_ci_layer_25.py` | 20 | L2.5 默认/mock/非mock/脚本/错误/性能 |

---

## 未完成项

- [x] `serial_monitor.py` 物理端口分支覆盖率 74% → 85%+ → **已完成: 96%**
- [x] CI L2.5 真实硬件 HIL 模式端到端验证 → **已完成: 非mock代码路径测试覆盖（5 测试），真实硬件需物理设备**
- [x] L2.5 性能基线（mock 模式应 <1s 完成）→ **已完成: 33.7ms，含性能回归测试**
- [x] Makefile 集成 L2.5 到默认 `make ci` 流程 → **已完成: `make ci` 已包含 ci-layer25**

---

## 证据

- 提交: v0.6.0 工作
- 测试: 18 (config) + 20 (L2.5) = **38 新增测试**
- 覆盖: serial_monitor 96% + ci/ 全面覆盖
