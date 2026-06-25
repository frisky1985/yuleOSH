# yuleOSH 知识管理模块 — 软件需求规格

> **版本**: v1.1.0  
> **状态**: 已根据老陈审查意见修订（Spec-Tech 对齐）  
> **作者**: 小马 🐴 (质量架构师)  
> **日期**: 2026-06-20  
> **规范文体**: RFC 2119 (SHALL/SHALL NOT/SHOULD/MAY)  
> **输入源**: 团队头脑风暴 + 专家评审锁定的行业约束及需求框架 + 老陈审查意见对齐  

---

## 目录

1. [核心定位与模块关系](#1-核心定位与模块关系)
2. [Spec 契约层](#2-spec-契约层不可变)
   - 2.1 [知识库 (KB) 模块](#21-知识库-kb-模块)
   - 2.2 [Lessons Learned (LL) 模块](#22-lessons-learned-ll-模块)
   - 2.3 [FMEA 模块](#23-fmea-模块)
   - 2.4 [CI/CD 集成](#24-cicd-集成)
   - 2.5 [知识债务仪表盘](#25-知识债务仪表盘)
   - 2.6 [跨模块与预留接口](#26-跨模块与预留接口)
3. [实现指引](#3-实现指引可变)
4. [术语表](#4-术语表)

---

## 1. 核心定位与模块关系

### 1.1 定位

yuleOSH 知识管理模块 = **知识沉淀 (KB)** + **Lessons Learned (LL)** + **FMEA** 三位一体系统，专为嵌入式汽车电子团队设计。

### 1.2 模块依赖

| 依赖模块 | 用途 | 契约级别 |
|---------|------|---------|
| store | 知识条目持久化、版本快照存储、索引 | 强制 |
| spec | 知识条目与需求/规格的追溯链接 | 强制 |
| ci | CI 全触点钩子（pre-commit / commit-msg / PR / merge / regression） | 强制 |
| pipeline | 知识审核流、衰减评估、闭环节点编排 | 强制 |
| evidence | 知识条目与测试证据、验收矩阵的关联 | 强制 |

### 1.3 行业约束映射总表

| # | 约束 | 覆盖条目 |
|---|------|---------|
| 1 | ASIL 分级 | KB-02, KB-15, FMEA-04, LL-02 |
| 2 | HW BOM 标签 | KB-05 |
| 3 | 跨 ECU FMEA | FMEA-03, FMEA-06 |
| 4 | DTC 检索 | KB-06, LL-05, FMEA-07 |
| 5 | 五层测试映射 | KB-10, CI-05 |
| 6 | 知识置信度衰减 | KB-07, KB-08, DASH-02 |
| 7 | OTA 版本绑定 | KB-09 |
| 8 | TCL 工具认证预留 | CROSS-01 |
| 9 | AUTOSAR 层级 | KB-11 |
| 10 | 售后闭环 | LL-06, FMEA-08 |
| 11 | PFMEA（过程 FMEA） | PK-01 ~ PK-10 |
| 12 | HARA / Safety Goal 追溯 | KBS-16 |

---

## 2. Spec 契约层（不可变）

### 2.1 知识库 (KB) 模块

#### KBS-01: 知识条目基础 CRUD
**SHALL** — 系统 SHALL 提供知识条目的创建、读取、更新、删除（CRUD）操作。  
**SHALL NOT** — 系统 SHALL NOT 允许物理删除已被其他模块引用或关联的知识条目，仅允许逻辑删除（软删除）。  

- **实现指引**: 建议使用 `is_deleted` 标记 + `deleted_at` 时间戳；store 层提供软删除过滤器。

---

#### KBS-02: 知识条目标识
**SHALL** — 每条知识条目 SHALL 拥有全局唯一标识符（UUID），且不可变。  

---

#### KBS-03: 知识条目元数据结构
**SHALL** — 每条知识条目 SHALL 包含以下强制元数据字段：
- `id` (UUID)
- `title` (字符串，≤200 字符)
- `content` (Markdown 正文)
- `status` (枚举: `draft`/`review_pending`/`approved`/`published`/`deprecated`/`archived`)
- `safety_level` (枚举: `ASIL_A`/`ASIL_B`/`ASIL_C`/`ASIL_D`/`QM`) — 对应行业约束 #1
- `created_by` (用户引用)
- `updated_by` (用户引用)
- `created_at` (时间戳)
- `updated_at` (时间戳)
- `version` (语义版本号: major.minor.patch)
- `confidence` (SMALLINT 0–100, 初始值 100) — 对应行业约束 #6
- `confidence_decay_policy` (枚举: `usage_based`) — 对应行业约束 #6；仅保留基于引用/搜索命中率的衰减策略（已移除 linear 和 step）
- `ota_binding` (结构体: `{ ota_version, ota_manifest_hash }`, 可选) — 对应行业约束 #7
- `tcl_doc_slot` (结构体: `{ tcl_tool_id, cert_doc_refs, assessment_status }`, 可选) — 对应行业约束 #8 (预留)
- `hw_bom` (JSONB 数组, 可选) — 支持多硬件平台标签，对应行业约束 #2；格式：`[{ "platform": "<平台名>", "chip": "<芯片型号>", "version": "<版本>" }]`

**SHOULD** — 系统 SHOULD 在创建时自动生成 `created_at` 和 `version` 初始值 `1.0.0`。  
**SHOULD** — 系统 SHOULD 在更新时自动递增 `version` 的 `patch` 段。

---

#### KB-01: 语义多模态搜索
**SHALL** — 系统 SHALL 提供知识条目的语义搜索能力，支持基于自然语言查询的全文和向量混合检索。  

- **实现指引**: 建议引入 embedding 向量存储（如 pgvector / Qdrant），通过 cosine similarity + BM25 混合排序，权重可配置。

**SHALL** — 语义搜索结果的排序 SHALL 将 `confidence` 因子（0–100 范围归一化）作为排序权重的一部分。  

---

#### KB-02: ASIL 等级属性与生命周期门禁
**SHALL** — 每条知识条目 SHALL 绑定 `safety_level` 属性（ASIL A/B/C/D/QM）。  

**SHALL** — 当知识条目的 `safety_level` 为 ASIL B/C/D 时，从 `draft` 到 `approved` 的状态转换 SHALL 要求至少一次独立评审（peer review），并记录评审 ID 和时间戳。  

**SHALL** — 从 `draft` 到 `review_pending` 的转换 SHALL 自动触发一条 pipeline 审批任务。  

**SHOULD** — ASIL D 级知识条目的评审 SHALL 要求至少两名独立评审人。  

---

#### KB-03: 版本快照链
**SHALL** — 系统 SHALL 为每次知识条目更新自动创建版本快照。  

**SHALL** — 每个版本快照 SHALL 包含完整的内容拷贝（非 diff 引用），以确保审计追溯的独立性。  

**SHALL** — 系统 SHALL 支持通过版本号或时间戳回滚到任意历史版本。  

**SHOULD** — 版本快照 SHALL 记录 `change_reason`（变更原因），由提交者在更新时填写。  

---

#### KB-04: 代码路径反向索引
**SHALL** — 知识条目 SHALL 支持关联一个或多个源代码文件路径（相对项目根路径）。  

**SHALL** — 当关联源代码文件路径的对应文件发生变更（通过 CI pre-commit / commit-msg 钩子检测），系统 SHALL 自动将相关知识条目的 `confidence` 下调 10（0–100 标尺），并在条目上标记 `code_path_stale: true`。  

**SHOULD** — 系统 SHOULD 提供反向查询：给定一个源文件路径，列出所有关联该路径的知识条目。  

---

#### KB-05: HW BOM 标签系统（多平台 JSONB）
**SHALL** — 知识标签系统 SHALL 支持多硬件平台的标签结构。  

**SHALL** — 硬件标签 SHALL 以 JSONB 数组形式存储，每个元素包含：
- `platform` (字符串，如 `"TDA4VM"`)
- `chip` (字符串，如 `"TDA4VM-Q1"`)
- `version` (字符串，如 `"1.2"`)

**SHALL** — 系统 SHALL 支持按任意 JSONB 路径进行独立筛选和组合筛选（如：匹配所有 `platform="TDA4VM"` 的条目，或同时匹配 `platform` + `chip` 的条目）。  

---

#### KB-06: DTC 一级检索维度
**SHALL** — 知识条目 SHALL 支持关联一个或多个 DTC（Diagnostic Trouble Code），格式符合 ISO 14229 / SAE J2012。  

**SHALL** — DTC SHALL 作为独立的第一级检索维度，提供专用搜索入口，可按 DTC 编码前缀匹配（如 `"P0100"` 模糊匹配所有 `P01xx`）。  

**SHOULD** — 系统 SHOULD 提供 DTC 自动补全（autocomplete）功能，基于已注册的 DTC 字典。  

**SHOULD** — 系统 SHOULD 在 KB 条目详情页展示该 DTC 关联的 FMEA 条目和 LL 条目数量。  

---

#### KB-07: 知识置信度衰减机制
**SHALL** — 系统 SHALL 为每条知识条目维护一个动态 `confidence` 值（SMALLINT 0–100），并定期运行衰减评估。  

**SHALL** — 衰减评估的触发方式：
- 定时任务（默认每 24 小时）
- 代码路径反向下调（KB-04 触发）
- 关联模块（如 FMEA 条目更新、LL 条目新增）的级联更新

**SHALL** — 衰减策略由 `confidence_decay_policy` 控制：
- `usage_based`: 基于引用/搜索命中率调整；若在评估周期内有命中，则重置衰减计数器；若无命中，每周期移除 2 点（上限 100）

**SHALL** — 设计变更触发器：当知识条目关联的源代码文件（KB-04）、OTA 版本（KB-09）、HW BOM 标签发生变更时，系统 SHALL 自动下调 `confidence`（下调规则见各自条目）。  

**SHALL** — 当 `confidence < 30` 时，系统 SHALL 自动将该条目加入"知识债务审查队列"（Knowledge Debt Review Queue）。  

---

#### KB-08: 置信度衰减的恢复
**SHALL** — 用户 SHALL 能够手动审查并重置知识条目的 `confidence` 值，重置操作 SHALL 记录审计日志。  

**SHALL** — 一次人工审查通过（状态从 `deprecated` 回 `approved` 或 `published`），SHALL 将 `confidence` 重置为 100 并重新开始衰减周期。  

**SHOULD** — 重置操作 SHOULD 触发一次版本快照（无需内容变更）。  

---

#### KB-09: OTA 版本双轨绑定
**SHALL** — 知识条目 SHALL 支持绑定一个 OTA 版本标识（`ota_binding` 字段）。  

**SHALL** — 当 OTA 版本更新时，系统 SHALL 自动创建知识条目的版本分支副本，并将旧版本标记为 `deprecated`，新版本 `confidence` 设为 80。  

**SHALL** — 知识搜索结果的排序 SHALL 优先展示与当前目标 OTA 版本匹配的知识条目。  

**SHOULD** — 系统 SHOULD 在 OTA 版本发布时自动生成一条"知识版本差异报告"，列出与上一版 OTA 绑定的知识变更。  

---

#### KB-10: 五层测试映射
**SHALL** — 知识条目 SHALL 支持关联测试用例，并标注测试层级（枚举: `HIL`/`SIL`/`MIL`/`PIL`/`Unit`）。  

**SHALL** — 一条知识条目 SHALL 允许关联多个测试层级，每个层级允许关联多个测试用例 ID。  

**SHALL** — 知识详情页 SHALL 展示每个测试层级的覆盖率状态（`pass`/`fail`/`not_run`/`no_test`）。  

**SHOULD** — 当任一测试层级的状态变为 `fail` 时，系统 SHOULD 自动将知识条目 `confidence` 下调 15（0–100 标尺）。  

---

#### KB-11: AUTOSAR 层级映射
**SHALL** — 知识条目 SHALL 支持绑定 AUTOSAR 层级标签（枚举集: `ASW`/`RTE`/`BSW`/`HW`），允许多选。  

**SHALL** — AUTOSAR 层级标签 SHALL 作为独立的过滤维度。  

**SHALL** — 搜索过滤 SHALL 支持 ASW/RTE/BSW/HW 的任意组合。  

---

#### KB-12: 语义搜索的已删除过滤
**SHALL** — 语义搜索 SHALL 默认排除软删除的知识条目。  

**MAY** — 系统 MAY 提供一个明确的 "include_deleted" 查询参数，允许管理员搜索已删除条目。  

---

#### KB-13: 知识条目审核流程
**SHALL** — 系统 SHALL 提供基于 pipeline 的知识条目审核流程。  

**SHALL** — 审核流程 SHALL 支持以下状态转换：
- `draft` → `review_pending` (提交审核)
- `review_pending` → `approved` (审核通过)
- `review_pending` → `draft` (驳回，需记录驳回原因)
- `approved` → `published` (发布上线)
- `published` → `deprecated` (标记过期)
- `deprecated` → `approved` (审查后恢复，跳过发布步骤)
- `approved` → `deprecated` (从已批准直接标记过期)

**SHALL** — 每一次状态转换 SHALL 记录操作人、操作时间、原因（可选）到审计日志。  

---

#### KB-14: 知识条目与 spec 模块追溯
**SHALL** — 知识条目 SHALL 支持关联一个或多个 Spec 条目 ID（来自 spec 模块）。  

**SHALL** — 当关联的 Spec 条目发生版本变更时，系统 SHALL 通知知识条目作者进行一致性审查。  

**SHOULD** — 系统 SHOULD 在 Spec 条目详情页展示关联的知识条目数量。  

---

#### KB-15: ASIL 等级与版本发布的绑定
**SHALL** — 当所有与某 OTA 版本绑定的 ASIL C/D 级知识条目状态非 `approved` 或 `published` 时，系统 SHALL 阻止该 OTA 版本的发布批准。  

**SHOULD** — 系统 SHOULD 在发布检查报告中列出所有未达标的知识条目及其 `safety_level`。  

---

#### KBS-16: 安全目标（Safety Goal）与 HARA 追溯
**SHALL** — 知识条目 SHALL 支持关联零个或多个安全目标 ID（Safety Goal ID，来自 HARA 模块／系统安全分析）。  

**SHALL** — 每条安全目标关联 SHALL 包含以下信息：
- `safety_goal_id` (字符串 — 安全目标标识，如 `SG-BRAKE-001`)
- `safety_goal_title` (字符串 — 安全目标标题)
- `safety_goal_desc` (字符串 — 安全目标描述摘要)
- `hara_ref` (字符串，可选 — 关联的 HARA 分析条目 ID)
- `hazard_id` (字符串，可选 — 关联的危险事件标识)
- `link_type` (枚举: `derived_from`/`contributes_to`/`verifies`/`constrains`)
- `asil_decomposition` (字符串，可选 — 如适用 ASIL 分解说明)

**SHALL** — 系统 SHALL 提供按安全目标 ID 反向检索知识条目的能力。  

**SHALL** — 当安全目标发生版本变更或 HARA 分析更新时，系统 SHALL 通知关联知识条目的负责人进行一致性审查。  

**SHOULD** — 在知识条目的详情页 SHOULD 展示关联的安全目标清单及其 `asil_decomposition`（如适用）。  

---

### 2.2 Lessons Learned (LL) 模块

#### LL-01: LL 条目基础结构
**SHALL** — 系统 SHALL 提供 Lessons Learned 条目的创建、读取、更新、关闭操作。  

**SHALL** — 每条 LL 条目 SHALL 包含以下强制字段：
- `id` (UUID)
- `title`
- `description` (Markdown)
- `root_cause` (Markdown) — 根因
- `category` (枚举: `design`/`coding`/`test`/`process`/`requirement`/`integration`/`hw`/`other`)
- `severity` (枚举: `info`/`minor`/`major`/`critical`/`catastrophic`) — 5 级严重度
- `closure_status` (枚举: `open`/`investigating`/`action_planned`/`implemented`/`mitigated`/`verified`/`closed`/`rejected`) — 8 状态生命周期
- `safety_level` (枚举: `ASIL_A`/`ASIL_B`/`ASIL_C`/`ASIL_D`/`QM`) — 对应行业约束 #1
- `source_ref` (结构体: `{ entity_type, entity_id }`) — 来源引用（如 Bug ID、FMEA 条目 ID、Code Review ID）
- `created_by`
- `assigned_to`
- `created_at`
- `closed_at`

---

#### LL-02: LL 条目的 ASIL 门禁
**SHALL** — 当 LL 条目的 `safety_level` 为 ASIL B/C/D 时，其 `closure_status` 从 `verified` 到 `closed` 的转换 SHALL 要求独立第三方的确认签字（sign-off），并记录签字人 ID。  

---

#### LL-03: 自动捕获 — Bug → LL 回灌
**SHALL** — 系统 SHALL 提供自动或半自动的 Bug→LL 回灌机制。  

**SHALL** — 系统 SHALL 提供 CI 钩子接口，当 Bug 被标记为 `root_cause_identified` 后，自动创建一条 LL 条目草案，预填 `source_ref`、`root_cause`（从 Bug 中提取）、`severity` 等信息。  

**SHALL** — 自动创建的 LL 条目草案 SHALL 进入 `open` 状态，需人工审阅后确认。  

---

#### LL-04: LL → Test Seed
**SHALL** — 当 LL 条目的 `closure_status` 变为 `closed` 时，系统 SHALL 自动为测试用例仓库生成一条"知识驱动测试种子"（Knowledge-driven Test Seed），包含：
- LL 的 `root_cause` 摘要
- 建议的测试场景描述
- 推荐的测试层级（基于 LL 的 `category`）

**SHALL** — 生成的测试种子 SHALL 存储在 evidence 模块中，并标记为 `auto_generated`。  

**SHALL** — 测试种子 SHALL 由一个负责任务分配的用户确认后方可纳入正式测试用例集。  

**SHOULD** — 如果已有测试用例覆盖该根因，系统 SHOULD 标记"已覆盖"而非生成重复种子。  

---

#### LL-05: DTC 关联
**SHALL** — LL 条目 SHALL 支持关联零个或多个 DTC 编码。  

**SHALL** — DTC 关联的 LL 条目 SHALL 在 KB 模块的 DTC 检索结果中一并返回。  

**SHALL** — 当 LL 条目与某个 DTC 关联且该 DTC 的诊断计数超过告警阈值时，系统 SHALL 将该 LL 条目标记为 `pending_review`。  

---

#### LL-06: 售后闭环 — DTC → FMEA → LL 自动回灌管道
**SHALL** — 系统 SHALL 提供售后数据回灌管道，接收来自售后工单系统的 DTC 命中数据。  

**SHALL** — 对于每个命中 DTC，系统 SHALL 执行以下自动步骤：
1. 查询 KB 模块中该 DTC 关联的知识条目
2. 查询 FMEA 模块中该 DTC 关联的失效模式
3. 检查是否存在现有的 LL 条目
4. 如果不存在，自动创建一条 `open` 状态的 LL 条目草案，填入 `source_ref` 为售后工单引用

**SHALL** — 每个回灌事件 SHALL 记录在审计日志中，包含原始 DTC、售后工单 ID、处理结果。  

---

#### LL-07: LL 闭环节点（8 状态生命周期）
**SHALL** — LL 条目状态转换链为：
```
open → investigating → action_planned → implemented → mitigated → verified → closed
                                                                                ↓
                                                                            rejected
```
每一跳 SHALL 记录：
- 时间戳
- 操作人
- 措施描述
- 验证方式（如 `review`/`test`/`simulation`/`field_data`/`analysis`）

**SHALL** — mitigated 状态定义：风险缓解措施已验证通过，但尚未完成最终验证的中间态。

**SHALL** — LL 条目进入 `closed` 状态后，SHALL 自动在 evidence 模块中生成一条"LI 知识闭合证据记录"。  

**SHALL** — `rejected` 状态 SHALL 要求填写驳回原因，并可从 `rejected` → `open` 重新发起分析。  

---

#### LL-08: LL 搜索与分类
**SHALL** — 系统 SHALL 提供按 `category`、`severity`、`safety_level`、`closure_status` 的 LL 条目过滤与聚合。  

**SHOULD** — 系统 SHOULD 提供 LL 条目的"相似事件检索"功能，基于语义相似度匹配历史 LL 条目，避免重复创建。  

---

### 2.3 FMEA 模块

#### FMEA-01: FMEA 条目基础结构
**SHALL** — 系统 SHALL 支持 FMEA 条目的创建、读取、更新、删除。  

**SHALL** — 每条 FMEA 条目 SHALL 包含以下强制字段：
- `id` (UUID)
- `fmea_id` (字符串，可读编号如 `FMEA-2026-0001`)
- `system` (字符串 — 系统/子系统名)
- `function` (字符串 — 功能描述)
- `failure_mode` (字符串 — 失效模式)
- `failure_effect` (字符串 — 失效后果)
- `failure_cause` (字符串 — 失效原因)
- `current_control` (字符串 — 当前控制措施)
- `recommended_action` (字符串 — 建议措施)
- `status` (枚举: `open`/`analysis`/`action_planned`/`action_done`/`verified`/`closed`)
- `rpn_severity` (整数 1–10) — 严重度
- `rpn_occurrence` (整数 1–10) — 频度
- `rpn_detection` (整数 1–10) — 探测度
- `rpn_total` (整数 — `rpn_severity × rpn_occurrence × rpn_detection`)
- `ap_priority` (枚举: `H`/`M`/`L` — AIAG-VDA Action Priority) — 替代纯 RPN 阈值门禁
- `ap_severity` (整数 1–10) — AIAG-VDA S 评级
- `ap_occurrence` (整数 1–10) — AIAG-VDA O 评级
- `ap_detection` (整数 1–10) — AIAG-VDA D 评级
- `safety_level` (枚举: `ASIL_A`/`ASIL_B`/`ASIL_C`/`ASIL_D`/`QM`) — 对应行业约束 #1
- `created_by`
- `updated_by`
- `created_at`
- `updated_at`

---

#### FMEA-02: FMEA as Code（YAML 格式）
**SHALL** — 系统 SHALL 支持以纯 YAML 文件定义和导入 FMEA 条目。  

**SHALL** — FMEA YAML 格式 SHALL 包含所有 FMEA-01 的强制字段。  

**SHALL** — YAML 导入 SHALL 经过 schema 校验，校验失败时返回详细的错误报告（行号+字段+错误类型）。  

**SHOULD** — 系统 SHOULD 支持从 YAML 导出完整 FMEA 表格（含自动计算的 RPN 和 AIAG-VDA Action Priority）。  

---

#### FMEA-03: 跨 ECU 失效链定义
**SHALL** — FMEA 条目 SHALL 支持定义跨 ECU 的失效传播链（Inter-ECU Failure Mode Chain）。  

**SHALL** — 每个失效链节点 SHALL 包含：
- `ecu_id` (ECU 标识符)
- `signal_name` (信号名)
- `failure_mode` (该 ECU 上的失效模式)
- `propagation_direction` (传播方向: `source`/`forward`/`backward`/`merge`)

**SHALL** — 系统 SHALL 在 FMEA 详情页以有向图（Directed Graph）形式可视化跨 ECU 失效链。  

**SHALL** — 跨 ECU 失效链中的任一点控制措施变更 SHALL 自动级联标记链上所有相关 FMEA 条目为 `open`（需重新分析）。  

---

#### FMEA-04: ASIL 等级的 FMEA 门禁
**SHALL** — 当 FMEA 条目的 `ap_priority` 为 `H` 且 `safety_level` 为 ASIL B/C/D 时，系统 SHALL 强制要求附加"措施有效性验证证据"（来自 evidence 模块）方可关闭。  

**SHALL** — ASIL C/D 级 FMEA 条目的创建/修改 SHALL 记录审计日志，并在 pipeline 中插入强制审批步骤。  

---

#### FMEA-05: AIAG-VDA Action Priority — 替代纯 RPN 阈值
**SHALL** — 系统 SHALL 基于 AIAG-VDA 第一版 Action Priority（AP）矩阵自动计算 `ap_priority`（H/M/L），取代传统的固定 RPN 阈值门禁。  

**SHALL** — Action Priority 的输入为三元组 `(ap_severity, ap_occurrence, ap_detection)`，查 AIAG-VDA AP 矩阵表确定最终等级（H=高优先需立即行动 / M=中优先需计划行动 / L=低优先可接受）。  

**SHALL** — 当 `ap_priority` 为 `H` 时，系统 SHALL ：
- 在仪表盘高亮标识
- 在 FMEA 详情页展示红色标记
- 自动在 pipeline 中触发高优先行动任务

**SHALL** — 系统 SHALL 同时保留 `rpn_total` 字段用于传统报告兼容，但 FMEA 的门禁判定以 `ap_priority` 为准（而非 `rpn_total` 阈值）。  

**MAY** — 系统 MAY 提供 AP 矩阵的可视化参考面板，展示当前条目的 S/O/D 在 AP 矩阵中的落点。  

---

#### FMEA-06: 跨 ECU 失效链版本管理
**SHALL** — 跨 ECU 失效链的修改 SHALL 触发连锁版本更新：链上任一节点修改，整条链 SHALL 生成新版本快照。  

**SHALL** — 系统 SHALL 支持跨 ECU 失效链的版本差异对比（diff），突出显示节点级别变化。  

---

#### FMEA-07: DTC → FMEA 映射
**SHALL** — FMEA 条目 SHALL 支持关联零个或多个 DTC 编码。  

**SHALL** — 系统 SHALL 提供"DTC 失效模式矩阵"视图，展示 DTC 编码与 FMEA 失效模式的一对多映射关系。  

**SHALL** — 当 FMEA 条目的 `failure_effect` 更新时，系统 SHALL 检查是否有新的 DTC 与该效果相关，并建议关联。  

---

#### FMEA-08: FMEA → Test → Telemetry 闭环
**SHALL** — 当 FMEA 条目的 `ap_priority` 为 `H` 或 `M` 时，系统 SHALL 自动在 evidence 模块中创建一条测试需求记录。  

**SHALL** — 生成的测试需求记录 SHALL 包含 FMEA 的 `failure_mode` 和 `recommended_action`。  

**SHALL** — 测试执行结果 SHALL 自动回写 FMEA 条目，更新其 `current_control` 有效性判定。  

**SHOULD** — 当遥测数据（Telemetry）中检测到与 FMEA 失效模式匹配的模式时，系统 SHOULD 自动通知 FMEA 条目负责人进行重新评估。  

---

#### FMEA-09: 轻量增量 FMEA
**SHALL** — 系统 SHALL 支持从一个已有的 FMEA 条目"派生"(fork) 一个新的 FMEA 条目，继承前者的全部字段并允许覆盖。  

**SHALL** — 派生条目 SHALL 自动记录 `parent_fmea_id`，形成 FMEA 家族树。  

**SHOULD** — 系统 SHOULD 支持批量 PR 级别的 FMEA 差异审查，在 CI 阶段展示本次变更新增/修改/删除的 FMEA 条目。  

---

#### PK-01: PFMEA 基础需求
**SHALL** — 系统 SHALL 支持过程 FMEA（PFMEA）条目的创建、读取、更新、删除，与 DFMEA 共享同一数据模型但要区分类别。  

**SHALL** — 每条 PFMEA 条目 SHALL 包含 `fmea_scope` 字段（枚举: `design`/`process`），标记该条目为 DFMEA 或 PFMEA。  

---

#### PK-02: PFMEA 强制字段
**SHALL** — PFMEA 条目 SHALL 除 FMEA-01 的通用字段外，额外包含：
- `process_step` (字符串 — 工序/工步名称)
- `process_parameter` (字符串，可选 — 工艺参数，如温度、压力、速度)
- `process_machine` (字符串，可选 — 设备/工装编号)
- `station_id` (字符串，可选 — 工位标识)
- `material_id` (字符串，可选 — 物料/来料编号)

---

#### PK-03: PFMEA 过程要素分析
**SHALL** — 每条 PFMEA SHALL 至少包含以下过程要素的失效分析：
- 人 (Man): 操作失误、培训不足、疲劳
- 机器 (Machine): 设备故障、工装磨损、校准漂移
- 料 (Material): 来料缺陷、批次差异、仓储条件
- 法 (Method): 工艺参数偏差、SOP 未遵守
- 环 (Environment): 温度/湿度/洁净度影响  
- 测 (Measurement): 检测方法缺陷、量具精度不足

**SHALL** — 上述过程要素分析记录在 PFMEA 条目的 `failure_cause` 字段中，建议标注要素标签（如 `[M]aterial`、`[M]achine`）。

---

#### PK-04: PFMEA 与 DFMEA 的追溯
**SHALL** — PFMEA 条目 SHALL 支持关联一个或多个 DFMEA 条目 ID，标识该工序失效由哪个设计决策引发或缓解。  

**SHALL** — 当关联的 DFMEA 条目的控制措施变更时，系统 SHALL 通知 PFMEA 条目负责人。  

---

#### PK-05: PFMEA 与 Control Plan 关联
**SHALL** — 每条 PFMEA 条目的 `current_control` SHALL 标注控制类型（`preventive`/`detective`）。  

**SHOULD** — 系统 SHOULD 提供从 PFMEA 条目到 Control Plan（控制计划）的导出接口，生成简要控制计划草案。  

---

#### PK-06: PFMEA Action Priority
**SHALL** — PFMEA 条目 SHALL 与 DFMEA 使用一致的 AIAG-VDA Action Priority（H/M/L）判定体系（参见 FMEA-05）。  

**SHALL** — 当 PFMEA 的 `ap_priority` 为 `H` 时，系统 SHALL 要求在 pipeline 中创建纠正措施任务，任务通过方可确认（`verified`）。  

---

#### PK-07: PFMEA 批产验证
**SHALL** — 当 PFMEA 条目的 `status` 变为 `verified` 时，系统 SHALL 自动在 evidence 模块中创建设备/工装的"初始过程能力研究"（Initial Process Capability Study）证据需求。  

**SHOULD** — 系统 SHOULD 允许用户上传 `Cpk` / `Ppk` 分析结果作为证据附件。  

---

#### PK-08: PFMEA → Test Seed
**SHALL** — 当 PFMEA 条目的 `ap_priority` 为 `H` 时，系统 SHALL 自动生成一条过程测试种子，包含失效模式、相关工位和推荐检验方法。  

---

#### PK-09: PFMEA 批量导入
**SHALL** — 系统 SHALL 支持从规范化的过程流程图（Process Flow Diagram，CSV 或 YAML 格式）批量生成 PFMEA 条目草案。  

---

#### PK-10: PFMEA DFMEA 统一仪表盘
**SHALL** — 知识债务仪表盘 SHALL 将 DFMEA 和 PFMEA 条目统一纳入统计，提供按 `fmea_scope` 过滤的能力。  

---

### 2.4 CI/CD 集成

#### CI-01: Pre-commit 钩子
**SHALL** — Pre-commit 阶段 SHALL 检查被修改文件中关联的知识条目是否存在 `code_path_stale` 标记。  

**SHALL** — 如果存在 `code_path_stale` 标记，pre-commit SHALL 输出警告信息，但不阻止提交。  

---

#### CI-02: Commit-msg 钩子
**SHALL** — Commit-msg 钩子 SHALL 解析提交信息中 `KB-<ID>` / `LL-<ID>` / `FMEA-<ID>` 的引用。  

**SHALL** — 对于每个解析到的引用，系统 SHALL 验证该 ID 在系统中真实存在；若不存在，SHALL 阻断提交（blocker 级别）。  

**SHOULD** — 对于涉及代码变更（.c/.h/.cpp/.go 等）但未引用任何知识条目的提交，系统 SHOULD 输出警告信息。  

**SHOULD** — 系统 SHOULD 在验证通过后，自动在对应条目中追加变更日志。  

---

#### CI-03: PR 检查
**SHALL** — PR 阶段 SHALL 执行以下检查：
1. 代码变更是否影响了有关联 FMEA 条目的模块 → 如果是，PR 评论中列出影响到的 FMEA 条目
2. 是否存在新增的 FMEA 条目未通过 YAML schema 校验 → 如果有，PR 被标记为 `fmea_failed`
3. 知识条目是否引用了不存在的模块路径 → 如果有，PR 评论中列出路径

**SHALL** — 当 PR 包含 FMEA YAML 变更时，SHALL 执行 YAML schema 校验，并通过 comment 汇报校验结果。  

---

#### CI-04: Merge 门禁
**SHALL** — Merge 阶段 SHALL 检查：
1. 是否有 FMEA 条目处于 `draft` 状态且 `safety_level` 为 ASIL C/D → 如果存在，阻止 merge
2. 是否有 LL 条目因关联的 DTC 售后计数超过阈值而标记为 `pending_review` → 如果存在，阻止 merge

**SHALL** — Merge 时 SHALL 自动触发一次知识条目置信度评估。  

---

#### CI-05: Regression 测试 — 五层知识映射报告
**SHALL** — Regression 阶段 SHALL 生成"知识-测试映射报告"，按知识条目列出每个测试层级（HIL/SIL/MIL/PIL/Unit）的最新执行结果和覆盖率。  

**SHALL** — 当某知识条目的所有五层测试均为 `pass` 时，系统 SHALL 将该知识条目的 `confidence` 上调 5（上限 100）。  

**SHALL** — 当某知识条目的任一测试层级出现 `fail` 时，系统 SHALL 自动下调 `confidence` 15（下限 0）。  

---

#### CI-06: CI 配置自动发现
**SHOULD** — 系统 SHOULD 自动发现项目根目录下的 yuleOSH 知识管理 CI 配置文件（`.yuleosh-knowledge.yaml`），无需手动注册。  

---

### 2.5 知识债务仪表盘

#### DASH-01: 核心指标
**SHALL** — 系统 SHALL 提供知识债务仪表盘，展示以下量化指标：
- 知识条目总量（按状态分解：`published`/`approved`/`draft`/`review_pending`/`deprecated`/`archived`）
- ASIL 等级分布统计
- 平均置信度（整体 + 按 ASIL 等级）
- 低置信度条目数（`confidence < 30`）
- 待审核知识条目数（状态为 `review_pending`）
- 未关闭 LL 条目数（按 `severity` 分解）
- FMEA 条目总数（按 Action Priority 分组：`H` / `M` / `L`）

---

#### DASH-02: 置信度衰减趋势
**SHALL** — 仪表盘 SHALL 展示置信度衰减趋势图（按天/周/月粒度），可过滤按 ASIL 等级或按模块。  

**SHOULD** — 系统 SHOULD 在置信度显著下降（一周内平均降幅 > 10）时自动发送通知给知识条目负责人。  

---

#### DASH-03: 知识覆盖率
**SHALL** — 仪表盘 SHALL 展示"知识-测试覆盖率"：
- 已映射测试的知识条目占比
- 按测试层级分解的覆盖率（HIL/SIL/MIL/PIL/Unit）
- 零测试覆盖的知识条目清单

---

#### DASH-04: 售后闭环统计
**SHALL** — 仪表盘 SHALL 展示售后 DTC 回灌管道统计：
- DTC 命中次数趋势
- DTC → FMEA → LL 回灌完成率
- 未回灌的 DTC 清单

---

### 2.6 跨模块与预留接口

#### CROSS-01: TCL 工具认证预留接口
**SHALL** — 知识条目元数据结构 SHALL 预留 `tcl_doc_slot` 字段（见 KBS-03），用于未来 TCL（Tool Confidence Level）认证文档的关联存储。  

**SHALL NOT** — 系统 SHALL NOT 将 TCL 预留字段用于其他用途。  

**MAY** — 系统 MAY 在 v2.0 中实现 TCL 认证文档自动校验功能。  

---

#### CROSS-02: DTC → FMEA → LL 全链自动回灌
**SHALL** — 系统 SHALL 提供从 DTC 诊断数据到 FMEA 重新评估，到 LL 条目的全自动回灌管道（详见 LL-06 + FMEA-08）。  

**SHALL** — 全链回灌的执行结果 SHALL 在仪表盘 DASH-04 中展示。  

---

#### CROSS-03: 知识条目模块间引用完整性
**SHALL** — 当 KB 条目、LL 条目、FMEA 条目之间存在交叉引用时，系统 SHALL 维护引用完整性，不允许删除被引用的条目（仅软删除）。  

---

#### CROSS-04: 审计日志
**SHALL** — 所有对 KB、LL、FMEA 条目的创建、更新、状态转换、删除操作 SHALL 记录审计日志，包含：操作人、操作时间、操作类型、条目 ID、变更前后摘要。  

---

#### CROSS-05: 权限模型
**SHALL** — 系统 SHALL 支持基于角色的访问控制（RBAC），至少包含以下角色：
- `reader`: 只读知识条目
- `contributor`: 创建/编辑知识条目
- `reviewer`: 审核知识条目
- `admin`: 管理权限、审计日志查看、恢复删除

**SHALL** — AI 审核视图生成的测试种子（LL-04）SHALL 标记为 `auto_generated`，仅 `reviewer` 及以上角色可确认或删除。  

---

## 3. 实现指引（可变）

以下为开发团队的推荐实施策略，**非契约约束**。

### 3.1 模块划分（建议）

建议按以下包结构组织代码：

```
yuleosh/knowledge/
├── kb/                  # 知识库模块
│   ├── models.py        # 数据模型
│   ├── crud.py          # CRUD 操作
│   ├── search.py        # 语义搜索
│   ├── versioning.py    # 版本快照管理
│   ├── confidence.py    # 置信度引擎
│   ├── tags.py          # 标签系统（HW BOM + AUTOSAR）
│   ├── dtc.py           # DTC 关联
│   ├── ota.py           # OTA 版本绑定
│   └── lifecycle.py     # 状态机与审核流程
├── ll/                  # Lessons Learned 模块
│   ├── models.py
│   ├── crud.py
│   ├── capture.py       # 自动捕获引擎
│   ├── test_seed.py     # Test Seed 生成
│   ├── aftermarket.py   # 售后回灌管道
│   └── closure.py       # 闭环节点管理
├── fmea/                # FMEA 模块
│   ├── models.py
│   ├── crud.py
│   ├── yaml_io.py       # YAML 导入/导出
│   ├── cross_ecu.py     # 跨 ECU 失效链
│   ├── rpn.py           # RPN 计算引擎
│   ├── ap_matrix.py     # AIAG-VDA Action Priority 矩阵
│   ├── pfmea.py         # PFMEA 过程分析
│   └── chain_graph.py   # 失效链可视化
├── ci/                  # CI/CD 集成
│   ├── hooks.py         # Pre-commit / Commit-msg / PR / Merge
│   └── regression.py    # Regression 报告
├── dashboard/           # 知识债务仪表盘
│   ├── metrics.py       # 指标聚合
│   └── views.py         # 视图渲染
└── common/              # 公共
    ├── audit.py         # 审计日志
    ├── rbac.py          # 权限模型
    ├── safety_goal.py   # Safety Goal / HARA 追溯
    └── tcl.py           # TCL 预留接口
```

### 3.2 实施优先级（建议）

| 优先级 | 模块 | 说明 |
|-------|------|------|
| P0 | KB CRUD + 状态机 + 版本快照 | 基础不可减 |
| P0 | FMEA 基础 CRUD + YAML IO | 核心功能 |
| P0 | LL 基础 CRUD + 闭环节点 | 核心功能 |
| P1 | ASIL 门禁（KB/FMEA/LL） | 行业约束 #1 |
| P1 | DTC 一级检索 | 行业约束 #4 |
| P1 | 语义搜索 | KB 完整度 |
| P2 | 置信度衰减 | 行业约束 #6 |
| P2 | HW BOM 标签 | 行业约束 #2 |
| P2 | CI/CD 钩子 | 流程集成 |
| P2 | PFMEA 基础 | 老陈审查补充 |
| P2 | Safety Goal 追溯 | 老陈审查补充 |
| P2 | 售后回灌管道 | 行业约束 #10 |
| P3 | 跨 ECU 失效链 | 行业约束 #3 |
| P3 | OTA 版本绑定 | 行业约束 #7 |
| P3 | AUTOSAR 层级 | 行业约束 #9 |
| P3 | 五层测试映射 | 行业约束 #5 |
| P3 | 知识债务仪表盘 | 量化可视 |
| P4 | TCL 预留接口 | 行业约束 #8 |

### 3.3 数据存储建议

- **主数据**: 沿用 store 模块的 PostgreSQL（含 pgvector 扩展支持语义搜索）
- **版本快照**: 同一 PostgreSQL 实例的 `knowledge_snapshots` 表，或用项目已有的事件溯源机制
- **向量索引**: pgvector（减少运维复杂度）或接入已有向量数据库
- **标签索引**: 用 PostgreSQL JSONB/GIN 索引加速 HW BOM 多平台标签和 AUTOSAR 层级检索
- **审计日志**: 独立的 `audit_log` 表，按月分区
- **FMEA YAML**: 存储于 Git 仓库，系统通过 CI 解析和同步

### 3.4 置信度衰减引擎设计思路（参考）

```
┌─────────────────────────────────┐
│   Confidence Engine (cron)      │
│   ┌───────────────────────────┐ │
│   │  Decay Policy             │ │
│   │  - usage_based (引用/搜索)│ │
│   │  - 设计变更触发器          │ │
│   │    (代码/OTA/HW BOM 变更) │ │
│   │  - 关联模块级联更新       │ │
│   └───────────────────────────┘ │
│   ↓                             │
│   ┌───────────────────────────┐ │
│   │  Threshold Gates          │ │
│   │  30  → Debt Review Queue  │ │
│   │  50  → Dashboard Warning  │ │
│   └───────────────────────────┘ │
└─────────────────────────────────┘
```

### 3.5 AIAG-VDA Action Priority 矩阵参考

实现时建议将 AIAG-VDA 第一版 AP 矩阵以查表或规则引擎形式实现。核心判断逻辑：

| Severity | Occurrence | Detection | AP 等级 | 含义 |
|----------|------------|-----------|---------|------|
| 9–10 | 7–10 | 7–10 | **H** | 高优先 — 必须立即采取行动 |
| 9–10 | 7–10 | 1–6 | **H** | 高优先 |
| 9–10 | 4–6 | 7–10 | **H** | 高优先 |
| 9–10 | 4–6 | 1–6 | **M** | 中优先 |
| 9–10 | 1–3 | 任意 | **M** | 中优先 |
| 5–8 | 7–10 | 7–10 | **H** | 高优先 |
| 5–8 | 7–10 | 4–6 | **M** | 中优先 |
| 5–8 | 7–10 | 1–3 | **L** | 低优先 |
| 5–8 | 4–6 | 7–10 | **M** | 中优先 |
| 5–8 | 4–6 | 4–6 | **L** | 低优先 |
| 5–8 | 4–6 | 1–3 | **L** | 低优先 |
| 5–8 | 1–3 | 任意 | **L** | 低优先 |
| 1–4 | 所有 | 所有 | **L** | 低优先 — 可接受 |

> **注意**: 上表为示意性简版；正式实现应参照 AIAG & VDA FMEA 手册第一版的 Action Priority 矩阵全表。

### 3.6 跨 ECU 失效链数据结构参考 YAML

```yaml
fmea_id: "FMEA-2026-0042"
failure_chain:
  - ecu_id: "ECU_BMS"
    signal_name: "CellVoltage_Avg"
    failure_mode: "Cell imbalance detection failure"
    propagation_direction: source
  - ecu_id: "ECU_VCU"
    signal_name: "CellBalance_Cmd"
    failure_mode: "Incorrect cell balance command"
    propagation_direction: forward
  - ecu_id: "ECU_BMS"
    signal_name: "CellBalance_Status"
    failure_mode: "Balance status feedback timeout"
    propagation_direction: backward
rpn_severity: 8
rpn_occurrence: 4
rpn_detection: 6
rpn_total: 192
ap_severity: 8
ap_occurrence: 4
ap_detection: 6
ap_priority: "H"
```

---

## 4. 术语表

| 术语 | 定义 |
|------|------|
| KB | Knowledge Base，知识库 |
| LL | Lessons Learned，经验教训 |
| FMEA | Failure Mode and Effects Analysis，失效模式与影响分析 |
| DFMEA | Design FMEA，设计 FMEA |
| PFMEA | Process FMEA，过程 FMEA（关注制造/装配工序） |
| ASIL | Automotive Safety Integrity Level，汽车安全完整性等级 |
| DTC | Diagnostic Trouble Code，诊断故障码 |
| OTA | Over-the-Air，远程升级 |
| TCL | Tool Confidence Level，工具置信度等级（ISO 26262-8） |
| AUTOSAR | AUTomotive Open System ARchitecture |
| RPN | Risk Priority Number，风险优先级数 |
| AIAG-VDA | Automotive Industry Action Group 与 Verband der Automobilindustrie 联合发布的 FMEA 手册 |
| AP | Action Priority，行动优先级（AIAG-VDA 替代 RPN 阈值的判定方法） |
| HARA | Hazard Analysis and Risk Assessment，危险分析与风险评估 |
| Safety Goal | 安全目标（ISO 26262 顶层安全要求） |
| HW BOM | Hardware Bill of Materials，硬件物料清单 |
| ECU | Electronic Control Unit，电子控制单元 |
| Control Plan | 控制计划（过程质量控制文件） |
| HIL/SIL/MIL/PIL/Unit | 硬件在环/软件在环/模型在环/处理器在环/单元测试五层级 |

---

> **变更记录**
> | 版本 | 日期 | 变更内容 | 作者 |
> |------|------|---------|------|
> | v1.0.0 | 2026-06-20 | 初始正式规约 | 小马 🐴 |
> | v1.1.0 | 2026-06-20 | 老陈审查对齐：LL 8 状态（含 mitigated）、KB 6 状态、FMEA 6 状态 + AP 优先级、LL 5 级严重度、Confidence SMALLINT 0-100、HW BOM JSONB 多平台、CI-02 升级 SHALL、新增 PFMEA PK-01~10、新增 KBS-16 HARA/安全目标追溯 | 小马 🐴 |
