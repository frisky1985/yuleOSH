# yuleOSH 故障树分析（FTA）模块 — 技术架构 & 数据模型

> **版本：** v1.0
> **领域：** FTA — Fault Tree Analysis
> **日期：** 2026-06-20
> **状态：** 草案，待小马审查

---

## 目录

1. [设计原则](#1-设计原则)
2. [总体架构](#2-总体架构)
3. [Part 1: 数据模型（PostgreSQL Schema）](#3-part-1-数据模型postgresql-schema)
4. [Part 2: 算法引擎](#4-part-2-算法引擎)
5. [Part 3: 可视化引擎](#5-part-3-可视化引擎)
6. [Part 4: Go 后端模块划分](#6-part-4-go-后端模块划分)
7. [Part 5: 与现有模块集成](#7-part-5-与现有模块集成)
8. [Part 6: 置信度与知识关联](#8-part-6-置信度与知识关联)
9. [Part 7: CI/CD 集成方案](#9-part-7-cicd-集成方案)
10. [Part 8: 实施路线](#10-part-8-实施路线)
11. [附录：FTA 理论基础速查](#11-附录fta-理论基础速查)

---

## 1. 设计原则

| 原则 | 说明 |
|------|------|
| **与 FMEA 互补而非替代** | FTA 是演绎分析（顶事件→底事件），FMEA 是归纳分析（底事件→顶事件），两者共享事件库 |
| **精确计算优先** | 最小割集计算使用下行法（MOCUS），提供精确结果，不做近似剪枝 |
| **可视化即验证** | 产出三种格式（文本树 / DOT / Mermaid），让工程师在 PR review 时可直接审查树结构 |
| **可追溯性** | 每个基本事件必须可追踪到 FMEA 条目、KB 条目或物理实体 |
| **渐进增强** | Phase 1 只做定性 + 基础定量，Phase 2 加可视化，Phase 3 加自动生成 |
| **与 ISO 26262 对齐** | 定量结果可以贡献给 ASIL 分解和随机硬件失效度量（PMHF） |

---

## 2. 总体架构

### 2.1 架构概览

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           yuleOSH Gateway                                │
├──────────────────────────────────────────────────────────────────────────┤
│                              ┌──────────────┐                            │
│                              │  API Layer   │                            │
│                              │ (REST/gRPC)  │                            │
│                              └──────┬───────┘                            │
│                                     │                                    │
│                    ┌────────────────┼───────────────┐                    │
│                    ▼                ▼                ▼                    │
│            ┌────────────┐  ┌────────────────┐  ┌────────────┐           │
│            │  FTA       │  │  FMEA Service  │  │  KB        │           │
│            │  Service   │◄►│  (事件引用)     │  │  Service   │           │
│            └─────┬──────┘  └────────────────┘  └─────┬──────┘           │
│                  │                                    │                  │
│                  ▼                                    │                  │
│       ┌─────────────────────┐                         │                  │
│       │  Algorithm Engine   │                         │                  │
│       │  (MOCUS + quant)    │                         │                  │
│       └──────────┬──────────┘                         │                  │
│                  ▼                                    ▼                  │
│       ┌─────────────────────────────────────────────────────┐            │
│       │              Store Adapter (PG)                      │            │
│       │  fta_trees | fta_events | fta_gates | fta_cut_sets  │            │
│       └──────────────────────────┬──────────────────────────┘            │
│                                  ▼                                       │
│       ┌─────────────────────────────────────────────────────┐            │
│       │  External / Integration                               │            │
│       │  (FMEA ⇄ FTA link, KB link, evidence, visualization) │            │
│       └──────────────────────────────────────────────────────┘            │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心数据流

```
手动创建 / YAML 导入 / FMEA 自动派生
          │
          ▼
    ┌──────────┐      ┌──────────────────┐
    │ 故障树定义 │─────►│ 图结构校验器      │
    │ (事件+门) │      │ (环检测 + 无父节点)│
    └──────────┘      └────────┬─────────┘
                               │
                               ▼
                    ┌──────────────────┐
                    │ 最小割集计算引擎   │
                    │ (MOCUS 下行法)     │
                    └────────┬─────────┘
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
            ┌──────────────┐  ┌──────────────┐
            │ 定性分析结果   │  │ 定量分析引擎   │
            │ (最小割集列表) │  │ (概率计算)    │
            └──────────────┘  └──────┬───────┘
                                     ▼
                            ┌──────────────────┐
                            │ 重要度排序        │
                            │ (F-V / Birnbaum)  │
                            └────────┬─────────┘
                                     ▼
                    ┌──────────────────────────────┐
                    │ 可视化输出                    │
                    │ (Text Tree / DOT / Mermaid)   │
                    └──────────────────────────────┘
```

### 2.3 关键架构决策（ADR）

| ADR | 决策 | 理由 |
|-----|------|------|
| ADR-FTA-001 | MOCUS 下行法作为首选最小割集算法 | 实现简单，工程实用，适用于中小规模故障树（节点 < 1000） |
| ADR-FTA-002 | BDD 作为 Phase 2 备选 | 当节点数 > 1000 或需精确概率计算时启用 |
| ADR-FTA-003 | 基本事件概率存储浮点数 | 概率值典型在 1e-9 ~ 1e-2 范围，float8 足够 |
| ADR-FTA-004 | 割集结果缓存到 `fta_cut_sets` 表 | 典型树计算一次后不会频繁变更，缓存避免重复计算 |
| ADR-FTA-005 | 可视化不依赖前端渲染库 | 输出 DOT/Mermaid 文本，前端只需显示 |

---

## 3. Part 1: 数据模型（PostgreSQL Schema）

### 3.1 ER 总览

```
fta_trees 1──N fta_events (顶事件引用 fta_trees.id → fta_events.id)
fta_trees 1──N fta_cut_sets (计算结果缓存)
fta_trees 1──N fta_event_links (关联 FMEA/KB)

fta_events 1──N fta_gates (父节点为事件的，其子门定义)

fta_gates —— 定义 AND/OR 门及其子节点（事件或门）
fta_gates 可以引用其他 fta_events 作为输入
fta_gates 可以引用其他 fta_gates 作为输入

fta_transfers —— 转移门，复用其他树中的子树

fta_event_links N──1 fmea_items / kb_articles (多态引用)
```

### 3.2 核心表定义

所有表均继承 yuleOSH store 模块的 `created_at`/`updated_at` 惯例，使用 `knowledge` schema。

#### 3.2.1 fta_trees — 故障树主表

```sql
CREATE TABLE IF NOT EXISTS knowledge.fta_trees (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 基本标识
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    system          TEXT NOT NULL,         -- 分析的系统，如 "BrakeSystem"
    subsystem       TEXT NOT NULL DEFAULT '',

    -- 版本
    fta_version     TEXT NOT NULL DEFAULT '0.1.0',

    -- 安全等级
    safety_level    SMALLINT NOT NULL DEFAULT 0,
                    -- 0:QM, 1:ASIL_A, 2:ASIL_B, 3:ASIL_C, 4:ASIL_D

    -- ASIL 分解目标
    target_pmhf     DOUBLE PRECISION,      -- 目标随机硬件失效率（per hour）

    -- 状态
    status          SMALLINT NOT NULL DEFAULT 0,
                    -- 0:draft, 1:analysis, 2:review, 3:approved, 4:superseded, 5:archived

    -- 顶事件引用
    top_event_id    UUID,                  -- 指向 fta_events.id（顶事件节点）

    -- 元数据
    creator_id      TEXT NOT NULL,
    reviewer_id     TEXT,

    -- 关联 FMEA（可选）
    fmea_entry_id   UUID REFERENCES knowledge.fmea_entries(id),

    -- 源文件（FTA as Code YAML 的路径）
    source_yaml     TEXT NOT NULL DEFAULT '',
    source_hash     TEXT NOT NULL DEFAULT '',

    -- 计算统计（缓存）
    calc_event_count       INT NOT NULL DEFAULT 0,
    calc_gate_count        INT NOT NULL DEFAULT 0,
    calc_min_cut_set_count INT NOT NULL DEFAULT 0,
    calc_last_at           TIMESTAMPTZ,     -- 上次计算时间
    calc_duration_ms       INT NOT NULL DEFAULT 0,

    -- 时间戳
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 索引
CREATE INDEX idx_fta_trees_system ON knowledge.fta_trees(system);
CREATE INDEX idx_fta_trees_status ON knowledge.fta_trees(status);
CREATE INDEX idx_fta_trees_safety ON knowledge.fta_trees(safety_level);
CREATE INDEX idx_fta_trees_updated ON knowledge.fta_trees(updated_at DESC);
```

#### 3.2.2 fta_events — 事件节点（顶事件/中间事件/基本事件）

```sql
CREATE TABLE IF NOT EXISTS knowledge.fta_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 所属故障树
    tree_id         UUID NOT NULL REFERENCES knowledge.fta_trees(id) ON DELETE CASCADE,

    -- 事件类型
    event_type      SMALLINT NOT NULL,
                    -- 0:top（顶事件）, 1:intermediate（中间事件）, 2:basic（基本事件）,
                    -- 3:undeveloped（未展开事件）, 4:conditional（条件事件）,
                    -- 5:house（房型事件，固定开/关）

    -- 事件标识（人工可读，树内唯一）
    event_ref       TEXT NOT NULL,          -- 如 "EVT-001", "BRAKE-FAIL"
    label           TEXT NOT NULL,          -- 事件标签，如 "Brake system failure"
    description     TEXT NOT NULL DEFAULT '',

    -- 基本事件概率（仅 event_type=2 有值）
    -- 概率 = 失效率 × 任务时间（或直接填写）
    -- 典型范围 1e-12 ~ 1.0
    probability     DOUBLE PRECISION,       -- 基本事件发生概率（0.0 ~ 1.0）

    -- 失效率（用于计算概率 = 1 - exp(-λ * t)）
    failure_rate    DOUBLE PRECISION,       -- λ，每小时失效率
    mission_time    DOUBLE PRECISION,       -- 任务时间，小时

    -- 房型事件开关（仅 event_type=5 有值）
    house_value     BOOLEAN,                -- true=发生, false=不发生

    -- 排序（树内显示顺序）
    sort_order      INT NOT NULL DEFAULT 0,

    -- 是否为未展开事件（Phase 2 自动展开用）
    is_undeveloped  BOOLEAN NOT NULL DEFAULT false,

    -- 外键关联（多态）
    -- 指向 fmea_items 或 kb_articles 或预留空
    linked_entity_type SMALLINT,            -- 0:fmea_item, 1:kb_article, 2:lesson, 3:custom
    linked_entity_id   UUID,

    -- 自定义属性（JSONB，扩展用）
    extra           JSONB,

    -- 时间戳
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- 约束
    UNIQUE (tree_id, event_ref)
);

-- 索引
CREATE INDEX idx_fta_events_tree ON knowledge.fta_events(tree_id);
CREATE INDEX idx_fta_events_type ON knowledge.fta_events(event_type);
CREATE INDEX idx_fta_events_linked ON knowledge.fta_events(linked_entity_type, linked_entity_id);
CREATE INDEX idx_fta_events_ref ON knowledge.fta_events(tree_id, event_ref);
```

#### 3.2.3 fta_gates — 逻辑门定义及子节点关系

```sql
CREATE TABLE IF NOT EXISTS knowledge.fta_gates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 所属故障树
    tree_id         UUID NOT NULL REFERENCES knowledge.fta_trees(id) ON DELETE CASCADE,

    -- 父事件（此门是哪个事件的分解）
    parent_event_id UUID NOT NULL REFERENCES knowledge.fta_events(id) ON DELETE CASCADE,

    -- 门类型
    gate_type       SMALLINT NOT NULL,
                    -- 0:AND, 1:OR, 2:INHIBIT（禁门）, 3:PAND（优先与门）
                    -- 4,5 (NOT/XOR): 预留 v2.0
                    -- AND/OR 覆盖 95% 实用场景

    -- 禁门条件描述（仅 INHIBIT）
    inhibit_condition TEXT,

    -- 排序
    sort_order      INT NOT NULL DEFAULT 0,

    -- 标签
    label           TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',

    -- 时间戳
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_fta_gates_tree ON knowledge.fta_gates(tree_id);
CREATE INDEX idx_fta_gates_parent ON knowledge.fta_gates(parent_event_id);

-- 门输入关系表（多对多：门 → 子事件/子门）
CREATE TABLE IF NOT EXISTS knowledge.fta_gate_inputs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    gate_id         UUID NOT NULL REFERENCES knowledge.fta_gates(id) ON DELETE CASCADE,

    -- 输入可以是事件或子门（多态）
    input_type      SMALLINT NOT NULL,
                    -- 0:event, 1:gate
    input_event_id  UUID REFERENCES knowledge.fta_events(id) ON DELETE CASCADE,
    input_gate_id   UUID REFERENCES knowledge.fta_gates(id) ON DELETE CASCADE,

    -- 输入序号（用于排序条件和 NOT 门）
    input_order     INT NOT NULL DEFAULT 0,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- 约束：必须指向一个有效输入
    CONSTRAINT fta_input_has_target CHECK (
        input_type = 0 AND input_event_id IS NOT NULL AND input_gate_id IS NULL
        OR
        input_type = 1 AND input_gate_id IS NOT NULL AND input_event_id IS NULL
    )
);

CREATE INDEX idx_fta_gate_inputs_gate ON knowledge.fta_gate_inputs(gate_id);
CREATE INDEX idx_fta_gate_inputs_event ON knowledge.fta_gate_inputs(input_event_id);
CREATE INDEX idx_fta_gate_inputs_gate2 ON knowledge.fta_gate_inputs(input_gate_id);
```

#### 3.2.4 fta_transfers — 转移门定义

转移门允许一棵树引用另一棵树的子树，实现复用。

```sql
CREATE TABLE IF NOT EXISTS knowledge.fta_transfers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    tree_id         UUID NOT NULL REFERENCES knowledge.fta_trees(id) ON DELETE CASCADE,

    -- 转移源：指向当前树的一个事件（该事件被子树展开）
    source_event_id UUID NOT NULL REFERENCES knowledge.fta_events(id) ON DELETE CASCADE,

    -- 转移方向
    transfer_type   SMALLINT NOT NULL,
                    -- 0:IN（子树移入）, 1:OUT（本树被引用）, 2:REPEATED（重复事件）

    -- 被引用的子树（目标树的事件）
    target_tree_id  UUID REFERENCES knowledge.fta_trees(id) ON DELETE SET NULL,
    target_event_id UUID REFERENCES knowledge.fta_events(id) ON DELETE SET NULL,

    -- 如果是重复事件（REPEATED），指向同一树内的另一个事件
    repeated_event_id UUID REFERENCES knowledge.fta_events(id) ON DELETE SET NULL,

    description     TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fta_transfer_has_target CHECK (
        (transfer_type = 0 OR transfer_type = 1)
        AND target_tree_id IS NOT NULL AND target_event_id IS NOT NULL
        AND repeated_event_id IS NULL
        OR
        transfer_type = 2
        AND repeated_event_id IS NOT NULL
        AND target_tree_id IS NULL AND target_event_id IS NULL
    )
);

CREATE INDEX idx_fta_transfers_tree ON knowledge.fta_transfers(tree_id);
CREATE INDEX idx_fta_transfers_source ON knowledge.fta_transfers(source_event_id);
CREATE INDEX idx_fta_transfers_target ON knowledge.fta_transfers(target_tree_id);
```

#### 3.2.5 fta_cut_sets — 计算出的最小割集

```sql
CREATE TABLE IF NOT EXISTS knowledge.fta_cut_sets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    tree_id         UUID NOT NULL REFERENCES knowledge.fta_trees(id) ON DELETE CASCADE,

    -- 割集编号（1-based）
    cut_set_order   INT NOT NULL DEFAULT 0,

    -- 割集中的事件数（阶数）
    order_count     INT NOT NULL DEFAULT 0,

    -- 割集概率（定量计算后写入）
    probability     DOUBLE PRECISION,

    -- 割集重要性（Phase 2 计算）
    fv_importance   DOUBLE PRECISION,      -- Fussell-Vesely 重要度
    birnbaum_imp    DOUBLE PRECISION,      -- Birnbaum 重要度

    -- 事件列表（JSONB 数组，便于快速展示和查询）
    -- 格式: [{"event_id": "uuid", "event_ref": "EVT-001", "label": "..."}, ...]
    events_json     JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- mocs: 是否来自 MOCUS 算法
    algorithm       SMALLINT NOT NULL DEFAULT 0,
                    -- 0:mocus, 1:bdd, 2:manual

    -- 计算批次（区分多次计算迭代）
    calc_batch      INT NOT NULL DEFAULT 1,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 索引
CREATE INDEX idx_fta_cut_sets_tree ON knowledge.fta_cut_sets(tree_id, cut_set_order);
CREATE INDEX idx_fta_cut_sets_order ON knowledge.fta_cut_sets(tree_id, order_count);
CREATE INDEX idx_fta_cut_sets_prob ON knowledge.fta_cut_sets(tree_id, probability DESC);
CREATE INDEX idx_fta_cut_sets_batch ON knowledge.fta_cut_sets(tree_id, calc_batch DESC);
```

#### 3.2.6 fta_event_links — 与 FMEA / KB / LL 条目的多态映射

```sql
CREATE TABLE IF NOT EXISTS knowledge.fta_event_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    tree_id         UUID NOT NULL REFERENCES knowledge.fta_trees(id) ON DELETE CASCADE,
    event_id        UUID NOT NULL REFERENCES knowledge.fta_events(id) ON DELETE CASCADE,

    -- 链接目标（多态）
    link_type       SMALLINT NOT NULL,
                    -- 0:fmea_item, 1:kb_article, 2:lesson, 3:fmea_entry,
                    -- 4:fmea_action, 5:evidence, 6:code_path

    linked_entity_id UUID NOT NULL,

    -- 链接语义
    relation        SMALLINT NOT NULL DEFAULT 0,
                    -- 0:causes（基本事件是 FMEA 失效原因）,
                    -- 1:mitigates（FMEA 措施可缓解此事件）,
                    -- 2:describes（KB 描述此事件）,
                    -- 3:references（一般引用）,
                    -- 4:derived_from（从 FMEA 自动派生）

    description     TEXT NOT NULL DEFAULT '',
    weight          SMALLINT NOT NULL DEFAULT 5,  -- 关联强度 1-10

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (event_id, link_type, linked_entity_id)
);

CREATE INDEX idx_fta_event_links_tree ON knowledge.fta_event_links(tree_id);
CREATE INDEX idx_fta_event_links_event ON knowledge.fta_event_links(event_id);
CREATE INDEX idx_fta_event_links_target ON knowledge.fta_event_links(link_type, linked_entity_id);
```

#### 3.2.7 fta_audit_logs — FTA 审计日志

```sql
CREATE TABLE IF NOT EXISTS knowledge.fta_audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tree_id         UUID NOT NULL REFERENCES knowledge.fta_trees(id) ON DELETE CASCADE,
    event_id        UUID REFERENCES knowledge.fta_events(id) ON DELETE SET NULL,
    action          SMALLINT NOT NULL,
                    -- 1:tree_created, 2:tree_status_change, 3:event_added,
                    -- 4:event_modified, 5:event_removed, 6:gate_added,
                    -- 7:gate_modified, 8:gate_removed, 9:calc_run,
                    -- 10:calc_recalc, 11:cut_set_invalidated,
                    -- 12:link_added, 13:link_removed, 14:yaml_sync,
                    -- 15:review_submitted, 16:review_approved
    operator_id     TEXT NOT NULL,
    comment         TEXT NOT NULL DEFAULT '',
    detail_json     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_fta_audit_tree ON knowledge.fta_audit_logs(tree_id, created_at DESC);
CREATE INDEX idx_fta_audit_operator ON knowledge.fta_audit_logs(operator_id);
```

### 3.3 事件概率来源

基本事件的概率可以通过以下方式获取：

```sql
-- 概率值优先级（从高到低）:
-- 1. fta_events.probability（直接填写）
-- 2. fta_events.failure_rate + mission_time → 1 - exp(-λt)
-- 3. 从关联的 fmea_items.occurrence 映射（occurrence 1-10 → 概率）
-- 4. 从 KB 条目中提取

-- 概率值存储为 DOUBLE PRECISION（float8），
-- 典型范围：1e-12（罕见） ~ 1.0（必然发生）
-- 定量计算时需要精确到 1e-15 精度
```

### 3.4 多版本支持

FTA 树支持版本化：

```sql
-- 版本管理策略（与 FMEA 一致，参考 tech-knowledge-management.md §5）:
-- 1. 每次重大修改创建新 fta_version
-- 2. 旧版本数据保留在表中（不删除）
-- 3. 同一树的不同版本共享事件 ID（如果语义相同）
-- 4. 割集计算结果按 tree_id + calc_batch 区分版本

-- 版本快照：每次正式版本发布时，复制 fta_events / fta_gates 到快照表
CREATE TABLE IF NOT EXISTS knowledge.fta_version_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tree_id         UUID NOT NULL REFERENCES knowledge.fta_trees(id) ON DELETE CASCADE,
    version         TEXT NOT NULL,
    snapshot_data   JSONB NOT NULL,        -- 完整树结构的 JSON 快照
    change_summary  TEXT NOT NULL DEFAULT '',
    triggered_by    SMALLINT NOT NULL DEFAULT 0,
                    -- 0:manual, 1:yaml_sync, 2:auto_calc
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (tree_id, version)
);

CREATE INDEX idx_fta_snaps_tree ON knowledge.fta_version_snapshots(tree_id, version DESC);
```

---

## 4. Part 2: 算法引擎

### 4.1 最小割集计算（MOCUS 下行法）

#### 4.1.1 算法原理

MOCUS（Method of Obtaining Cut Sets）是经典的下行法（Top-down）算法：

```
输入：故障树（从顶事件出发的 AND/OR 门树）
输出：最小割集列表

算法步骤：
1. 从顶事件开始
2. 逐层下行：
   - OR 门：将每个输入分支拆成独立行（增加割集数量）
   - AND 门：将输入合并到同一行（增加割集阶数）
3. 遇到基本事件 → 替换为事件 ID
4. 展开完成后，每行是一个割集（按基本事件集合）
5. 最小化：移除包含另一割集的超集（子集消去）
```

```
示例：
         TOP (OR)
        /     \
      AND     EVT-C
     /   \
  EVT-A  EVT-B

展开过程：
Step 0: {{ AND, EVT-C }}
Step 1: OR 门展开 → {{ AND }, { EVT-C }}
Step 2: AND 门展开 → {{ EVT-A, EVT-B }, { EVT-C }}
Step 3: 基本事件替换完成

割集: {EVT-A, EVT-B} 和 {EVT-C}
（已是最小化，无子集/超集关系）
```

#### 4.1.2 算法实现（Go 伪代码）

```go
// pkg/fta/engine/mocus.go

package engine

// CutSet 表示一个最小割集
type CutSet struct {
    EventIDs    []uuid.UUID
    EventRefs   []string
    Order       int     // 阶数（包含的基本事件数）
}

// MOCUSResult 保存计算结果
type MOCUSResult struct {
    CutSets     []CutSet
    TotalCount  int
    MaxOrder    int
    MinOrder    int
    Duration    time.Duration
}

// ComputeMOCUS 执行下行法计算
func ComputeMOCUS(ctx context.Context, tree *domain.FTATree,
    events map[uuid.UUID]*domain.FTAEvent,
    gates map[uuid.UUID]*domain.FTAGate,
    gateInputs map[uuid.UUID][]*domain.FTAGateInput) (*MOCUSResult, error) {

    // 1. 找到顶事件对应的门
    topGate, err := findTopGate(tree.TopEventID, gates, gateInputs)
    if err != nil {
        return nil, err
    }

    // 2. 递归下行展开
    // 使用 [][]uuid.UUID 作为中间结果集
    // 每行是一个候选割集
    rows := [][]uuid.UUID{}

    for _, input := range gateInputs[topGate.ID] {
        subRows, err := expand(input, events, gates, gateInputs)
        if err != nil {
            return nil, err
        }
        rows = append(rows, subRows...)
    }

    // 如果顶级是 AND 门，需合并
    // ...

    // 3. 最小化（子集消去）
    minimal := minimizeCutSets(rows)

    // 4. 格式化为结果
    result := &MOCUSResult{
        CutSets:    toCutSets(minimal, events),
        TotalCount: len(minimal),
        Duration:   time.Since(start),
    }

    return result, nil
}

// expand 递归展开一个门或事件
func expand(input *domain.FTAGateInput,
    events map[uuid.UUID]*domain.FTAEvent,
    gates map[uuid.UUID]*domain.FTAGate,
    gateInputs map[uuid.UUID][]*domain.FTAGateInput) ([][]uuid.UUID, error) {

    switch input.InputType {
    case 0: // 输入是事件
        evt := events[*input.InputEventID]
        switch evt.EventType {
        case domain.EventTypeBasic, domain.EventTypeHouse, domain.EventTypeUndeveloped:
            // 基本事件 → 作为叶子节点返回
            return [][]uuid.UUID{{evt.ID}}, nil
        case domain.EventTypeIntermediate:
            // 中间事件 → 找到对应的门继续展开
            gate := findGateByParentEvent(evt.ID, gates, gateInputs)
            if gate == nil {
                return nil, fmt.Errorf("intermediate event %s has no gate", evt.EventRef)
            }
            return expandGate(gate, events, gates, gateInputs)
        }
    case 1: // 输入直接是门
        gate := gates[*input.InputGateID]
        return expandGate(gate, events, gates, gateInputs)
    }
    return nil, fmt.Errorf("unknown input type: %d", input.InputType)
}

// expandGate 根据门类型展开
func expandGate(gate *domain.FTAGate,
    events map[uuid.UUID]*domain.FTAEvent,
    gates map[uuid.UUID]*domain.FTAGate,
    gateInputs map[uuid.UUID][]*domain.FTAGateInput) ([][]uuid.UUID, error) {

    inputs := gateInputs[gate.ID]
    var result [][]uuid.UUID

    switch gate.GateType {
    case domain.GateTypeOR:
        // OR 门：每个输入独立成行
        for _, input := range inputs {
            rows, err := expand(input, events, gates, gateInputs)
            if err != nil {
                return nil, err
            }
            result = append(result, rows...)
        }

    case domain.GateTypeAND:
        // AND 门：所有输入合并到同一行
        // 取第一个输入展开
        firstRows, err := expand(inputs[0], events, gates, gateInputs)
        if err != nil {
            return nil, err
        }
        result = firstRows

        for _, input := range inputs[1:] {
            nextRows, err := expand(input, events, gates, gateInputs)
            if err != nil {
                return nil, err
            }
            // 笛卡尔积合并
            var merged [][]uuid.UUID
            for _, r1 := range result {
                for _, r2 := range nextRows {
                    combined := append(append([]uuid.UUID{}, r1...), r2...)
                    merged = append(merged, combined)
                }
            }
            result = merged
        }

    // NOT/XOR: 暂不实现，v2.0 随 BDD 方法一起引入
    // case domain.GateTypeNOT: ...
    // case domain.GateTypeXOR: ...

    case domain.GateTypeINHIBIT:
        // 禁门（INHIBIT）：AND 语义 + inhibit_condition 过滤
        // inhibit_condition 作为额外约束，与所有输入做笛卡尔积
        if len(inputs) == 0 {
            return nil, nil
        }
        firstRows, err := expand(inputs[0], events, gates, gateInputs)
        if err != nil {
            return nil, err
        }
        result = firstRows
        for _, input := range inputs[1:] {
            nextRows, err := expand(input, events, gates, gateInputs)
            if err != nil {
                return nil, err
            }
            var merged [][]uuid.UUID
            for _, r1 := range result {
                for _, r2 := range nextRows {
                    combined := append(append([]uuid.UUID{}, r1...), r2...)
                    merged = append(merged, combined)
                }
            }
            result = merged
        }

    case domain.GateTypePAND:
        // PAND（优先与门）：时序约束不影响割集展开
        // 割集层面等价于 AND（含全部输入事件）
        if len(inputs) == 0 {
            return nil, nil
        }
        firstRows, err := expand(inputs[0], events, gates, gateInputs)
        if err != nil {
            return nil, err
        }
        result = firstRows
        for _, input := range inputs[1:] {
            nextRows, err := expand(input, events, gates, gateInputs)
            if err != nil {
                return nil, err
            }
            var merged [][]uuid.UUID
            for _, r1 := range result {
                for _, r2 := range nextRows {
                    combined := append(append([]uuid.UUID{}, r1...), r2...)
                    merged = append(merged, combined)
                }
            }
            result = merged
        }
    }

    return result, nil
}

// minimizeCutSets 执行子集消去（最小化）
// 先按 size 升序排，大集合如果包含小集合则移除
func minimizeCutSets(rows [][]uuid.UUID) [][]uuid.UUID {
    // 1. 去重（将每个行转为 set）
    var sets []map[uuid.UUID]struct{}
    for _, row := range rows {
        set := make(map[uuid.UUID]struct{})
        for _, eid := range row {
            set[eid] = struct{}{}
        }
        sets = append(sets, set)
    }

    // 2. 按 size 升序排序
    sort.Slice(sets, func(i, j int) bool {
        return len(sets[i]) < len(sets[j])
    })

    // 3. 子集消去：从最小集合开始，移除包含它的所有超集
    keep := make([]bool, len(sets))
    for i := range sets {
        keep[i] = true
    }
    for i := 0; i < len(sets); i++ {
        if !keep[i] {
            continue
        }
        for j := i + 1; j < len(sets); j++ {
            if !keep[j] {
                continue
            }
            if isSubsetOf(sets[i], sets[j]) {
                // sets[i] 是 sets[j] 的子集 → 移除 sets[j]
                keep[j] = false
            } else if isSubsetOf(sets[j], sets[i]) {
                // sets[j] 是 sets[i] 的子集 → 移除 sets[i]
                keep[i] = false
                break
            }
        }
    }

    // 4. 收集保留的集合
    var minimal []map[uuid.UUID]struct{}
    for i, k := range keep {
        if k {
            minimal = append(minimal, sets[i])
        }
    }

    // 5. 转回 []uuid.UUID
    result := make([][]uuid.UUID, len(minimal))
    for i, set := range minimal {
        for id := range set {
            result[i] = append(result[i], id)
        }
    }
    return result
}

func isSubsetOf(a, b map[uuid.UUID]struct{}) bool {
    if len(a) > len(b) {
        return false
    }
    for k := range a {
        if _, ok := b[k]; !ok {
            return false
        }
    }
    return true
}
```

#### 4.1.3 性能考量

| 树规模 | 节点数 | 预期割集数 | 计算时间（估计） |
|--------|--------|-----------|----------------|
| 小型 | < 50 | < 100 | < 10ms |
| 中型 | 50-200 | 100-10K | 10ms-1s |
| 大型 | 200-1000 | 10K-100K | 1-30s |
| 超大型 | > 1000 | > 100K | 建议使用 BDD |

**优化策略：**
1. 在展开过程中进行早期剪枝（深度优先 + 重复事件检测）
2. 子集消去使用排序后比较（O(n log n) instead of O(n²)）
3. 计算超时保护（默认 30s 超时）

### 4.2 定性分析接口

```go
// pkg/fta/engine/qualitative.go

type QualitativeResult struct {
    TreeID          uuid.UUID
    CutSets         []CutSet
    TotalCount      int

    // 阶数分布
    OrderDist       map[int]int    // {1: 5, 2: 12, 3: 3} 表示 1阶5个，2阶12个

    // 最小/最大/平均阶数
    MinOrder        int
    MaxOrder        int
    AvgOrder        float64

    // 基本事件出现频次（事件 → 出现在多少个割集中）
    EventFrequency  map[uuid.UUID]int

    // 时间
    CalculatedAt    time.Time
    Duration        time.Duration
}

// 定性分析：计算最小割集 + 统计信息
func (e *Engine) AnalyzeQualitative(ctx context.Context, treeID uuid.UUID) (*QualitativeResult, error) {
    // 1. 从 DB 加载树结构
    tree, events, gates, gateInputs, err := e.store.LoadFullTree(ctx, treeID)
    if err != nil {
        return nil, err
    }

    // 2. 环检测
    if err := e.validateNoCycles(tree, gates, gateInputs); err != nil {
        return nil, fmt.Errorf("tree has cycles: %w", err)
    }

    // 3. 执行 MOCUS
    mocusResult, err := ComputeMOCUS(ctx, tree, events, gates, gateInputs)
    if err != nil {
        return nil, err
    }

    // 4. 统计
    result := &QualitativeResult{
        TreeID:        treeID,
        CutSets:       mocusResult.CutSets,
        TotalCount:    mocusResult.TotalCount,
        OrderDist:     make(map[int]int),
        EventFrequency: make(map[uuid.UUID]int),
        MinOrder:      mocusResult.MinOrder,
        MaxOrder:      mocusResult.MaxOrder,
        CalculatedAt:  time.Now(),
        Duration:      mocusResult.Duration,
    }

    for _, cs := range mocusResult.CutSets {
        result.OrderDist[cs.Order]++
        result.AvgOrder += float64(cs.Order)
        for _, eid := range cs.EventIDs {
            result.EventFrequency[eid]++
        }
    }
    if result.TotalCount > 0 {
        result.AvgOrder /= float64(result.TotalCount)
    }

    return result, nil
}
```

### 4.3 定量概率计算接口

#### 4.3.1 AND/OR 概率计算

```go
// pkg/fta/engine/quantitative.go

type QuantitativeResult struct {
    TopEventProbability float64            // 顶事件发生概率
    CutSetProbabilities []CutSetProb       // 每个割集的概率
    TotalProbability    float64            // 所有割集累加概率（近似）

    // 不确定性范围（使用蒙特卡洛时）
    Confidence95Lower   float64
    Confidence95Upper   float64

    // PMHF（随机硬件失效率，per hour）
    PMHF                float64

    CalculatedAt        time.Time
    Duration            time.Duration
}

type CutSetProb struct {
    CutSetOrder int
    Probability float64
    Events      []uuid.UUID
}

// 基本概率运算：
// OR 门: P(A ∪ B) = P(A) + P(B) - P(A ∩ B)
//       近似（小概率时）: P(A) + P(B)
// AND 门: P(A ∩ B) = P(A) × P(B)
// 精确 AND: P(A ∩ B × C) = P(A) × P(B) × P(C)

func (e *Engine) CalculateQuantitative(ctx context.Context, treeID uuid.UUID, opts *QuantOptions) (*QuantitativeResult, error) {
    // 1. 加载全量数据
    tree, events, gates, gateInputs, err := e.store.LoadFullTree(ctx, treeID)
    if err != nil {
        return nil, err
    }

    // 2. 递归计算顶事件概率（自下而上）
    topProb, err := e.calcProbabilityRecursive(tree.TopEventID, events, gates, gateInputs)
    if err != nil {
        return nil, err
    }

    // 3. 计算割集概率
    cutSets, _ := e.store.LoadCutSets(ctx, treeID)
    var cutProbs []CutSetProb
    totalProb := 0.0

    for _, cs := range cutSets {
        prob := 1.0
        for _, evtID := range cs.EventIDs {
            evt := events[evtID]
            prob *= evt.Probability
        }
        cutProbs = append(cutProbs, CutSetProb{
            CutSetOrder: cs.Order,
            Probability: prob,
            Events:      cs.EventIDs,
        })
        totalProb += prob
    }

    result := &QuantitativeResult{
        TopEventProbability: topProb,
        CutSetProbabilities: cutProbs,
        TotalProbability:    totalProb,
        CalculatedAt:        time.Now(),
        Duration:            time.Since(start),
    }

    return result, nil
}

// calcProbabilityRecursive 自下而上递归计算事件概率
func (e *Engine) calcProbabilityRecursive(
    eventID uuid.UUID,
    events map[uuid.UUID]*domain.FTAEvent,
    gates map[uuid.UUID]*domain.FTAGate,
    gateInputs map[uuid.UUID][]*domain.FTAGateInput,
) (float64, error) {

    evt := events[eventID]

    switch evt.EventType {
    case domain.EventTypeBasic:
        return evt.Probability, nil

    case domain.EventTypeHouse:
        if evt.HouseValue {
            return 1.0, nil
        }
        return 0.0, nil

    case domain.EventTypeTop, domain.EventTypeIntermediate:
        gate := findGateByParentEvent(eventID, gates, gateInputs)
        if gate == nil {
            return 0, fmt.Errorf("no gate for event %s", evt.EventRef)
        }

        inputs := gateInputs[gate.ID]
        var inputProbs []float64
        for _, input := range inputs {
            p, err := e.calcProbabilityRecursiveInput(input, events, gates, gateInputs)
            if err != nil {
                return 0, err
            }
            inputProbs = append(inputProbs, p)
        }

        switch gate.GateType {
        case domain.GateTypeOR:
            // P(A ∪ B) = 1 - (1-P(A))×(1-P(B))
            prod := 1.0
            for _, p := range inputProbs {
                prod *= (1.0 - p)
            }
            return 1.0 - prod, nil

        case domain.GateTypeAND:
            // P(A ∩ B) = P(A) × P(B)
            prod := 1.0
            for _, p := range inputProbs {
                prod *= p
            }
            return prod, nil

        // NOT/XOR: v2.0 随 BDD 方法一起引入
        // case domain.GateTypeNOT: ...
        // case domain.GateTypeXOR: ...
        }
    }

    return 0, fmt.Errorf("unknown event type: %d", evt.EventType)
}
```

#### 4.3.2 PMHF 计算

```go
// PMHF（Probabilistic Metric for Random Hardware Failures）
// ISO 26262-10:2018 定义的随机硬件失效率指标

func (e *Engine) CalculatePMHF(ctx context.Context, treeID uuid.UUID) (float64, error) {
    // PMHF = Σ (每个最小割集的贡献)
    // 每个割集贡献 = Π(基本事件失效率) × 诊断覆盖率修正

    // 简化版：顶事件概率 / 任务时间
    quant, err := e.CalculateQuantitative(ctx, treeID, nil)
    if err != nil {
        return 0, err
    }

    tree, err := e.store.GetTree(ctx, treeID)
    if err != nil {
        return 0, err
    }

    if tree.MissionTime > 0 {
        return quant.TopEventProbability / tree.MissionTime, nil
    }

    return 0, fmt.Errorf("mission_time not set for tree %s", treeID)
}
```

### 4.4 重要性排序接口

#### 4.4.1 Fussell-Vesely 重要度

```go
// pkg/fta/engine/importance.go

type ImportanceResult struct {
    TreeID          uuid.UUID
    EventImportance []EventImportance     // 按重要度降序排列
}

type EventImportance struct {
    EventID          uuid.UUID
    EventRef         string
    Label            string
    FussellVesely    float64   // F-V 重要度
    Birnbaum         float64   // Birnbaum 重要度
    RiskReduction    float64   // 风险降低权重（RRW）
    RiskAchievement  float64   // 风险达成权重（RAW）
    OccursInCutSets  int       // 出现在多少个割集中
}

// Fussell-Vesely 重要度:
// I_FV(i) = P(包含事件 i 的所有割集) / P(顶事件)
// = 事件 i 对顶事件概率的贡献比例

func (e *Engine) CalculateFussellVesely(ctx context.Context,
    treeID uuid.UUID, quant *QuantitativeResult,
    cutSets []CutSet, events map[uuid.UUID]*domain.FTAEvent) ([]EventImportance, error) {

    // 1. 按事件汇总割集概率
    eventProbSum := make(map[uuid.UUID]float64)
    eventCount := make(map[uuid.UUID]int)

    for i, cs := range cutSets {
        for _, eid := range cs.EventIDs {
            eventProbSum[eid] += quant.CutSetProbabilities[i].Probability
            eventCount[eid]++
        }
    }

    // 2. 计算 F-V 重要度
    topProb := quant.TopEventProbability
    var results []EventImportance

    for eid, sumProb := range eventProbSum {
        fv := sumProb / topProb
        evt := events[eid]
        results = append(results, EventImportance{
            EventID:        eid,
            EventRef:       evt.EventRef,
            Label:          evt.Label,
            FussellVesely: fv,
            RiskReduction: 1.0 / (1.0 - fv),
            OccursInCutSets: eventCount[eid],
        })
    }

    // 3. 按 F-V 降序排列
    sort.Slice(results, func(i, j int) bool {
        return results[i].FussellVesely > results[j].FussellVesely
    })

    return results, nil
}
```

#### 4.4.2 Birnbaum 重要度

```go
// Birnbaum 重要度:
// I_B(i) = P(顶事件 | P(i)=1) - P(顶事件 | P(i)=0)
// = 顶事件概率对基本事件概率的偏导数

func (e *Engine) CalculateBirnbaum(ctx context.Context,
    treeID uuid.UUID, events map[uuid.UUID]*domain.FTAEvent,
    gates map[uuid.UUID]*domain.FTAGate,
    gateInputs map[uuid.UUID][]*domain.FTAGateInput) ([]EventImportance, error) {

    // 对于每个基本事件，计算:
    // 1. 设 P(i)=1 时的顶事件概率
    // 2. 设 P(i)=0 时的顶事件概率
    // 3. Birnbaum = 差值

    topEventID := findTopEventID(treeID, events)

    var results []EventImportance

    for eid, evt := range events {
        if evt.EventType != domain.EventTypeBasic {
            continue
        }

        // 保存原概率
        originalProb := evt.Probability

        // P(i)=1
        evt.Probability = 1.0
        prob1, _ := e.calcProbabilityRecursive(topEventID, events, gates, gateInputs)

        // P(i)=0
        evt.Probability = 0.0
        prob0, _ := e.calcProbabilityRecursive(topEventID, events, gates, gateInputs)

        // 恢复
        evt.Probability = originalProb

        birnbaum := prob1 - prob0

        results = append(results, EventImportance{
            EventID:     eid,
            EventRef:    evt.EventRef,
            Label:       evt.Label,
            Birnbaum:    birnbaum,
        })
    }

    sort.Slice(results, func(i, j int) bool {
        return results[i].Birnbaum > results[j].Birnbaum
    })

    return results, nil
}
```

### 4.5 算法引擎入口

```go
// pkg/fta/engine/engine.go

type Engine struct {
    store   store.FTAStore
    logger  *zap.Logger
}

type CalcOptions struct {
    IncludeQuantitative bool      // 是否计算定量
    IncludeImportance   bool      // 是否计算重要度
    MaxCutSets          int       // 最大割集数（0=不限制）
    Timeout             time.Duration
    Algorithm           string    // "mocus" | "bdd" (Phase 2)
}

type FullAnalysisResult struct {
    Qualitative  *QualitativeResult
    Quantitative *QuantitativeResult
    Importance   *ImportanceResult
    PMHF         float64
}

func (e *Engine) RunFullAnalysis(ctx context.Context, treeID uuid.UUID, opts *CalcOptions) (*FullAnalysisResult, error) {
    // 1. 定性分析
    qual, err := e.AnalyzeQualitative(ctx, treeID)
    if err != nil {
        return nil, err
    }

    result := &FullAnalysisResult{
        Qualitative: qual,
    }

    // 2. 缓存割集
    if err := e.store.SaveCutSets(ctx, treeID, qual.CutSets, "mocus"); err != nil {
        return nil, err
    }

    // 3. 定量分析
    if opts != nil && opts.IncludeQuantitative {
        quant, err := e.CalculateQuantitative(ctx, treeID, nil)
        if err != nil {
            e.logger.Warn("quantitative analysis failed", zap.Error(err))
        } else {
            result.Quantitative = quant
            result.PMHF, _ = e.CalculatePMHF(ctx, treeID)
        }
    }

    // 4. 重要度分析
    if opts != nil && opts.IncludeImportance && result.Quantitative != nil {
        tree, events, gates, gateInputs, err := e.store.LoadFullTree(ctx, treeID)
        if err == nil {
            fv, _ := e.CalculateFussellVesely(ctx, treeID, result.Quantitative,
                result.Qualitative.CutSets, events)
            birn, _ := e.CalculateBirnbaum(ctx, treeID, events, gates, gateInputs)
            result.Importance = &ImportanceResult{
                TreeID:          treeID,
                EventImportance: mergeImportance(fv, birn),
            }
        }
    }

    // 5. 更新树的计算元数据
    e.store.UpdateCalcMeta(ctx, treeID, &CalcMeta{
        CutSetCount: qual.TotalCount,
        Duration:    result.Qualitative.Duration,
    })

    return result, nil
}
```

---

## 5. Part 3: 可视化引擎

### 5.1 文本树输出格式

```go
// pkg/fta/visual/text_tree.go

// 输出示例：

// Tree: Brake System Failure (FTA-TREE-001)
// =========================================
// TOP: [OR] Brake system failure
// ├── GATE-001: [AND] Brake ECU + Pedal dual failure
// │   ├── EVT-001: [BASIC] Brake ECU power supply failure [P=1.2e-4]
// │   └── EVT-002: [BASIC] Pedal sensor dual redundant failure [P=5.0e-5]
// ├── GATE-002: [OR] Brake pedal mechanical failure
// │   ├── EVT-003: [BASIC] Pedal spring fatigue fracture [P=3.0e-6]
// │   └── GATE-003: [AND] Pedal position sensor failure
// │       ├── EVT-004: [BASIC] Hall sensor 1 failure [P=1.0e-5]
// │       └── EVT-005: [BASIC] Hall sensor 2 failure [P=1.0e-5]
// └── EVT-006: [BASIC] CAN bus communication loss [P=2.0e-4]
//
// --- 统计分析 ---
// Total cut sets: 5
// Order distribution: 1st=2, 2nd=3
// Min order: 1, Max order: 2
// Top event probability: 3.47e-4
// PMHF: 3.47e-7 /h

func (v *Visualizer) RenderTextTree(ctx context.Context, treeID uuid.UUID) (string, error) {
    tree, events, gates, gateInputs, err := v.store.LoadFullTree(ctx, treeID)
    if err != nil {
        return "", err
    }

    var sb strings.Builder
    sb.WriteString(fmt.Sprintf("Tree: %s (%s)\n", tree.Name, treeID))
    sb.WriteString(strings.Repeat("=", len(tree.Name)+20) + "\n")

    // 从顶事件开始递归渲染
    topEvent := events[tree.TopEventID]
    v.renderEventTree(&sb, topEvent, events, gates, gateInputs, "", true)

    // 添加统计信息
    meta, _ := v.store.GetTreeMeta(ctx, treeID)
    if meta != nil {
        sb.WriteString("\n--- 统计分析 ---\n")
        sb.WriteString(fmt.Sprintf("Total cut sets: %d\n", meta.CutSetCount))
        // ...
    }

    return sb.String(), nil
}
```

### 5.2 Graphviz DOT 格式输出

```go
// pkg/fta/visual/dot.go

// 输出示例（DOT format）：

// digraph FT_BrakeSystem {
//     rankdir=TB;
//     node [shape=box, style="rounded,filled", fillcolor="#E8F0FE"];
//
//     // 顶事件
//     TOP [label="Brake system failure", shape=box, fillcolor="#FFCCCC"];
//
//     // 门
//     GATE_001 [label="AND", shape=invtriangle, fillcolor="#FFF3CD"];
//     GATE_002 [label="OR",  shape=triangle, fillcolor="#FFF3CD"];
//     GATE_003 [label="AND", shape=invtriangle, fillcolor="#FFF3CD"];
//
//     // 基本事件
//     EVT_001 [label="Brake ECU power supply failure\nP=1.2e-4", shape=ellipse, fillcolor="#D4EDDA"];
//     EVT_002 [label="Pedal sensor dual redundant failure\nP=5.0e-5", shape=ellipse, fillcolor="#D4EDDA"];
//     EVT_003 [label="Pedal spring fatigue fracture\nP=3.0e-6", shape=ellipse, fillcolor="#D4EDDA"];
//     EVT_004 [label="Hall sensor 1 failure\nP=1.0e-5", shape=ellipse, fillcolor="#D4EDDA"];
//     EVT_005 [label="Hall sensor 2 failure\nP=1.0e-5", shape=ellipse, fillcolor="#D4EDDA"];
//     EVT_006 [label="CAN bus communication loss\nP=2.0e-4", shape=ellipse, fillcolor="#D4EDDA"];
//
//     // 边
//     TOP -> GATE_001;
//     TOP -> GATE_002;
//     TOP -> EVT_006;
//     GATE_001 -> EVT_001;
//     GATE_001 -> EVT_002;
//     GATE_002 -> EVT_003;
//     GATE_002 -> GATE_003;
//     GATE_003 -> EVT_004;
//     GATE_003 -> EVT_005;
// }

func (v *Visualizer) RenderDOT(ctx context.Context, treeID uuid.UUID) (string, error) {
    tree, events, gates, gateInputs, err := v.store.LoadFullTree(ctx, treeID)
    if err != nil {
        return "", err
    }

    var sb strings.Builder
    safeName := sanitizeDOTID(tree.Name)
    sb.WriteString(fmt.Sprintf("digraph FT_%s {\n", safeName))
    sb.WriteString("    rankdir=TB;\n")
    sb.WriteString("    node [shape=box, style=\"rounded,filled\", fillcolor=\"#E8F0FE\"];\n\n")

    // 递归生成节点和边
    // ... (递归遍历树结构)

    sb.WriteString("}\n")
    return sb.String(), nil
}
```

### 5.3 Mermaid 流程图输出

```go
// pkg/fta/visual/mermaid.go

// 输出示例（Mermaid）：

// ```mermaid
// graph TD
//     TOP["Brake system failure"]:::top --> G01["AND"]:::gate
//     TOP --> G02["OR"]:::gate
//     TOP --> EVT006["CAN bus communication loss"]:::basic
//     G01 --> EVT001["Brake ECU power supply failure"]:::basic
//     G01 --> EVT002["Pedal sensor dual redundant failure"]:::basic
//     G02 --> EVT003["Pedal spring fatigue fracture"]:::basic
//     G02 --> G03["AND"]:::gate
//     G03 --> EVT004["Hall sensor 1 failure"]:::basic
//     G03 --> EVT005["Hall sensor 2 failure"]:::basic
//
//     classDef top fill:#ffcccc,stroke:#cc0000,stroke-width:2px
//     classDef gate fill:#fff3cd,stroke:#cc9900
//     classDef basic fill:#d4edda,stroke:#28a745
// ```

func (v *Visualizer) RenderMermaid(ctx context.Context, treeID uuid.UUID) (string, error) {
    tree, events, gates, gateInputs, err := v.store.LoadFullTree(ctx, treeID)
    if err != nil {
        return "", err
    }

    var sb strings.Builder
    sb.WriteString("graph TD\n")

    // BFS 遍历树，生成节点和边
    // ...

    sb.WriteString("\n")
    sb.WriteString("    classDef top fill:#ffcccc,stroke:#cc0000,stroke-width:2px\n")
    sb.WriteString("    classDef gate fill:#fff3cd,stroke:#cc9900\n")
    sb.WriteString("    classDef basic fill:#d4edda,stroke:#28a745\n")

    return sb.String(), nil
}
```

### 5.4 可视化引擎接口

```go
// pkg/fta/visual/visualizer.go

type Visualizer struct {
    store store.FTAStore
}

type OutputFormat int

const (
    OutputFormatText    OutputFormat = 0
    OutputFormatDOT     OutputFormat = 1
    OutputFormatMermaid OutputFormat = 2
)

func (v *Visualizer) Render(ctx context.Context, treeID uuid.UUID, format OutputFormat) (string, error) {
    switch format {
    case OutputFormatText:
        return v.RenderTextTree(ctx, treeID)
    case OutputFormatDOT:
        return v.RenderDOT(ctx, treeID)
    case OutputFormatMermaid:
        return v.RenderMermaid(ctx, treeID)
    default:
        return "", fmt.Errorf("unknown format: %d", format)
    }
}

// 割集列表输出
func (v *Visualizer) RenderCutSets(ctx context.Context, treeID uuid.UUID) (string, error) {
    cutSets, err := v.store.LoadCutSets(ctx, treeID)
    if err != nil {
        return "", err
    }

    var sb strings.Builder
    sb.WriteString(fmt.Sprintf("Minimum Cut Sets (%d total)\n", len(cutSets)))
    sb.WriteString("================================\n\n")

    for i, cs := range cutSets {
        sb.WriteString(fmt.Sprintf("CS-%04d [order=%d]: ", i+1, cs.Order))
        for j, eid := range cs.EventIDs {
            if j > 0 {
                sb.WriteString(" ∩ ")
            }
            sb.WriteString(eid.String())
        }
        sb.WriteString("\n")
    }

    return sb.String(), nil
}
```

---

## 6. Part 4: Go 后端模块划分

### 6.1 Package 结构

```
internal/
├── domain/
│   └── fta/
│       ├── tree.go            # FTATree 实体
│       ├── event.go           # FTAEvent + 类型枚举
│       ├── gate.go            # FTAGate + GateInput + 类型枚举
│       ├── transfer.go        # FTATransfer
│       ├── cut_set.go         # CutSet
│       ├── event_link.go      # FTAEventLink
│       ├── snapshot.go        # FTAVersionSnapshot
│       ├── audit.go           # FTAAuditLog
│       └── result.go          # 分析结果值对象
│
├── service/
│   └── fta/
│       ├── service.go         # FTAService 接口 + 构造
│       ├── tree_service.go    # 树 CRUD + 版本管理
│       ├── calc_service.go    # 分析编排（调用 engine）
│       ├── link_service.go    # FMEA/KB 链接管理
│       ├── visualize_service.go # 可视化输出
│       └── yaml_service.go    # YAML 导入导出
│
├── handler/
│   └── fta/
│       ├── tree_handler.go    # 树 CRUD REST
│       ├── calc_handler.go    # 分析触发 API
│       ├── visualize_handler.go # 可视化输出 API
│       └── link_handler.go    # 链接管理 API
│
├── store/
│   └── fta/
│       ├── store.go           # FTAStore 接口定义
│       ├── tree_repo.go       # 树 CRUD
│       ├── event_repo.go      # 事件 CRUD
│       ├── gate_repo.go       # 门 + 输入 CRUD
│       ├── cut_set_repo.go    # 割集 CRUD
│       ├── link_repo.go       # 链接 CRUD
│       └── migration.go       # DDL 初始化
│
├── engine/
│   └── fta/
│       ├── engine.go          # Engine 主入口
│       ├── mocus.go           # MOCUS 下行法
│       ├── qualitative.go     # 定性分析
│       ├── quantitative.go    # 定量分析
│       ├── importance.go      # 重要度排序
│       └── validate.go        # 图结构校验
│
├── visual/
│   └── fta/
│       ├── visualizer.go      # Visualizer 主入口
│       ├── text_tree.go       # 文本树输出
│       ├── dot.go             # Graphviz DOT 输出
│       └── mermaid.go         # Mermaid 输出
│
└── fta_codec/
    ├── yaml_parser.go         # YAML → domain.FTATree
    ├── yaml_serializer.go     # domain.FTATree → YAML
    └── schema.go              # FTA YAML Schema
```

### 6.2 关键接口定义

```go
// internal/service/fta/service.go

// FTAService 是 FTA 模块的业务接口
type FTAService interface {
    // ===== 树 CRUD =====
    CreateTree(ctx context.Context, req *CreateTreeRequest) (*domain.FTATree, error)
    GetTree(ctx context.Context, id uuid.UUID) (*domain.FTATree, error)
    ListTrees(ctx context.Context, filter TreeFilter) ([]*domain.FTATree, int64, error)
    UpdateTree(ctx context.Context, req *UpdateTreeRequest) (*domain.FTATree, error)
    DeleteTree(ctx context.Context, id uuid.UUID) error

    // ===== 事件管理 =====
    AddEvent(ctx context.Context, req *AddEventRequest) (*domain.FTAEvent, error)
    UpdateEvent(ctx context.Context, req *UpdateEventRequest) (*domain.FTAEvent, error)
    RemoveEvent(ctx context.Context, treeID, eventID uuid.UUID) error
    ListEvents(ctx context.Context, treeID uuid.UUID) ([]*domain.FTAEvent, error)

    // ===== 门管理 =====
    AddGate(ctx context.Context, req *AddGateRequest) (*domain.FTAGate, error)
    UpdateGate(ctx context.Context, req *UpdateGateRequest) error
    RemoveGate(ctx context.Context, gateID uuid.UUID) error

    // ===== 分析 =====
    RunQualitative(ctx context.Context, treeID uuid.UUID) (*engine.QualitativeResult, error)
    RunFullAnalysis(ctx context.Context, treeID uuid.UUID, opts *engine.CalcOptions) (*engine.FullAnalysisResult, error)

    // ===== 可视化 =====
    RenderTree(ctx context.Context, treeID uuid.UUID, format visual.OutputFormat) (string, error)
    RenderCutSets(ctx context.Context, treeID uuid.UUID) (string, error)

    // ===== 链接 =====
    LinkToFMEA(ctx context.Context, eventID uuid.UUID, fmeaItemID uuid.UUID, relation int) (*domain.FTAEventLink, error)
    LinkToKB(ctx context.Context, eventID uuid.UUID, articleID uuid.UUID, relation int) (*domain.FTAEventLink, error)
    ListLinks(ctx context.Context, eventID uuid.UUID) ([]*domain.FTAEventLink, error)

    // ===== YAML =====
    ImportFromYAML(ctx context.Context, yamlContent []byte) (*domain.FTATree, error)
    ExportToYAML(ctx context.Context, treeID uuid.UUID) ([]byte, error)
}
```

### 6.3 Store 接口定义

```go
// internal/store/fta/store.go

type FTAStore interface {
    // ===== 树 =====
    CreateTree(ctx context.Context, tree *domain.FTATree) (*domain.FTATree, error)
    GetTree(ctx context.Context, id uuid.UUID) (*domain.FTATree, error)
    GetTreeByIDWithEvents(ctx context.Context, id uuid.UUID) (*domain.FTATree, error)
    ListTrees(ctx context.Context, filter TreeFilter) ([]*domain.FTATree, int64, error)
    UpdateTree(ctx context.Context, tree *domain.FTATree) error
    DeleteTree(ctx context.Context, id uuid.UUID) error
    UpdateCalcMeta(ctx context.Context, treeID uuid.UUID, meta *CalcMeta) error

    // ===== 全量加载 =====
    LoadFullTree(ctx context.Context, treeID uuid.UUID) (
        tree *domain.FTATree,
        events map[uuid.UUID]*domain.FTAEvent,
        gates map[uuid.UUID]*domain.FTAGate,
        gateInputs map[uuid.UUID][]*domain.FTAGateInput,
        err error,
    )

    // ===== 事件 =====
    CreateEvent(ctx context.Context, event *domain.FTAEvent) (*domain.FTAEvent, error)
    UpdateEvent(ctx context.Context, event *domain.FTAEvent) error
    DeleteEvent(ctx context.Context, id uuid.UUID) error
    ListEventsByTree(ctx context.Context, treeID uuid.UUID) ([]*domain.FTAEvent, error)
    GetEvent(ctx context.Context, id uuid.UUID) (*domain.FTAEvent, error)

    // ===== 门 =====
    CreateGate(ctx context.Context, gate *domain.FTAGate) (*domain.FTAGate, error)
    CreateGateInput(ctx context.Context, input *domain.FTAGateInput) error
    UpdateGate(ctx context.Context, gate *domain.FTAGate) error
    DeleteGate(ctx context.Context, id uuid.UUID) error
    GetGateInputs(ctx context.Context, gateID uuid.UUID) ([]*domain.FTAGateInput, error)
    ListGatesByParentEvent(ctx context.Context, eventID uuid.UUID) ([]*domain.FTAGate, error)

    // ===== 割集 =====
    SaveCutSets(ctx context.Context, treeID uuid.UUID, cutSets []CutSet, algorithm string) error
    LoadCutSets(ctx context.Context, treeID uuid.UUID) ([]CutSet, error)
    ClearCutSets(ctx context.Context, treeID uuid.UUID) error

    // ===== 链接 =====
    CreateEventLink(ctx context.Context, link *domain.FTAEventLink) (*domain.FTAEventLink, error)
    DeleteEventLink(ctx context.Context, id uuid.UUID) error
    ListEventLinks(ctx context.Context, eventID uuid.UUID) ([]*domain.FTAEventLink, error)
    ListEventsLinkedToFMEA(ctx context.Context, fmeaItemID uuid.UUID) ([]*domain.FTAEvent, error)

    // ===== 审计 =====
    CreateAuditLog(ctx context.Context, log *domain.FTAAuditLog) error
    ListAuditLogs(ctx context.Context, treeID uuid.UUID, limit, offset int) ([]*domain.FTAAuditLog, int64, error)
}
```

### 6.4 FTA as Code — YAML Schema

```yaml
# yuleOSH FTA — FTA as Code 定义
# Schema 版本: v1.0
#
# 一个 YAML 文件对应一棵故障树。

# ——— 元数据 ———
name: "Brake System FTA — Power Supply"
system: "BrakeSystem"
subsystem: "BrakeByWire"
fta_version: "1.0.0"
safety_level: "ASIL_D"     # QM | ASIL_A | ASIL_B | ASIL_C | ASIL_D
target_pmhf: 1e-7          # 目标 PMHF (/h)
created_by: "stefan"
date: "2026-06-20"

# ——— 关联 FMEA（可选） ———
fmea_entry_ref:
  id: "550e8400-e29b-41d4-a716-446655440000"
  name: "BrakeSystem FMEA v1.0"

# ——— 事件定义 ———
events:
  - id: "EVT-TOP"
    type: "top"
    label: "Brake system loss of function"
    description: "Brake system fails to provide requested braking force"

  - id: "EVT-PWR"
    type: "intermediate"
    label: "Brake ECU power supply failure"
    description: "ECU loses power from primary and backup sources"

  - id: "EVT-SEN"
    type: "intermediate"
    label: "Pedal sensor signal loss"
    description: "Both pedal sensor signals unavailable"

  - id: "EVT-CAN"
    type: "basic"
    label: "CAN bus communication loss"
    description: "Complete loss of CAN communication to brake ECU"
    probability: 2.0e-4

  - id: "EVT-PRI-PWR"
    type: "basic"
    label: "Primary 12V power loss"
    description: "Vehicle primary power supply (12V battery) interrupted"
    probability: 1.0e-4

  - id: "EVT-BAK-PWR"
    type: "basic"
    label: "Backup capacitor depleted"
    description: "Backup energy storage capacitor below minimum voltage"
    probability: 2.0e-5

  - id: "EVT-HALL1"
    type: "basic"
    label: "Hall sensor 1 failure"
    description: "Primary Hall effect pedal position sensor failed"
    probability: 1.0e-5

  - id: "EVT-HALL2"
    type: "basic"
    label: "Hall sensor 2 failure"
    description: "Secondary Hall effect pedal position sensor failed"
    probability: 1.0e-5

# ——— 门定义 ———
gates:
  # 顶事件：Brake loss (OR) → power failure OR sensor loss OR CAN loss
  - id: "GATE-TOP"
    parent_event: "EVT-TOP"
    gate_type: "OR"
    inputs:
      - type: "event"    # 事件作为输入
        ref: "EVT-PWR"
      - type: "event"
        ref: "EVT-SEN"
      - type: "event"
        ref: "EVT-CAN"

  # Power failure: (AND) primary loss AND backup loss
  - id: "GATE-PWR"
    parent_event: "EVT-PWR"
    gate_type: "AND"
    inputs:
      - type: "event"
        ref: "EVT-PRI-PWR"
      - type: "event"
        ref: "EVT-BAK-PWR"

  # Sensor signal loss: (AND) Hall1 fails AND Hall2 fails
  - id: "GATE-SEN"
    parent_event: "EVT-SEN"
    gate_type: "AND"
    inputs:
      - type: "event"
        ref: "EVT-HALL1"
      - type: "event"
        ref: "EVT-HALL2"

# ——— 链接定义（与 FMEA / KB 关联） ———
links:
  - event: "EVT-PRI-PWR"
    target_type: "fmea_item"
    target_id: "550e8400-e29b-41d4-a716-446655440001"
    relation: "derived_from"
    description: "Derived from FMEA item BM-001: VCC short to GND"

  - event: "EVT-HALL1"
    target_type: "kb_article"
    target_id: "550e8400-e29b-41d4-a716-446655440010"
    relation: "describes"
    description: "KB article on Hall sensor failure modes and root causes"
```

---

## 7. Part 5: 与现有模块集成

### 7.1 集成总览

| yuleOSH 模块 | 集成方式 | 方向 |
|-------------|----------|------|
| **FMEA** | 基本事件通过 `fta_event_links` 引用 `fmea_items` | 双向往来 |
| **KB** | 基本事件通过 `fta_event_links` 引用 `kb_articles` | 单向（FTA→KB） |
| **LL** | 割集→Lesson 自动创建（高风险割集） | FTA→LL |
| **store** | 新增 `pkg/store/fta/` 子包 | FTA→store |
| **evidence** | 分析结果通过 `evidence_id` 字段引用 | FTA→evidence |
| **spec** | FTA 结果可作为 spec 模块的验证输入 | spec→FTA（读取） |

### 7.2 FMEA ⇄ FTA 双向链接

```
FMEA 方向（归纳）：具体的失效原因 → 失效模式 → 失效影响 → 顶事件
FTA 方向（演绎）：顶事件 → 中间事件（逻辑门） → 基本事件

双向链接：
┌────────────────────────────────────────────────────┐
│  FMEA Item:                                       │
│    failure_cause: "Sensor VCC short to GND"       │
│    failure_mode:  "Pedal sensor stuck at 0V"      │
│    failure_effect: "Brake enters failsafe mode"   │
└──────────┬─────────────────────────────────────────┘
           │ fta_event_links (relation: causes / derived_from)
           ▼
┌────────────────────────────────────────────────────┐
│  FTA 基本事件:                                      │
│    event_ref: "EVT-VCC-SHORT"                     │
│    label: "Sensor VCC short to GND"               │
│    probability: 3.0e-5                            │
└────────────────────────────────────────────────────┘
```

**FTA 从 FMEA 自动创建基本事件的流程：**

```go
// FMEA Item → FTA Basic Event 自动映射
//
// Mapped from: fmea_items
//   failure_cause → fta_events.label
//   occurrence (1-10) → fta_events.probability (映射表)
//   severity / detection → 存为 extra 字段
//
// Occurrence → Probability 映射表:
const occurrenceToProb = map[int]float64{
    1: 1.0e-6,   // 极低
    2: 5.0e-6,
    3: 1.0e-5,
    4: 5.0e-5,
    5: 1.0e-4,
    6: 5.0e-4,
    7: 1.0e-3,
    8: 5.0e-3,
    9: 1.0e-2,
    10: 5.0e-2,  // 极高
}
```

### 7.3 FTA → FMEA 反向传播

当 FTA 计算完成后，高重要度的基本事件可以反向传播到 FMEA：

```go
// FTA 结果 → FMEA RPN 调整建议
//
// 触发条件: FTA 分析完成后
// 逻辑:
//   1. 找出 Fussell-Vesely 重要度 > 0.01 的基本事件
//   2. 通过 fta_event_links 找到关联的 fmea_items
//   3. 比较 fta 概率与 fmea occurrence：若概率高但 occurrence 低，标记待调整
//   4. 自动创建 FMEA action 建议
func (s *FTAService) PropagateToFMEA(ctx context.Context, treeID uuid.UUID) error {
    tree, err := s.store.GetTree(ctx, treeID)
    if err != nil {
        return err
    }
    if tree.FMEAEntryID == nil {
        return nil  // 没有关联 FMEA
    }

    // 计算重要度
    result, err := s.Engine.RunFullAnalysis(ctx, treeID, &engine.CalcOptions{
        IncludeQuantitative: true,
        IncludeImportance:   true,
    })
    if err != nil {
        return err
    }

    // 遍历高重要度事件
    for _, imp := range result.Importance.EventImportance {
        if imp.FussellVesely < 0.01 {
            continue
        }

        // 找到关联的 FMEA items
        links, _ := s.store.ListEventLinks(ctx, imp.EventID)
        for _, link := range links {
            if link.LinkType != domain.LinkTypeFMEAItem {
                continue
            }

            // 创建 FMEA 调整建议（作为 FMEA Action）
            if s.fmeaService != nil {
                _ = s.fmeaService.CreateSuggestedAction(ctx, &domain.FMEAAction{
                    FMEAItemID:  link.LinkedEntityID,
                    Description: fmt.Sprintf(
                        "[Auto] FTA analysis suggests adjusting occurrence: "+
                        "basic event %s has F-V importance=%.4f",
                        imp.EventRef, imp.FussellVesely),
                    Priority: 2,  // medium
                })
            }
        }
    }

    return nil
}
```

### 7.4 evidence 模块集成

```go
// FTA 分析完成后，将结果同步到 evidence 模块

func (s *FTAService) syncToEvidence(ctx context.Context, treeID uuid.UUID, result *engine.FullAnalysisResult) error {
    // 1. 创建分析证据
    evidenceID, err := s.evidenceService.Create(ctx, &evidence.Evidence{
        Type:      evidence.TypeAnalysis,
        EntityID:  treeID.String(),
        EntityType: "fta_tree",
        Content: map[string]interface{}{
            "cut_set_count": result.Qualitative.TotalCount,
            "top_prob":      result.Quantitative.TopEventProbability,
            "pmhf":          result.PMHF,
            "min_order":     result.Qualitative.MinOrder,
            "max_order":     result.Qualitative.MaxOrder,
        },
        Tags: []string{"fta", "auto_analysis"},
    })
    if err != nil {
        return err
    }

    // 2. 更新树的计算引用
    return s.store.UpdateCalcEvidence(ctx, treeID, evidenceID)
}
```

### 7.5 spec 模块集成

```go
// Spec review 时自动检查是否有对应的 FTA

type SpecFTAIntegration struct {
    ftaService FTAService
}

func (s *SpecFTAIntegration) ReviewCheck(ctx context.Context, specID string, system string) (*SpecCheckResult, error) {
    // 查找系统的 FTA 树
    trees, _, _ := s.ftaService.ListTrees(ctx, TreeFilter{
        System: system,
        Status: []int{StatusApproved},
    })

    if len(trees) == 0 {
        return &SpecCheckResult{
            HasFTA: false,
            Message: fmt.Sprintf("System %s has no FTA tree. "+
                "Consider creating one for safety analysis.", system),
        }, nil
    }

    return &SpecCheckResult{HasFTA: true, TreeCount: len(trees)}, nil
}
```

---

## 8. Part 6: 置信度与知识关联

### 8.1 FTA 置信度衰减

FTA 树的分析结果也会纳入置信度体系：

```go
// FTA 树的置信度衰减策略（参考 tech-knowledge-management.md §6.5）

// 触发条件：
// 1. 关联的 FMEA 条目发生变更
// 2. 关联的 KB 条目发生变更
// 3. 关联的代码路径发生变更
// 4. 割集计算结果超过 90 天未重新计算

// 衰减事件映射:
type FTADecayEvent struct {
    EventType   string     // "fmea_change" | "kb_change" | "code_change" | "time_decay"
    TargetID    uuid.UUID
    OldCutSetID uuid.UUID  // 旧割集计算 ID，标记失效
}

func (s *FTAService) OnFMEADecayEvent(ctx context.Context, evt *FTADecayEvent) error {
    // 1. 找到引用该 FMEA item 的所有基本事件
    events, _ := s.store.ListEventsLinkedToFMEA(ctx, evt.TargetID)

    // 2. 对每个事件所属的树，标记割集失效
    seen := make(map[uuid.UUID]bool)
    for _, ev := range events {
        if seen[ev.TreeID] {
            continue
        }
        seen[ev.TreeID] = true

        // 3. 失效旧割集
        _ = s.store.ClearCutSets(ctx, ev.TreeID)

        // 4. 记录审计
        _ = s.store.CreateAuditLog(ctx, &domain.FTAAuditLog{
            TreeID:  ev.TreeID,
            Action:  domain.AuditCutSetInvalidated,
            Comment: fmt.Sprintf("Cut sets invalidated due to FMEA change: %s", evt.TargetID),
        })

        // 5. 通知负责人
        s.notifier.Notify(ctx, ev.TreeID, "FTA tree cut sets invalidated due to FMEA change")
    }

    return nil
}
```

### 8.2 与 knowledge_confidence_snapshots 集成

```go
// FTA 树的置信度快照复用 knowledge.knowledge_confidence_snapshots 表
// entity_type=3 代表 fta_tree, entity_type=4 代表 fta_event

// 使用示例（沿用现有置信度快照表）：
// INSERT INTO knowledge.knowledge_confidence_snapshots
//     (entity_type, entity_id, confidence, decay_reason, auto_flag)
// VALUES
//     (3, 'fta-tree-uuid', 70, 'fmea_change', true);

// FTA 置信度阈值:
const (
    FTAConfidenceHigh   = 80   // 最近重新计算且无依赖变更
    FTAConfidenceMedium = 50   // 超过 90 天未重新计算
    FTAConfidenceLow    = 30   // 关联 FMEA 有重大变更
    FTAConfidenceStale  = 10   // 源 FMEA 已 superseded
)
```

---

## 9. Part 7: CI/CD 集成方案

### 9.1 CI 触点规划

| # | 触点 | 触发时机 | 具体动作 | 阻断级别 |
|---|------|----------|----------|---------|
| 1 | **Pre-commit hook** | `git commit` 前 | FTA YAML 格式校验 + 图结构环检测 | warning |
| 2 | **Merge gate** | PR merge 前 | FTA YAML schema 校验 + 顶事件一致性检查 | blocker |
| 3 | **Post-merge pipeline** | merge 后 | 自动重新计算受影响树的割集 | info |
| 4 | **FMEA change trigger** | FMEA YAML merge | 自动失效关联 FTA 树的旧割集，通知负责人 | info |
| 5 | **FTA auto-calc** | 定时 Job（每周） | 重新计算所有树（检测漂移） | info |

### 9.2 Pre-commit Hook

```yaml
# .githooks/pre-commit — FTA 相关检查

checklist:
  - if 变更文件在 fta/ 目录下:
      run: yuleosh fta validate --yaml {changed_file}
      on_fail:
        severity: warning
        message: "FTA YAML 格式校验未通过，请修复后提交"

  - if 变更文件匹配 fta/*.yaml:
      run: yuleosh fta validate-cycles --yaml {changed_file}
      on_fail:
        severity: warning
        message: "FTA 图结构包含循环引用，请检查门定义"
```

### 9.3 Merge Gate

```go
// internal/pipeline/fta/merge_gate.go

func (g *MergeGate) Check(ctx context.Context, prID string) (*CICheckResult, error) {
    var blockers []string

    // 1. FTA YAML Schema 校验
    changedFTAs := listChangedFTAs(ctx, prID)
    for _, yamlFile := range changedFTAs {
        if err := validateFTAYAML(yamlFile); err != nil {
            blockers = append(blockers, fmt.Sprintf(
                "FTA YAML %s 校验失败: %s", yamlFile, err))
        }
    }

    // 2. 顶事件一致性检查（如果关联 FMEA 也有变更）
    for _, yamlFile := range changedFTAs {
        tree, _ := parseFTAYAML(yamlFile)
        if tree.FMEAEntryID != nil {
            fmeaChanged := checkFMEAChanged(ctx, prID, *tree.FMEAEntryID)
            if fmeaChanged {
                blockers = append(blockers, fmt.Sprintf(
                    "FTA %s 关联的 FMEA 条目同时变更，请确认顶事件一致性",
                    tree.Name))
            }
        }
    }

    // 3. 基本事件概率检查
    for _, yamlFile := range changedFTAs {
        tree, _ := parseFTAYAML(yamlFile)
        for _, evt := range tree.Events {
            if evt.Type == "basic" && evt.Probability > 1.0 {
                blockers = append(blockers, fmt.Sprintf(
                    "Event %s probability=%.2e > 1.0", evt.ID, evt.Probability))
            }
        }
    }

    if len(blockers) > 0 {
        return &CICheckResult{Passed: false, Severity: "blocker", Blockers: blockers}, nil
    }

    return &CICheckResult{Passed: true}, nil
}
```

---

## 10. Part 8: 实施路线

### 10.1 Phase 1 — 核心数据结构 + 基本割集计算（35 人·天）

**定位：** 能创建树、能算最小割集、能存结果。

| 编号 | 工作项 | 人·天 | 依赖 |
|------|--------|:-----:|------|
| P1-1 | DB migration：fta_trees, fta_events, fta_gates, fta_gate_inputs, fta_transfers, fta_cut_sets, fta_event_links, fta_audit_logs, fta_version_snapshots | 3 | — |
| P1-2 | Domain 实体定义（FTATree, FTAEvent, FTAGate, CutSet 等） | 2 | — |
| P1-3 | Store 接口 + repo 实现（CRUD + 全量加载） | 5 | P1-1 |
| P1-4 | FTA Service：树 CRUD + 事件/门管理 | 4 | P1-2 + P1-3 |
| P1-5 | MOCUS 下行法引擎（展开 + 子集消去） | 5 | P1-3 |
| P1-6 | 图结构校验器（环检测 + 无父节点检查） | 2 | P1-5 |
| P1-7 | 定性分析 API（触发 MOCUS + 返回割集） | 2 | P1-5 + P1-6 |
| P1-8 | FTA Handler：REST API（树/事件/门 CRUD + 分析触发） | 3 | P1-4 + P1-7 |
| P1-9 | FTA YAML Schema 定义 + 解析器 | 3 | P1-1 |
| P1-10 | FMEA → FTA 基本事件自动创建（基本映射） | 2 | P1-9 + FMEA 模块 |
| P1-11 | Pre-commit hook + Merge gate（YAML 校验 + 环检测） | 2 | P1-6 + P1-9 |
| P1-12 | 测试 + 文档 | 2 | P1-1 ~ P1-11 |
| | **合计** | **35** | |

**Phase 1 交付状态：**
- ✅ 全量核心表建成（含审计日志）
- ✅ 树/事件/门 CRUD RESTful API
- ✅ MOCUS 下行法最小割集计算
- ✅ 环检测 + 图结构校验
- ✅ FTA YAML 解析 + 导入
- ✅ FMEA → FTA 基本事件映射（基础版）
- ✅ Pre-commit + Merge gate（YAML + 环检测）
- ❌ 定量分析
- ❌ 可视化
- ❌ 重要度排序

### 10.2 Phase 2 — 定量分析 + 可视化（20 人·天）

**定位：** 能算概率、能画树、能排序。

| 编号 | 工作项 | 人·天 | 依赖 |
|------|--------|:-----:|------|
| P2-1 | 定量分析引擎（AND/OR 概率计算 + PMHF） | 4 | Phase 1 |
| P2-2 | 重要度排序（Fussell-Vesely + Birnbaum） | 3 | P2-1 |
| P2-3 | 文本树可视化输出 | 2 | Phase 1 |
| P2-4 | Graphviz DOT 输出 | 2 | Phase 1 |
| P2-5 | Mermaid 流程图输出 | 2 | Phase 1 |
| P2-6 | 可视化 Handler（可选格式参数） | 1 | P2-3 + P2-4 + P2-5 |
| P2-7 | 割集查看 + 事件频率统计 | 2 | Phase 1 |
| P2-8 | FTA → FMEA 反向传播（高重要度事件标记） | 2 | P2-2 + FMEA 模块 |
| P2-9 | 置信度衰减集成 + 割集失效机制 | 2 | Phase 1 + KM 模块 |
| | **合计** | **20** | |

**Phase 2 交付状态（增量）：**
- ✅ 定量分析（顶事件概率 + PMHF）
- ✅ 重要度排序（F-V + Birnbaum）
- ✅ 三种可视化输出（Text / DOT / Mermaid）
- ✅ FTA ↔ FMEA 双向传播
- ✅ 置信度衰减 + 割集失效管理

### 10.3 Phase 3 — 全自动生成（15 人·天）

**定位：** 从 FMEA 自动构建故障树 + 自动重新计算。

| 编号 | 工作项 | 人·天 | 依赖 |
|------|--------|:-----:|------|
| P3-1 | FMEA → FTA 自动树生成（从 FMEA 导出自动构建完整树） | 5 | Phase 2 + FMEA 模块 |
| P3-2 | 自动割集重新计算 Job（FMEA 变更时自动触发） | 3 | Phase 2 + 事件总线 |
| P3-3 | 定时 Job（每周重新计算所有活跃树） | 2 | Phase 2 |
| P3-4 | 割集差异比较（新旧割集 diff） | 2 | Phase 1 |
| P3-5 | FTA 报告自动生成（含可视化截图） | 2 | Phase 2 |
| P3-6 | 顶事件 → FMEA 影响链可视化 | 1 | Phase 2 |
| | **合计** | **15** | |

### 10.4 里程碑总览

```
Phase 1 (35人·天) ───→ Phase 2 (20人·天) ───→ Phase 3 (15人·天)
     │                       │                       │
     ▼                       ▼                       ▼
  核心数据                 定量分析                 全自动
  + 割集计算               + 可视化                 + 自愈
  ┌────────────┐    ┌────────────┐        ┌────────────┐
  │ DDL  + MVC │    │ AND/OR 概率│        │ FMEA→FTA  │
  │ MOCUS 算法 │    │ F-V重要度  │        │ 自动生成   │
  │ YAML 解析  │    │ DOT/Mermaid│        │ 定时重算   │
  │ FMEA 映射  │    │ 反向传播   │        │ 差异比较   │
  │ CI 检查    │    │ 置信度     │        │ 报告生成   │
  │ 环检测     │    │ 割集失效   │        │            │
  └────────────┘    └────────────┘        └────────────┘
```

### 10.5 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|:----:|:----:|---------|
| 割集数量爆炸（门多→组合爆炸） | 中 | 高 | Phase 1 加 MaxCutSets 截断上限；Phase 2 可选 BDD |
| MOCUS 子集消去 O(n²) 性能 | 中 | 中 | 排序后比较 + 提前终止；超过 100K 割集提示 BDD |
| 概率数据不准确 | 低 | 中 | 默认使用 occurrence 映射表，允许人工修正 |
| 环检测漏判 | 低 | 高 | 使用 DFS + 三色标记法，单元测试覆盖典型环场景 |

---

## 11. 附录：FTA 理论基础速查

### 11.1 常见门类型

| 门类型 | 符号 | 输出条件 | 概率公式 |
|--------|------|---------|---------|
| AND | ∩（门形） | 所有输入同时发生 | P = Π Pi |
| OR | ∪（门形） | 至少一个输入发生 | P = 1 - Π(1-Pi) |
| NOT | 否定 | 输入不发生 | P = 1 - Pi |
| XOR | 异或 | 恰好一个输入发生（工程上近似 OR） | P ≈ Pi + Pj - 2PiPj |
| INHIBIT | 六边形 | 输入发生且条件满足 | P = Pi × Pcondition |

### 11.2 基本事件类型

| 类型 | 说明 | 概率来源 |
|------|------|---------|
| Basic（基本事件） | 最基本的失效原因，不再向下分解 | 直接填写或从 FMEA occurrence 映射 |
| Undeveloped（未展开事件） | 暂不展开，标记为未完全分析 | 直接填写 |
| House（房型事件） | 固定开关状态（开/关） | 1.0 或 0.0 |
| Conditional（条件事件） | 描述激活条件 | 条件概率 |

### 11.3 重要度指标速查

| 指标 | 符号 | 含义 | 公式 |
|------|------|------|------|
| Fussell-Vesely | I_FV(i) | 事件 i 对顶事件概率的贡献比例 | I_FV(i) = P(包含 i 的割集之和) / P(顶事件) |
| Birnbaum | I_B(i) | 事件 i 概率变化对顶事件的影响 | I_B(i) = P(顶事件\|P(i)=1) - P(顶事件\|P(i)=0) |
| Risk Reduction Worth | RRW | 事件 i 完全可靠时顶事件概率降低倍数 | RRW = P(顶事件) / P(顶事件\|P(i)=0) |
| Risk Achievement Worth | RAW | 事件 i 一定失效时顶事件概率增加倍数 | RAW = P(顶事件\|P(i)=1) / P(顶事件) |

### 11.4 PMHF 与 ASIL 目标

| ASIL | PMHF 目标（ISO 26262-5:2018） |
|------|------------------------------|
| QM | 无定量要求 |
| ASIL A | < 1.0 × 10⁻⁶ /h |
| ASIL B | < 1.0 × 10⁻⁷ /h |
| ASIL C | < 1.0 × 10⁻⁷ /h |
| ASIL D | < 1.0 × 10⁻⁸ /h |

> **注意：** PMHF 仅覆盖随机硬件失效，不覆盖系统性失效。FTA 定量分析的 PMHF 结果可与 ASIL 目标对比，辅助 ASIL 分解和硬件架构评估。

### 11.5 术语对照

| 中文 | English | 说明 |
|------|---------|------|
| 故障树 | Fault Tree | 演绎失效分析图 |
| 顶事件 | Top Event | 系统的"顶"—需要分析的系统级失效 |
| 基本事件 | Basic Event | 叶子节点，不再向下分解 |
| 中间事件 | Intermediate Event | 通过逻辑门分解的事件 |
| 逻辑门 | Logic Gate | AND/OR/NOT 等布尔运算 |
| 割集 | Cut Set | 导致顶事件发生的失效组合 |
| 最小割集 | Minimal Cut Set | 去掉任意基本事件就不再是割集的割集 |
| 阶数 | Order | 割集中包含的基本事件数量 |
| 下行法 | MOCUS (Method of Obtaining Cut Sets) | 自上而下的割集枚举算法 |
| 上行法 | Bottom-up Method | 自下而上的布尔代数化简 |
| Fussell-Vesely 重要度 | Fussell-Vesely Importance | 事件概率对顶事件的贡献比例 |
| Birnbaum 重要度 | Birnbaum Importance | 事件概率变化对顶事件的影响程度 |

---

> **文档状态：** v1.0 — 初始草案
>
> **后续步骤：**
> 1. 小马审查 architecture + data model + 算法设计
> 2. 分歧点由小明裁决（割集截断策略、Occurrence → Probability 映射表）
> 3. 锁定后进入 Phase 1 编码
