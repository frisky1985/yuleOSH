-- ============================================================================
-- yuleOSH Knowledge Management — Phase 1 DDL
-- Schema: knowledge
-- Version: 1
-- Target: PostgreSQL 15+ (with pgvector extension optional for Phase 2)
-- Migration tool: yuleOSH built-in migrator (or psql -f)
-- ============================================================================
-- Core tables:   kb_articles, kb_versions, lessons, fmea_entries, fmea_items
-- Auxiliary:     kb_version_audit_logs, ll_audit_logs, fmea_audit_logs,
--                knowledge_tags, kb_article_tags, knowledge_dtc_map,
--                knowledge_test_map, knowledge_code_paths, lesson_actions,
--                lesson_test_seeds, fmea_actions, fmea_item_cross_ecu,
--                knowledge_confidence_snapshots
-- Total:         7 core + 8 auxiliary = 15 tables
-- ============================================================================

BEGIN;

-- ── Schema ────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS knowledge;
SET search_path TO knowledge;

-- ============================================================================
-- 1. kb_articles — 知识条目主表
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge.kb_articles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    summary         TEXT NOT NULL DEFAULT '',
    content         TEXT NOT NULL DEFAULT '',
    body_format     SMALLINT NOT NULL DEFAULT 0,  -- 0:markdown, 1:html

    -- 6 状态生命周期：0:draft, 1:review_pending, 2:approved, 3:published, 4:deprecated, 5:archived
    status          SMALLINT NOT NULL DEFAULT 0 CHECK (status >= 0 AND status <= 5),

    -- ASIL 分级：0:QM, 1:ASIL_A, 2:ASIL_B, 3:ASIL_C, 4:ASIL_D
    asil            SMALLINT NOT NULL DEFAULT 0 CHECK (asil >= 0 AND asil <= 4),

    -- AUTOSAR 层级（位掩码）：bit0:ASW, bit1:RTE, bit2:BSW, bit3:HW
    autosar_layer   SMALLINT NOT NULL DEFAULT 0,

    -- HW BOM 标签（JSONB 数组，多平台）
    hw_bom          JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- OTA 版本绑定（JSON）
    -- { "min_ota": "v2.1.0", "max_ota": "v2.3.0", "affected": true }
    ota_binding     JSONB,

    -- DTC 编码数组（主表冗余加速过滤，详表在 knowledge_dtc_map）
    dtc_codes       TEXT[] NOT NULL DEFAULT '{}',

    -- TCL 工具认证预留字段
    -- { "tcl_tool_id": "...", "cert_doc_refs": [...], "assessment_status": "..." }
    tcl_doc_slot    JSONB,

    -- Safety Goal 安全目标关联（JSONB 数组）
    -- [{ "safety_goal_id": "SG-BRAKE-001", "link_type": "verifies", ... }]
    safety_goals    JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- 代码路径反向索引（JSONB 数组）
    code_paths      JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- 元数据
    author_id       TEXT NOT NULL,
    reviewer_id     TEXT,
    tags            TEXT[] NOT NULL DEFAULT '{}',

    -- 置信度 0–100
    confidence      SMALLINT NOT NULL DEFAULT 100 CHECK (confidence >= 0 AND confidence <= 100),

    -- 置信度衰减策略：0:usage_based（仅保留此策略）
    confidence_decay_policy SMALLINT NOT NULL DEFAULT 0,

    -- 代码路径过期标记
    code_path_stale BOOLEAN NOT NULL DEFAULT false,

    -- 版本快照
    current_version INT NOT NULL DEFAULT 1,
    latest_version_id UUID,  -- 指向 kb_versions.id

    -- 软删除
    is_deleted      BOOLEAN NOT NULL DEFAULT false,
    deleted_at      TIMESTAMPTZ,

    -- 时间戳
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- kb_articles 索引
CREATE INDEX IF NOT EXISTS idx_kb_articles_status ON knowledge.kb_articles(status) WHERE NOT is_deleted;
CREATE INDEX IF NOT EXISTS idx_kb_articles_asil ON knowledge.kb_articles(asil) WHERE NOT is_deleted;
CREATE INDEX IF NOT EXISTS idx_kb_articles_autosar ON knowledge.kb_articles(autosar_layer) WHERE NOT is_deleted;
CREATE INDEX IF NOT EXISTS idx_kb_articles_confidence ON knowledge.kb_articles(confidence) WHERE NOT is_deleted;
CREATE INDEX IF NOT EXISTS idx_kb_articles_dtc ON knowledge.kb_articles USING GIN(dtc_codes) WHERE NOT is_deleted;
CREATE INDEX IF NOT EXISTS idx_kb_articles_hw_bom ON knowledge.kb_articles USING GIN(hw_bom) WHERE NOT is_deleted;
CREATE INDEX IF NOT EXISTS idx_kb_articles_tags ON knowledge.kb_articles USING GIN(tags) WHERE NOT is_deleted;
CREATE INDEX IF NOT EXISTS idx_kb_articles_updated ON knowledge.kb_articles(updated_at DESC) WHERE NOT is_deleted;
CREATE INDEX IF NOT EXISTS idx_kb_articles_author ON knowledge.kb_articles(author_id) WHERE NOT is_deleted;
CREATE INDEX IF NOT EXISTS idx_kb_articles_deleted ON knowledge.kb_articles(is_deleted, deleted_at);
-- GIN index for safety_goals JSONB array
CREATE INDEX IF NOT EXISTS idx_kb_articles_safety_goals ON knowledge.kb_articles USING GIN(safety_goals) WHERE NOT is_deleted;

-- ============================================================================
-- 2. kb_versions — 版本快照链
-- ============================================================================
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
    safety_goals    JSONB NOT NULL DEFAULT '[]'::jsonb,
    change_summary  TEXT NOT NULL DEFAULT '',
    changed_by      TEXT NOT NULL DEFAULT '',
    confidence      SMALLINT NOT NULL DEFAULT 100,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(article_id, version)
);

CREATE INDEX IF NOT EXISTS idx_kb_versions_article ON knowledge.kb_versions(article_id, version DESC);

-- ============================================================================
-- 3. kb_version_audit_logs — 版本审批审计（CROSS-04）
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge.kb_version_audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id      UUID REFERENCES knowledge.kb_versions(id) ON DELETE CASCADE,
    article_id      UUID NOT NULL REFERENCES knowledge.kb_articles(id) ON DELETE CASCADE,
    action          SMALLINT NOT NULL,
                    -- 1:submit_review, 2:approve, 3:reject, 4:rollback,
                    -- 5:force_publish, 6:confidence_reset, 7:spec_ref_update
    operator_id     TEXT NOT NULL,
    comment         TEXT NOT NULL DEFAULT '',
    old_status      SMALLINT,
    new_status      SMALLINT,
    detail_json     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kb_audit_version ON knowledge.kb_version_audit_logs(version_id);
CREATE INDEX IF NOT EXISTS idx_kb_audit_article ON knowledge.kb_version_audit_logs(article_id, created_at DESC);

-- ============================================================================
-- 4. ll_audit_logs — LL 审计日志（CROSS-04）
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge.ll_audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lesson_id       UUID NOT NULL REFERENCES knowledge.lessons(id) ON DELETE CASCADE,
    action          SMALLINT NOT NULL,
                    -- 1:created, 2:status_change, 3:severity_change, 4:assign,
                    -- 5:confidence_change, 6:link_to_article, 7:comment,
                    -- 8:generate_test_seed, 9:close, 10:reopen, 11:dtc_threshold
    operator_id     TEXT NOT NULL,
    comment         TEXT NOT NULL DEFAULT '',
    old_status      SMALLINT,
    new_status      SMALLINT,
    old_severity    SMALLINT,
    new_severity    SMALLINT,
    old_confidence  SMALLINT,
    new_confidence  SMALLINT,
    detail_json     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ll_audit_lesson ON knowledge.ll_audit_logs(lesson_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ll_audit_operator ON knowledge.ll_audit_logs(operator_id);

-- ============================================================================
-- 5. fmea_audit_logs — FMEA 审计日志（CROSS-04）
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge.fmea_audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fmea_entry_id   UUID REFERENCES knowledge.fmea_entries(id) ON DELETE CASCADE,
    fmea_item_id    UUID REFERENCES knowledge.fmea_items(id) ON DELETE CASCADE,
    action          SMALLINT NOT NULL,
                    -- 1:entry_created, 2:entry_status_change, 3:item_created,
                    -- 4:item_status_change, 5:rpn_update, 6:action_created,
                    -- 7:action_status_change, 8:confidence_change,
                    -- 9:yaml_sync, 10:cross_ecu_update, 11:review_completed,
                    -- 12:ap_change, 13:fork
    operator_id     TEXT NOT NULL,
    comment         TEXT NOT NULL DEFAULT '',
    detail_json     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fmea_audit_has_target CHECK (
        fmea_entry_id IS NOT NULL OR fmea_item_id IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_fmea_audit_entry ON knowledge.fmea_audit_logs(fmea_entry_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fmea_audit_item ON knowledge.fmea_audit_logs(fmea_item_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fmea_audit_operator ON knowledge.fmea_audit_logs(operator_id);

-- ============================================================================
-- 6. knowledge_tags — 标签定义
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge.knowledge_tags (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL UNIQUE,
    category        SMALLINT NOT NULL DEFAULT 0,
                    -- 0:general, 1:asil, 2:autosar, 3:ecu, 4:dtc, 5:test, 6:ota
    color           TEXT NOT NULL DEFAULT '#1890FF',
    description     TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_tags_category ON knowledge.knowledge_tags(category);

-- ============================================================================
-- 7. kb_article_tags — 知识-标签多对多
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge.kb_article_tags (
    article_id      UUID NOT NULL REFERENCES knowledge.kb_articles(id) ON DELETE CASCADE,
    tag_id          UUID NOT NULL REFERENCES knowledge.knowledge_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (article_id, tag_id)
);

-- ============================================================================
-- 8. knowledge_dtc_map — DTC 关联表（一级检索维度）
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge.knowledge_dtc_map (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dtc_code        TEXT NOT NULL,
    dtc_description TEXT NOT NULL DEFAULT '',
    article_id      UUID REFERENCES knowledge.kb_articles(id) ON DELETE CASCADE,
    lesson_id       UUID REFERENCES knowledge.lessons(id) ON DELETE CASCADE,
    fmea_item_id    UUID REFERENCES knowledge.fmea_items(id) ON DELETE CASCADE,
    weight          SMALLINT NOT NULL DEFAULT 5 CHECK (weight >= 1 AND weight <= 10),
    source          SMALLINT NOT NULL DEFAULT 0,
                    -- 0:manual, 1:auto_parse, 2:ota_report, 3:diagnostic_log, 4:aftermarket
    extra           JSONB,
    -- 售后回灌数据
    aftermarket_hits     INT NOT NULL DEFAULT 0,
    aftermarket_alert_threshold INT NOT NULL DEFAULT 10,
    pending_review       BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT dtc_has_target CHECK (
        article_id IS NOT NULL OR lesson_id IS NOT NULL OR fmea_item_id IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_knowledge_dtc_map_code ON knowledge.knowledge_dtc_map(dtc_code);
CREATE INDEX IF NOT EXISTS idx_knowledge_dtc_map_article ON knowledge.knowledge_dtc_map(article_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_dtc_map_lesson ON knowledge.knowledge_dtc_map(lesson_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_dtc_map_fmea ON knowledge.knowledge_dtc_map(fmea_item_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_dtc_map_pending ON knowledge.knowledge_dtc_map(pending_review) WHERE pending_review = true;

-- ============================================================================
-- 9. knowledge_test_map — 五层测试映射
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge.knowledge_test_map (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id      UUID REFERENCES knowledge.kb_articles(id) ON DELETE CASCADE,
    lesson_id       UUID REFERENCES knowledge.lessons(id) ON DELETE CASCADE,
    fmea_item_id    UUID REFERENCES knowledge.fmea_items(id) ON DELETE CASCADE,
    test_layer      SMALLINT NOT NULL,
                    -- 0:HIL, 1:SIL, 2:MIL, 3:PIL, 4:Unit
    test_suite      TEXT NOT NULL,
    test_case_id    TEXT NOT NULL,
    test_status     SMALLINT NOT NULL DEFAULT 0,
                    -- 0:not_run, 1:pass, 2:fail, 3:blocked, 4:not_applicable
    last_run_at     TIMESTAMPTZ,
    evidence_id     TEXT,
    extra           JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT test_has_target CHECK (
        article_id IS NOT NULL OR lesson_id IS NOT NULL OR fmea_item_id IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_knowledge_test_map_layer ON knowledge.knowledge_test_map(test_layer);
CREATE INDEX IF NOT EXISTS idx_knowledge_test_map_suite ON knowledge.knowledge_test_map(test_suite);
CREATE INDEX IF NOT EXISTS idx_knowledge_test_map_case ON knowledge.knowledge_test_map(test_case_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_test_map_status ON knowledge.knowledge_test_map(test_status);

-- ============================================================================
-- 10. knowledge_code_paths — 代码路径反向索引
-- ============================================================================
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

CREATE INDEX IF NOT EXISTS idx_code_paths_repo_file ON knowledge.knowledge_code_paths(repo, file_path);
CREATE INDEX IF NOT EXISTS idx_code_paths_article ON knowledge.knowledge_code_paths(article_id);

-- ============================================================================
-- 11. lessons — Lessons Learned 主表
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge.lessons (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 来源：0:manual, 1:auto_bug, 2:ci_failure, 3:ota_incident,
    --       4:customer_complaint, 5:fmea_derived, 6:audit_finding, 7:aftermarket
    source          SMALLINT NOT NULL DEFAULT 0,
    source_ref      TEXT NOT NULL DEFAULT '',

    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',

    -- 5 级严重度：0:info, 1:minor, 2:major, 3:critical, 4:catastrophic
    severity        SMALLINT NOT NULL DEFAULT 0 CHECK (severity >= 0 AND severity <= 4),

    -- 8 状态生命周期：0:open, 1:investigating, 2:action_planned, 3:implemented,
    --              4:mitigated, 5:verified, 6:closed, 7:rejected
    status          SMALLINT NOT NULL DEFAULT 0 CHECK (status >= 0 AND status <= 7),

    -- 分类：0:design, 1:coding, 2:test, 3:process, 4:requirement,
    --       5:integration, 6:hw, 7:other
    category        SMALLINT NOT NULL DEFAULT 0,

    -- ASIL 等级：0:QM, 1:ASIL_A, 2:ASIL_B, 3:ASIL_C, 4:ASIL_D
    safety_level    SMALLINT NOT NULL DEFAULT 0 CHECK (safety_level >= 0 AND safety_level <= 4),

    -- 关联 KB 条目
    article_id      UUID REFERENCES knowledge.kb_articles(id),

    -- OTA 绑定
    ota_version     TEXT,
    ota_fix_version TEXT,

    root_cause      TEXT NOT NULL DEFAULT '',
    resolution      TEXT NOT NULL DEFAULT '',

    applied_to      TEXT[] NOT NULL DEFAULT '{}',

    author_id       TEXT NOT NULL,
    assignee_id     TEXT,

    -- 置信度 0–100
    confidence      SMALLINT NOT NULL DEFAULT 80 CHECK (confidence >= 0 AND confidence <= 100),

    -- DTC 关联
    dtc_codes       TEXT[] NOT NULL DEFAULT '{}',

    -- DTC 售后回灌标记
    aftermarket_hits     INT NOT NULL DEFAULT 0,
    pending_review       BOOLEAN NOT NULL DEFAULT false,

    -- 闭环节点记录（JSONB 数组）
    -- [{ "from_status": 0, "to_status": 1, "at": "...", "by": "...", "method": "test", "description": "..." }]
    closure_journal JSONB NOT NULL DEFAULT '[]'::jsonb,

    sign_off_id     TEXT,  -- ASIL 闭合的第三方签字人

    closed_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lessons_source ON knowledge.lessons(source);
CREATE INDEX IF NOT EXISTS idx_lessons_severity ON knowledge.lessons(severity);
CREATE INDEX IF NOT EXISTS idx_lessons_status ON knowledge.lessons(status);
CREATE INDEX IF NOT EXISTS idx_lessons_category ON knowledge.lessons(category);
CREATE INDEX IF NOT EXISTS idx_lessons_article ON knowledge.lessons(article_id);
CREATE INDEX IF NOT EXISTS idx_lessons_pending ON knowledge.lessons(pending_review) WHERE pending_review = true;
CREATE INDEX IF NOT EXISTS idx_lessons_dtc ON knowledge.lessons USING GIN(dtc_codes);

-- ============================================================================
-- 12. lesson_actions — 纠正行动计划
-- ============================================================================
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
    evidence_id     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lesson_actions_lesson ON knowledge.lesson_actions(lesson_id);
CREATE INDEX IF NOT EXISTS idx_lesson_actions_status ON knowledge.lesson_actions(status);

-- ============================================================================
-- 13. lesson_test_seeds — 从 LL 反哺测试种子
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge.lesson_test_seeds (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lesson_id       UUID NOT NULL REFERENCES knowledge.lessons(id) ON DELETE CASCADE,
    test_layer      SMALLINT NOT NULL,
                    -- 0:HIL, 1:SIL, 2:MIL, 3:PIL, 4:Unit
    test_type       SMALLINT NOT NULL DEFAULT 0,
                    -- 0:regression, 1:boundary, 2:negative, 3:stress, 4:compatibility
    scenario_desc   TEXT NOT NULL,
    suggested_code  TEXT NOT NULL DEFAULT '',
    ci_artifact     TEXT,
    status          SMALLINT NOT NULL DEFAULT 0,
                    -- 0:proposed, 1:approved, 2:implemented, 3:merged, 4:deprecated
    auto_generated  BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_by     TEXT,
    rejected_by     TEXT,
    reject_reason   TEXT,
    merged_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_lesson_test_seeds_lesson ON knowledge.lesson_test_seeds(lesson_id);

-- ============================================================================
-- 14. fmea_entries — FMEA 主记录
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge.fmea_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',

    -- 作用域：0:design (DFMEA), 1:process (PFMEA)
    fmea_scope      SMALLINT NOT NULL DEFAULT 0,

    system          TEXT NOT NULL,
    subsystem       TEXT NOT NULL DEFAULT '',

    -- 范围：0:single_ecu, 1:cross_ecu, 2:system_level
    scope           SMALLINT NOT NULL DEFAULT 0,

    -- 版本
    fmea_version    TEXT NOT NULL DEFAULT '0.1.0',

    -- ASIL 等级（强制字段）
    safety_level    SMALLINT NOT NULL DEFAULT 0 CHECK (safety_level >= 0 AND safety_level <= 4),

    -- 关联 KB 条目（可选）
    article_id      UUID REFERENCES knowledge.kb_articles(id),

    -- 派生（FMEA-09）
    parent_entry_id UUID REFERENCES knowledge.fmea_entries(id),

    -- 元数据
    creator_id      TEXT NOT NULL,
    reviewer_id     TEXT,

    -- 生命周期：0:draft, 1:review, 2:approved, 3:superseded
    status          SMALLINT NOT NULL DEFAULT 0 CHECK (status >= 0 AND status <= 3),

    -- 源文件（FMEA as Code YAML）
    source_yaml     TEXT NOT NULL DEFAULT '',
    source_hash     TEXT NOT NULL DEFAULT '',

    -- PFMEA 额外字段（PK-02）
    process_step       TEXT NOT NULL DEFAULT '',
    process_parameter  TEXT NOT NULL DEFAULT '',
    process_machine    TEXT NOT NULL DEFAULT '',
    station_id         TEXT NOT NULL DEFAULT '',
    material_id        TEXT NOT NULL DEFAULT '',

    -- 时间
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fmea_entries_system ON knowledge.fmea_entries(system);
CREATE INDEX IF NOT EXISTS idx_fmea_entries_scope ON knowledge.fmea_entries(scope);
CREATE INDEX IF NOT EXISTS idx_fmea_entries_status ON knowledge.fmea_entries(status);
CREATE INDEX IF NOT EXISTS idx_fmea_entries_parent ON knowledge.fmea_entries(parent_entry_id);

-- ============================================================================
-- 15. fmea_items — FMEA 条目（失效模式明细）
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge.fmea_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fmea_entry_id   UUID NOT NULL REFERENCES knowledge.fmea_entries(id) ON DELETE CASCADE,
    item_index      INT NOT NULL,

    -- AUTOSAR 层级（位掩码）
    autosar_layer   SMALLINT NOT NULL DEFAULT 0,

    -- ASIL 等级
    safety_level    SMALLINT NOT NULL DEFAULT 0 CHECK (safety_level >= 0 AND safety_level <= 4),

    -- 三域
    function_desc   TEXT NOT NULL,
    component       TEXT NOT NULL,
    layer           TEXT NOT NULL DEFAULT '',

    -- 失效模式
    failure_mode    TEXT NOT NULL,
    failure_effect  TEXT NOT NULL,
    failure_cause   TEXT NOT NULL,
    failure_mechanism TEXT NOT NULL DEFAULT '',

    -- 三域 RPN（原始）
    severity        SMALLINT NOT NULL CHECK (severity >= 1 AND severity <= 10),
    occurrence      SMALLINT NOT NULL CHECK (occurrence >= 1 AND occurrence <= 10),
    detection       SMALLINT NOT NULL CHECK (detection >= 1 AND detection <= 10),
    rpn             INT NOT NULL GENERATED ALWAYS AS (severity * occurrence * detection) STORED,

    -- AIAG-VDA Action Priority
    ap_severity     SMALLINT CHECK (ap_severity >= 1 AND ap_severity <= 10),
    ap_occurrence   SMALLINT CHECK (ap_occurrence >= 1 AND ap_occurrence <= 10),
    ap_detection    SMALLINT CHECK (ap_detection >= 1 AND ap_detection <= 10),
    ap_priority     CHAR(1)
                    CHECK (ap_priority IS NULL OR ap_priority IN ('H', 'M', 'L')),

    -- 当前控制
    current_control TEXT NOT NULL DEFAULT '',
    control_type    SMALLINT NOT NULL DEFAULT 0,  -- 0:preventive, 1:detective

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

    -- 置信度 0–100
    confidence      SMALLINT NOT NULL DEFAULT 100 CHECK (confidence >= 0 AND confidence <= 100),

    -- 6 状态生命周期：0:open, 1:analysis, 2:action_planned, 3:action_done, 4:verified, 5:closed
    status          SMALLINT NOT NULL DEFAULT 0 CHECK (status >= 0 AND status <= 5),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fmea_items_entry ON knowledge.fmea_items(fmea_entry_id, item_index);
CREATE INDEX IF NOT EXISTS idx_fmea_items_rpn ON knowledge.fmea_items(rpn DESC);
CREATE INDEX IF NOT EXISTS idx_fmea_items_status ON knowledge.fmea_items(status);
CREATE INDEX IF NOT EXISTS idx_fmea_items_dtc ON knowledge.fmea_items USING GIN(dtc_codes);
CREATE INDEX IF NOT EXISTS idx_fmea_items_ap ON knowledge.fmea_items(ap_priority);

-- ============================================================================
-- 16. fmea_actions — FMEA 纠正措施
-- ============================================================================
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

CREATE INDEX IF NOT EXISTS idx_fmea_actions_item ON knowledge.fmea_actions(fmea_item_id);
CREATE INDEX IF NOT EXISTS idx_fmea_actions_status ON knowledge.fmea_actions(status);

-- ============================================================================
-- 17. fmea_item_cross_ecu — 跨 ECU 失效链
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge.fmea_item_cross_ecu (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_item_id  UUID NOT NULL REFERENCES knowledge.fmea_items(id) ON DELETE CASCADE,
    target_item_id  UUID NOT NULL REFERENCES knowledge.fmea_items(id) ON DELETE CASCADE,
    relation_type   SMALLINT NOT NULL DEFAULT 0,
                    -- 0:cascade, 1:shared_cause, 2:redundancy, 3:feedback
    propagation_desc TEXT NOT NULL DEFAULT '',
    propagation_delay TEXT,
    source_ecu_id   TEXT NOT NULL DEFAULT '',
    target_ecu_id   TEXT NOT NULL DEFAULT '',
    signal_name     TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT cross_ecu_diff_items CHECK (source_item_id != target_item_id)
);

CREATE INDEX IF NOT EXISTS idx_fmea_cross_ecu_source ON knowledge.fmea_item_cross_ecu(source_item_id);
CREATE INDEX IF NOT EXISTS idx_fmea_cross_ecu_target ON knowledge.fmea_item_cross_ecu(target_item_id);

-- ============================================================================
-- 18. knowledge_confidence_snapshots — 置信度衰减快照
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge.knowledge_confidence_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     SMALLINT NOT NULL,
                    -- 0:kb_article, 1:lesson, 2:fmea_item
    entity_id       UUID NOT NULL,
    old_confidence  SMALLINT,
    new_confidence  SMALLINT NOT NULL,
    decay_reason    TEXT NOT NULL DEFAULT '',
                    -- "time_decay", "usage_decay", "ota_update", "hw_change",
                    -- "test_failure", "review_outdated", "manual_reassess",
                    -- "code_path_change", "confidence_reset"
    auto_flag       BOOLEAN NOT NULL DEFAULT true,
    operator_id     TEXT,
    snapshot_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_confidence_snaps_entity
    ON knowledge.knowledge_confidence_snapshots(entity_type, entity_id, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_confidence_snaps_time
    ON knowledge.knowledge_confidence_snapshots(snapshot_at DESC);

-- ============================================================================
-- Migration tracking
-- ============================================================================
INSERT INTO _meta (key, value)
VALUES ('knowledge_migration_version', '1')
ON CONFLICT (key) DO UPDATE SET value = '1';

COMMIT;
