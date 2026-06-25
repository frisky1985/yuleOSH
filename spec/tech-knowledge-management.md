# yuleOSH 知识管理模块 — 技术架构 & 数据模型

> **版本：** v1.2（根据老陈最终复检意见修复）
> **领域：** KB + FMEA + Lessons Learned 三位一体
> **日期：** 2026-06-20
> **状态：** 草案，待小马审查

---

## 目录

1. [总体架构](#1-总体架构)
2. [数据模型设计](#2-数据模型设计)
3. [Go 后端模块划分](#3-go-后端模块划分)
4. [FMEA as Code — YAML Schema](#4-fmea-as-code--yaml-schema)
5. [版本化策略](#5-版本化策略)
6. [搜索与推荐引擎](#6-搜索与推荐引擎)
7. [CI/CD 集成方案](#7-cicd-集成方案)
8. [与现有 yuleOSH 模块的集成点](#8-与现有-yuleosh-模块的集成点)
9. [实施路线](#9-实施路线)
10. [附录：索引策略速查](#10-附录索引策略速查)
11. [ASPICE SWE.5 五层测试 ←→ 三层验证映射](#11-aspice-swe5-五层测试--三层验证映射)
12. [外部系统集成（Polarion/Codebeamer/OSLC）](#12-外部系统集成polarioncodebeameroslc)

---

## 1. 总体架构

### 1.1 架构概览

```
┌──────────────────────────────────────────────────────────────┐
│                       yuleOSH Gateway                         │
├──────────────────────────────────────────────────────────────┤
│                     ┌──────────────┐                          │
│                     │   API Layer  │                          │
│                     │ (REST/gRPC)  │                          │
│                     └──────┬───────┘                          │
│                            │                                  │
│              ┌─────────────┼─────────────┐                    │
│              ▼             ▼             ▼                    │
│       ┌──────────┐ ┌──────────┐ ┌──────────┐                │
│       │ KB       │ │ LL       │ │ FMEA     │                │
│       │ Service  │ │ Service  │ │ Service  │                │
│       └────┬─────┘ └────┬─────┘ └────┬─────┘                │
│            │            │            │                       │
│            └────────────┼────────────┘                       │
│                         ▼                                    │
│              ┌─────────────────────┐                         │
│              │  Domain / Core      │                         │
│              │  (entities, errors,  │                         │
│              │   usecases)          │                         │
│              └──────────┬──────────┘                         │
│                         ▼                                    │
│              ┌─────────────────────┐                         │
│              │   Store Adapter     │                         │
│              │   (PG + pgvector)   │                         │
│              └──────────┬──────────┘                         │
│                         ▼                                    │
│              ┌─────────────────────┐                         │
│              │   External          │                         │
│              │   (ci / pipeline /   │                         │
│              │    evidence / spec)  │                         │
│              └─────────────────────┘                         │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 关键架构决策（ADR）

| ADR | 决策 | 理由 |
|-----|------|------|
| ADR-001 | 独立版本库（非 Git 同步，非纯独立） | 见 §5 版本化策略 |
| ADR-002 | pgvector + BM25 混合搜索 | 语义+关键词互补，停机兜底 |
| ADR-003 | FMEA as Code (YAML) → DB 持久化 | YAML 供人类读写，DB 供程序查询/CI |
| ADR-004 | 证据链统一走 evidence 模块 | 复用已有能力，避免二开 |
| ADR-005 | CI 触点通过 hook script 嵌入现有 Pipeline | 最小侵入 |

---

## 2. 数据模型设计

### 2.1 ER 总览

```
kb_articles 1──N kb_versions
kb_articles N──N knowledge_tags (多对多 ⇢ kb_article_tags)
kb_articles N──N knowledge_dtc_map
kb_articles N──N knowledge_test_map
kb_articles N──N knowledge_code_paths (反向索引)
kb_versions 1──N kb_version_audit_logs

lessons N──N knowledge_tags (多对多 ⇢ lesson_tags)
lessons 1──N lesson_test_seeds
lessons 1──N evidence_links (via evidence module)
lessons 1──N lesson_ota_bindings
lessons 1──N ll_audit_logs

fmea_entries 1──N fmea_audit_logs
fmea_items 1──N fmea_audit_logs
fmea_items 1──N fmea_actions

fmea_entries 1──N fmea_items
fmea_items 1──N fmea_actions
fmea_items N──N fmea_item_cross_ecu

knowledge_confidence_snapshots N──1 kb_articles / lessons / fmea_items
```

### 2.2 核心表定义

以下给出完整 DDL。所有表均继承 yuleOSH store 模块的 `created_at`/`updated_at` 惯例。

#### 2.2.1 kb_articles — 知识条目主表

```sql
CREATE TABLE IF NOT EXISTS knowledge.kb_articles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    summary         TEXT NOT NULL DEFAULT '',
    content         TEXT NOT NULL DEFAULT '',
    body_format     SMALLINT NOT NULL DEFAULT 0,  -- 0:markdown, 1:html
    status          SMALLINT NOT NULL DEFAULT 0,
                    -- 0:draft, 1:review_pending, 2:approved, 3:published, 4:deprecated, 5:archived
                    -- ⚡ 与 Spec 对齐确认：6 状态完整，无遗漏

    -- ASIL 分级
    asil            SMALLINT NOT NULL DEFAULT 0,  -- 0:QM, 1:ASIL_A, 2:ASIL_B, 3:ASIL_C, 4:ASIL_D

    -- AUTOSAR 层级（位掩码，支持多选）
    autosar_layer   SMALLINT NOT NULL DEFAULT 0,
                    -- bit 0:ASW, bit 1:RTE, bit 2:BSW, bit 3:HW

    -- HW BOM 标签（JSON 数组，支持多平台）
    -- JSONB Schema（已与 Spec 确认采用 JSONB，非独立列）：
    -- [
    --   {
    --     "platform": "TDA4VM",       -- 平台名（必填）
    --     "chip": "TDA4VM-Q1",         -- 芯片型号（必填）
    --     "version": "1.2",            -- 硬件版本（可选）
    --     "variant": "high",           -- 硬件变体：low/standard/high（可选）
    --     "location": "left_door",     -- 安装位置（可选）
    --     "supplier": "Bosch"          -- 供应商（可选）
    --   },
    --   ...
    -- ]
    hw_bom          JSONB NOT NULL DEFAULT '[]'::jsonb,
                    -- [{ "platform": "TDA4VM", "chip": "TDA4VM-Q1", "version": "1.2" }, ...]

    -- OTA 版本绑定（JSON）
    ota_binding     JSONB,
                    -- { "min_ota": "v2.1.0", "max_ota": "v2.3.0", "affected": true }

    -- DTC 关联（数组，主表冗余为快速过滤，详情在 knowledge_dtc_map）
    dtc_codes       TEXT[] NOT NULL DEFAULT '{}',

    -- 代码路径反向索引（JSONB 数组）
    code_paths      JSONB NOT NULL DEFAULT '[]'::jsonb,
                    -- [{ "repo": "yuleosh/ecu-fw", "path": "src/swc/brake.c", "line": 42 }, ...]

    -- 元数据
    author_id       TEXT NOT NULL,
    reviewer_id     TEXT,
    tags            TEXT[] NOT NULL DEFAULT '{}',

    -- 置信度（0-100）
    confidence      SMALLINT NOT NULL DEFAULT 100 CHECK (confidence >= 0 AND confidence <= 100),

    -- 版本快照：当前版本号
    current_version INT NOT NULL DEFAULT 1,
    latest_version_id UUID,  -- 指向 kb_versions.id

    -- 时间戳
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 索引
CREATE INDEX idx_kb_articles_status ON knowledge.kb_articles(status);
CREATE INDEX idx_kb_articles_asil ON knowledge.kb_articles(asil);
CREATE INDEX idx_kb_articles_autosar ON knowledge.kb_articles(autosar_layer);
CREATE INDEX idx_kb_articles_confidence ON knowledge.kb_articles(confidence);
CREATE INDEX idx_kb_articles_dtc ON knowledge.kb_articles USING GIN(dtc_codes);
CREATE INDEX idx_kb_articles_hw_bom ON knowledge.kb_articles USING GIN(hw_bom);
CREATE INDEX idx_kb_articles_tags ON knowledge.kb_articles USING GIN(tags);
CREATE INDEX idx_kb_articles_updated ON knowledge.kb_articles(updated_at DESC);
```

#### 2.2.2 kb_versions — 版本快照链

```sql
CREATE TABLE IF NOT EXISTS knowledge.kb_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id      UUID NOT NULL REFERENCES knowledge.kb_articles(id) ON DELETE CASCADE,
    version         INT NOT NULL,
    title           TEXT NOT NULL,
    summary         TEXT NOT NULL,
    content         TEXT NOT NULL,
    body_format     SMALLINT NOT NULL DEFAULT 0,
    asil            SMALLINT NOT NULL DEFAULT 0,
    autosar_layer   SMALLINT NOT NULL DEFAULT 0,
    hw_bom          JSONB NOT NULL DEFAULT '[]'::jsonb,
    ota_binding     JSONB,
    dtc_codes       TEXT[] NOT NULL DEFAULT '{}',
    code_paths      JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags            TEXT[] NOT NULL DEFAULT '{}',
    change_summary  TEXT NOT NULL DEFAULT '',
    changed_by      TEXT NOT NULL DEFAULT '',
    confidence      SMALLINT NOT NULL DEFAULT 100,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(article_id, version)
);

CREATE INDEX idx_kb_versions_article ON knowledge.kb_versions(article_id, version DESC);
```

#### 2.2.3 kb_version_audit_logs — 版本审批审计

```sql
CREATE TABLE IF NOT EXISTS knowledge.kb_version_audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id      UUID NOT NULL REFERENCES knowledge.kb_versions(id) ON DELETE CASCADE,
    article_id      UUID NOT NULL REFERENCES knowledge.kb_articles(id) ON DELETE CASCADE,
    action          SMALLINT NOT NULL,
                    -- 1:submit_review, 2:approve, 3:reject, 4:rollback, 5:force_publish
    operator_id     TEXT NOT NULL,
    comment         TEXT NOT NULL DEFAULT '',
    old_status      SMALLINT,
    new_status      SMALLINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_kb_audit_version ON knowledge.kb_version_audit_logs(version_id);
CREATE INDEX idx_kb_audit_article ON knowledge.kb_version_audit_logs(article_id, created_at DESC);
```

#### 2.2.3a ll_audit_logs — LL 审计日志（CROSS-04 要求）

```sql
CREATE TABLE IF NOT EXISTS knowledge.ll_audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lesson_id       UUID NOT NULL REFERENCES knowledge.lessons(id) ON DELETE CASCADE,
    action          SMALLINT NOT NULL,
                    -- 1:created, 2:status_change, 3:severity_change, 4:assign,
                    -- 5:confidence_change, 6:link_to_article, 7:comment,
                    -- 8:generate_test_seed, 9:close, 10:reopen
    operator_id     TEXT NOT NULL,
    comment         TEXT NOT NULL DEFAULT '',
    old_status      SMALLINT,
    new_status      SMALLINT,
    old_severity    SMALLINT,
    new_severity    SMALLINT,
    old_confidence  SMALLINT,
    new_confidence  SMALLINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ll_audit_lesson ON knowledge.ll_audit_logs(lesson_id, created_at DESC);
CREATE INDEX idx_ll_audit_operator ON knowledge.ll_audit_logs(operator_id);
```

#### 2.2.3b fmea_audit_logs — FMEA 审计日志（CROSS-04 要求）

```sql
CREATE TABLE IF NOT EXISTS knowledge.fmea_audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fmea_entry_id   UUID REFERENCES knowledge.fmea_entries(id) ON DELETE CASCADE,
    fmea_item_id    UUID REFERENCES knowledge.fmea_items(id) ON DELETE CASCADE,
    action          SMALLINT NOT NULL,
                    -- 1:entry_created, 2:entry_status_change, 3:item_created,
                    -- 4:item_status_change, 5:rpn_update, 6:action_created,
                    -- 7:action_status_change, 8:confidence_change,
                    -- 9:yaml_sync, 10:cross_ecu_update, 11:review_completed
    operator_id     TEXT NOT NULL,
    comment         TEXT NOT NULL DEFAULT '',
    detail_json     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fmea_audit_has_target CHECK (
        fmea_entry_id IS NOT NULL OR fmea_item_id IS NOT NULL
    )
);

CREATE INDEX idx_fmea_audit_entry ON knowledge.fmea_audit_logs(fmea_entry_id, created_at DESC);
CREATE INDEX idx_fmea_audit_item ON knowledge.fmea_audit_logs(fmea_item_id, created_at DESC);
CREATE INDEX idx_fmea_audit_operator ON knowledge.fmea_audit_logs(operator_id);
```

#### 2.2.4 knowledge_tags — 标签定义

```sql
CREATE TABLE IF NOT EXISTS knowledge.knowledge_tags (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL UNIQUE,
    category        SMALLINT NOT NULL DEFAULT 0,
                    -- 0:general, 1:asil, 2:autosar, 3:ecu, 4:dtc, 5:test, 6:ota
    color           TEXT NOT NULL DEFAULT '#1890FF',
    description     TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_knowledge_tags_category ON knowledge.knowledge_tags(category);
```

#### 2.2.5 kb_article_tags — 知识-标签多对多

```sql
CREATE TABLE IF NOT EXISTS knowledge.kb_article_tags (
    article_id      UUID NOT NULL REFERENCES knowledge.kb_articles(id) ON DELETE CASCADE,
    tag_id          UUID NOT NULL REFERENCES knowledge.knowledge_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (article_id, tag_id)
);
```

#### 2.2.6 knowledge_dtc_map — DTC 关联表（一级检索维度）

```sql
CREATE TABLE IF NOT EXISTS knowledge.knowledge_dtc_map (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dtc_code        TEXT NOT NULL,
    dtc_description TEXT NOT NULL DEFAULT '',
    article_id      UUID REFERENCES knowledge.kb_articles(id) ON DELETE CASCADE,
    lesson_id       UUID REFERENCES knowledge.lessons(id) ON DELETE CASCADE,
    fmea_item_id    UUID REFERENCES knowledge.fmea_items(id) ON DELETE CASCADE,
    weight          SMALLINT NOT NULL DEFAULT 5,  -- 关联强度 1-10
    source          SMALLINT NOT NULL DEFAULT 0,
                    -- 0:manual, 1:auto_parse, 2:ota_report, 3:diagnostic_log
    extra           JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- 至少关联一个实体
    CONSTRAINT dtc_has_target CHECK (
        article_id IS NOT NULL OR lesson_id IS NOT NULL OR fmea_item_id IS NOT NULL
    )
);

CREATE INDEX idx_knowledge_dtc_map_code ON knowledge.knowledge_dtc_map(dtc_code);
CREATE INDEX idx_knowledge_dtc_map_article ON knowledge.knowledge_dtc_map(article_id);
CREATE INDEX idx_knowledge_dtc_map_lesson ON knowledge.knowledge_dtc_map(lesson_id);
CREATE INDEX idx_knowledge_dtc_map_fmea ON knowledge.knowledge_dtc_map(fmea_item_id);
```

#### 2.2.7 knowledge_test_map — 五层测试映射

```sql
CREATE TABLE IF NOT EXISTS knowledge.knowledge_test_map (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id      UUID REFERENCES knowledge.kb_articles(id) ON DELETE CASCADE,
    lesson_id       UUID REFERENCES knowledge.lessons(id) ON DELETE CASCADE,
    fmea_item_id    UUID REFERENCES knowledge.fmea_items(id) ON DELETE CASCADE,
    test_layer      SMALLINT NOT NULL,
                    -- 0:HIL, 1:SIL, 2:MIL, 3:PIL, 4:Unit
    test_suite      TEXT NOT NULL,  -- e.g. "yuleosh/ecu-brake-hil"
    test_case_id    TEXT NOT NULL,  -- e.g. "TC-BRAKE-042"
    test_status     SMALLINT NOT NULL DEFAULT 0,
                    -- 0:not_run, 1:pass, 2:fail, 3:blocked, 4:not_applicable
    last_run_at     TIMESTAMPTZ,
    evidence_id     TEXT,           -- 关联 evidence 模块
    extra           JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT test_has_target CHECK (
        article_id IS NOT NULL OR lesson_id IS NOT NULL OR fmea_item_id IS NOT NULL
    )
);

CREATE INDEX idx_knowledge_test_map_layer ON knowledge.knowledge_test_map(test_layer);
CREATE INDEX idx_knowledge_test_map_suite ON knowledge.knowledge_test_map(test_suite);
CREATE INDEX idx_knowledge_test_map_case ON knowledge.knowledge_test_map(test_case_id);
```

#### 2.2.8 knowledge_code_paths — 代码路径反向索引

```sql
CREATE TABLE IF NOT EXISTS knowledge.knowledge_code_paths (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id      UUID NOT NULL REFERENCES knowledge.kb_articles(id) ON DELETE CASCADE,
    repo            TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    line_start      INT,
    line_end        INT,
    language        TEXT NOT NULL DEFAULT '',
    last_verified_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_code_paths_repo_file ON knowledge.knowledge_code_paths(repo, file_path);
CREATE INDEX idx_code_paths_article ON knowledge.knowledge_code_paths(article_id);
```

#### 2.2.9 lessons — Lessons Learned 主表

```sql
CREATE TABLE IF NOT EXISTS knowledge.lessons (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- 来源
    source          SMALLINT NOT NULL,
                    -- 0:manual, 1:auto_bug, 2:ci_failure, 3:ota_incident,
                    -- 4:customer_complaint, 5:fmea_derived, 6:audit_finding

    source_ref      TEXT NOT NULL DEFAULT '',  -- 外部引用：bug_url / ci_run_id / ota_event_id
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',

    severity        SMALLINT NOT NULL DEFAULT 0 CHECK (severity >= 0 AND severity <= 4),
                    -- 0:info, 1:minor, 2:major, 3:critical, 4:catastrophic
                    -- ⚡ 等小马决策后与 Spec 对齐；当前 Tech 保留 5 级（与 Spec 草案一致）

    status          SMALLINT NOT NULL DEFAULT 0,
                    -- 0:open, 1:investigating, 2:action_planned, 3:implemented,
                    -- 4:mitigated, 5:verified, 6:closed, 7:rejected
                    -- ⚡ mitigated 对应 Spec 中的 '风险已缓解' 阶段：已执行缓解措施但未完成最终验证

    -- 分类
    category        SMALLINT NOT NULL DEFAULT 0,
                    -- 0:design, 1:process, 2:tooling, 3:requirement,
                    -- 4:implementation, 5:testing, 6:deployment, 7:hw, 8:sw

    -- 安全等级（强制字段，Spec FMEA-01 & LL-01）
    safety_level    SMALLINT NOT NULL DEFAULT 0,
                    -- 0:QM, 1:ASIL_A, 2:ASIL_B, 3:ASIL_C, 4:ASIL_D

    -- 知识绑定
    article_id      UUID REFERENCES knowledge.kb_articles(id),

    -- OTA 绑定
    ota_version     TEXT,            -- 问题出现时的 OTA 版本
    ota_fix_version TEXT,            -- 修复版本

    root_cause      TEXT NOT NULL DEFAULT '',
    resolution      TEXT NOT NULL DEFAULT '',

    applied_to      TEXT[] NOT NULL DEFAULT '{}',  -- 已应用于哪些项目/ECU

    author_id       TEXT NOT NULL,
    assignee_id     TEXT,

    -- 置信度衰减相关
    confidence      SMALLINT NOT NULL DEFAULT 80,  -- 0-100，已与 Spec 确认：Tech 端统一使用 SMALLINT（0-100），
                                                    -- Spec 验收矩阵中的 0.9/0.7 等 float 值映射为 90/70 等整数
    verify_count    INT NOT NULL DEFAULT 0,
    reapply_interval_days INT NOT NULL DEFAULT 90,  -- 置信度复查周期

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_lessons_source ON knowledge.lessons(source);
CREATE INDEX idx_lessons_severity ON knowledge.lessons(severity);
CREATE INDEX idx_lessons_status ON knowledge.lessons(status);
CREATE INDEX idx_lessons_category ON knowledge.lessons(category);
CREATE INDEX idx_lessons_article ON knowledge.lessons(article_id);
CREATE INDEX idx_lessons_ota ON knowledge.lessons(ota_version);
```

#### 2.2.10 lesson_actions — 纠正行动计划

```sql
CREATE TABLE IF NOT EXISTS knowledge.lesson_actions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lesson_id       UUID NOT NULL REFERENCES knowledge.lessons(id) ON DELETE CASCADE,
    action_type     SMALLINT NOT NULL,
                    -- 0:code_change, 1:test_add, 2:process_change, 3:doc_update,
                    -- 4:training, 5:design_review
    description     TEXT NOT NULL,
    assignee_id     TEXT NOT NULL DEFAULT '',
    status          SMALLINT NOT NULL DEFAULT 0,
                    -- 0:todo, 1:in_progress, 2:done, 3:cancelled
    due_at          TIMESTAMPTZ,
    evidence_id     TEXT,           -- 关联 evidence 模块
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_lesson_actions_lesson ON knowledge.lesson_actions(lesson_id);
CREATE INDEX idx_lesson_actions_status ON knowledge.lesson_actions(status);
CREATE INDEX idx_lesson_actions_assignee ON knowledge.lesson_actions(assignee_id);
```

#### 2.2.11 lesson_test_seeds — 从 LL 反哺测试种子

```sql
CREATE TABLE IF NOT EXISTS knowledge.lesson_test_seeds (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lesson_id       UUID NOT NULL REFERENCES knowledge.lessons(id) ON DELETE CASCADE,
    test_layer      SMALLINT NOT NULL,
                    -- 0:HIL, 1:SIL, 2:MIL, 3:PIL, 4:Unit
    test_type       SMALLINT NOT NULL DEFAULT 0,
                    -- 0:regression, 1:boundary, 2:negative, 3:stress, 4:compatibility
    scenario_desc   TEXT NOT NULL,
    suggested_code  TEXT NOT NULL DEFAULT '',
    ci_artifact     TEXT,           -- 生成的 CI artifact 路径
    status          SMALLINT NOT NULL DEFAULT 0,
                    -- 0:proposed, 1:approved, 2:implemented, 3:merged, 4:deprecated
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_by     TEXT,
    merged_at       TIMESTAMPTZ
);

CREATE INDEX idx_lesson_test_seeds_lesson ON knowledge.lesson_test_seeds(lesson_id);
```

#### 2.2.12 fmea_entries — FMEA 主记录

```sql
CREATE TABLE IF NOT EXISTS knowledge.fmea_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    system          TEXT NOT NULL,        -- 分析的系统，如 "BrakeSystem"
    subsystem       TEXT NOT NULL DEFAULT '',
    -- 范围
    scope           SMALLINT NOT NULL DEFAULT 0,
                    -- 0:single_ecu, 1:cross_ecu, 2:system_level
    -- 版本锁定
    fmea_version    TEXT NOT NULL DEFAULT '0.1.0',
    -- 安全等级（强制字段，Spec FMEA-01）
    safety_level    SMALLINT NOT NULL DEFAULT 0,
                    -- 0:QM, 1:ASIL_A, 2:ASIL_B, 3:ASIL_C, 4:ASIL_D
    -- 关联知识条目（可选）
    article_id      UUID REFERENCES knowledge.kb_articles(id),
    -- 元数据
    creator_id      TEXT NOT NULL,
    reviewer_id     TEXT,
    status          SMALLINT NOT NULL DEFAULT 0,
                    -- 0:draft, 1:review, 2:approved, 3:superseded
                    -- ⚡ 等小马决策后对齐
    -- 源文件（FMEA as Code YAML 的路径）
    source_yaml     TEXT NOT NULL DEFAULT '',
    source_hash     TEXT NOT NULL DEFAULT '', -- YAML 内容 SHA256
    -- 时间
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_fmea_entries_system ON knowledge.fmea_entries(system);
CREATE INDEX idx_fmea_entries_scope ON knowledge.fmea_entries(scope);
CREATE INDEX idx_fmea_entries_status ON knowledge.fmea_entries(status);
```

#### 2.2.13 fmea_items — FMEA 条目（失效模式明细）

```sql
CREATE TABLE IF NOT EXISTS knowledge.fmea_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fmea_entry_id   UUID NOT NULL REFERENCES knowledge.fmea_entries(id) ON DELETE CASCADE,
    item_index      INT NOT NULL,       -- 保留 YAML 中的顺序

    -- AUTOSAR 层级
    autosar_layer   SMALLINT NOT NULL DEFAULT 0,
                    -- bit 0:ASW, bit 1:RTE, bit 2:BSW, bit 3:HW

    -- 安全等级（强制字段，Spec FMEA-01）
    safety_level    SMALLINT NOT NULL DEFAULT 0,
                    -- 0:QM, 1:ASIL_A, 2:ASIL_B, 3:ASIL_C, 4:ASIL_D

    -- 三域：功能/组件/层次
    function_desc   TEXT NOT NULL,       -- 功能描述
    component       TEXT NOT NULL,       -- 组件/模块名
    layer           TEXT NOT NULL DEFAULT '',  -- 层次细分

    -- 失效模式
    failure_mode    TEXT NOT NULL,
    failure_effect  TEXT NOT NULL,       -- 失效影响
    failure_cause   TEXT NOT NULL,       -- 失效原因
    failure_mechanism TEXT NOT NULL DEFAULT '',

    -- 三域 RPN（原始）
    severity        SMALLINT NOT NULL CHECK (severity >= 1 AND severity <= 10),
    occurrence      SMALLINT NOT NULL CHECK (occurrence >= 1 AND occurrence <= 10),
    detection       SMALLINT NOT NULL CHECK (detection >= 1 AND detection <= 10),
    rpn             INT NOT NULL GENERATED ALWAYS AS (severity * occurrence * detection) STORED,

    -- 当前控制
    current_control TEXT NOT NULL DEFAULT '',

    -- 建议措施
    recommended_action TEXT NOT NULL DEFAULT '',

    -- 措施后 RPN
    planned_severity   SMALLINT CHECK (planned_severity >= 1 AND planned_severity <= 10),
    planned_occurrence SMALLINT CHECK (planned_occurrence >= 1 AND planned_occurrence <= 10),
    planned_detection  SMALLINT CHECK (planned_detection >= 1 AND planned_detection <= 10),
    planned_rpn         INT GENERATED ALWAYS AS (
        planned_severity * planned_occurrence * planned_detection
    ) STORED,

    -- DTC 关联
    dtc_codes       TEXT[] NOT NULL DEFAULT '{}',

    -- 证据关联
    evidence_ids    TEXT[] NOT NULL DEFAULT '{}',

    -- 置信度
    confidence      SMALLINT NOT NULL DEFAULT 100,

    -- 生命周期
    status          SMALLINT NOT NULL DEFAULT 0,
                    -- 0:open, 1:analysis, 2:action_planned, 3:action_done, 4:verified, 5:closed
                    -- ⚡ 等小马决策后可能与 Spec 对齐；当前 Tech 6 状态完整
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_fmea_items_entry ON knowledge.fmea_items(fmea_entry_id, item_index);
CREATE INDEX idx_fmea_items_rpn ON knowledge.fmea_items(rpn DESC);
CREATE INDEX idx_fmea_items_status ON knowledge.fmea_items(status);
CREATE INDEX idx_fmea_items_dtc ON knowledge.fmea_items USING GIN(dtc_codes);
```

#### 2.2.14 fmea_actions — FMEA 纠正措施

```sql
CREATE TABLE IF NOT EXISTS knowledge.fmea_actions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fmea_item_id    UUID NOT NULL REFERENCES knowledge.fmea_items(id) ON DELETE CASCADE,
    description     TEXT NOT NULL,
    owner_id        TEXT NOT NULL DEFAULT '',
    rpn_before      INT NOT NULL,
    rpn_after       INT,
    status          SMALLINT NOT NULL DEFAULT 0,
                    -- 0:proposed, 1:approved, 2:in_progress, 3:done, 4:verified, 5:cancelled
    priority        SMALLINT NOT NULL DEFAULT 1,
                    -- 1:low, 2:medium, 3:high, 4:critical
    due_at          TIMESTAMPTZ,
    evidence_id     TEXT,
    test_link_id    UUID REFERENCES knowledge.knowledge_test_map(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_fmea_actions_item ON knowledge.fmea_actions(fmea_item_id);
CREATE INDEX idx_fmea_actions_status ON knowledge.fmea_actions(status);
```

#### 2.2.15 fmea_item_cross_ecu — 跨 ECU 失效链

```sql
CREATE TABLE IF NOT EXISTS knowledge.fmea_item_cross_ecu (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_item_id  UUID NOT NULL REFERENCES knowledge.fmea_items(id) ON DELETE CASCADE,
    target_item_id  UUID NOT NULL REFERENCES knowledge.fmea_items(id) ON DELETE CASCADE,
    relation_type   SMALLINT NOT NULL DEFAULT 0,
                    -- 0:cascade（级联）, 1:shared_cause（共因）,
                    -- 2:redundancy（冗余失效）, 3:feedback（反馈回路）
    propagation_desc TEXT NOT NULL DEFAULT '',
    propagation_delay TEXT,  -- e.g. "immediate", "100ms", "1000ms"
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT cross_ecu_diff_items CHECK (source_item_id != target_item_id)
);

CREATE INDEX idx_fmea_cross_ecu_source ON knowledge.fmea_item_cross_ecu(source_item_id);
CREATE INDEX idx_fmea_cross_ecu_target ON knowledge.fmea_item_cross_ecu(target_item_id);
```

#### 2.2.16 knowledge_confidence_snapshots — 置信度衰减快照

```sql
CREATE TABLE IF NOT EXISTS knowledge.knowledge_confidence_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     SMALLINT NOT NULL,
                    -- 0:kb_article, 1:lesson, 2:fmea_item
    entity_id       UUID NOT NULL,
    confidence      SMALLINT NOT NULL,
    decay_reason    TEXT NOT NULL DEFAULT '',
                    -- "time_decay", "ota_update", "hw_change", "test_failure",
                    -- "review_outdated", "manual_reassess"
    auto_flag       BOOLEAN NOT NULL DEFAULT true,  -- true = 自动触发
    snapshot_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_confidence_snaps_entity ON knowledge.knowledge_confidence_snapshots(entity_type, entity_id, snapshot_at DESC);
CREATE INDEX idx_confidence_snaps_time ON knowledge.knowledge_confidence_snapshots(snapshot_at DESC);
```

### 2.3 pgvector 语义搜索索引

#### 2.3.1 向量列设计

```sql
-- 在知识库相关表上启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- kb_articles 的内容向量（按需分 chunk，这里存聚合向量）
ALTER TABLE knowledge.kb_articles ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- fmea_items 的失效模式向量
ALTER TABLE knowledge.kb_items ADD COLUMN IF NOT EXISTS embedding text_embedding vector(1536);
```

> **注意：** pgvector 列在 MVP 阶段可选索引。Phase 1 只建表不加 embedding 列，Phase 2 再 ALTER 加。

#### 2.3.2 索引策略

```sql
-- Phase 2 引入的索引
CREATE INDEX ON knowledge.kb_articles USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- 如果数据量 > 100K，可升级到 HNSW（Phase 3）
-- CREATE INDEX ON knowledge.kb_articles USING hnsw (embedding vector_cosine_ops);
```

#### 2.3.3 混合搜索查询示例

```sql
-- 混合搜索：关键词 + 向量
WITH semantic AS (
    SELECT id, title, 1 - (embedding <=> $query_embedding) AS score
    FROM knowledge.kb_articles
    WHERE embedding IS NOT NULL
      AND status = 3  -- published
    ORDER BY embedding <=> $query_embedding
    LIMIT 50
),
keyword AS (
    SELECT id, title, ts_rank(to_tsvector('english', title || ' ' || content), plainto_tsquery('english', $keywords)) AS score
    FROM knowledge.kb_articles
    WHERE to_tsvector('english', title || ' ' || content) @@ plainto_tsquery('english', $keywords)
      AND status = 3
    LIMIT 50
),
combined AS (
    SELECT id, title, MAX(score) AS score FROM (
        SELECT id, title, score * 0.7 AS score FROM semantic
        UNION ALL
        SELECT id, title, score * 0.3 AS score FROM keyword
    ) sub GROUP BY id, title
)
SELECT id, title, score
FROM combined
ORDER BY score DESC
LIMIT 20;
```

### 2.4 与现有 store 模块的衔接

```go
// pkg/store/knowledge/ 是全新的子包，遵循 store 模块已有惯例：

// 接口定义（位于 internal/store/interface.go 同级位置）
type KnowledgeStore interface {
    // KB
    GetArticle(ctx context.Context, id uuid.UUID) (*domain.KbArticle, error)
    ListArticles(ctx context.Context, filter ArticleFilter) ([]*domain.KbArticle, int64, error)
    CreateArticle(ctx context.Context, a *domain.KbArticle) (*domain.KbArticle, error)
    UpdateArticle(ctx context.Context, a *domain.KbArticle) error
    DeleteArticle(ctx context.Context, id uuid.UUID) error

    // 版本
    CreateVersion(ctx context.Context, v *domain.KbVersion) error
    GetVersion(ctx context.Context, articleID uuid.UUID, version int) (*domain.KbVersion, error)
    ListVersions(ctx context.Context, articleID uuid.UUID) ([]*domain.KbVersion, error)

    // 搜索
    SearchArticles(ctx context.Context, q SearchQuery) ([]*SearchResult, error)
    SemanticSearch(ctx context.Context, embedding []float32, limit int) ([]*SearchResult, error)

    // LL
    CreateLesson(ctx context.Context, l *domain.Lesson) error
    ListLessons(ctx context.Context, filter LessonFilter) ([]*domain.Lesson, int64, error)

    // FMEA
    CreateFMEA(ctx context.Context, f *domain.FMEAEntry) error
    GetFMEABySystem(ctx context.Context, system string) (*domain.FMEAEntry, error)

    // DTC 检索
    GetByDTCCode(ctx context.Context, dtc string) (*DTCSearchResult, error)
}
```

**衔接原则：**
1. `knowledge` 子包放在已有的 `pkg/store/` 下，复用 `store.WithTx()` 等基础设施
2. DB migration 采用现有工具（已确认架构中已有 migration），新增 migration 文件 `YYYYMMDD_knowledge_init.sql`
3. 审计日志通过 `store.WithAudit()` 模式，或直接写入 `kb_version_audit_logs` 表

---

## 3. Go 后端模块划分

### 3.1 Package 结构

```
internal/
├── domain/
│   └── knowledge/
│       ├── kb_article.go              # KBArticle 实体 + value objects
│       ├── kb_version.go              # KBVersion
│       ├── lesson.go                  # Lesson + LessonAction + TestSeed
│       ├── fmea.go                    # FMEAEntry + FMEAItem + FMEAAction
│       ├── tag.go                     # KnowledgeTag
│       ├── dtc_map.go                 # DTCMap
│       ├── confidence.go              # ConfidenceSnapshot
│       └── search.go                  # 搜索相关值对象
│
├── service/
│   └── knowledge/
│       ├── service.go                 # Service 接口 + 构造 + 事务编排
│       ├── kb_service.go              # KB CRUD + 版本链逻辑
│       ├── ll_service.go              # Lessons Learned 业务逻辑
│       ├── fmea_service.go            # FMEA 业务 + YAML 解析 + RPN 计算
│       ├── search_service.go          # 混合搜索编排
│       ├── dtc_service.go             # DTC 检索 + 售后闭环
│       ├── confidence_service.go      # 置信度衰减计算
│       └── auto_capture_service.go    # Bug/CI → LL 自动捕获
│
├── handler/
│   └── knowledge/
│       ├── kb_handler.go              # KB REST/gRPC handler
│       ├── ll_handler.go              # LL handler
│       ├── fmea_handler.go            # FMEA handler
│       └── search_handler.go          # 搜索 + DTC 检索 handler
│
├── store/
│   └── knowledge/
│       ├── store.go                   # KnowledgeStore 接口实现
│       ├── kb_repo.go                 # KB CRUD
│       ├── version_repo.go            # 版本快照
│       ├── lesson_repo.go             # Lessons
│       ├── fmea_repo.go               # FMEA
│       ├── tag_repo.go                # Tags
│       ├── dtc_repo.go                # DTC 映射
│       ├── search_repo.go             # 全文搜索 + pgvector
│       └── migration.go               # 初始化 DDL
│
├── pipeline/
│   └── knowledge/
│       ├── pipeline.go                # 集成 Pipeline 接口
│       ├── pre_commit_hook.go         # Pre-commit 检查
│       ├── commit_msg_hook.go         # Commit-msg 解析
│       ├── pr_checklist.go            # PR 门禁
│       ├── merge_gate.go              # Merge 门禁
│       └── regression_hook.go         # 回归触发
│
├── fmea_codec/
│   ├── yaml_parser.go                 # YAML → domain.FMEAEntry
│   ├── yaml_serializer.go             # domain.FMEAEntry → YAML
│   ├── schema.go                      # FMEA YAML Schema 定义
│   └── validator.go                   # Schema 校验 + 约束检查
│
└── ci/
    └── knowledge_ci.go                 # 对接 ci 模块
```

### 3.2 关键接口定义

```go
// internal/service/knowledge/service.go

type KnowledgeService interface {
    // ===== KB =====
    CreateArticle(ctx context.Context, req *CreateArticleRequest) (*domain.KbArticle, error)
    GetArticle(ctx context.Context, id uuid.UUID) (*domain.KbArticle, error)
    UpdateArticle(ctx context.Context, req *UpdateArticleRequest) (*domain.KbArticle, error)
    PublishDraft(ctx context.Context, id uuid.UUID, reviewerID string) error
    DeprecateArticle(ctx context.Context, id uuid.UUID) error

    // ===== LL =====
    CaptureLesson(ctx context.Context, req *CaptureLessonRequest) (*domain.Lesson, error)
    AutoCaptureFromBug(ctx context.Context, bugRef string) (*domain.Lesson, error)
    CloseLesson(ctx context.Context, id uuid.UUID) error
    GenerateTestSeed(ctx context.Context, lessonID uuid.UUID, layer int) (*domain.LessonTestSeed, error)

    // ===== FMEA =====
    CreateFMEAFromYAML(ctx context.Context, yamlContent []byte) (*domain.FMEAEntry, error)
    UpdateFMEAItem(ctx context.Context, itemID uuid.UUID, req *UpdateFMEAItemRequest) error
    CalculateCrossECUChain(ctx context.Context, entryID uuid.UUID) ([]*domain.CrossECULink, error)
    SyncFMEAFromYAML(ctx context.Context, yamlPath string) (*domain.FMEAEntry, error)

    // ===== 搜索 =====
    Search(ctx context.Context, q *SearchQuery) (*SearchResultSet, error)
    SearchByDTC(ctx context.Context, dtc string) (*DTCSearchResult, error)

    // ===== 置信度 =====
    RecalcConfidence(ctx context.Context, entityType int, entityID uuid.UUID) error
    BatchDecayCheck(ctx context.Context) ([]*domain.ConfidenceSnapshot, error)
}
```

### 3.3 与 ci 模块的集成点

```go
// internal/ci/knowledge_ci.go

// CI 触发的知识检查
type KnowledgeCIChecker struct {
    svc    knowledge.KnowledgeService
    logger *zap.Logger
}

func (c *KnowledgeCIChecker) CheckPreCommit(changedFiles []string) *CICheckResult
func (c *KnowledgeCIChecker) CheckCommitMsg(msg string) *CICheckResult
func (c *KnowledgeCIChecker) CheckPRContents(prID string) *CICheckResult
func (c *KnowledgeCIChecker) CheckMergeGate(branch string) *CICheckResult
func (c *KnowledgeCIChecker) TriggerRegression(scope string) *CICheckResult

type CICheckResult struct {
    Passed    bool
    Severity  string   // "blocker" | "warning" | "info"
    Messages  []string
    Blockers  []Blocker
}
```

---

## 4. FMEA as Code — YAML Schema

### 4.1 完整 YAML Schema

```yaml
# yuleOSH FMEA — FMEA as Code 定义
# Schema 版本: v1.0
#
# 一个 YAML 文件对应一个 fmea_entry。
# 文件按系统组织：fmea/brake-system/v1.0.yaml

# ——— 元数据 ———
name: "BrakeSystem FMEA v1.0"
system: "BrakeSystem"
subsystem: "BrakeByWire"
scope: "cross_ecu"          # single_ecu | cross_ecu | system_level
fmea_version: "1.0.0"
created_by: "stefan"
reviewed_by: "xiao_ma"
date: "2026-06-20"

# ——— 关联知识条目（可选） ———
article_ref:
  id: "550e8400-e29b-41d4-a716-446655440000"
  title: "BrakeByWire Power Supply Redundancy Design"

# ——— AUTOSAR 层级定义（文件级默认，item 可覆盖） ———
autosar_layer:
  - ASW
  - RTE
  - BSW
  - HW

# ——— 跨 ECU 定义（仅 cross_ecu scope 需要） ———
ecu_map:
  ECU_BRAKE: "Software cluster: Brake ECU (TDA4VM)"
  ECU_VCU:   "Software cluster: Vehicle Control Unit (S32K)"

# ——— 条目列表 ———
items:
  - id: "BM-001"
    function: "Brake-by-Wire pedal position sensing"
    component: "Pedal Sensor Module"
    layer: "HW"
    failure_mode: "Pedal position sensor signal stuck at 0V"
    failure_effect: "Brake controller detects no pedal input → failsafe mode"
    failure_cause: "Sensor VCC short to GND due to PCB trace damage"
    failure_mechanism: "Thermal stress on PCB joint → crack → short"
    autosar_layer: HW

    # 三域 RPN（原始）
    severity: 9
    occurrence: 3
    detection: 4

    # 当前控制
    current_control: "Redundant Hall sensor + plausibility check in BSW"

    # 建议措施
    recommended_action: |
      1. Add conformal coating to sensor PCB
      2. Implement sensor VCC voltage monitoring in ASW
      3. Add cross-ECU plausibility with VCU

    # 措施后 RPN
    planned_severity: 9
    planned_occurrence: 2
    planned_detection: 6

    # DTC 关联
    dtc_codes:
      - "U0123"
      - "C1234"

    # 证据
    evidence_refs:
      - "evt-001"   # 指向 evidence 模块

    # 置信度
    confidence: 85

    # 状态
    status: "action_planned"  # open | analysis | action_planned | action_done | verified | closed

    # ——— 措施（每个 item 可带多条 action） ———
    actions:
      - description: "Design review of pedal sensor PCB layout"
        owner: "steve_pcb"
        rpn_before: 108
        status: "done"
        due: "2026-07-01"
      - description: "Implement VCC monitoring in ASW Brake Manager"
        owner: "alice_sw"
        rpn_before: 108
        rpn_after: 72
        status: "in_progress"
        due: "2026-08-15"

    # ——— 跨 ECU 传播（cross_ecu 场景） ———
    cross_ecu:
      - target: "VCU-012"     # 目标 item id
        target_ecu: "ECU_VCU"
        relation: "cascade"   # cascade | shared_cause | redundancy | feedback
        propagation: "immediate"
        propagation_desc: "Brake fail-safe triggers VCU emergency stop"

  - id: "BM-002"
    function: "Brake pedal force feedback (active pedal)"
    component: "Active Pedal Simulator"
    layer: "HW + ASW"
    failure_mode: "Active pedal stuck in full travel position"
    failure_effect: "Driver loses tactile pedal feedback → potential over-brake"
    failure_cause: "ASW state machine stuck in initialization loop"
    severity: 7
    occurrence: 4
    detection: 5
    current_control: "Watchdog timer + ASW state timeout reset"
    recommended_action: ""
    planned_severity: 7
    planned_occurrence: 3
    planned_detection: 7
    status: "open"
```

### 4.2 Schema 约束说明

| 字段 | 必填 | 约束 |
|------|------|------|
| `items[].severity/occurrence/detection` | 是 | 1-10 |
| `items[].autosar_layer` | 是 | 均为大写，逗号联合使用 (e.g. "ASW + BSW") |
| `items[].dtc_codes` | 否 | 必须符合 SAE J2012 格式（`[A-Z][0-9]{4}`） |
| `items[].planned_severity/occurrence/detection` | 否 | 一旦填一个则需全填 |
| `items[].status` | 是 | 必须在枚举列表内 |
| `scope` 为 `cross_ecu` 时 | 是 | 必须定义 `ecu_map` 且至少一个 item 含 `cross_ecu` |

### 4.3 YAML → DB 同步流程

```
Git Push (fmea/*.yaml change)
  │
  ▼
Pre-commit hook (yaml-schema-validate + lint)
  │
  ▼
CI merge gate (fmea-yaml-validate)
  │
  ▼
Merge to main
  │
  ▼
Post-merge pipeline
  ├── fmea-codec.ParseYAML()       # 解析
  ├── fmea-codec.Validate()        # 校验约束
  ├── fmea_repo.SyncFromYAML()     # 对比 DB 已有 version：
  │   ├── source_hash 不同 → 创建新版本
  │   ├── items diff → UPDATE/INSERT/DELETE
  │   └── 状态管理 → 保持已关闭 item 不重置
  └── ci.Pipeline → 触发 FMEA→Test→Telemetry
```

---

## 5. 版本化策略

### 5.1 比较三种方案

| 维度 | 方案 A: Git 同步 | 方案 B: 纯独立版本库 | 方案 C: 混合（推荐） |
|------|:---:|:---:|:---:|
| **数据一致性** | YAML在Git，DB镜像 | 全在DB | YAML在Git，DB含全量+版本链 |
| **跨分支回滚** | 天然支持 | 需要自研 | 简单回滚+版本链独立 |
| **离线编辑** | 本地IDE+YAML | 需API | 本地IDE+YAML |
| **CI集成** | 直接操作文件 | 需API调用 | 直接操作文件 |
| **审计追溯** | Git log | DB audit logs | 双轨（Git+DB） |
| **语义搜索** | 需独立索引 | DB原生支持 | DB原生支持 |
| **实现复杂度** | 低 | 高 | 中 |

### 5.2 推荐：混合策略（方案 C）

**核心设计：**
- **YAML 源码** 存入 `git/yuleosh-knowledge/`（独立仓库）
- **DB 全量镜像** 由 CI/GitHook 自动同步
- **版本链** 在 DB 中以 `kb_versions` / `fmea_entries.fmea_version` 独立维护
- **Git 不作为唯一版本源** — DB 始终保持可查询的完整版本历史

**FMEA 版本管理细节：**

```
Git 仓库                        DB 版本链
fmea/brake-system/
├── v1.0.yaml                   fmea_entries (source_hash: abc123)
├── v1.1.yaml                   fmea_entries (source_hash: def456) ← current
└── v1.2-dev.yaml               fmea_entries (source_hash: ghi789) ← draft
```

**KB 文章版本管理：**

```
KB Web UI / API
  │
  ├── 编辑 → 自动触发版本快照（kb_versions）
  │
  ├── 提交审核 → kb_version_audit_logs.action=submit_review
  │
  ├── 审批通过 → kb_articles.current_version++
  │             └── kb_articles.latest_version_id 更新
  │
  └── 回滚 → kb_articles.latest_version_id 指向历史版本
             └── 记录 audit_log
```

**理由：**
1. **开发友好** — 工程师用本机编辑器改 YAML，提交 Git PR，无需额外工具
2. **工程友好** — CI 直接跑 YAML 校验，无需 mock 数据
3. **运维友好** — DB 始终保持可查询的完整版本历史，不上 Git 也能查
4. **审计友好** — 双轨互验：Git blame + DB audit log

---

## 6. 搜索与推荐引擎

### 6.1 搜索架构

```
User Query
│
├─ Structured: DTC 检索
│   └─ knowledge_dtc_map.dtc_code = $dtc (精确匹配)
│      └─ 返回关联的所有实体（KB/LL/FMEA）
│
├─ Structured: Tag/BOM/ASIL 过滤
│   └─ WHERE tags @> ARRAY[$tag] AND hw_bom @> $bom_json
│
└─ Unstructured: 语义+关键词混合
    ├─ 关键词分支
    │   └─ PostgreSQL full-text search (GIN + tsvector)
    └─ 语义分支
        └─ pgvector (IVFFLAT → HNSW)
            └─ Embedding 生成（Phase 2 引入）
                └─ 可选：本地模型 / 远程 API
```

### 6.2 搜索引擎接口

```go
type SearchQuery struct {
    Keywords     string            // 自然语言输入
    DTCCodes     []string          // DTC 精确检索
    Tags         []string          // 标签过滤
    ASIL         []int             // ASIL 过滤
    AUTOSARLayer []int             // AUTOSAR 层级过滤
    HWPlatforms  []string          // 硬件平台过滤
    Status       []int             // 状态过滤
    EntityTypes  []int             // 0:kb, 1:lesson, 2:fmea 全要
    Limit        int
    Offset       int
    SortBy       string            // "relevance" | "confidence" | "updated_at"
}

type SearchResult struct {
    EntityType   int
    EntityID     uuid.UUID
    Title        string
    Snippet      string
    Score        float64
    Confidence   int
    Tags         []string
    MatchedDTC   []string
    MatchedPath  []string          // 匹配的代码路径
}

type SearchResultSet struct {
    Results []*SearchResult
    Total   int64
    DTCResults []*DTCSearchResult  // DTC 检索独立结果
}
```

### 6.3 DTC 检索（一级维度）

DTC 检索是 MVP 的 **P0 功能**，因为售后闭环 → DTC → FMEA → LL 是核心业务价值所在。

```sql
-- DTC 检索聚合查询
SELECT
    d.dtc_code,
    d.dtc_description,
    d.source,
    d.weight,
    jsonb_build_object(
        'type', 'article',
        'id', a.id,
        'title', a.title
    ) AS kb_article,
    jsonb_build_object(
        'type', 'lesson',
        'id', l.id,
        'title', l.title,
        'severity', l.severity
    ) AS lesson,
    jsonb_build_object(
        'type', 'fmea_item',
        'id', fi.id,
        'failure_mode', fi.failure_mode,
        'rpn', fi.rpn
    ) AS fmea
FROM knowledge.knowledge_dtc_map d
LEFT JOIN knowledge.kb_articles a ON d.article_id = a.id
LEFT JOIN knowledge.lessons l ON d.lesson_id = l.id
LEFT JOIN knowledge.fmea_items fi ON d.fmea_item_id = fi.id
WHERE d.dtc_code = $1
ORDER BY d.weight DESC;
```

### 6.4 推荐引擎（Phase 2+）

```go
// 基于 pgvector + 相似度推荐
// 输入：当前查看文章
// 输出：相关 KB + Lessons + FMEAs

func (s *SearchService) Recommend(ctx context.Context, articleID uuid.UUID, limit int) ([]*SearchResult, error) {
    // 1. 获取当前文章的 embedding
    article, _ := s.store.GetArticle(ctx, articleID, false)
    if article.Embedding == nil {
        return s.RecommendByTags(ctx, articleID, limit)  // 兜底：基于标签
    }

    // 2. pgvector 余弦相似度
    semanticResults, _ := s.store.SemanticSearch(ctx, article.Embedding.Data, limit)

    // 3. DTC 驱动推荐（当前文章有 DTC 关联）
    if len(article.DTCCodes) > 0 {
        dtcResults, _ := s.store.SearchByDTCCodes(ctx, article.DTCCodes, limit)
        return merge(semanticResults, dtcResults), nil
    }

    return semanticResults, nil
}
```

### 6.5 置信度衰减策略（Phase 2+）

> **设计决策（依据老陈审查意见）：** 砍掉线性衰减（linear）和阶梯衰减（step）策略，
> 仅保留 **基于使用频率（usage_based）** + **设计变更事件驱动** 两种策略。

#### 6.5.1 策略一：基于使用频率衰减（usage_based）

知识条目的置信度根据**一段时间内的被使用/引用频率**动态调整：

| 访问频次（最近 90 天） | 置信度变化 | 说明 |
|------------------------|-----------|------|
| ≥10 次                 | 不变或 +5 | 高频使用，知识活跃 |
| 5-9 次                 | 不变      | 正常使用 |
| 2-4 次                 | -5        | 低频使用，适度衰减 |
| 0-1 次                 | -10       | 几乎未被引用，加速衰减 |
| 连续 180 天无访问       | 降至 30   | 标记为"待审查" |

**触发时机：** 定时 Job（每日凌晨运行 `BatchDecayCheck`）

```go
// Phase 2 实现
func (s *ConfidenceService) decayByUsage(ctx context.Context, entityType int, entityID uuid.UUID) (int, error) {
    // 1. 查询近 90 天使用次数（search_log / dtc_query_log / ci_hits）
    usageCount, _ := s.store.CountRecentUsage(ctx, entityType, entityID, 90)

    // 2. 计算新置信度
    current := currentConfidence(entityType, entityID)
    var delta int
    switch {
    case usageCount >= 10:
        delta = 5
    case usageCount >= 5:
        delta = 0
    case usageCount >= 2:
        delta = -5
    default:
        delta = -10
    }

    newConfidence := clamp(current + delta, 0, 100)

    // 3. 如果有 180 天无访问，强制降至 30
    lastAccess, _ := s.store.GetLastAccessTime(ctx, entityType, entityID)
    if lastAccess != nil && time.Since(*lastAccess).Hours() > 180*24 {
        newConfidence = 30
    }

    return newConfidence, nil
}
```

#### 6.5.2 策略二：设计变更事件驱动

当代码/设计/需求变更影响到某知识条目时，**立即触发置信度重置**：

| 事件类型 | 影响范围 | 置信度重置 | 触发方式 |
|----------|----------|-----------|----------|
| CI merge 涉及关联代码文件 | 关联 knowledge_code_paths 的 KB 条目 | 降至 50（标记待审查） | Post-merge hook |
| FMEA YAML 更新 | 对应 fmea_entries | 维持但 diff 触发 notify | YAML sync 时 |
| OTA 版本升级 | 绑定 ota_binding 的 KB/LL | 降至 40 | OTA 发布事件 |
| 硬件平台变更 | 匹配 hw_bom 的知识条目 | 降至 30 | BOM 变更事件 |
| 关联测试失败（test_map） | 对应知识条目 | 降至 20 | CI test report |
| 人工标记"已过时" | 指定条目 | 强制设为 0 | 人工操作 |

```go
func (s *ConfidenceService) OnDesignChange(ctx context.Context, event *DesignChangeEvent) error {
    affected, _ := s.store.FindAffectedEntities(ctx, event)
    for _, entity := range affected {
        newConfidence := s.getEventDrivenTarget(event.Type)
        _, _ = s.store.CreateSnapshot(ctx, &domain.ConfidenceSnapshot{
            EntityType:  entity.EntityType,
            EntityID:    entity.EntityID,
            Confidence:  newConfidence,
            DecayReason: fmt.Sprintf("event_driven:%s", event.Type),
            AutoFlag:    true,
        })
        s.store.UpdateConfidence(ctx, entity.EntityType, entity.EntityID, newConfidence)
        s.auditLogger.LogConfidenceChange(ctx, entity, currentConfidence, newConfidence, event.Type)
    }
    return s.notifier.NotifyAffectedAuthors(ctx, affected)
}

func (s *ConfidenceService) getEventDrivenTarget(eventType string) int {
    switch eventType {
    case "code_change":
        return 50
    case "ota_upgrade":
        return 40
    case "hw_change":
        return 30
    case "test_failure":
        return 20
    default:
        return 50
    }
}
```

#### 6.5.3 置信度阈值定义

```go
const (
    ConfidenceHigh     = 80
    ConfidenceMedium   = 50
    ConfidenceLow      = 30
    ConfidenceStale    = 20
)
```

**已移除的衰减策略（根据老陈审查意见）：**
- ~~线性衰减（linear）：每 N 天固定降低 M 点~~ → 过于机械，无法反映真实知识活跃度
- ~~阶梯衰减（step）：每 N 天降低一个固定阶梯~~ → 同上，阶梯设计缺乏业务依据

#### 6.5.4 执行流程

```
定时 Job（每日凌晨）               设计变更事件
     │                                   │
     ▼                                   ▼
BatchDecayCheck ───────────      OnDesignChange
     │                                   │
     ├─ usage_based 计算                ├─ 查找受影响实体
     │   └─ 置信度变化→记录快照          ├─ 设置目标置信度
     │                                  ├─ 记录快照 + 审计
     └─ 标记需人工审查的条目             └─ 通知作者
              │
              ▼
       每日审查通知
```

---

## 7. CI/CD 集成方案

### 7.1 全触点规划

| # | 触点 | 触发时机 | 具体动作 | 阻断级别 | 代价 |
|---|------|----------|----------|----------|------|
| 1 | **Pre-commit hook** | `git commit` 前 | 代码变更涉及知识关联文件（YAML/代码路径）时，检查关联知识是否正确 | warning | 小 |
| 2 | **Commit-msg hook** | 写入 commit-msg 后 | 解析 commit 中 `KB-XXX` / `LL-XXX` / `FMEA-XXX` 引用，验证引用存在 | blocker | 小 |
| 3 | **PR checklist** | 创建 PR 时 | 自动添加知识关联检查清单 + 失校检查（未关联合并将标记） | warning | 中 |
| 4 | **Merge gate** | PR merge 前 | FMEA YAML Schema 校验 + 必要 RPN 检查 + CI 知识债务检查 | blocker | 中 |
| 5 | **Regression hook** | Post-merge | 根据变更文件，反向索引查找受影响知识条目 → 通知相关人重审置信度 | info | 中 |
| 6 | **Auto-capture** | Bug/CI fail | Bug 创建或 CI 失败时，分析错误 → 自动创建 LL → 生成 Test Seed | info | 大 |

### 7.2 Pre-commit Hook

```yaml
# .githooks/pre-commit 逻辑
# 代价评估：小

checklist:
  - if 变更文件在 fmea/ 目录下:
      run: yuleosh knowledge validate-fmea --yaml {changed_file}
      on_fail:
        severity: warning
        message: "FMEA YAML 格式校验未通过，建议修复后提交"

  - if 变更 .c/.h/.cpp/.go 文件:
      run: yuleosh knowledge check-code-path --diff {staged_diff}
      on_match:
        severity: info
        message: "代码变更涉及知识关联路径 {path}，建议同步更新知识条目"
```

### 7.3 Commit-msg Hook（CI-02 约束级别）

> **CI-02 约束级别（待小马决策）：**
> - 若 Spec 决策为 **SHALL**（必须）：保留当前 `blocker` 级别，后续补充验收矩阵
> - 若 Spec 决策为 **SHOULD**（建议）：将 `blocker` 降为 `warning`
> - 当前暂按 SHALL 保留 blocker，待决策后调整

```yaml
# .githooks/commit-msg 逻辑
# 代价评估：小

regex_rules:
  - pattern: "FMEA-([A-Z0-9-]+)"
    action: verify_exists
    endpoint: fmea_items:id
    on_fail:
      severity: blocker
      message: "FMEA-ID {ref} 在系统中不存在，请核对"

  - pattern: "KB-([a-f0-9-]+)"
    action: verify_exists
    endpoint: kb_articles:id
    on_fail:
      severity: blocker
      message: "KB-ID {ref} 在系统中不存在，请核对"

  - pattern: "LL-([a-f0-9-]+)"
    action: verify_exists
    endpoint: lessons:id
    on_fail:
      severity: blocker
      message: "LL-ID {ref} 在系统中不存在，请核对"

  - if: diff_contains_code
    and: no_ref_match
    action: warn
    on_fail:
      severity: warning
      message: "代码变更建议引用关联知识条目（KB-xxx / LL-xxx / FMEA-xxx）"

# 验收矩阵（当 CI-02 决策为 SHALL 时补充）：
# | 测试用例 | 输入 | 预期 | 阻断级别 |
# |----------|------|------|----------|
# | TC-CI-02-001 | commit msg 含无效 KB-ID | 校验失败 + blocker | blocker |
# | TC-CI-02-002 | commit msg 含有效 KB-ID | 校验通过 | pass |
# | TC-CI-02-003 | commit msg 无引用但含代码变更 | warning 提示 | warning |
```

### 7.4 PR Checklist (自动添加)

```yaml
# PR Template — yuleosh 自动注入
# 代价评估：中

- [ ] 知识关联确认：
  - [ ] 代码变更是否指向已存在的知识条目？若无，是否需新建 KB 条目？
  - [ ] 代码变更是否涉及已有 FMEA 条目？若是，RPN 是否需要更新？
  - [ ] Lessons Learned 的 Test Seed 是否已生成或更新？
- [ ] FMEA YAML 格式校验通过（CI 自动检查）
- [ ] 代码路径反向索引是否已更新？
```

### 7.5 Merge Gate

```go
// internal/pipeline/knowledge/merge_gate.go
// 代价评估：中

func (g *MergeGate) Check(ctx context.Context, prID string) (*CICheckResult, error) {
    var blockers []string

    // 1. FMEA YAML Schema 校验
    changedFMEAs := listChangedFMEA(ctx, prID)
    for _, yamlFile := range changedFMEAs {
        if err := validateFMEAYAML(yamlFile); err != nil {
            blockers = append(blockers, fmt.Sprintf(
                "FMEA YAML %s 校验失败: %s", yamlFile, err))
        }
    }

    // 2. RPN 上限检查（blocker 级别）
    if hasCriticalFMEA(ctx, prID) {
        // RPN > 200 且没有 planned action → 阻断
        highItems := findHighRPNItemsWithoutPlan(ctx, prID)
        for _, item := range highItems {
            blockers = append(blockers, fmt.Sprintf(
                "FMEA item %s RPN=%d > 200，请先制定纠正措施",
                item.ID, item.RPN))
        }
    }

    // 3. 知识债务检查（warning）
    debtItems := checkKnowledgeDebt(ctx, prID)
    if len(debtItems) > 0 {
        // log warnings, 但不阻断
        g.logger.Warn("知识债务条目", zap.Int("count", len(debtItems)))
    }

    if len(blockers) > 0 {
        return &CICheckResult{Passed: false, Severity: "blocker", Blockers: blockers}, nil
    }

    return &CICheckResult{Passed: true}, nil
}
```

### 7.6 Regression Hook (Post-merge)

```yaml
# post-merge hook 逻辑
# 代价评估：中

steps:
  - name: "反向索引 → 受影响知识条目"
    run: yuleosh knowledge find-affected --changed-files {merged_files}
    output: affected_knowledge.json

  - name: "降低受影响条目置信度（自动衰减）"
    run: yuleosh knowledge decay-confidence --input affected_knowledge.json
    # 目标：让涉及变更的旧知识自动标记"待审查"

  - name: "通知相关负责人"
    run: yuleosh notify --template knowledge_regression_alert
                        --recipients {affected_knowledge.authors}
                        --message "您的知识条目因代码变更需要重新审阅"

  - name: "触发 FMEA → Test 管道（若有变更）"
    if: merged_files matches "fmea/"
    run: yuleosh ci trigger-fmea-test --fmea_yaml {changed_fmea}
```

### 7.7 Auto-capture（Phase 3）

```yaml
# Bug 或 CI Failure 自动捕获
# 代价评估：大（需 AI 或规则引擎）

trigger:
  - event: "bug_created"
    filter: priority in (P0, P1, P2)
    action: yuleosh knowledge auto-capture-lesson --bug {bug_id}

  - event: "ci_test_failure"
    filter: failure_count >= 3 in 7 days
    action: yuleosh knowledge auto-capture-lesson --ci-run {run_id}

auto_capture_pipeline:
  - step: "分析错误信息"
    # Phase 2: 规则模板匹配
    # Phase 3: LLM 自动分析
  - step: "创建 Lesson"
  - step: "生成 Test Seed（layer: Unit/SIL）"
  - step: "CI 提交 PR（含 Test Seed 代码）"
  - step: "通知开发者审查"
```

### 7.8 与现有 ci 模块的对接方式

```go
// internal/ci/ci.go（已有模块）

// 新增知识管理 hook 注册
func (c *CM) RegisterKnowledgeHooks() {
    knowledgeChecker := knowledge_ci.NewKnowledgeCIChecker(c.svc.knowledge, c.logger)

    // Pre-commit
    c.RegisterHook("pre-commit", &Hook{
        Priority: HookPriorityMedium,
        Execute: func(ctx *HookContext) error {
            result := knowledgeChecker.CheckPreCommit(ctx.ChangedFiles)
            return ctx.HandleResult(result)
        },
    })

    // Commit-msg
    c.RegisterHook("commit-msg", &Hook{
        Priority: HookPriorityHigh,
        Execute: func(ctx *HookContext) error {
            result := knowledgeChecker.CheckCommitMsg(ctx.CommitMsg)
            return ctx.HandleResult(result)
        },
    })

    // Merge gate
    c.RegisterHook("merge-gate", &Hook{
        Priority: HookPriorityHigh,
        Execute: func(ctx *HookContext) error {
            result := knowledgeChecker.CheckMergeGate(ctx.Branch)
            return ctx.HandleResult(result)
        },
    })

    // Post-merge regression
    c.RegisterPipelineStep("post-merge", PipelineStep{
        Name:     "knowledge-regression-check",
        Runnable: knowledgeChecker.TriggerRegression,
        Async:    true,
    })
}
```

---

## 8. 与现有 yuleOSH 模块的集成点

### 8.1 集成总览

| yuleOSH 模块 | 集成方式 | 方向 |
|-------------|----------|------|
| **store** | 新增 `pkg/store/knowledge/` 子包 | 知识模块 → store |
| **ci** | 注册 KnowledgeHooks（如上） | 知识模块 → ci |
| **pipeline** | 新增 `internal/pipeline/knowledge/` | 知识模块 → pipeline |
| **evidence** | 知识/LL/FMEA 通过 `evidence_id` 字段引用 | 双向往来 |
| **spec** | FMEA YAML 可作为 spec 模块的观察输入 | spec → 知识模块（读取） |
| **queue/event** | 事件驱动：confidence decay / regression / auto-capture | 知识模块 → event bus |

### 8.2 evidence 模块集成

```go
// evidence 模块集成示例
// FMEA Item 创建/更新时自动生成 evidence 记录

type KnowledgeEvidenceCollector struct {
    evidenceService evidence.Service
}

func (c *KnowledgeEvidenceCollector) OnFMEAItemCreated(ctx context.Context, item *domain.FMEAItem) error {
    // 自动创建 evidence（分析阶段的证据）
    return c.evidenceService.Create(ctx, &evidence.Evidence{
        Type:      evidence.TypeAnalysis,
        EntityID:  item.ID.String(),
        EntityType: "fmea_item",
        Content: map[string]interface{}{
            "failure_mode": item.FailureMode,
            "rpn":          item.RPN,
            "dtc_codes":    item.DTCCodes,
        },
        Tags:      []string{"fmea", "auto_captured"},
    })
}

// FMEA Action 完成时挂载 evidence（整改证据）
func (c *KnowledgeEvidenceCollector) OnFMEAActionClosed(ctx context.Context, action *domain.FMEAAction) error {
    return c.evidenceService.Create(ctx, &evidence.Evidence{
        Type:      evidence.TypeValidation,
        EntityID:  action.ID.String(),
        EntityType: "fmea_action",
        Content: map[string]interface{}{
            "description": action.Description,
            "rpn_before": action.RPNBefore,
            "rpn_after":  action.RPNAfter,
        },
        Tags: []string{"fmea", "action_completed"},
    })
}
```

### 8.3 spec 模块集成

```go
// spec 模块：FMEA 可供 spec 审查时参考
// 在 spec review 过程中，自动检查是否存在相关 FMEA

type SpecFMEAIntegration struct {
    knowledgeService KnowledgeService
}

func (s *SpecFMEAIntegration) ReviewCheck(ctx context.Context, specID string, system string) (*SpecCheckResult, error) {
    // 查找指定系统的 FMEA
    entry, err := s.knowledgeService.GetFMEABySystem(ctx, system)
    if err != nil {
        return nil, err
    }

    // 检查 spec 变更是否已被 FMEA 覆盖
    uncovered, err := s.findUncoveredFailureModes(ctx, specID, entry)
    if err != nil {
        return nil, err
    }

    return &SpecCheckResult{
        HasFMEA:       entry != nil,
        UncoveredCount: len(uncovered),
        UncoveredItems: uncovered,
    }, nil
}
```

---

## 9. 实施路线

### 9.1 Phase 1 — 地基（MVP，重估后 48 人·天）

> **工作量重估依据（老陈审查意见 2026-06-20）：**
> 原 30 人·天严重低估，实际重估为 **48 人·天**。主要增量来自：
> 1. LL/FMEA 审计日志表补全（+2 人·天）
> 2. OSLC/ReqIF 集成接口设计（+4 人·天，§12）
> 3. Polarion REST API 双向同步原型（+4 人·天）
> 4. 置信度衰减引擎调整 + 事件驱动实现（+3 人·天）
> 5. 验收矩阵补全（CI-02 等，+2 人·天）
> 6. 各工作项低估校正（+3 人·天）

**定位：** 能存、能查、能跑最小闭环。

| 编号 | 工作项 | 人·天 | 依赖 |
|------|--------|:-----:|------|
| P1-1 | DB migration：核心表（含 kb_articles, kb_versions, lessons, fmea_entries, fmea_items, fmea_actions, tags, dtc_map, test_map, code_paths） | 3 | — |
| P1-2 | DB migration：审计日志表（ll_audit_logs, fmea_audit_logs） | 2 | P1-1 |
| P1-3 | Store 接口 + repo 实现（CRUD，不含搜索） | 4 | P1-1 |
| P1-4 | KB Service：CRUD + 版本快照创建 | 3 | P1-3 |
| P1-5 | KB Handler：REST API | 2 | P1-4 |
| P1-6 | LL Service：手动创建 + 搜索 + 审计日志（ll_audit_logs） | 3 | P1-2 + P1-3 |
| P1-7 | FMEA Service：从 YAML 创建 + 基础 CRUD + 审计日志 | 4 | P1-2 + P1-3 |
| P1-8 | FMEA YAML 解析器 + Schema 校验 | 3 | P1-7 |
| P1-9 | DTC 检索接口（精确匹配 + 关联查询） | 2 | P1-1 |
| P1-10 | Pre-commit hook + Commit-msg hook 集成（含 CI-02 验收矩阵） | 3 | ci 模块 |
| P1-11 | Merge gate（FMEA YAML 校验 + RPN 检查） | 2 | P1-8 + ci 模块 |
| P1-12 | PR checklist 自动注入 | 1 | ci 模块 |
| P1-13 | 知识债务仪表盘（简单计数+列表） | 3 | P1-3 |
| P1-14 | 置信度衰减 — 事件驱动触发 + 定时 Job 骨架 | 3 | P1-3 |
| P1-15 | OSLC Provider 接口设计 + ReqIF 导出 | 4 | — |
| P1-16 | Polarion REST API 双向同步原型 | 4 | P1-15 |
| P1-17 | 依赖：硬件平台/BOM 标签体系 | 2 | — |
| P1-18 | 测试 + 文档 + 验收矩阵 | 4 | P1-1 ~ P1-17 |
| | **合计** | **48** | |

**Phase 1 交付状态：**
- ✅ 全量核心表建成（含审计日志表）
- ✅ KB/LL/FMEA CRUD RESTful API
- ✅ LL/FMEA 审计日志落地
- ✅ FMEA YAML 解析+导入
- ✅ DTC 检索（精确匹配）
- ✅ Pre-commit + Commit-msg（含 CI-02 验收矩阵）+ Merge gate
- ✅ OSLC Provider 接口设计 + ReqIF 导出
- ✅ Polarion REST API 双向同步原型
- ✅ 置信度衰减事件驱动触发（定时 Job 骨架）
- ✅ 知识债务仪表盘（基础版）
- ❌ 语义搜索
- ❌ 自动捕获

### 9.2 Phase 2 — 智能化（目标 25 人·天）

**定位：** 引入语义搜索 + 置信度管理 + AI 辅助。

| 编号 | 工作项 | 人·天 | 依赖 |
|------|--------|:-----:|------|
| P2-1 | pgvector 扩展 + embedding 列 + IVFFLAT 索引 | 1 | Phase 1 |
| P2-2 | Embedding 生成服务（本地/远程模型集成） | 3 | P2-1 |
| P2-3 | 混合搜索（语义 + 关键词 + DTC） | 3 | P2-2 + P1-8 |
| P2-4 | 推荐引擎（基于 embedding + DTC + tag） | 2 | P2-3 |
| P2-5 | 置信度衰减 — usage_based 定时计算 + 阈值审查 | 2 | Phase 1（骨架已由 P1-14 完成） |
| P2-6 | 置信度管理 API + UI | 2 | P2-5 |
| P2-7 | Cross-ECU FMEA 链可视化（后端） | 3 | P1-6 |
| P2-8 | Regression hook（后合并自动衰减） | 2 | P2-5 + pipeline |
| P2-9 | 自动生成 Test Seed（基于规则模板） | 3 | P1-5 |
| P2-10 | AI 知识摘要/分类（辅助人工） | 2 | P2-2 |
| P2-11 | 知识债务仪表盘增强（置信度/失校/老化） | 1 | P2-5 |
| | **合计** | **25** | |

**Phase 2 交付状态（增量）：**
- ✅ 语义混合搜索
- ✅ 推荐引擎
- ✅ 置信度自动衰减
- ✅ Cross-ECU 链管理
- ✅ Regression hook
- ✅ Test Seed 规则生成
- ✅ AI 辅助摘要/分类
- ❌ 全自动捕获

### 9.3 Phase 3 — 自动化（目标 20 人·天）

**定位：** 打通全自动闭环。

| 编号 | 工作项 | 人·天 | 依赖 |
|------|--------|:-----:|------|
| P3-1 | Bug→LL 自动捕获管道 | 4 | Phase 2 |
| P3-2 | CI Failure→LL 自动捕获管道 | 3 | Phase 2 |
| P3-3 | LL→Test Seed 自动 PR 提交 | 3 | P3-1 + CI |
| P3-4 | FMEA→Test→Telemetry 闭环（对接 telemetry） | 4 | Phase 2 |
| P3-5 | Auto-capture 置信度门槛 + 人工确认机制 | 2 | P3-1 |
| P3-6 | pgvector HNSW 索引迁移 + 优化 | 1 | P2-1 |
| P3-7 | 售后闭环自动化（DTC Report → FMEA + LL） | 3 | Phase 2 |
| | **合计** | **20** | |

### 9.4 里程碑总览

```
Phase 1 (48人·天) ───→ Phase 2 (25人·天) ───→ Phase 3 (20人·天)
     │                       │                       │
     ▼                       ▼                       ▼
    MVP 可用               智能搜索                全自动闭环
    KB/LL/FMEA CRUD        语义搜索                Bug→LL→Test
    DTC 检索               置信度衰减              CI failure→LL
    CI 门禁                推荐引擎                FMEA→Test→Telemetry
    FMEA YAML              跨ECU链                 售后闭环
    知识债务仪表盘          Regression hook
```

**总工作量：** 93 人·天（重估后 | Phase 1: 48 + Phase 2: 25 + Phase 3: 20）
（约 4-5 个月，视团队规模）

---

## 10. 附录：索引策略速查

### 10.1 索引类型汇总

| 表 | 索引列 | 索引类型 | 用途 | 引入阶段 |
|----|--------|----------|------|----------|
| kb_articles | status | B-tree | 状态过滤 | P1 |
| kb_articles | asil | B-tree | ASIL 分级查询 | P1 |
| kb_articles | confidence | B-tree | 置信度排序 | P1 |
| kb_articles | dtc_codes | GIN | DTC 数组包含查询 | P1 |
| kb_articles | hw_bom | GIN (jsonb_path_ops) | HW BOM JSONB 过滤 | P1 |
| kb_articles | tags | GIN | 标签过滤 | P1 |
| kb_articles | updated_at DESC | B-tree | 最近更新排序 | P1 |
| kb_articles | embedding | IVFFLAT(vec_cosine_ops) | 语义搜索 | P2 |
| kb_articles | embedding | HNSW(vec_cosine_ops) | 高吞吐语义搜索 | P3 |
| kb_versions | (article_id, version) DESC | B-tree (复合) | 版本快照检索 | P1 |
| lessons | source, severity, status | B-tree (多列) | 多维过滤 | P1 |
| lessons | ota_version | B-tree | OTA 版本检索 | P1 |
| fmea_items | rpn DESC | B-tree | RPN 排序（高优先） | P1 |
| fmea_items | dtc_codes | GIN | DTC 查询 | P1 |
| knowledge_dtc_map | dtc_code | B-tree | DTC 精确检索 | P1 |
| knowledge_test_map | (test_suite, test_case_id) | B-tree (复合) | 测试用例逆向查询 | P1 |
| knowledge_code_paths | (repo, file_path) | B-tree (复合) | 代码路径反向索引 | P1 |
| knowledge_confidence_snaps | (entity_type, entity_id, snapshot_at) DESC | B-tree (复合) | 置信度历史 | P2 |
| ll_audit_logs | (lesson_id, created_at DESC) | B-tree (复合) | LL 审计日志查询 | P1 |
| fmea_audit_logs | (fmea_entry_id, created_at DESC) | B-tree (复合) | FMEA 审计日志查询 | P1 |

### 10.2 Full-text Search 配置

```sql
-- 建立 tsvector 列（可选项，视图或物化列均可）
ALTER TABLE knowledge.kb_articles
    ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content, ''))
    ) STORED;

CREATE INDEX idx_kb_fts ON knowledge.kb_articles USING GIN(search_vector);

-- Lessons 类似
ALTER TABLE knowledge.lessons
    ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, '') || ' ' || coalesce(root_cause, '') || ' ' || coalesce(resolution, ''))
    ) STORED;

CREATE INDEX idx_lessons_fts ON knowledge.lessons USING GIN(search_vector);
```

### 10.3 分页与排序约定

```sql
-- 统一的分页模式：cursor-based（推荐，避免 OFFSET 深分页问题）

-- KV 主表均带 updated_at 排序，分页建议：
SELECT * FROM knowledge.kb_articles
WHERE status = 3
  AND (updated_at, id) < ($cursor_time, $cursor_id)  -- 游标分页
ORDER BY updated_at DESC, id DESC
LIMIT 20;
```

---

## 11. ASPICE SWE.5 五层测试 ←→ 三层验证映射

> **背景：** yuleOSH 采用五层测试体系（HIL/SIL/MIL/PIL/Unit），ASPICE SWE.5 要求三层验证（单元测试、集成测试、系统测试）。
> 下表建立 yuleOSH 五层 ←→ ASPICE 三层的映射关系，用于 CI-10 / KB-10 合规检查。

### 11.1 层级映射

| yuleOSH 五层 | 缩写 | ASPICE SWE.5 对应 | 验证意图 | 知识管理触点 |
|-------------|:----:|:-----------------:|----------|-------------|
| **Hardware-in-the-Loop** | HIL | 系统测试（SWE.5 §3） | 真实硬件环境下的系统级验证 | knowledge_test_map.layer=0; FMEA 交叉验证 |
| **Software-in-the-Loop** | SIL | 集成测试（SWE.5 §2） | 软件在环，总线级仿真 | knowledge_test_map.layer=1; LL Test Seed 输出目标 |
| **Model-in-the-Loop** | MIL | 单元/集成测试（SWE.5 §1-2） | 模型级别功能验证 | knowledge_test_map.layer=2 |
| **Processor-in-the-Loop** | PIL | 集成测试（SWE.5 §2） | 编译后目标处理器上验证 | knowledge_test_map.layer=3; 代码路径反向索引校验 |
| **Unit Test** | Unit | 单元测试（SWE.5 §1） | 最小单元函数级测试 | knowledge_test_map.layer=4; Test Seed 直接输出 |

### 11.2 KB-10 / CI-05 合规检查

```go
func (g *MergeGate) checkASPICECompliance(ctx context.Context, prID string) []string {
    var violations []string
    changedFMEAs := listChangedFMEA(ctx, prID)
    for _, fmea := range changedFMEAs {
        for _, item := range fmea.Items {
            mappedLayer := mapFMEToTestLayer(item.AutosarLayer)
            if item.Severity >= 7 && !hasTestForLayer(ctx, item.ID, mappedLayer) {
                violations = append(violations, fmt.Sprintf(
                    "FMEA item %s severity=%d 缺少对应测试层 %s", item.ID, item.Severity, mappedLayer))
            }
        }
    }
    changedLLs := listChangedLessons(ctx, prID)
    for _, ll := range changedLLs {
        for _, seed := range ll.TestSeeds {
            if !isASPICEMappingValid(seed.TestLayer) {
                violations = append(violations, fmt.Sprintf(
                    "LL %s Test Seed layer=%d 无对应 ASPICE 验证层级", ll.ID, seed.TestLayer))
            }
        }
    }
    return violations
}
```

### 11.3 测试覆盖率要求

| ASPICE SWE.5 级别 | 对应 yuleOSH 层 | 覆盖率门槛 | 知识管理要求 |
|------------------|:---------------:|:---------:|-------------|
| 单元测试（SWE.5 §1） | Unit, MIL | ≥80% 分支覆盖率 | 失败时触发生成 LL → Test Seed |
| 集成测试（SWE.5 §2） | SIL, PIL | 所有接口至少 1 正向+1 负向用例 | 必须关联 FMEA item 或 KB 条目 |
| 系统测试（SWE.5 §3） | HIL | 所有 SWE.5 需求可追踪 | 通过 knowledge_test_map 双向追溯 |

---

## 12. 外部系统集成（Polarion / Codebeamer / OSLC）

> **老陈审查意见（2026-06-20）：** 这是目前最致命的缺口。ASPICE 认证时，工具间需求追溯是强制要求，
> 缺乏 Polarion/Codebeamer/OSLC 集成策略将直接导致 ASPICE 审核不通过。

### 12.1 集成概览

```
┌──────────────┐     OSLC CM / AM      ┌──────────────────┐
│  Polarion    │ ◄═══════════════════► │  yuleOSH KM      │
│  (ALM/Req)   │     OSLC QM           │  (Knowledge Mgmt)│
└──────────────┘                       └──────────────────┘
       │                                       │
       │ ReqIF (标准交换格式)                    │ REST / gRPC
       ▼                                       ▼
┌──────────────┐                       ┌──────────────────┐
│  Codebeamer  │                       │  yuleOSH Core    │
│  (Dev/Test)  │                       │  (KB/LL/FMEA)    │
└──────────────┘                       └──────────────────┘
```

### 12.2 OSLC Provider 接口设计

#### 12.2.1 支持的 OSLC 域

| OSLC 域 | 对应 yuleOSH 实体 | OSLC 资源形状 | 用途 |
|---------|------------------|-------------|------|
| **OSLC CM**（Change Management） | lessons (LL) | `oslc_cm:ChangeRequest` | 与 Polarion 工作项互引用 |
| **OSLC AM**（Architecture Management） | kb_articles (KB) | `oslc_am:Resource` | 需求-知识追溯 |
| **OSLC QM**（Quality Management） | fmea_items (FMEA) | `oslc_qm:TestResult` | FMEA-测试追溯 |

#### 12.2.2 核心端点

```
# OSLC Service Provider Catalog
GET /oslc/provider        → 服务提供商目录

# OSLC CM — Lessons Learned
GET /oslc/cm/lessons/{id}           → RDF/XML 或 JSON-LD 格式的 LL 条目
GET /oslc/cm/lessons?oslc.where=... → 查询 LL
POST /oslc/cm/lessons               → 创建 LL（Polarion 端发起）

# OSLC AM — Knowledge Base
GET /oslc/am/articles/{id}          → RDF/XML 或 JSON-LD 格式的 KB 条目
GET /oslc/am/articles?oslc.where=.. → 查询 KB

# OSLC QM — FMEA
GET /oslc/qm/fmea-items/{id}        → RDF/XML 或 JSON-LD 格式的 FMEA 条目
GET /oslc/qm/fmea-items?oslc.where= → 查询 FMEA items
```

#### 12.2.3 资源表示（RDF/XML 示例）

```xml
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:dcterms="http://purl.org/dc/terms/"
         xmlns:oslc_cm="http://open-services.net/ns/cm#"
         xmlns:yuleosh="http://yuleosh.io/ns/knowledge#">
  <oslc_cm:ChangeRequest rdf:about="http://yuleosh/oslc/cm/lessons/{uuid}">
    <dcterms:identifier>{uuid}</dcterms:identifier>
    <dcterms:title>{title}</dcterms:title>
    <dcterms:description>{description}</dcterms:description>
    <oslc_cm:status>mitigated</oslc_cm:status>
    <oslc_cm:severity>critical</oslc_cm:severity>
    <yuleosh:confidence>70</yuleosh:confidence>
  </oslc_cm:ChangeRequest>
</rdf:RDF>
```

#### 12.2.4 发现机制 — Service Provider Catalog

```json
GET /oslc/provider
{
  "title": "yuleOSH KM OSLC Provider",
  "services": [
    {
      "domain": "http://open-services.net/ns/cm#",
      "resourceType": "http://open-services.net/ns/cm#ChangeRequest",
      "resourceShape": {
        "describes": "http://yuleosh/oslc/shapes/cm-lesson",
        "properties": [
          {"name": "dcterms:title", "occurs": "exactly-one", "valueType": "xsd:string"},
          {"name": "oslc_cm:status", "occurs": "exactly-one", "allowedValues": ["open","investigating","action_planned","implemented","mitigated","verified","closed","rejected"]}
        ]
      },
      "endpoint": "http://yuleosh/oslc/cm/lessons"
    },
    {
      "domain": "http://open-services.net/ns/am#",
      "endpoint": "http://yuleosh/oslc/am/articles"
    },
    {
      "domain": "http://open-services.net/ns/qm#",
      "endpoint": "http://yuleosh/oslc/qm/fmea-items"
    }
  ]
}
```

### 12.3 ReqIF 导出

```go
func (s *KBService) ExportToReqIF(ctx context.Context, filter ArticleFilter) ([]byte, error) {
    articles, _, _ := s.store.ListArticles(ctx, filter)
    // 序列化为 ReqIF XML 格式
    return serializeReqIF("yuleOSH Knowledge Export", articles)
}

func (s *KBService) ImportFromReqIF(ctx context.Context, reqifData []byte) (int, error) {
    // 解析 ReqIF，逐条创建 KB 条目
    return s.parseAndImportReqIF(ctx, reqifData)
}
```

### 12.4 Polarion REST API 双向同步

#### 12.4.1 同步架构

```
Polarion                     yuleOSH
  │                            │
  ├─ WebHook (WorkItem change) │
  │         ─────────────────► ├─ 匹配并更新本地 KB/LL/FMEA
  │                            │
  │                            ├─ 定时 Job（每 15min）
  │                            │    └─ GET /polarion/rest/wi/{since}
  │         ◄───────────────── │       └─ 增量同步
  │                            │
  │                            ├─ yuleOSH 变更时
  │         PUT /wi/{id} ────► │       └─ 推送至 Polarion
```

#### 12.4.2 同步映射表

| yuleOSH 实体 | Polarion WorkItem Type | 字段映射 | 同步方向 |
|-------------|----------------------|---------|---------|
| kb_articles | `KBArticle`（自定义） | title↔title, summary↔description, status↔status, asil↔customField(Asil) | 双向 |
| lessons | `ChangeRequest`（标准） | title↔title, root_cause↔resolution, severity↔priority, status↔status | 双向 |
| fmea_items | `FMEAItem`（自定义） | failure_mode↔title, rpn↔customField(FMEA_RPN) | 单向（yuleOSH→Polarion） |

#### 12.4.3 冲突解决策略：Polarion 优先（作为 ALM 权威源），软删除而非物理删除

### 12.5 Codebeamer 集成（复用 §12.2 OSLC Provider，额外通过 REST API）

### 12.6 集成优先级

| 功能 | ASPICE 贡献 | 复杂度 | 阶段 |
|------|:----------:|:------:|:----:|
| OSLC CM Provider（LL） | ★★★ | 中 | Phase 1 |
| ReqIF 导出（KB） | ★★★ | 低 | Phase 1 |
| Polarion 双向同步（KB） | ★★ | 高 | Phase 1（原型）| 
| OSLC AM/QM Provider | ★★ | 中 | Phase 2 |
| Codebeamer 对接 | ★★ | 中 | Phase 2 |

---

> **文档状态：** v1.2 — 已根据老陈最终复检意见完成 Tech 端修复。
>
> **变更记录（2026-06-20）：**
> - **P0:** LL 生命周期新增 mitigated 状态（4:mitigated）；KB 6 状态对齐确认；FMEA 6 状态等小马决策；HW BOM 补充 JSONB Schema；confidence 类型确认 SMALLINT 0-100
> - **P0:** 新增 §12 外部系统集成（OSLC Provider + ReqIF 导出 + Polarion 双向同步）
> - **P0:** 置信度类型：保持 SMALLINT 0-100，Spec 验收矩阵 float 值映射为整数
> - **P1:** 新增 ll_audit_logs 和 fmea_audit_logs 表（CROSS-04）
> - **P1:** 置信度衰减策略砍掉 linear/step，保留 usage_based + 事件驱动（§6.5）
> - **P1:** CI-02 约束级别暂按 SHALL 保留 blocker，补充验收矩阵
> - **P1:** 新增 §11 ASPICE SWE.5 五层←→三层映射表
> - **P1:** Phase 1 工作量重估 30→48 人·天（原总计 75→93 人·天）
>
> **变更记录（2026-06-20 复检修复）：**
> - **P0-2:** 补全 safety_level 强制字段：lessons（§2.2.9）、fmea_entries（§2.2.12）、fmea_items（§2.2.13）
> - **P0-3:** kb_articles.confidence DEFAULT 50→100（§2.2.1）；kb_versions.confidence DEFAULT 50→100（§2.2.2）
> - **P0-4:** fmea_items.confidence DEFAULT 70→100（§2.2.13）
> - **P0-1:** ✅ 确认 lessons.status 已包含 4:mitigated（§2.2.9），无需修改
>
> **后续步骤：**
> 1. 小马审查 architecture + data model + 新增章节
> 2. 分歧点由小明裁决（LL/FMEA 状态枚举、CI-02 约束级别）
> 3. 锁定后进入 Phase 1 编码
