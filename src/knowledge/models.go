// Package knowledge 定义 yuleOSH 知识管理模块（KB + LL + FMEA）的核心数据模型。
//
// 数据源: spec-knowledge-management.md v1.1.0 + tech-knowledge-management.md v1.2
// 所有枚举值采用 uint8 编码以保持 DDL SMALLINT 兼容。
package knowledge

import (
	"time"

	"github.com/google/uuid"
)

// ============================================================================
// 枚举类型
// ============================================================================

// KBStatus 知识条目的 6 状态生命周期（Spec KBS-03 / KB-13）
type KBStatus uint8

const (
	KBStatusDraft         KBStatus = iota // 0 — 草稿
	KBStatusReviewPending                 // 1 — 待审核
	KBStatusApproved                      // 2 — 已批准
	KBStatusPublished                     // 3 — 已发布
	KBStatusDeprecated                    // 4 — 已废弃
	KBStatusArchived                      // 5 — 已归档
)

// SafetyLevel 安全等级（Spec 行业约束 #1）
type SafetyLevel uint8

const (
	SafetyLevelQM    SafetyLevel = iota // 0 — QM
	SafetyLevelASIL_A                   // 1
	SafetyLevelASIL_B                   // 2
	SafetyLevelASIL_C                   // 3
	SafetyLevelASIL_D                   // 4
)

// AUTOSARLayer 位掩码，支持多选（Spec KB-11）
type AUTOSARLayer uint8

const (
	AUTOSARLayerASW AUTOSARLayer = 1 << iota // bit 0
	AUTOSARLayerRTE                          // bit 1
	AUTOSARLayerBSW                          // bit 2
	AUTOSARLayerHW                           // bit 3
)

// LLClosureStatus LL 条目 8 状态生命周期（Spec LL-07）
type LLClosureStatus uint8

const (
	LLStatusOpen            LLClosureStatus = iota // 0 — 打开
	LLStatusInvestigating                          // 1 — 调查中
	LLStatusActionPlanned                          // 2 — 已计划行动
	LLStatusImplemented                            // 3 — 已实施
	LLStatusMitigated                              // 4 — 已缓解
	LLStatusVerified                               // 5 — 已验证
	LLStatusClosed                                 // 6 — 已关闭
	LLStatusRejected                               // 7 — 已驳回
)

// LLSeverity LL 严重度 5 级（Spec LL-01）
type LLSeverity uint8

const (
	LLSeverityInfo        LLSeverity = iota // 0
	LLSeverityMinor                         // 1
	LLSeverityMajor                         // 2
	LLSeverityCritical                      // 3
	LLSeverityCatastrophic                  // 4
)

// LLCategory LL 类别（Spec LL-01）
type LLCategory uint8

const (
	LLCategoryDesign      LLCategory = iota // 0
	LLCategoryCoding                        // 1
	LLCategoryTest                          // 2
	LLCategoryProcess                       // 3
	LLCategoryRequirement                   // 4
	LLCategoryIntegration                   // 5
	LLCategoryHW                            // 6
	LLCategoryOther                         // 7
)

// FMEAScope FMEA 范围（Spec FMEA-01, PK-01）
type FMEAScope uint8

const (
	FMEAScopeSingleECU FMEAScope = iota // 0 — single_ecu
	FMEAScopeCrossECU                    // 1 — cross_ecu
	FMEAScopeSystemLevel                // 2 — system_level
)

// FMEAItemStatus FMEA 条目 6 状态生命周期（Spec FMEA-01）
type FMEAItemStatus uint8

const (
	FMEAItemStatusOpen         FMEAItemStatus = iota // 0
	FMEAItemStatusAnalysis                           // 1
	FMEAItemStatusActionPlanned                      // 2
	FMEAItemStatusActionDone                         // 3
	FMEAItemStatusVerified                           // 4
	FMEAItemStatusClosed                             // 5
)

// FMEAEntryStatus FMEA 主记录状态（Tech §2.2.12）
type FMEAEntryStatus uint8

const (
	FMEAEntryStatusDraft     FMEAEntryStatus = iota // 0
	FMEAEntryStatusReview                           // 1
	FMEAEntryStatusApproved                         // 2
	FMEAEntryStatusSuperseded                       // 3
)

// FMEAActionPriority AIAG-VDA Action Priority 等级（Spec FMEA-05）
type FMEAActionPriority uint8

const (
	FMEAActionPriorityH FMEAActionPriority = iota + 1 // 1 — 高优先
	FMEAActionPriorityM                                // 2 — 中优先
	FMEAActionPriorityL                                // 3 — 低优先
)

// APPriority 简写映射
const (
	APPriorityH = "H"
	APPriorityM = "M"
	APPriorityL = "L"
)

// ControlType PFMEA 控制类型（Spec PK-05）
type ControlType uint8

const (
	ControlTypePreventive ControlType = iota // 0
	ControlTypeDetective                     // 1
)

// TestLayer 五层测试层级（Spec KB-10）
type TestLayer uint8

const (
	TestLayerHIL  TestLayer = iota // 0
	TestLayerSIL                   // 1
	TestLayerMIL                   // 2
	TestLayerPIL                   // 3
	TestLayerUnit                  // 4
)

// TestStatus 测试执行状态
type TestStatus uint8

const (
	TestStatusNotRun     TestStatus = iota // 0
	TestStatusPass                         // 1
	TestStatusFail                         // 2
	TestStatusBlocked                      // 3
	TestStatusNotApplicable                // 4
)

// LLSources LL 来源（Tech §2.2.9）
type LLSource uint8

const (
	LLSourceManual             LLSource = iota // 0
	LLSourceAutoBug                            // 1
	LLSourceCIFailure                          // 2
	LLSourceOTAIncident                        // 3
	LLSourceCustomerComplaint                  // 4
	LLSourceFMEADerived                        // 5
	LLSourceAuditFinding                       // 6
)

// LinkType 安全目标关联类型（Spec KBS-16）
type LinkType uint8

const (
	LinkTypeDerivedFrom   LinkType = iota // 0 — derived_from
	LinkTypeContributesTo                 // 1 — contributes_to
	LinkTypeVerifies                      // 2 — verifies
	LinkTypeConstrains                    // 3 — constrains
)

// ============================================================================
// 值对象
// ============================================================================

// HWBomEntry 硬件 BOM 标签（Spec KBS-03 / KB-05）
type HWBomEntry struct {
	Platform string `json:"platform" db:"platform"`   // 平台名，如 "TDA4VM"
	Chip     string `json:"chip" db:"chip"`           // 芯片型号，如 "TDA4VM-Q1"
	Version  string `json:"version,omitempty" db:"version"` // 硬件版本，可选
	Variant  string `json:"variant,omitempty" db:"variant"` // 硬件变体，可选
	Location string `json:"location,omitempty" db:"location"` // 安装位置，可选
	Supplier string `json:"supplier,omitempty" db:"supplier"` // 供应商，可选
}

// OTABinding OTA 版本绑定（Spec KBS-03 / KB-09）
type OTABinding struct {
	MinOTA   string `json:"min_ota,omitempty" db:"min_ota"`
	MaxOTA   string `json:"max_ota,omitempty" db:"max_ota"`
	Affected bool   `json:"affected" db:"affected"`
}

// CodePathEntry 代码路径反向索引（Spec KB-04）
type CodePathEntry struct {
	Repo     string `json:"repo" db:"repo"`         // 仓库名
	Path     string `json:"path" db:"path"`         // 相对项目根路径
	Line     int    `json:"line,omitempty" db:"line"` // 行号，可选
	Language string `json:"language,omitempty" db:"language"`
}

// SafetyGoalLink 安全目标关联（Spec KBS-16）
type SafetyGoalLink struct {
	SafetyGoalID    string   `json:"safety_goal_id" db:"safety_goal_id"`
	SafetyGoalTitle string   `json:"safety_goal_title" db:"safety_goal_title"`
	SafetyGoalDesc  string   `json:"safety_goal_desc,omitempty" db:"safety_goal_desc"`
	HARARef         string   `json:"hara_ref,omitempty" db:"hara_ref"`
	HazardID        string   `json:"hazard_id,omitempty" db:"hazard_id"`
	LinkType        LinkType `json:"link_type" db:"link_type"`
	ASILDecomp      string   `json:"asil_decomposition,omitempty" db:"asil_decomposition"`
}

// TCLDocSlot TCL 工具认证预留字段（Spec CROSS-01）
type TCLDocSlot struct {
	TCLToolID        string `json:"tcl_tool_id" db:"tcl_tool_id"`
	CertDocRefs      string `json:"cert_doc_refs" db:"cert_doc_refs"`
	AssessmentStatus string `json:"assessment_status" db:"assessment_status"`
}

// SourceRef LL 来源引用（Spec LL-01）
type SourceRef struct {
	EntityType string `json:"entity_type" db:"entity_type"` // 如 "bug", "fmea", "code_review"
	EntityID   string `json:"entity_id" db:"entity_id"`
}

// CrossECULink 跨 ECU 失效链节点（Spec FMEA-03）
type CrossECULink struct {
	ECUID              string `json:"ecu_id" db:"ecu_id"`
	SignalName         string `json:"signal_name" db:"signal_name"`
	FailureMode        string `json:"failure_mode" db:"failure_mode"`
	PropagationDir     string `json:"propagation_direction" db:"propagation_direction"` // source / forward / backward / merge
	RelationType       uint8  `json:"relation_type,omitempty" db:"relation_type"`
	PropagationDesc    string `json:"propagation_desc,omitempty" db:"propagation_desc"`
	PropagationDelay   string `json:"propagation_delay,omitempty" db:"propagation_delay"`
}

// KnowledgeTag 标签定义（Tech §2.2.4）
type KnowledgeTag struct {
	ID          uuid.UUID `json:"id" db:"id"`
	Name        string    `json:"name" db:"name"`
	Category    uint8     `json:"category" db:"category"` // 0:general,1:asil,2:autosar,3:ecu,4:dtc,5:test,6:ota
	Color       string    `json:"color" db:"color"`
	Description string    `json:"description" db:"description"`
	CreatedAt   time.Time `json:"created_at" db:"created_at"`
}

// ============================================================================
// 核心实体 —— KB 模块
// ============================================================================

// KbArticle 知识条目主表（Spec KBS-01 ~ KBS-16）
type KbArticle struct {
	ID                   uuid.UUID         `json:"id" db:"id"`
	Title                string            `json:"title" db:"title"`                                   // ≤200 字符
	Summary              string            `json:"summary" db:"summary"`
	Content              string            `json:"content" db:"content"`                               // Markdown 正文
	BodyFormat           uint8             `json:"body_format" db:"body_format"`                       // 0:markdown, 1:html
	Status               KBStatus          `json:"status" db:"status"`                                 // 6 状态
	ASIL                 SafetyLevel       `json:"safety_level" db:"asil"`                             // 对应 Spec safety_level
	AUTOSARLayer         AUTOSARLayer      `json:"autosar_layer" db:"autosar_layer"`                   // 位掩码
	HWBom                []HWBomEntry      `json:"hw_bom" db:"hw_bom"`                                 // JSONB
	OTABinding           *OTABinding       `json:"ota_binding,omitempty" db:"ota_binding"`             // JSONB 可选
	DTCCodes             []string          `json:"dtc_codes" db:"dtc_codes"`                           // TEXT[]
	CodePaths            []CodePathEntry   `json:"code_paths" db:"code_paths"`                         // JSONB
	AuthorID             string            `json:"author_id" db:"author_id"`
	ReviewerID           string            `json:"reviewer_id,omitempty" db:"reviewer_id"`
	Tags                 []string          `json:"tags" db:"tags"`                                     // TEXT[]
	Confidence           uint8             `json:"confidence" db:"confidence"`                         // 0–100 SMALLINT
	ConfidenceDecayPolicy string           `json:"confidence_decay_policy,omitempty" db:"confidence_decay_policy"` // "usage_based"
	CurrentVersion       int               `json:"current_version" db:"current_version"`
	LatestVersionID      *uuid.UUID        `json:"latest_version_id,omitempty" db:"latest_version_id"`
	CodePathStale        bool              `json:"code_path_stale" db:"code_path_stale"`
	IsDeleted            bool              `json:"is_deleted" db:"is_deleted"`
	DeletedAt            *time.Time        `json:"deleted_at,omitempty" db:"deleted_at"`
	TCLDocSlot           *TCLDocSlot       `json:"tcl_doc_slot,omitempty" db:"tcl_doc_slot"`           // JSONB 可选，预留
	SafetyGoals          []SafetyGoalLink  `json:"safety_goals,omitempty" db:"safety_goals"`           // JSONB 可选（KBS-16）
	CreatedAt            time.Time         `json:"created_at" db:"created_at"`
	UpdatedAt            time.Time         `json:"updated_at" db:"updated_at"`
}

// KbVersion 版本快照（Spec KB-03）
type KbVersion struct {
	ID                uuid.UUID     `json:"id" db:"id"`
	ArticleID         uuid.UUID     `json:"article_id" db:"article_id"`
	Version           int           `json:"version" db:"version"`
	Title             string        `json:"title" db:"title"`
	Summary           string        `json:"summary" db:"summary"`
	Content           string        `json:"content" db:"content"`
	BodyFormat        uint8         `json:"body_format" db:"body_format"`
	ASIL              SafetyLevel   `json:"safety_level" db:"asil"`
	AUTOSARLayer      AUTOSARLayer  `json:"autosar_layer" db:"autosar_layer"`
	HWBom             []HWBomEntry  `json:"hw_bom" db:"hw_bom"`
	OTABinding        *OTABinding   `json:"ota_binding,omitempty" db:"ota_binding"`
	DTCCodes          []string      `json:"dtc_codes" db:"dtc_codes"`
	CodePaths         []CodePathEntry `json:"code_paths" db:"code_paths"`
	Tags              []string      `json:"tags" db:"tags"`
	ChangeSummary     string        `json:"change_summary,omitempty" db:"change_summary"` // 变更原因
	ChangedBy         string        `json:"changed_by" db:"changed_by"`
	Confidence        uint8         `json:"confidence" db:"confidence"`
	CreatedAt         time.Time     `json:"created_at" db:"created_at"`
}

// KbVersionAuditLog 版本审批审计（Tech §2.2.3）
type KbVersionAuditLog struct {
	ID         uuid.UUID  `json:"id" db:"id"`
	VersionID  uuid.UUID  `json:"version_id" db:"version_id"`
	ArticleID  uuid.UUID  `json:"article_id" db:"article_id"`
	Action     uint8      `json:"action" db:"action"` // 1:submit_review,2:approve,3:reject,4:rollback,5:force_publish
	OperatorID string     `json:"operator_id" db:"operator_id"`
	Comment    string     `json:"comment" db:"comment"`
	OldStatus  *KBStatus  `json:"old_status,omitempty" db:"old_status"`
	NewStatus  *KBStatus  `json:"new_status,omitempty" db:"new_status"`
	CreatedAt  time.Time  `json:"created_at" db:"created_at"`
}

// KbArticleTag 知识-标签多对多关联
type KbArticleTag struct {
	ArticleID uuid.UUID `json:"article_id" db:"article_id"`
	TagID     uuid.UUID `json:"tag_id" db:"tag_id"`
}

// KnowledgeDTCMap DTC 关联表（Spec KB-06）
type KnowledgeDTCMap struct {
	ID             uuid.UUID  `json:"id" db:"id"`
	DTCCode        string     `json:"dtc_code" db:"dtc_code"`
	DTCDescription string     `json:"dtc_description" db:"dtc_description"`
	ArticleID      *uuid.UUID `json:"article_id,omitempty" db:"article_id"`
	LessonID       *uuid.UUID `json:"lesson_id,omitempty" db:"lesson_id"`
	FMEAItemID     *uuid.UUID `json:"fmea_item_id,omitempty" db:"fmea_item_id"`
	Weight         uint8      `json:"weight" db:"weight"`       // 1–10
	Source         uint8      `json:"source" db:"source"`       // 0:manual,1:auto_parse,2:ota_report,3:diagnostic_log
	Extra          string     `json:"extra,omitempty" db:"extra"`
	CreatedAt      time.Time  `json:"created_at" db:"created_at"`
}

// KnowledgeTestMap 五层测试映射（Spec KB-10）
type KnowledgeTestMap struct {
	ID          uuid.UUID  `json:"id" db:"id"`
	ArticleID   *uuid.UUID `json:"article_id,omitempty" db:"article_id"`
	LessonID    *uuid.UUID `json:"lesson_id,omitempty" db:"lesson_id"`
	FMEAItemID  *uuid.UUID `json:"fmea_item_id,omitempty" db:"fmea_item_id"`
	TestLayer   TestLayer  `json:"test_layer" db:"test_layer"`
	TestSuite   string     `json:"test_suite" db:"test_suite"`
	TestCaseID  string     `json:"test_case_id" db:"test_case_id"`
	TestStatus  TestStatus `json:"test_status" db:"test_status"`
	LastRunAt   *time.Time `json:"last_run_at,omitempty" db:"last_run_at"`
	EvidenceID  string     `json:"evidence_id,omitempty" db:"evidence_id"`
	Extra       string     `json:"extra,omitempty" db:"extra"`
	CreatedAt   time.Time  `json:"created_at" db:"created_at"`
}

// KnowledgeCodePath 代码路径反向索引（Tech §2.2.8）
type KnowledgeCodePath struct {
	ID             uuid.UUID  `json:"id" db:"id"`
	ArticleID      uuid.UUID  `json:"article_id" db:"article_id"`
	Repo           string     `json:"repo" db:"repo"`
	FilePath       string     `json:"file_path" db:"file_path"`
	LineStart      *int       `json:"line_start,omitempty" db:"line_start"`
	LineEnd        *int       `json:"line_end,omitempty" db:"line_end"`
	Language       string     `json:"language,omitempty" db:"language"`
	LastVerifiedAt *time.Time `json:"last_verified_at,omitempty" db:"last_verified_at"`
	CreatedAt      time.Time  `json:"created_at" db:"created_at"`
}

// ============================================================================
// 核心实体 —— LL 模块
// ============================================================================

// Lesson Lessons Learned 条目（Spec LL-01 ~ LL-08）
type Lesson struct {
	ID                  uuid.UUID       `json:"id" db:"id"`
	Source              LLSource        `json:"source" db:"source"`
	SourceRef           string          `json:"source_ref" db:"source_ref"` // 外部引用
	Title               string          `json:"title" db:"title"`
	Description         string          `json:"description" db:"description"`
	RootCause           string          `json:"root_cause" db:"root_cause"`
	Resolution          string          `json:"resolution,omitempty" db:"resolution"`
	Severity            LLSeverity      `json:"severity" db:"severity"`                         // 5 级
	Status              LLClosureStatus `json:"closure_status" db:"status"`                     // 8 状态
	Category            LLCategory      `json:"category" db:"category"`
	SafetyLevel         SafetyLevel     `json:"safety_level" db:"safety_level"`                 // 强制字段
	ArticleID           *uuid.UUID      `json:"article_id,omitempty" db:"article_id"`           // 关联 KB 条目
	OTAVersion          string          `json:"ota_version,omitempty" db:"ota_version"`         // 问题出现时 OTA 版本
	OTAFixVersion       string          `json:"ota_fix_version,omitempty" db:"ota_fix_version"` // 修复版本
	AppliedTo           []string        `json:"applied_to,omitempty" db:"applied_to"`           // TEXT[]
	AuthorID            string          `json:"author_id" db:"author_id"`
	AssigneeID          string          `json:"assignee_id,omitempty" db:"assignee_id"`
	Confidence          uint8           `json:"confidence" db:"confidence"`                     // 0–100
	VerifyCount         int             `json:"verify_count" db:"verify_count"`
	ReapplyIntervalDays int             `json:"reapply_interval_days" db:"reapply_interval_days"`
	ClosedAt            *time.Time      `json:"closed_at,omitempty" db:"closed_at"`
	CreatedAt           time.Time       `json:"created_at" db:"created_at"`
	UpdatedAt           time.Time       `json:"updated_at" db:"updated_at"`
}

// LessonAction 纠正行动计划（Tech §2.2.10）
type LessonAction struct {
	ID          uuid.UUID  `json:"id" db:"id"`
	LessonID    uuid.UUID  `json:"lesson_id" db:"lesson_id"`
	ActionType  uint8      `json:"action_type" db:"action_type"` // 0:code_change,1:test_add,2:process_change,3:doc_update,4:training,5:design_review
	Description string     `json:"description" db:"description"`
	AssigneeID  string     `json:"assignee_id" db:"assignee_id"`
	Status      uint8      `json:"status" db:"status"` // 0:todo,1:in_progress,2:done,3:cancelled
	DueAt       *time.Time `json:"due_at,omitempty" db:"due_at"`
	EvidenceID  string     `json:"evidence_id,omitempty" db:"evidence_id"`
	CreatedAt   time.Time  `json:"created_at" db:"created_at"`
	UpdatedAt   time.Time  `json:"updated_at" db:"updated_at"`
}

// LessonTestSeed LL → Test Seed（Spec LL-04）
type LessonTestSeed struct {
	ID           uuid.UUID  `json:"id" db:"id"`
	LessonID     uuid.UUID  `json:"lesson_id" db:"lesson_id"`
	TestLayer    TestLayer  `json:"test_layer" db:"test_layer"`
	TestType     uint8      `json:"test_type" db:"test_type"` // 0:regression,1:boundary,2:negative,3:stress,4:compatibility
	ScenarioDesc string     `json:"scenario_desc" db:"scenario_desc"`
	SuggestedCode string    `json:"suggested_code,omitempty" db:"suggested_code"`
	CIArtifact   string     `json:"ci_artifact,omitempty" db:"ci_artifact"`
	Status       uint8      `json:"status" db:"status"` // 0:proposed,1:approved,2:implemented,3:merged,4:deprecated
	CreatedAt    time.Time  `json:"created_at" db:"created_at"`
	ApprovedBy   string     `json:"approved_by,omitempty" db:"approved_by"`
	MergedAt     *time.Time `json:"merged_at,omitempty" db:"merged_at"`
}

// LLAuditLog LL 审计日志（CROSS-04）
type LLAuditLog struct {
	ID            uuid.UUID      `json:"id" db:"id"`
	LessonID      uuid.UUID      `json:"lesson_id" db:"lesson_id"`
	Action        uint8          `json:"action" db:"action"` // 1:created,2:status_change,…
	OperatorID    string         `json:"operator_id" db:"operator_id"`
	Comment       string         `json:"comment" db:"comment"`
	OldStatus     *LLClosureStatus `json:"old_status,omitempty" db:"old_status"`
	NewStatus     *LLClosureStatus `json:"new_status,omitempty" db:"new_status"`
	OldSeverity   *LLSeverity    `json:"old_severity,omitempty" db:"old_severity"`
	NewSeverity   *LLSeverity    `json:"new_severity,omitempty" db:"new_severity"`
	OldConfidence *uint8         `json:"old_confidence,omitempty" db:"old_confidence"`
	NewConfidence *uint8         `json:"new_confidence,omitempty" db:"new_confidence"`
	CreatedAt     time.Time      `json:"created_at" db:"created_at"`
}

// LessonOTABinding LL OTA 绑定
type LessonOTABinding struct {
	ID       uuid.UUID `json:"id" db:"id"`
	LessonID uuid.UUID `json:"lesson_id" db:"lesson_id"`
	OTAVersion string  `json:"ota_version" db:"ota_version"`
}

// ============================================================================
// 核心实体 —— FMEA 模块
// ============================================================================

// FMEAEntry FMEA 主记录（Spec FMEA-01, PK-01）
type FMEAEntry struct {
	ID          uuid.UUID       `json:"id" db:"id"`
	Name        string          `json:"name" db:"name"`
	Description string          `json:"description" db:"description"`
	System      string          `json:"system" db:"system"`
	Subsystem   string          `json:"subsystem,omitempty" db:"subsystem"`
	Scope       FMEAScope       `json:"scope" db:"scope"`            // single_ecu / cross_ecu / system_level
	FMEAVersion string          `json:"fmea_version" db:"fmea_version"`
	SafetyLevel SafetyLevel     `json:"safety_level" db:"safety_level"` // 强制字段
	ArticleID   *uuid.UUID      `json:"article_id,omitempty" db:"article_id"`
	CreatorID   string          `json:"creator_id" db:"creator_id"`
	ReviewerID  string          `json:"reviewer_id,omitempty" db:"reviewer_id"`
	Status      FMEAEntryStatus `json:"status" db:"status"` // draft/review/approved/superseded
	SourceYAML  string          `json:"source_yaml,omitempty" db:"source_yaml"`
	SourceHash  string          `json:"source_hash,omitempty" db:"source_hash"`
	CreatedAt   time.Time       `json:"created_at" db:"created_at"`
	UpdatedAt   time.Time       `json:"updated_at" db:"updated_at"`
}

// FMEAItem FMEA 条目（失效模式明细）（Spec FMEA-01, PK-02）
type FMEAItem struct {
	ID                uuid.UUID         `json:"id" db:"id"`
	FMEAEntryID       uuid.UUID         `json:"fmea_entry_id" db:"fmea_entry_id"`
	ItemIndex         int               `json:"item_index" db:"item_index"`
	AUTOSARLayer      AUTOSARLayer      `json:"autosar_layer" db:"autosar_layer"`
	SafetyLevel       SafetyLevel       `json:"safety_level" db:"safety_level"`           // 强制字段
	FunctionDesc      string            `json:"function_desc" db:"function_desc"`         // 功能描述
	Component         string            `json:"component" db:"component"`                 // 组件/模块名
	Layer             string            `json:"layer,omitempty" db:"layer"`               // 层次细分
	FailureMode       string            `json:"failure_mode" db:"failure_mode"`           // 失效模式
	FailureEffect     string            `json:"failure_effect" db:"failure_effect"`       // 失效影响
	FailureCause      string            `json:"failure_cause" db:"failure_cause"`         // 失效原因
	FailureMechanism  string            `json:"failure_mechanism,omitempty" db:"failure_mechanism"`
	Severity          uint8             `json:"rpn_severity" db:"severity"`               // 1–10
	Occurrence        uint8             `json:"rpn_occurrence" db:"occurrence"`           // 1–10
	Detection         uint8             `json:"rpn_detection" db:"detection"`             // 1–10
	RPN               int               `json:"rpn_total" db:"rpn"`                       // severity × occurrence × detection, GENERATED ALWAYS
	CurrentControl    string            `json:"current_control" db:"current_control"`
	ControlType       *ControlType      `json:"control_type,omitempty" db:"control_type"` // PFMEA（Spec PK-05）
	RecommendedAction string            `json:"recommended_action" db:"recommended_action"`
	PlannedSeverity   *uint8            `json:"planned_severity,omitempty" db:"planned_severity"`
	PlannedOccurrence *uint8            `json:"planned_occurrence,omitempty" db:"planned_occurrence"`
	PlannedDetection  *uint8            `json:"planned_detection,omitempty" db:"planned_detection"`
	PlannedRPN        *int              `json:"planned_rpn,omitempty" db:"planned_rpn"`   // GENERATED ALWAYS
	DTCCodes          []string          `json:"dtc_codes" db:"dtc_codes"`                 // TEXT[]
	EvidenceIDs       []string          `json:"evidence_ids" db:"evidence_ids"`           // TEXT[]
	Confidence        uint8             `json:"confidence" db:"confidence"`               // 0–100
	Status            FMEAItemStatus    `json:"status" db:"status"`                       // 6 状态
	APSeverity        *uint8            `json:"ap_severity,omitempty" db:"ap_severity"`   // AIAG-VDA S: 1–10
	APOccurrence      *uint8            `json:"ap_occurrence,omitempty" db:"ap_occurrence"`
	APDetection       *uint8            `json:"ap_detection,omitempty" db:"ap_detection"`
	APPriority        *FMEAActionPriority `json:"ap_priority,omitempty" db:"ap_priority"` // H/M/L
	FMEAScope         *FMEAScope        `json:"fmea_scope,omitempty" db:"fmea_scope"`     // design / process (PFMEA, PK-01)
	ProcessStep       string            `json:"process_step,omitempty" db:"process_step"` // PFMEA 附加字段（PK-02）
	ProcessParameter  string            `json:"process_parameter,omitempty" db:"process_parameter"`
	ProcessMachine    string            `json:"process_machine,omitempty" db:"process_machine"`
	StationID         string            `json:"station_id,omitempty" db:"station_id"`
	MaterialID        string            `json:"material_id,omitempty" db:"material_id"`
	ParentFMEAItemID  *uuid.UUID        `json:"parent_fmea_item_id,omitempty" db:"parent_fmea_item_id"` // FMEA-09 派生
	CreatedAt         time.Time         `json:"created_at" db:"created_at"`
	UpdatedAt         time.Time         `json:"updated_at" db:"updated_at"`
}

// FMEAAction FMEA 纠正措施（Tech §2.2.14）
type FMEAAction struct {
	ID          uuid.UUID  `json:"id" db:"id"`
	FMEAItemID  uuid.UUID  `json:"fmea_item_id" db:"fmea_item_id"`
	Description string     `json:"description" db:"description"`
	OwnerID     string     `json:"owner_id" db:"owner_id"`
	RPNBefore   int        `json:"rpn_before" db:"rpn_before"`
	RPNAfter    *int       `json:"rpn_after,omitempty" db:"rpn_after"`
	Status      uint8      `json:"status" db:"status"`     // 0:proposed,1:approved,2:in_progress,3:done,4:verified,5:cancelled
	Priority    uint8      `json:"priority" db:"priority"` // 1:low,2:medium,3:high,4:critical
	DueAt       *time.Time `json:"due_at,omitempty" db:"due_at"`
	EvidenceID  string     `json:"evidence_id,omitempty" db:"evidence_id"`
	TestLinkID  *uuid.UUID `json:"test_link_id,omitempty" db:"test_link_id"`
	CreatedAt   time.Time  `json:"created_at" db:"created_at"`
	UpdatedAt   time.Time  `json:"updated_at" db:"updated_at"`
}

// FMEAItemCrossECU 跨 ECU 失效链（Spec FMEA-03 / FMEA-06）
type FMEAItemCrossECU struct {
	ID              uuid.UUID `json:"id" db:"id"`
	SourceItemID    uuid.UUID `json:"source_item_id" db:"source_item_id"`
	TargetItemID    uuid.UUID `json:"target_item_id" db:"target_item_id"`
	RelationType    uint8     `json:"relation_type" db:"relation_type"`       // 0:cascade,1:shared_cause,2:redundancy,3:feedback
	PropagationDesc string    `json:"propagation_desc,omitempty" db:"propagation_desc"`
	PropagationDelay string   `json:"propagation_delay,omitempty" db:"propagation_delay"`
	CreatedAt       time.Time `json:"created_at" db:"created_at"`
}

// FMEAAuditLog FMEA 审计日志（CROSS-04）
type FMEAAuditLog struct {
	ID          uuid.UUID  `json:"id" db:"id"`
	FMEAEntryID *uuid.UUID `json:"fmea_entry_id,omitempty" db:"fmea_entry_id"`
	FMEAItemID  *uuid.UUID `json:"fmea_item_id,omitempty" db:"fmea_item_id"`
	Action      uint8      `json:"action" db:"action"`
	OperatorID  string     `json:"operator_id" db:"operator_id"`
	Comment     string     `json:"comment" db:"comment"`
	DetailJSON  string     `json:"detail_json,omitempty" db:"detail_json"`
	CreatedAt   time.Time  `json:"created_at" db:"created_at"`
}

// ============================================================================
// 置信度模块
// ============================================================================

// ConfidenceSnapshot 置信度衰减快照（Spec KB-07 / KB-08）
type ConfidenceSnapshot struct {
	ID          uuid.UUID `json:"id" db:"id"`
	EntityType  uint8     `json:"entity_type" db:"entity_type"`   // 0:kb_article, 1:lesson, 2:fmea_item
	EntityID    uuid.UUID `json:"entity_id" db:"entity_id"`
	Confidence  uint8     `json:"confidence" db:"confidence"`
	DecayReason string    `json:"decay_reason" db:"decay_reason"` // "time_decay","ota_update","hw_change","test_failure",…
	AutoFlag    bool      `json:"auto_flag" db:"auto_flag"`      // true=自动触发
	SnapshotAt  time.Time `json:"snapshot_at" db:"snapshot_at"`
}
