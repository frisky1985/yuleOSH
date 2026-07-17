# yuleOSH Knowledge Graph — P2 Spec Delta

> **版本**: v2.3.0-draft
> **状态**: 草案
> **作者**: 小马 🐴 (质量架构师)
> **日期**: 2026-07-17
> **审查人**: 小明 🧑‍💼 (需求/裁决), 小克 🐰 (开发/实现)
> **格式**: RFC 2119 (SHALL/SHALL NOT/SHOULD/MAY)

---

## 概述

本文档定义 Knowledge Graph P2 阶段的 spec 增量，覆盖 P0/P1 已交付模块之外的下一层能力。

### 当前状态回顾

| 能力 | P0 | P1 | P2 (本 delta) |
|------|:--:|:--:|:--------------:|
| RTM 导入 + 基础查询 | ✅ | ✅ | ✅ |
| 增量构建 + CI 集成 | — | ✅ | ✅ |
| **追溯矩阵自动生成** | — | — | **✅ NEW** |
| **度量报告 (Metrics)** | — | — | **✅ NEW** |
| **事件通知机制** | — | — | **✅ NEW** |
| ASPICE 审计可视化 | — | — | 🔶 P3 |
| Merge Gate 集成 | — | — | 🔶 P3 |

### 总则

1. **向后兼容**: 所有新增功能 SHALL NOT 修改 P0/P1 已有 API 签名和行为
2. **增量交付**: 每个新增模块独立可验证，不依赖其他 P2 模块
3. **可观测**: 所有模块通过 CLI 和日志输出可观测结果

---

## 1. 追溯矩阵自动生成 (KG-40 实现)

### KG-40-RTM: 追溯矩阵生成

**SHALL** — 系统 SHALL 提供从知识图谱自动生成追溯矩阵（RTM）的能力。

**SHALL** — RTM 生成 SHALL 支持以下输出格式：
- **Markdown** — 人类可读的表格，与现有 `requirement-traceability-matrix.md` 格式兼容
- **HTML** — 带样式和交互的网页，可直接用于审计演示
- **CSV** — 逗号分隔值，可直接导入 Excel/飞书多维表格

**SHALL** — RTM 内容 SHALL 包含以下列：
- `Requirement ID` — 需求编号
- `Statement` — 需求陈述摘要（前 80 字符）
- `Test Files` — 覆盖该需求的测试文件列表
- `Test Functions` — 覆盖该需求的测试函数列表
- `Code Files` — 实现该需求的代码文件列表
- `Status` — 覆盖状态 (covered / partial / uncovered)
- `Confidence` — 追溯置信度标签 (explicit / derived / heuristic)

**SHALL** — RTM 生成 SHALL 支持按层过滤：
- `--layer unit` — SWE.4 单元测试覆盖
- `--layer integration` — SWE.5 集成测试覆盖
- `--layer sil` — SIL 仿真测试
- `--layer hil` — HIL 硬件测试
- `--layer system` — 系统测试

**SHALL** — `yuleosh kg report rtm` CLI 命令 SHALL 触发 RTM 生成。

### KG-40-RTM-ACC: 验收判定

| ID | 条件 | 预期结果 |
|----|------|----------|
| ACC-RTM-01 | GIVEN 已引导的知识图谱 WHEN 执行 `yuleosh kg report rtm --format markdown` | THEN 输出包含所有 Requirement 节点及其测试/代码覆盖 |
| ACC-RTM-02 | GIVEN 已引导的知识图谱 WHEN 执行 `yuleosh kg report rtm --format html` | THEN 输出为有效的 HTML 表格文件 |
| ACC-RTM-03 | GIVEN 已引导的知识图谱 WHEN 执行 `yuleosh kg report rtm --format csv` | THEN 输出为有效的 CSV 文件，可用 Excel 打开 |
| ACC-RTM-04 | GIVEN 有未覆盖需求 WHEN 生成 RTM | THEN 对应行的 Status 列为 `uncovered` |

---

## 2. 度量报告 (KG-METRICS)

### KG-METRICS-01: 度量计算

**SHALL** — 系统 SHALL 提供从知识图谱生成度量报告的能力。

**SHALL** — 度量报告 SHALL 包含以下指标：

#### 2.1 覆盖率指标
- `total_requirements` — 总需求数
- `covered_requirements` — 有 covers 边的需求数
- `uncovered_requirements` — 无 covers 边的需求数
- `coverage_percentage` — 覆盖率百分比

#### 2.2 测试分布
- `tests_by_layer` — 按测试层分组的测试文件/函数数
- `tests_by_status` — 按最近运行状态分组的测试数

#### 2.3 图健康度
- `orphan_code_files` — 孤立代码文件数
- `orphan_test_files` — 孤立测试文件数
- `low_confidence_edges` — 低置信度边数
- `edges_by_type` — 按边类型分布的统计

#### 2.4 变更趋势 (跨快照)
- `trend_nodes` — 节点数变化趋势
- `trend_edges` — 边数变化趋势  
- `trend_coverage` — 覆盖率变化趋势

**SHALL** — 趋势数据 SHALL 从快照中提取，对比当前快照与最近 N 个快照。

**SHALL** — `yuleosh kg report metrics` CLI 命令 SHALL 触发度量报告生成。

**MAY** — 度量报告 MAY 以 JSON 格式输出，用于被其他工具消费。

### KG-METRICS-01-ACC: 验收判定

| ID | 条件 | 预期结果 |
|----|------|----------|
| ACC-MET-01 | GIVEN 已引导的知识图谱 WHEN 执行 `yuleosh kg report metrics` | THEN 输出包含覆盖率、测试分布、图健康度 |
| ACC-MET-02 | GIVEN 有 2 个以上快照 WHEN 生成度量报告 | THEN 输出包含覆盖率趋势数据 |
| ACC-MET-03 | GIVEN 有孤立节点 WHEN 生成度量报告 | THEN 输出标记 orphan 节点数 |

---

## 3. 事件通知机制 (KG-EVENT)

### KG-EVENT-01: 事件总线

**SHALL** — 系统 SHALL 提供一个轻量级事件总线，在知识图谱关键操作时发出事件通知。

**SHALL** — 事件总线 SHALL 支持以下事件类型：
- `node.created` — 节点创建
- `node.updated` — 节点更新
- `node.deleted` — 节点软删除
- `edge.created` — 边创建
- `edge.updated` — 边更新
- `edge.deleted` — 边删除
- `snapshot.created` — 快照创建
- `build.completed` — 增量构建完成
- `impact.ready` — 影响分析结果就绪

**SHALL** — 每个事件 SHALL 包含以下信息：
- `event_type` — 事件类型
- `timestamp` — ISO 8601 时间戳
- `source` — 事件来源模块名称
- `data` — 事件相关数据（节点/边信息）

**SHALL** — 事件订阅者 SHALL 支持 `on(event_type, callback)` 注册模式。

**SHALL** — 事件总线 SHALL 支持 `once(event_type, callback)` 一次性订阅模式。

**SHALL** — 事件总线 SHALL 在发出事件时捕获异常，不中断事件来源。

### KG-EVENT-02: CI 钩子集成

**SHALL** — `build.completed` 事件 SHALL 触发以下操作：
1. 自动运行 `impact_analysis` 检测受影响的需求和测试
2. 将影响分析结果写入事件 `data` 中

**SHOULD** — 事件系统 SHOULD 支持以下钩子注册方式：
- Python 回调函数
- Shell 命令（通过 `subprocess`）

**MAY** — CI 钩子 MAY 在增量构建完成后自动调用外部 webhook URL。

### KG-EVENT-ACC: 验收判定

| ID | 条件 | 预期结果 |
|----|------|----------|
| ACC-EVT-01 | GIVEN 创建新节点 WHEN store.upsert_node() 调用 | THEN `node.created` 事件被发出 |
| ACC-EVT-02 | GIVEN 注册了事件回调 WHEN 匹配事件类型被触发 | THEN 回调被调用，且 data 包含事件信息 |
| ACC-EVT-03 | GIVEN 增量构建完成 WHEN build.completed 事件发出 | THEN data 中包含影响分析结果 |

---

## 4. CLI 命令增量

### 新增命令

```bash
yuleosh kg report rtm [--format {markdown,html,csv}] [--layer {unit,integration,sil,hil,system}] [--output FILE]
yuleosh kg report metrics [--format {json,text}] [--trend N]
yuleosh kg events listen [--duration SECONDS] [--filter EVENT_TYPE]
```

### 修改命令

无修改。所有新增命令为独立子命令。

---

## 5. 向后兼容性声明

| 已有 API/CLI | 兼容性 | 说明 |
|-------------|--------|------|
| `KGStore` 所有方法 | ✅ 完全兼容 | 事件通过装饰器注入，方法签名不变 |
| `queries.py` 所有函数 | ✅ 完全兼容 | 签名和行为不变 |
| `importer.py` 所有函数 | ✅ 完全兼容 | 新增事件通知不影响原有逻辑 |
| `kg_cli.py` 所有命令 | ✅ 完全兼容 | 新增子命令不修改现有子命令行为 |
| `__init__.py` 导出 | ✅ 完全兼容 | 通过增量导入新增模块 |

---

## 6. 验收判定矩阵总表

| ID | KG-Spec关联 | 优先级 | 判定标准 |
|----|------------|:------:|----------|
| ACC-RTM-01 | KG-40 | P0 | RTM Markdown 输出正确 |
| ACC-RTM-02 | KG-40 | P1 | RTM HTML 输出有效 |
| ACC-RTM-03 | KG-40 | P1 | RTM CSV 输出有效 |
| ACC-RTM-04 | KG-40 | P0 | 未覆盖需求标记为 uncovered |
| ACC-MET-01 | KG-METRICS | P0 | 度量报告包含完整指标 |
| ACC-MET-02 | KG-METRICS | P1 | 快照趋势数据可用 |
| ACC-MET-03 | KG-METRICS | P0 | 孤立节点标记 |
| ACC-EVT-01 | KG-EVENT | P0 | 节点创建事件发出 |
| ACC-EVT-02 | KG-EVENT | P0 | 事件回调正确触发 |
| ACC-EVT-03 | KG-EVENT | P1 | 构建完成事件含影响分析 |

---

## 7. 依赖关系

```
P2 模块依赖结构:

spec-delta-kg-next.md
├── reporter.py (P2-1: RTM + P2-2: Metrics)
│   ├── 依赖: store.py (KGStore CRUD) ✅
│   ├── 依赖: queries.py (get_graph_stats, impact_analysis) ✅
│   └── 输出: markdown/html/csv
│
└── events.py (P2-3: 事件通知)
    ├── 依赖: store.py ✅ (通过装饰器注入)
    ├── 依赖: kg_cli.py ✅ (events子命令)
    └── 输出: 事件日志 / 回调 / shell钩子
```

---

*本文档由小马 🐴 起草，待小明 🧑‍💼 终审和小克 🐰 实现确认。*
