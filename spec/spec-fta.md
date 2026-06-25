# yuleOSH 故障树分析（FTA）模块 — 软件需求规格

> **版本**: v1.0.0  
> **状态**: 初始正式规约  
> **作者**: 小马 🐴 (质量架构师)  
> **日期**: 2026-06-20  
> **规范文体**: RFC 2119 (SHALL/SHALL NOT/SHOULD/MAY)  
> **输入源**: ISO 26262-10 §6 / IEC 61025 / AIAG-VDA FMEA 手册 / 团队 FMEA 模块经验

---

## 目录

1. [核心定位与模块关系](#1-核心定位与模块关系)
2. [Spec 契约层](#2-spec-契约层不可变)
   - A. [核心数据结构](#a-核心数据结构-fta-01fta-05)
   - B. [分析功能](#b-分析功能-fta-06fta-10)
   - C. [可视化与协作](#c-可视化与协作-fta-11fta-14)
   - D. [与现有模块集成](#d-与现有模块集成-fta-15fta-18)
   - E. [行业约束](#e-行业约束-fta-19fta-20)
3. [实现指引](#3-实现指引可变)
4. [术语表](#4-术语表)

---

## 1. 核心定位与模块关系

### 1.1 定位

FTA 模块是 yuleOSH 体系中的 **演绎式安全分析** 引擎，与现有的 FMEA（归纳式）构成完整的失效分析双引擎。

| 维度 | FMEA | FTA |
|:-----|:-----|:-----|
| 方向 | 自底向上（Inductive） | 自顶向下（Deductive） |
| 起点 | "这个部件可能怎么坏？" | "这个系统故障怎么发生的？" |
| 结构 | 表格（行记录） | 树（逻辑门 + 事件） |
| 输出 | RPN / Action Priority | 最小割集 / 顶事件概率 |
| 核心问题 | 严重度 × 频度 × 探测度 | 故障逻辑组合 × 底事件概率 |
| 标准 | AIAG-VDA FMEA 手册 | ISO 26262-10, IEC 61025 |

### 1.2 互补关系

```
┌─────────────────────────────────────────────────┐
│              yuleOSH 失效分析体系                    │
│                                                     │
│   FMEA (归纳)                    FTA (演绎)          │
│   ┌──────────────────┐       ┌──────────────────┐   │
│   │ 部件/功能 → 失效  │       │ 系统故障 → 逻辑门  │   │
│   │ 自底向上展开      │ ◄──► │ 自顶向下分解      │   │
│   │ 表格 + 矩阵      │       │ 树 + 割集         │   │
│   └────────┬─────────┘       └────────┬─────────┘   │
│            │                           │            │
│            ▼                           ▼            │
│   ┌────────────────────────────────────────────┐   │
│   │           共享故障数据库（Knowledge Base）     │   │
│   │   - 基本事件 = 知识条目 / FMEA 失效原因       │   │
│   │   - DTC 双向追溯                             │   │
│   │   - 安全目标（Safety Goal）映射              │   │
│   └────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### 1.3 模块依赖

| 依赖模块 | 用途 | 契约级别 |
|---------|------|---------|
| store | 故障树持久化、版本快照、分析结果存储 | 强制 |
| kb（知识管理） | 基本事件 → 知识条目追溯、DTC 关联 | 强制 |
| fmea | 失效原因共享、失效模式交叉引用 | 强制 |
| evidence | 割集 → 测试用例映射、证据绑定 | 强制 |
| pipeline | 故障树审核流、割集验证阶段 | 强制 |
| ci | 故障树 YAML schema 校验、割集回归检查 | 强制 |

### 1.4 行业约束映射总表

| # | 约束 | 覆盖条目 |
|---|------|---------|
| 1 | ISO 26262 安全目标追溯 | FTA-08, FTA-19 |
| 2 | ISO 26262 ASIL 分解与门禁 | FTA-01, FTA-02, FTA-08, FTA-19 |
| 3 | IEC 61025 割集算法合规 | FTA-06, FTA-07 |
| 4 | ASPICE SYS.3 系统需求分析 | FTA-20 |
| 5 | 最小割集 → 测试用例覆盖 | FTA-17 |
| 6 | 故障树版本管理与审计 | FTA-13, CROSS-04 |
| 7 | OpenPSA / XML 导入导出 | FTA-14 |
| 8 | 跨团队协作编辑 | FTA-12 |
| 9 | 嵌入式 ECU 实时约束 | FTA-08（底事件概率数据来自现场） |
| 10 | 与 FMEA 共享故障库 | FTA-10, FTA-16 |

---

## 2. Spec 契约层（不可变）

### A. 核心数据结构（FTA-01 ~ FTA-05）

---

#### FTA-01: 顶事件定义（Top Event）

**SHALL** — 系统 SHALL 支持创建、读取、更新、删除故障树的顶事件（Top Event）。

**SHALL** — 每个顶事件 SHALL 包含以下强制字段：
- `id` (UUID — 全局唯一标识)
- `fta_id` (字符串 — 可读编号，如 `FTA-BRAKE-001`)
- `title` (字符串 — 顶事件标题，如 "制动距离超标")
- `description` (Markdown — 系统级故障现象描述)
- `safety_goal_ref` (字符串数组，可选 — 关联的安全目标 ID 列表，如 `["SG-BRAKE-001"]`)
- `asil` (枚举: `ASIL_A`/`ASIL_B`/`ASIL_C`/`ASIL_D`/`QM` — 顶事件继承的安全等级)
- `system` (字符串 — 所属系统/子系统名称)
- `status` (枚举: `draft`/`review_pending`/`approved`/`deprecated`——故障树生命周期)
- `created_by` (用户引用)
- `updated_by` (用户引用)
- `created_at` (时间戳)
- `updated_at` (时间戳)
- `version` (语义版本号: major.minor.patch)

**SHALL** — 每个顶事件 SHALL 有且仅有一个根节点（Root Node），根节点的类型固定为顶事件节点。

**SHALL** — 系统 SHALL 支持以顶事件为入口展开整棵故障树。

**SHOULD** — 系统 SHOULD 在创建时自动生成 `fta_id`（按序列递增，如 `FTA-2026-0001`）。

**SHOULD** — 当 `safety_goal_ref` 引用的安全目标发生变更时，系统 SHOULD 通知顶事件负责人进行一致性审查。

---

#### FTA-02: 逻辑门（Gates）

**SHALL** — 系统 SHALL 支持以下逻辑门类型：

| 门类型 | 标识符 | 含义 | 逻辑语义 |
|--------|--------|------|---------|
| AND 门 | `AND` | 所有子事件同时发生则输出发生 | `P_out = ∏ P_sub_i` |
| OR 门 | `OR` | 任一子事件发生则输出发生 | `P_out = 1 - ∏(1 - P_sub_i)` |
| 优先 AND 门 | `PAND` | 子事件按特定顺序依次发生则输出发生 | 时序约束下的 AND |
| 禁止门 | `INHIBIT` | 条件事件为真时输入事件导致输出 | 条件使能下的 AND |

**SHALL** — 每个逻辑门 SHALL 包含以下强制字段：
- `id` (UUID)
- `gate_type` (枚举: `AND`/`OR`/`PAND`/`INHIBIT`)
- `parent_node_id` (UUID — 父节点 ID，必须指向事件节点或另一个门)
- `parent_connection` (枚举: `top_event`/`intermediate_event`/`gate_output`)
- `description` (字符串，可选 — 门的功能描述)
- `condition` (字符串，可选 — 仅 `INHIBIT` 门使用，描述使能条件)

**SHALL** — 系统 SHALL 验证故障树的拓扑结构合法性：
- 根节点必须是顶事件
- 每个非叶节点必须至少有一个子节点
- 不得存在循环引用（系统性环路检测）
- 叶节点必须是基本事件或未展开事件

**SHALL** — 当逻辑门类型为 `PAND` 时，系统 SHALL 要求用户指定子事件的发生顺序。

**SHALL NOT** — INHIBIT 门 SHALL NOT 在无 `condition` 字段时使用；系统 SHALL 在校验阶段拒绝创建不完整的 INHIBIT 门。

**MAY** — 系统 MAY 在 v2.0 中扩展支持 XOR 门（异或）和 NOT 门（非）。

---

#### FTA-03: 基本事件（Basic Event）

**SHALL** — 系统 SHALL 支持创建、读取、更新、删除故障树的叶节点——基本事件（Basic Event）。

**SHALL** — 每个基本事件 SHALL 包含以下强制字段：
- `id` (UUID)
- `event_type` (枚举: `basic`/`undeveloped`/`house`/`condition`——基本/未展开/房型/条件事件)
- `title` (字符串 — 事件标题，如 "左前轮速传感器断路")
- `description` (Markdown — 事件详细描述)
- `failure_rate` (浮点数，可选 — 失效率 λ，单位: FIT/`10⁻⁹/h`；仅 `basic` 类型使用)
- `mission_time` (浮点数，可选 — 任务时间 T，单位: h；仅 `basic` 类型使用)
- `probability` (浮点数，可选 — 直接概率值 P，覆盖 `failure_rate × mission_time` 的计算结果)
- `exposure_time` (浮点数，可选 — 暴露时间，用于间歇故障建模)
- `repair_rate` (浮点数，可选 — 修复率 μ，用于可修复系统定量分析)
- `knowledge_ref` (UUID，可选 — 关联的 KB 知识条目 ID，参见 FTA-15)
- `fmea_ref` (UUID，可选 — 关联的 FMEA 条目 ID，参见 FTA-16)
- `dtc_ref` (字符串数组，可选 — 关联的 DTC 编码列表)
- `source` (枚举: `field_data`/`lab_test`/`expert_estimate`/`handbook`/`fmea_derived`——概率来源)
- `uncertainty_bounds` (结构体 `{ lower, upper }`，可选 — 概率置信区间，对应 IEC 61025 不确定性处理)

**SHALL** — 基本事件类型语义：

| `event_type` | 含义 | 是否可定量 |
|-------------|------|-----------|
| `basic` | 基本事件——最基本的失效原因，有概率数据 | 是 |
| `undeveloped` | 未展开事件——没有进一步分析的子故障树 | 否（定性参与） |
| `house` | 房型事件——固定为真（发生）或假（不发生） | 条件过滤 |
| `condition` | 条件事件——用于 INHIBIT 门的使能条件 | 布尔参与 |

**SHALL** — 当 `probability` 字段为空但 `failure_rate` 和 `mission_time` 均存在时，系统 SHALL 自动计算：

```
P = 1 - e^(-λ × T)    （不可修复系统，指数分布）
```

当 `λ × T < 0.01` 时，允许近似为 `P ≈ λ × T`。

**SHALL** — 当 `probablity` 和 `failure_rate` 均不存在时，该基本事件 SHALL 被标记为 `probabilty_undefined`，在定量分析中排除该事件（纳入定性分析）。

**SHALL** — 系统 SHALL 维护基本事件的引用完整性：当基本事件被关联的 KB 条目或 FMEA 条目标记为软删除时，系统 SHALL 在基本事件上添加 `ref_deleted` 标记，但不自动删除基本事件本身。

**SHOULD** — 当基本事件关联的 FMEA 条目发生 RPN/AP 变更时，系统 SHOULD 标记该基本事件为 `pending_review`。

---

#### FTA-04: 中间事件（Intermediate Event）

**SHALL** — 系统 SHALL 支持创建、读取、更新、删除故障树的中间事件节点（Intermediate Event）。

**SHALL** — 中间事件 SHALL 包含以下强制字段：
- `id` (UUID)
- `title` (字符串 — 事件描述，如 "左前轮速信号异常")
- `description` (Markdown，可选 — 详细描述)
- `parent_gate_id` (UUID — 所属的上级逻辑门)
- `sub_gate_id` (UUID — 下级的子逻辑门 ID)
- `is_negated` (布尔，默认 `false`——标记该中间事件是否取非)

**SHALL** — 中间事件 SHALL 连接一个逻辑门的输出和一个下层逻辑门的输入，形成树状结构。

**SHALL** — 中间事件不得是树的叶节点——每个中间事件 SHALL 必须有子逻辑门。

**SHALL NOT** — 系统 SHALL NOT 允许中间事件直接包含基本事件作为内容；中间事件仅作为逻辑门之间的结构节点。

**MAY** — 系统 MAY 允许中间事件引用其他故障树的顶事件（构成跨树引用，参见 FTA-05）。

---

#### FTA-05: 条件 / 转移门（Transfer Gate）

**SHALL** — 系统 SHALL 支持两种转移机制：

1. **相同事件引用（Shared Event）**: 同一基本事件在一棵故障树中重复出现（共享）
2. **跨树转移（Transfer Gate）**: 一棵故障树的子树引用另一棵故障树的完整子树

**SHALL** — 转移门 SHALL 包含以下字段：
- `id` (UUID)
- `transfer_type` (枚举: `in`/`out`——转入/转出)
- `target_fta_id` (字符串——目标故障树的 `fta_id`)
- `target_node_id` (UUID——目标故障树中的节点 ID)
- `label` (字符串——转移标签，用于树上的引用标记)
- `bidirectional` (布尔——是否双向同步；默认 `true`)

**SHALL** — 当转移门类型为 `out`（转出）且被引用的目标故障树发生变更时，系统 SHALL 自动将引用方的故障树标记为 `pending_review`。

**SHALL** — 系统 SHALL 在故障树校验阶段检测循环转移引用（A → B → A），并拒绝创建循环引用。

**SHALL** — 共享基本事件（同一棵故障树中 + 跨树引用中重复出现的基本事件）SHALL 视为同一个事件，定量分析中 SHALL 使用同一概率值。

**SHOULD** — 系统 SHOULD 在故障树可视化中标注转移节点，使用标准 Transfer Triangle 符号（三角形 + 标签）。

---

### B. 分析功能（FTA-06 ~ FTA-10）

---

#### FTA-06: 最小割集自动计算（Minimal Cut Set）

**SHALL** — 系统 SHALL 支持自动计算故障树的最小割集（Minimal Cut Sets, MCS）。

**SHALL** — 最小割集算法 SHALL 满足以下要求：
- 正确处理 AND/OR/PAND/INHIBIT 逻辑门
- 返回的所有割集必须是 **最小** 的（移除任一基本事件后不再构成割集）
- 结果 SHALL 按割集阶数（包含的基本事件数量）升序排列
- 结果 SHALL 标记一阶割集（单点故障——Single Point Failure）

**SHALL** — 系统 SHALL 支持以下最小割集求解算法，用户可配置选择：

| 算法 | 适用场景 | 复杂度 |
|------|---------|--------|
| **自底向上 (Bottom-Up)** | 中小规模树（<100 基本事件） | O(n²) |
| **MOCUS (Method of Obtaining Cut Sets)** | 通用 | O(2^n) 最坏 |
| **BDD (Binary Decision Diagram)** | 大规模树（建议默认） | 多项式期望 |

**SHALL** — 当故障树规模超过预设阈值（默认 200 节点）时，系统 SHALL 自动切换至 BDD 算法并提示用户。

**SHALL** — 最小割集计算结果 SHALL 包含：
- `cut_sets` (数组 — `[[event_id_1, event_id_2, ...], ...]`)
- `total_count` (整数 — 割集总数)
- `order_distribution` (映射 — `{ "order_1": count, "order_2": count, ... }`)
- `single_point_failures` (数组 — 一阶割集列表，即单点故障事件)
- `computation_time_ms` (整数 — 计算耗时)
- `algorithm_used` (字符串 — 使用的算法名称)
- `computed_at` (时间戳)

**SHALL** — 最小割集计算 SHALL 为异步操作：当故障树较大时，系统 SHALL 提供进度反馈（百分比 + 预估剩余时间）。

**SHALL** — 系统 SHALL 在执行最小割集计算前验证故障树的完备性（所有叶节点必须为基本事件或未展开事件）。

**SHALL NOT** — 系统 SHALL NOT 将未展开事件（`undeveloped`）纳入定量割集计算（定性分析中包含）。

---

#### FTA-07: 定性分析（Qualitative Analysis）

**SHALL** — 系统 SHALL 根据最小割集结果进行定性分析：

1. **单点故障分析** — 列出所有一阶割集；标记每个单点故障及其关联的安全等级（ASIL）
2. **割集阶数分析** — 按阶数统计分布；高阶数割集（≥4 阶）标注为"组合依赖"（需多条件同时成立）
3. **结构重要性** — 基于故障树拓扑结构计算每个基本事件的结构重要性度（Structural Importance）

**SHALL** — 结构重要性度 SHALL 遵循以下定义：

```
I_struct(i) = (所有包含事件 i 的最小割集数) / (全部最小割集数)
```

**SHALL** — 定性分析报告 SHALL 按以下优先级排序事件：

| 优先级 | 判定条件 | 颜色标记 |
|--------|---------|---------|
| P1 (Critical) | 单点故障 + ASIL C/D | 🟥 红色 |
| P2 (High) | 单点故障 + ASIL A/B | 🟧 橙色 |
| P3 (Medium) | 一阶 + QM / 二阶集合 | 🟨 黄色 |
| P4 (Low) | 三阶及以上 | ⬜ 无色 |

**SHALL** — 系统 SHALL 将定性分析结果以表格形式输出，包含：事件 ID、事件标题、割集阶数、结构重要性度、优先级等级、ASIL 级别。

**SHOULD** — 系统 SHOULD 将 P1 级别事件自动提交至知识债务审查队列（Knowledge Debt Review Queue）。

---

#### FTA-08: 定量分析（Quantitative Analysis）

**SHALL** — 系统 SHALL 支持基于底事件概率的顶事件概率定量计算。

**SHALL** — 定量计算的数学基础：

- AND 门输出：`P_out = ∏ᵢ P_subᵢ`
- OR 门输出：`P_out = 1 - ∏ᵢ (1 - P_subᵢ)`
- 顶事件概率：通过故障树结构递归计算（精确值）或通过最小割集容斥原理（近似值）

**SHALL** — 系统 SHALL 提供以下概率计算方法：

| 方法 | 精度 | 说明 |
|------|------|------|
| **精确递归 (Exact Recursive)** | 精确 | 直接按故障树结构计算，适用于小规模树 |
| **容斥近似 (Inclusion-Exclusion)** | 可配置精度 | 基于最小割集的容斥级数截断（默认一阶 + 二阶） |
| **Esary-Proschan 上界** | 保守上界 | `P_top ≤ 1 - ∏(1 - P_cs_i)`，用于安全分析 |
| **Monte Carlo 仿真** | 统计近似 | 配置采样次数（默认 10⁶），输出均值 + 置信区间 |

**SHALL** — 定量分析用于概率计算的基本事件优先顺序：
1. 使用用户直接提供的 `probablity`
2. 若不存在，计算 `1 - e^(-λ × T)`
3. 若 `failure_rate` 也不存在，标记为 `probabilty_undefined`，排除出定量分析

**SHALL** — 定量分析报告 SHALL 包含：
- `top_event_probability` (浮点数 — 顶事件概率)
- `top_event_unavailability` (浮点数 — 不可用度，如适用可修复系统)
- `expected_number_of_failures` (浮点数 — 故障期望次数)
- `method_used` (字符串)
- `excluded_events` (数组 — 因概率数据缺失而排除的基本事件列表)
- `computation_time_ms`
- `computed_at`

**SHALL** — 当定量分析中排除的基本事件数量超过全部基本事件的 20% 时，系统 SHALL 输出警告：分析结果可能不完整。

**SHOULD** — 系统 SHOULD 允许用户按 ASIL 等级过滤定量分析（例如，仅关注 ASIL C/D 相关割集的定量结果）。

**SHALL** — 顶事件概率分析结果 SHALL 可关联到安全目标（Safety Goal）的定量安全要求。例如：若安全目标要求 `P_top < 10⁻⁷/h`，系统 SHALL 支持将此阈值录入并在定量报告中对比。

---

#### FTA-09: 重要性排序（Fussell-Vesely / Birnbaum）

**SHALL** — 系统 SHALL 支持两种经典重要性测度计算：

1. **Fussell-Vesely (FV) 重要性**：

```
FV(i) = P(包含事件 i 的所有割集的并集) / P(顶事件)
```

含义：事件 i 对顶事件概率的贡献率。

2. **Birnbaum (B) 重要性**：

```
B(i) = P(顶事件 | 事件 i 发生) - P(顶事件 | 事件 i 不发生)
```

含义：事件 i 的概率变化对顶事件概率的边际影响。

**SHALL** — 重要性排序结果 SHALL 以降序排列，包含：
- 事件 ID、事件标题
- Fussell-Vesely 值（0–1 范围）
- Birnbaum 值（0–1 范围）
- 排序等级（由用户选择基于 FV 或 Birnbaum）

**SHALL** — 系统 SHALL 支持按重要性阈值筛选（如：仅展示 `FV > 0.01` 的事件）。

**SHOULD** — 系统 SHOULD 在仪表盘中高亮显示 `FV > 0.1` 且 ASIL C/D 的基本事件，将其列入重点关注清单。

**SHALL** — 重要性排序的输入数据源 SHALL 与定量分析（FTA-08）保持一致，使用同一次计算的概率数据。

**MAY** — 系统 MAY 在 v2.0 中扩展支持以下重要性测度：
- Risk Reduction Worth (RRW) = `1 / (1 - FV(i))`
- Risk Achievement Worth (RAW) = `B(i) / P_top + 1`
- Criticality Importance = `B(i) × P(i) / P_top`

---

#### FTA-10: 与 FMEA 条目的双向追溯

**SHALL** — 基本事件 SHALL 支持直接关联零个或多个 FMEA 条目 ID（参见 FTA-03 的 `fmea_ref` 字段）。

**SHALL** — FMEA 条目也 SHALL 支持反向关联 FTA 基本事件：在 FMEA 条目的详情页展示关联的 FTA 基本事件列表及其所属故障树。

**SHALL** — 双向追溯的实现 SHALL 在 store 层维护一张关联表 `fta_fmea_link`，包含：
- `link_id` (UUID)
- `fta_event_id` (UUID)
- `fmea_entry_id` (UUID)
- `link_type` (枚举: `cause_to_failure_mode`/`failure_mode_to_top_event`/`equivalent`)
- `semantic_note` (字符串，可选 — 关联语义说明)
- `created_at` (时间戳)
- `created_by` (用户引用)

**SHALL** — 当 FMEA 条目被软删除时，系统 SHALL 自动标记关联的 `fta_fmea_link` 为 `link_stale`，但保留记录以供审计。

**SHALL** — 当基本事件关联的 FMEA 条目发生变更时（如 `failure_cause` 更新），系统 SHALL 自动将该基本事件标记为 `pending_review`。

**SHALL** — 系统 SHALL 提供"FMEA → FTA 交叉分析报告"，展示：
- 每个 FMEA 失效原因在多少棵故障树中被引用
- 每个 FTA 基本事件关联的 FMEA 失效模式的失效链关系
- 未被任何 FTA 引用的 FMEA 条目（潜在缺失的顶事件分析）
- 未被任何 FMEA 覆盖的 FTA 基本事件（潜在缺失的失效模式分析）

**SHOULD** — 系统 SHOULD 在 FTA 最小割集报告中标注每个割集中包含的 FMEA 关联信息，帮助工程师快速定位失效模式。

---

### C. 可视化与协作（FTA-11 ~ FTA-14）

---

#### FTA-11: 故障树可视化

**SHALL** — 系统 SHALL 提供故障树的图形化展示。

**SHALL** — 故障树可视化 SHALL 使用标准符号体系：

| 节点类型 | 图形符号 | 说明 |
|---------|---------|------|
| 顶事件 | 矩形（顶部双线） | 系统故障描述 |
| 中间事件 | 矩形（单线） | 中间故障事件 |
| 基本事件 | 圆形 | 不可再分的基本失效 |
| 未展开事件 | 菱形 | 待进一步分析的子树 |
| 房型事件 | 房屋形 | 固定条件 |
| AND 门 | 门形（拱底平顶） | 所有输入同时发生 |
| OR 门 | 门形（拱顶平底） | 任一输入发生 |
| PAND 门 | AND 门 + 顺序标记 | 按序发生 |
| INHIBIT 门 | 六边形 | 条件使能 |
| 转移门 | 三角形（in/out 标签） | 跨树引用 |

**SHALL** — 故障树可视化 SHALL 支持以下交互操作：
- 展开/折叠子树
- 拖拽节点调整布局
- 点击节点跳转至事件详情
- 缩放（滚轮缩放 + 框选放大）
- 自动布局（层级树布局 / 正交布局）
- 导出为 SVG/PNG/PDF

**SHALL** — 系统 SHALL 在可视化中叠加分析结果标记：
- 一阶割集（单点故障）的叶子节点 SHALL 用红色边框高亮
- 包含高重要性（FV > 0.1）事件的路径 SHALL 用橙色高亮
- 概率缺失的基本节点用虚线边框标记

**SHALL** — 系统 SHALL 提供"文本树"呈现形式（作为图形化的降级替代）：

```
┌── [Top] 制动距离超标 (ASIL D)
│
├── OR ──┐
│        │
│  ┌─────┴─────┐
│  │ [IE-1] 制动力不足 │
│  │               │
│  ├── AND ──┐    │
│  │  │      │    │
│  │ BE-A   BE-B  │
│  │               │
│  └───────────────┘
│
└── [BE-C] 制动踏板传感器失效 (P1)
```

**SHOULD** — 系统 SHOULD 支持布局自定义（横向/纵向排列，节点间距配置）。

---

#### FTA-12: 多用户协作编辑

**SHALL** — 系统 SHALL 支持多用户同时编辑不同的故障树，或同一故障树的不同子树。

**SHALL** — 当多用户同时编辑同一棵故障树时，系统 SHALL 采用乐观锁（Optimistic Locking）+ 冲突检测机制：
- 每次保存时校验当前版本与用户加载时版本是否一致
- 不一致时提示冲突，要求用户合并（显示差异对比）后重新提交

**SHALL** — 编辑锁定机制：
- 用户可选择"锁定子树"（子树级别的编辑锁）
- 锁定后其他用户对该子树的编辑将被拒绝，提示锁定人信息
- 锁定超过 30 分钟无活动自动释放（可配置）

**SHALL** — 系统 SHALL 提供故障树注释功能：
- 节点级别注释（Markdown 格式）
- 注释可提及（@mention）其他用户
- 注释支持回复链

**SHOULD** — 系统 SHOULD 在修改时自动通知相关用户（故障树创建者、最近修改者、锁定联系人）。

**MAY** — 系统 MAY 提供实时协同预览（WebSocket 推送其它用户的编辑操作）。

---

#### FTA-13: 版本控制（变更追溯）

**SHALL** — 系统 SHALL 为每棵故障树维护完整的版本快照链。

**SHALL** — 每次保存（无论是否结构变更）SHALL 创建一个版本快照：
- 版本号递增规则：major.minor.patch
  - `patch`: 单节点属性修改（描述、概率值等）
  - `minor`: 结构变更（增/删节点、修改门类型等）
  - `major`: 顶事件变更 / 安全目标重新映射

**SHALL** — 每个版本快照 SHALL 包含：
- `version` (字符串)
- `snapshot` (JSON — 故障树的完整结构序列化)
- `change_summary` (字符串 — 用户填写的变更摘要)
- `changed_by` (用户引用)
- `created_at` (时间戳)
- `diff_with_previous` (字符串，可选 — 自动生成的变更差异描述)

**SHALL** — 系统 SHALL 支持任意两个版本间的差异对比（版本 diff）：
- 结构差异（新增/删除/移动的节点）
- 属性差异（概率值变更、描述修改）
- 拓扑差异（门类型更改、连接关系变化）

**SHALL** — 系统 SHALL 支持回滚到任意历史版本，回滚操作 SHALL 创建一个新版本（而非覆盖历史版本）。

**SHALL** — 故障树的版本快照 SHALL 纳入项目审计日志（CROSS-04）。

---

#### FTA-14: 导入 / 导出（互操作性）

**SHALL** — 系统 SHALL 支持以 JSON 格式导出／导入故障树的完整结构。

**SHALL** — JSON Schema SHALL 包含所有节点（顶事件、中间事件、基本事件、逻辑门、转移门）及其完整属性。

**SHALL** — 系统 SHALL 支持 OpenPSA 格式（IEC 61025 / NUREG-0492 兼容）的导入和导出。

**SHALL** — OpenPSA 导入 / 导出 SHALL 涵盖：
- 顶事件定义
- 基本事件及其概率数据
- AND/OR/PAND/INHIBIT 逻辑门
- 转移门（跨树引用）
- 割集分析结果（可选）

**SHALL** — OpenPSA 导入时 SHALL 执行 schema 校验，校验失败则返回行级错误报告。

**SHALL** — 系统 SHALL 支持 YAML 格式的导入 / 导出（与 FAME 模块 YAML 风格一致）：

```yaml
fta_id: "FTA-BRAKE-001"
title: "制动距离超标"
asil: "ASIL_D"
safety_goal_ref:
  - "SG-BRAKE-001"
gates:
  - id: "gate-1"
    gate_type: "OR"
    parent_node_id: "top"
    description: "制动失效的两种途径"
events:
  - id: "be-1"
    event_type: "basic"
    title: "左前轮速传感器断路"
    failure_rate: 0.5   # FIT
    mission_time: 1000   # hours
    dtc_ref:
      - "C0035"
    fmea_ref: "FMEA-2026-0042"
```

**SHOULD** — 系统 SHOULD 支持从 FTA YAML 文件批量创建 / 更新故障树（与 CI 集成，参见 FTA-18）。

**MAY** — 系统 MAY 支持从故障树可视化界面直接导出为图像（SVG/PNG/PDF，已见于 FTA-11）。

---

### D. 与现有模块集成（FTA-15 ~ FTA-18）

---

#### FTA-15: 与知识管理 KB 模块联动

**SHALL** — 基本事件 SHALL 支持关联零个或多个 KB 知识条目（`knowledge_ref` 字段，参见 FTA-03）。

**SHALL** — 关联的语义包括但不限于：
- 基本事件 = 该知识条目的核心失效机制
- 基本事件 = 知识条目描述的故障模式的直接引用
- 基本事件 = 知识条目中的经验教训（Lessons Learned）具体化

**SHALL** — 系统 SHALL 提供 KB → FTA 反向追溯：在 KB 知识条目的详情页展示关联的 FTA 基本事件列表及其所属故障树。

**SHALL** — 当关联的 KB 条目 confidence 降至 < 30 时，系统 SHALL 自动将关联的基本事件标记为 `knowledge_stale`。

**SHALL** — 系统 SHALL 在基本事件详情页展示关联 KB 条目的置信度（`confidence` 值）和时效状态（`status`）。

**SHOULD** — 系统 SHOULD 提供"从知识条目生成 FTA 基本事件草案"的快捷操作，预填基本事件的 `title` 和 `description`。

---

#### FTA-16: 与 FMEA 模块联动

**SHALL** — 系统 SHALL 建立 FTA 与 FMEA 的共享故障数据库（参见 FTA-10 双向追溯）。

**SHALL** — 共享故障数据库的核心映射规则：

| FMEA 元素 | FTA 元素 | 映射关系 |
|-----------|----------|---------|
| `failure_cause` (失效原因) | `basic_event` (基本事件) | 直接映射 |
| `failure_mode` (失效模式) | `intermediate_event` (中间事件) | 候选映射 |
| `failure_effect` (失效后果) | `top_event` (顶事件) | 候选映射 |
| `current_control` (控制措施) | FTA 未覆盖（由 FMEA 侧维护） | — |
| DTC 编码 | `dtc_ref` | 共享字段 |

**SHALL** — 当用户创建 FTA 基本事件时，系统 SHALL 提供从 FMEA 的 `failure_cause` 字段自动搜索和填充的功能。

**SHALL** — 当用户创建 FTA 顶事件时，系统 SHALL 建议可能匹配的 FMEA `failure_effect` 条目。

**SHALL** — 系统 SHALL 提供一个"共享故障库"视图，展示所有已被 FMEA 和/或 FTA 引用的故障描述，以及各自的引用计数和模块归属。

**SHOULD** — 系统 SHOULD 在 FMEA 和 FTA 编辑器中提供互相跳转的链接（"转到 FTA 基本事件"、"转到 FMEA 失效原因"）。

---

#### FTA-17: 与测试模块联动

**SHALL** — 最小割集分析结果 SHALL 自动生成测试需求建议。

**SHALL** — 测试需求生成规则：

| 割集特征 | 测试策略 | 测试类型建议 |
|----------|---------|-------------|
| 一阶割集（单点故障） | 必须覆盖——每个单点故障至少一个测试用例 | Unit / SIL |
| 二阶割集 | 组合测试——至少覆盖所有二阶组合的子集 | SIL / HIL |
| 三阶以上 | 抽样测试——基于重要性排序覆盖 FV 前 20% | HIL / 系统集成 |
| PAND 门割集 | 时序测试——验证事件顺序 | HIL / 仿真 |

**SHALL** — 系统 SHALL 为每个生成的测试需求记录：
- 来源割集 ID（`cut_set_id`）
- 关联的基本事件列表
- 推荐测试类型
- 分析粒度为"需要覆盖"（`coverage_required`）
- 证据模块中的测试用例 ID（待填写）

**SHALL** — 系统 SHALL 在割集分析更新时（如新增割集或概率变更）自动标记上一轮生成的测试需求为 `stale`。

**SHOULD** — 系统 SHOULD 提供"测试覆盖度仪表盘"：已覆盖割集数 / 总割集数，按 ASIL 等级分解。

**SHOULD** — 系统 SHOULD 在 evidence 模块中创建"割集验证任务"，链接对应的测试计划。

---

#### FTA-18: 与 Pipeline 联动

**SHALL** — 系统 SHALL 在 pipeline 中引入故障树分析阶段（FTA Stage）。

**SHALL** — FTA Pipeline 阶段包含以下检查项：

| 检查项 | 阻断级别 | 说明 |
|--------|---------|------|
| FTA YAML Schema 校验 | blocker | 故障树定义文件格式校验失败阻断 |
| 最小割集计算一致性 | blocker | 同一故障树的前后两次割集结果不一致 |
| 单点故障发现 | warning | 新发现未经评估的一阶割集 |
| 定量概率超限 | blocker | 顶事件概率超过对应安全目标的阈值 |
| 基本事件概率缺失 | warning | 超过 10% 的基本事件概率数据缺失 |
| 未解决的跨树引用 | blocker | 转移门指向的目标故障树不存在 |
| 关联 KB 置信度过低 | warning | 基本事件关联的 KB 条目 confidence < 30 |

**SHALL** — YAML Schema 校验（CI 阶段的 FTA 检查，参 CI-01 / CI-03 风格）：
- FTA YAML 文件变更在 PR 阶段 SHALL 自动验证 schema
- 校验失败则在 PR 评论中报告行级错误
- 校验通过则自动触发最小割集计算，并将结果附加到 PR 评论

**SHALL** — 当 pipeline 发现"定量概率超限"（blocker）时，pipeline SHALL 停止并通知相关安全分析师（Safety Engineer）。

**SHOULD** — 系统 SHOULD 在 merge 时自动生成"故障树分析检查清单"，包含本次变更涉及的所有故障树的状态和最新割集结果。

---

### E. 行业约束（FTA-19 ~ FTA-20）

---

#### FTA-19: ISO 26262 安全目标映射

**SHALL** — 每个顶事件（Top Event）SHALL 支持关联零个或多个安全目标 ID（`safety_goal_ref`，参见 FTA-01）。

**SHALL** — 关联的安全目标信息 SHALL 包含：
- `safety_goal_id` (字符串 — 如 `SG-BRAKE-001`)
- `safety_goal_title` (字符串)
- `safety_goal_desc` (字符串 — 安全目标功能描述)
- `safety_goal_quant` (浮点数，可选 — 安全目标的量化安全要求，如 `P_top < 10⁻⁷/h`)
- `asil` (枚举: `ASIL_A`/`ASIL_B`/`ASIL_C`/`ASIL_D`/`QM`)

**SHALL** — 当安全目标的量化安全要求存在时，系统 SHALL 在定量分析报告中自动对比顶事件概率与该阈值，并给出达标/超限判定（参见 FTA-08）。

**SHALL** — 当顶事件的 `asil` 为 ASIL B/C/D 时，故障树状态从 `draft` 到 `approved` 的转换 SHALL 要求至少一次独立评审。

**SHOULD** — ASIL D 级顶事件的评审 SHALL 要求至少两名独立评审人。

**SHOULD** — 系统 SHOULD 在故障树详情页展示安全目标矩阵，按安全目标分组展示关联的顶事件及其定量达标状态。

**SHALL NOT** — ASIL B/C/D 级顶事件 SHALL NOT 被物理删除（仅允许软删除）。

---

#### FTA-20: ASPICE SYS.3 系统需求分析映射

**SHALL** — FTA 模块的设计和实施 SHALL 支持 ASPICE SYS.3（系统需求分析）的过程要求。

**SHALL** — 故障树的构建过程 SHALL 映射到 ASPICE SYS.3 的工作产品：

| ASPICE SYS.3 工作产品 | FTA 对应物 | 说明 |
|----------------------|-----------|------|
| 系统需求（System Requirements） | 顶事件 + 中间事件 | 故障树中的事件对应需要分析的系统故障需求 |
| 系统需求间的依赖关系 | 逻辑门 + 转移门 | 系统故障之间的逻辑组合关系 |
| 系统需求分析报告 | 最小割集报告 + 定性报告 | 分析结果文档化 |
| 需求追溯矩阵 | 安全目标映射 + FMEA 追溯 | 双向可追溯 |

**SHALL** — 系统 SHALL 提供"ASPICE SYS.3 合规性检查清单"，按项检查故障树分析过程：

1. 顶事件是否定义清晰？（已覆盖 → FTA-01）
2. 故障树是否覆盖所有安全目标？（已覆盖 → FTA-19）
3. 最小割集是否已计算？（已覆盖 → FTA-06）
4. 单点故障是否已标记并评估？（已覆盖 → FTA-07）
5. 定量概率是否已分析（如适用）？（已覆盖 → FTA-08）
6. FMEA 与 FTA 的双向追溯是否建立？（已覆盖 → FTA-10）
7. 故障树是否经过评审？（已覆盖 → FTA-19）
8. 版本历史是否可审计？（已覆盖 → FTA-13）
9. 分析结果是否文档化（报告/导出）？（已覆盖 → FTA-14）

**SHALL** — 系统 SHALL 以故障树分析报告的形式输出 ASPICE SYS.3 的证据，支持审计场景。

**SHOULD** — 系统 SHOULD 提供 ASPICE SYS.3 交付物模板（基于故障树分析结果自动填充关键字段）。

---

## 3. 实现指引（可变）

以下为开发团队的推荐实施策略，**非契约约束**。

### 3.1 模块划分（建议）

```
yuleosh/fta/
├── models/
│   ├── top_event.py        # 顶事件模型
│   ├── gate.py             # 逻辑门模型
│   ├── basic_event.py      # 基本事件模型
│   ├── intermediate.py     # 中间事件模型
│   ├── transfer.py         # 转移门模型
│   └── analysis.py         # 分析结果模型
├── crud/
│   ├── tree_crud.py        # 故障树 CRUD
│   ├── validation.py       # 拓扑校验（环路检测、完备性）
│   └── linking.py          # 跨模块引用管理
├── analysis/
│   ├── mcs_bottom_up.py    # 自底向上最小割集
│   ├── mcs_mocus.py        # MOCUS 算法
│   ├── mcs_bdd.py          # BDD 算法
│   ├── qualitative.py      # 定性分析
│   ├── quantitative.py     # 定量分析（精确/近似/Monte Carlo）
│   └── importance.py       # FV / Birnbaum 重要性排序
├── visualization/
│   ├── text_tree.py        # 文本树生成
│   ├── graph_layout.py     # 图形布局引擎
│   └── export_image.py     # SVG/PNG 导出
├── io/
│   ├── json_io.py          # JSON 序列化/反序列化
│   ├── opensa_io.py        # OpenPSA 格式
│   ├── yaml_io.py          # YAML 格式
│   └── schema_validator.py # Schema 校验
├── integration/
│   ├── kb_link.py          # FTA ↔ KB 联动
│   ├── fmea_link.py        # FTA ↔ FMEA 追溯
│   ├── test_link.py        # 割集 → 测试用例
│   └── pipeline.py         # Pipeline 集成
├── collaboration/
│   ├── locking.py          # 子树锁定
│   ├── conflict.py         # 冲突检测
│   └── annotation.py       # 注释系统
└── common/
    ├── versioning.py       # 版本快照管理
    └── audit.py            # 审计日志
```

### 3.2 数据存储建议

| 数据 | 存储方案 | 索引策略 |
|------|---------|---------|
| 故障树结构（节点 + 边） | PostgreSQL JSONB（整棵树序列化）+ 节点表（关系型） | GIN 索引 on JSONB |
| 版本快照 | 同一 PostgreSQL 实例的 `fta_snapshots` 表 | (fta_id, version) 联合索引 |
| 最小割集结果 | 分析结果缓存表 | (fta_id, computed_at) 索引 |
| 跨模块关联表（FTA-FMEA 等） | 独立关联表 `fta_fmea_link` | 双向索引 |
| 审计日志 | 独立 `audit_log` 表，按月分区 | (entity_id, timestamp) |
| FTA YAML 文件 | Git 仓库 | N/A（Git 原生） |

### 3.3 BDD 最小割集算法设计思路（参考）

```
┌─────────────────────────────────────┐
│  Fault Tree → BDD Transformation     │
│                                      │
│  输入: 故障树（以 ITE 格式表示）       │
│  递归转换:                            │
│    IF-Then-Else (ITE) 结构:           │
│    - 基本事件 x → ITE(x, 1, 0)       │
│    - AND(a,b) → ITE(x, AND(a1,b1),   │
│                        AND(a0,b0))   │
│    - OR(a,b)  → ITE(x, OR(a1,b1),    │
│                        OR(a0,b0))    │
│                                      │
│  优化: 变量排序（重量启发式/深度优先）  │
│  输出: 压缩 BDD + 最小割集提取        │
│        通过 BDD 中路径枚举获得割集     │
└─────────────────────────────────────┘
```

### 3.4 实施优先级（建议）

| 优先级 | 模块 | 说明 |
|-------|------|------|
| P0 | 故障树 CRUD + 拓扑校验 | 基础不可减 |
| P0 | 核心数据结构（FTA-01~05） | 数据模型基础 |
| P0 | 最小割集计算（FTA-06, BDD 优先） | 核心分析 |
| P0 | 文本树可视化（FTA-11 降级） | 最低可用可视化 |
| P0 | YAML 导入/导出（FTA-14） | 与 FMEA 模块一致 |
| P1 | 定性分析 + 单点故障标记（FTA-07） | 安全分析关键 |
| P1 | 定量分析（FTA-08） | 安全目标验证 |
| P1 | FMEA 双向追溯（FTA-10, FTA-16） | 模块互联 |
| P1 | 版本快照（FTA-13） | 审计合规 |
| P2 | Fussell-Vesely / Birnbaum（FTA-09） | 优化级排序 |
| P2 | KB 联动（FTA-15） | 知识闭环 |
| P2 | 图形化可视化（FTA-11 GUI） | 交互体验 |
| P2 | Pipeline 集成（FTA-18） | 流程嵌入 |
| P3 | 测试联动（FTA-17） | 测试覆盖 |
| P3 | OpenPSA 导入/导出（FTA-14） | 互操作性 |
| P3 | 多用户协作 + 锁定（FTA-12） | 团队协作 |
| P3 | ISO 26262 / ASPICE 报告（FTA-19/20） | 审计输出 |
| P4 | Monte Carlo 仿真定量分析（FTA-08） | 高级分析 |

### 3.5 故障树存储 JSON 结构参考

```json
{
  "fta_id": "FTA-BRAKE-001",
  "version": "1.2.0",
  "title": "制动距离超标",
  "asil": "ASIL_D",
  "safety_goal_ref": ["SG-BRAKE-001"],
  "nodes": [
    {
      "id": "top-001",
      "type": "top_event",
      "title": "制动距离超标",
      "description": "车辆在100km/h初速下制动距离超过40m",
      "children": ["gate-001"]
    },
    {
      "id": "gate-001",
      "type": "gate",
      "gate_type": "OR",
      "children": ["ie-001", "be-003"]
    },
    {
      "id": "ie-001",
      "type": "intermediate",
      "title": "制动力不足",
      "children": ["gate-002"]
    },
    {
      "id": "gate-002",
      "type": "gate",
      "gate_type": "AND",
      "children": ["be-001", "be-002"]
    },
    {
      "id": "be-001",
      "type": "basic_event",
      "event_type": "basic",
      "title": "左前轮速传感器断路",
      "failure_rate": 0.5,
      "mission_time": 1000,
      "dtc_ref": ["C0035"],
      "fmea_ref": "FMEA-2026-0042",
      "knowledge_ref": "kb-uuid-xxxx"
    },
    {
      "id": "be-002",
      "type": "basic_event",
      "event_type": "basic",
      "title": "右前轮速传感器断路",
      "failure_rate": 0.5,
      "mission_time": 1000,
      "dtc_ref": ["C0036"]
    },
    {
      "id": "be-003",
      "type": "basic_event",
      "event_type": "basic",
      "title": "制动踏板传感器失效",
      "failure_rate": 0.3,
      "mission_time": 1000,
      "dtc_ref": ["P0571"],
      "fmea_ref": "FMEA-2026-0051"
    }
  ]
}
```

---

## 4. 术语表

| 术语 | 定义 |
|------|------|
| FTA | Fault Tree Analysis，故障树分析（演绎式失效分析方法） |
| Top Event | 顶事件——故障树的根节点，描述系统级故障 |
| Basic Event | 基本事件——故障树的叶节点，不可再分的底层失效原因 |
| Intermediate Event | 中间事件——故障树中的中间层节点，由逻辑门连接的故障事件 |
| Gate | 逻辑门——定义子事件之间的逻辑组合关系 |
| AND Gate | 与门——所有输入事件同时发生才触发输出 |
| OR Gate | 或门——任一输入事件发生即触发输出 |
| PAND Gate | 优先与门——输入事件按特定顺序依次发生才触发输出 |
| INHIBIT Gate | 禁止门——条件事件为真时输入事件触发输出 |
| Transfer Gate | 转移门——跨故障树引用机制 |
| Cut Set | 割集——导致顶事件发生的基本事件集合 |
| Minimal Cut Set (MCS) | 最小割集——去掉任一元素后不再构成割集的割集 |
| Single Point Failure | 单点故障——一个基本事件就能导致顶事件发生的故障（一阶割集） |
| BDD | Binary Decision Diagram，二元决策图——用于高效计算最小割集的算法 |
| MOCUS | Method of Obtaining Cut Sets——经典最小割集算法 |
| Fussell-Vesely (FV) | 一种重要性测度，度量事件对顶事件概率的贡献率 |
| Birnbaum | 一种重要性测度，度量事件概率变化对顶事件概率的边际影响 |
| FIT | Failure In Time，失效率单位（1 FIT = 10⁻⁹/h） |
| Mission Time | 任务时间，系统运行时间（h），用于概率计算 |
| OpenPSA | Open PSA 格式——IEC 61025 兼容的故障树交换格式 |
| Safety Goal | 安全目标（ISO 26262 顶层安全要求） |
| ASIL | Automotive Safety Integrity Level，汽车安全完整性等级 |
| ASPICE SYS.3 | Automotive SPICE 过程"系统需求分析" |
| KB | Knowledge Base，知识库（yuleOSH 知识管理模块） |
| FMEA | Failure Mode and Effects Analysis，失效模式与影响分析 |
| DTC | Diagnostic Trouble Code，诊断故障码 |
| ITE | If-Then-Else，BDD 构建中的基本逻辑结构 |
| FIT Rate | Failure In Time rate，失效率（每 10⁹ 工作小时） |
| IEC 61025 | 国际电工委员会故障树分析标准 |
| ISO 26262-10 | ISO 26262 第 10 部分——功能安全指南（含 FTA 指导） |

---

> **变更记录**
> | 版本 | 日期 | 变更内容 | 作者 |
> |------|------|---------|------|
> | v1.0.0 | 2026-06-20 | 初始正式规约 | 小马 🐴 |
