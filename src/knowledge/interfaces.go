// Package knowledge 定义 yuleOSH 知识管理模块的 Go 服务契约。
//
// 本文件仅包含接口定义，不包含任何实现。
// 实现由开发团队在 Phase 1+ 中对应填充。
//
// 数据源: spec-knowledge-management.md v1.1.0
// 引用规范: RFC 2119（SHALL / SHALL NOT / SHOULD / MAY）
package knowledge

import (
	"context"
	"time"

	"github.com/google/uuid"
)

// ============================================================================
// KBServer — 知识条目 CRUD + 生命周期
// ============================================================================

// KBServer 定义知识条目（KB Article）的完整 CRUD 与生命周期管理接口。
// 覆盖 Spec: KBS-01 ~ KBS-03, KB-02, KB-03, KB-08, KB-09, KB-13 ~ KB-15, KBS-16
type KBServer interface {
	// ===== 基础 CRUD（KBS-01 / KBS-02 / KBS-03） =====

	// CreateArticle 创建一条知识条目。
	// SHALL 返回 201 + 完整条目，包含自动生成的 id (UUID v4)、created_at、version=1.0.0、confidence=100。
	// SHALL 校验 title、content、safety_level 为必填。
	// SHALL NOT 允许创建缺少 safety_level 的条目。
	CreateArticle(ctx context.Context, req *CreateArticleRequest) (*KbArticle, error)

	// GetArticle 读取指定知识条目。
	// SHALL 返回完整的条目内容（含关联的 SafetyGoals、CodePaths 等关联数据）。
	// SHALL 默认不返回软删除的条目，除非 explicitDeleted=true。
	GetArticle(ctx context.Context, id uuid.UUID, explicitDeleted bool) (*KbArticle, error)

	// UpdateArticle 更新知识条目。
	// SHALL 自动递增 version.patch 段。
	// SHALL 自动创建版本快照（完整内容拷贝，KB-03）。
	// SHOULD 校验并提示填写 change_reason。
	UpdateArticle(ctx context.Context, req *UpdateArticleRequest) (*KbArticle, error)

	// SoftDeleteArticle 逻辑删除知识条目（KBS-01）。
	// SHALL 设置 is_deleted=true, deleted_at=now()。
	// SHALL NOT 阻止操作，即使条目被引用（引用完整性由 CROSS-03 保障）。
	SoftDeleteArticle(ctx context.Context, id uuid.UUID) error

	// HardDeleteArticle 物理删除知识条目。
	// SHALL NOT 允许删除被其他模块引用或关联的条目，返回 409 Conflict。
	// SHALL 仅在管理员角色且有 is_deleted 标记时允许。
	HardDeleteArticle(ctx context.Context, id uuid.UUID) error

	// RestoreArticle 恢复软删除的知识条目。
	RestoreArticle(ctx context.Context, id uuid.UUID) (*KbArticle, error)

	// ListArticles 列出知识条目（支持分页和多重过滤）。
	ListArticles(ctx context.Context, filter *ArticleFilter) ([]*KbArticle, int64, error)

	// ===== 状态转换（KB-02 / KB-13） =====

	// SubmitForReview 提交审核: draft → review_pending。
	// SHALL 自动触发 pipeline 审批任务。
	// SHALL 记录审计日志（操作人、时间、原因）。
	SubmitForReview(ctx context.Context, id uuid.UUID, req *SubmitReviewRequest) error

	// ApproveArticle 审核通过: review_pending → approved。
	// SHALL — 当 safety_level=ASIL_B/C/D 时，要求在转换前存在至少一次独立评审记录。
	// SHALL — 当 safety_level=ASIL_D 时，要求至少两名不同评审人 sign-off。
	// SHALL — 缺少评审记录时返回 403 Forbidden。
	ApproveArticle(ctx context.Context, id uuid.UUID, req *ApproveRequest) error

	// RejectReview 审核驳回: review_pending → draft。
	// SHALL 记录驳回原因。
	RejectReview(ctx context.Context, id uuid.UUID, req *RejectRequest) error

	// PublishArticle 发布: approved → published。
	PublishArticle(ctx context.Context, id uuid.UUID) error

	// DeprecateArticle 标记过期: published/approved → deprecated。
	DeprecateArticle(ctx context.Context, id uuid.UUID, reason string) error

	// ReinstateArticle 审查后恢复: deprecated → approved（跳过发布步骤，KB-08）。
	// SHALL 将 confidence 重置为 100。
	ReinstateArticle(ctx context.Context, id uuid.UUID, req *ReinstateRequest) error

	// ===== 版本管理（KB-03） =====

	// GetVersionHistory 获取指定条目的所有版本快照列表。
	GetVersionHistory(ctx context.Context, articleID uuid.UUID) ([]*KbVersion, error)

	// GetVersion 获取指定版本号的快照。
	GetVersion(ctx context.Context, articleID uuid.UUID, version int) (*KbVersion, error)

	// RollbackToVersion 回滚到指定历史版本。
	// SHALL 创建一个新版本（version++），内容与目标历史版本一致。
	// SHALL 记录回滚操作到审计日志。
	RollbackToVersion(ctx context.Context, articleID uuid.UUID, targetVersion int, reason string) (*KbArticle, error)

	// ===== 关联管理 =====

	// LinkSpecEntries 关联 Spec 条目（KB-14）。
	LinkSpecEntries(ctx context.Context, articleID uuid.UUID, specEntryIDs []string) error

	// LinkSafetyGoals 关联安全目标（KBS-16）。
	// SHALL 每个关联包含 safety_goal_id、link_type 等完整字段。
	// SHALL 当安全目标版本变更时触发通知。
	LinkSafetyGoals(ctx context.Context, articleID uuid.UUID, goals []SafetyGoalLink) error

	// GetBySafetyGoalID 按安全目标 ID 反向检索知识条目（KBS-16）。
	GetBySafetyGoalID(ctx context.Context, safetyGoalID string) ([]*KbArticle, error)

	// LinkCodePaths 关联代码路径（KB-04）。
	LinkCodePaths(ctx context.Context, articleID uuid.UUID, paths []CodePathEntry) error

	// LinkDTCCodes 关联 DTC 编码（KB-06）。
	LinkDTCCodes(ctx context.Context, articleID uuid.UUID, dtcCodes []string) error

	// LinkTestCases 关联测试用例及层级（KB-10）。
	LinkTestCases(ctx context.Context, articleID uuid.UUID, testLinks []TestLinkInput) error

	// ===== OTA 双轨绑定（KB-09 / KB-15） =====

	// BindOTAVersion 绑定 OTA 版本到知识条目。
	BindOTAVersion(ctx context.Context, articleID uuid.UUID, binding *OTABinding) error

	// OnOTAUpgrade OTA 版本升级事件处理。
	// SHALL 自动创建版本分支副本，旧版本标记 deprecated，新版本 confidence=80。
	// SHALL 在搜索中优先展示匹配目标 OTA 版本的条目。
	OnOTAUpgrade(ctx context.Context, oldOTA string, newOTA string) ([]*KbArticle, error)

	// CheckOTAPublishGate 检查 OTA 发布的 ASIL 门禁（KB-15）。
	// SHALL 当任何 ASIL_C/D 级绑定条目状态非 approved/published 时返回拒绝。
	CheckOTAPublishGate(ctx context.Context, otaVersion string) (*OTAPublishGateResult, error)
}

// ============================================================================
// KBQuery — 搜索与检索
// ============================================================================

// KBQuery 定义知识条目的搜索与检索接口。
// 覆盖 Spec: KB-01, KB-04, KB-05, KB-06, KB-11, KB-12
type KBQuery interface {
	// Search 多模态混合搜索（KB-01）。
	// SHALL 支持基于自然语言查询的全文和向量混合检索（cosine similarity + BM25）。
	// SHALL 将 confidence 因子（0–100 归一化）作为排序权重的一部分。
	// SHALL 默认排除软删除条目（KB-12）。
	// MAY 提供 include_deleted 参数供管理员搜索已删除条目（KB-12）。
	Search(ctx context.Context, query *SearchQuery) (*SearchResultSet, error)

	// SemanticSearch 纯语义搜索（基于 embedding）。
	SemanticSearch(ctx context.Context, embedding []float32, limit int) ([]*SearchResult, error)

	// SearchByDTC 按 DTC 编码检索（KB-06）。
	// SHALL 作为独立的第一级检索维度。
	// SHALL 支持精确匹配和前缀匹配（如 "P01" 匹配所有 P01xx）。
	// SHOULD 在结果中展示关联的 FMEA 条目和 LL 条目数量。
	SearchByDTC(ctx context.Context, dtc string, prefixMatch bool) (*DTCSearchResultSet, error)

	// AutocompleteDTC DTC 自动补全（KB-06 SHOULD）。
	AutocompleteDTC(ctx context.Context, prefix string, limit int) ([]string, error)

	// SearchByHWPlatform 按硬件平台过滤（KB-05 JSONB）。
	// SHALL 支持任意 JSONB 路径的独立筛选和组合筛选。
	SearchByHWPlatform(ctx context.Context, filter *HWPlatformFilter) ([]*KbArticle, error)

	// SearchByAUTOSARLayer 按 AUTOSAR 层级过滤（KB-11）。
	// SHALL 支持 ASW/RTE/BSW/HW 的任意组合。
	SearchByAUTOSARLayer(ctx context.Context, layers AUTOSARLayer) ([]*KbArticle, error)

	// SearchByCodePath 反向查询：给定源文件路径，列出所有关联条目（KB-04 SHOULD）。
	SearchByCodePath(ctx context.Context, repo string, filePath string) ([]*KbArticle, error)

	// ListByStatus 按状态汇总（仪表盘用）。
	ListByStatus(ctx context.Context) (map[KBStatus]int64, error)

	// ListByASIL 按 ASIL 等级汇总。
	ListByASIL(ctx context.Context) (map[SafetyLevel]int64, error)

	// ListDebtQueue 获取低置信度审查队列（confidence < 30, KB-07）。
	ListDebtQueue(ctx context.Context) ([]*KbArticle, error)
}

// ============================================================================
// LLService — Lessons Learned
// ============================================================================

// LLService 定义 Lessons Learned 条目的完整生命周期接口。
// 覆盖 Spec: LL-01 ~ LL-08
type LLService interface {
	// ===== 基础 CRUD（LL-01） =====

	// CreateLesson 创建 LL 条目。
	// SHALL 校验 title、root_cause、category、severity（含 catastrophic）为必填。
	// SHALL closure_status 默认为 open，初始状态为 8 状态链起点。
	CreateLesson(ctx context.Context, req *CreateLessonRequest) (*Lesson, error)

	// GetLesson 读取指定 LL 条目。
	GetLesson(ctx context.Context, id uuid.UUID) (*Lesson, error)

	// UpdateLesson 更新 LL 条目。
	// SHALL 记录每次非平凡变更到审计日志。
	UpdateLesson(ctx context.Context, req *UpdateLessonRequest) (*Lesson, error)

	// ListLessons 列出 LL 条目（支持按 category/severity/safety_level/closure_status 过滤，LL-08）。
	ListLessons(ctx context.Context, filter *LessonFilter) ([]*Lesson, int64, error)

	// ===== 闭环节点管理（LL-07） =====

	// TransitionStatus 执行 LL 条目的状态转换。
	// SHALL 遵循 8 状态转换链：open→investigating→action_planned→implemented→mitigated→verified→closed（或 rejected）。
	// SHALL 每一步记录：时间戳、操作人、措施描述、验证方式。
	// SHALL 从 rejected 可重新回到 open。
	// SHALL — 当 safety_level=ASIL_B/C/D 时，verified→closed 要求第三方签字确认（LL-02）。
	// SHALL 进入 closed 后自动生成 evidence 闭合证据记录。
	TransitionStatus(ctx context.Context, id uuid.UUID, req *LLTransitionRequest) error

	// RejectLesson 驳回 LL 条目（从任何状态进入 rejected）。
	// SHALL 要求填写驳回原因。
	RejectLesson(ctx context.Context, id uuid.UUID, reason string) error

	// CloseLesson 关闭 LL 条目（从 verified 进入 closed，含 ASIL 门禁检查）。
	// SHALL 自动在 evidence 模块生成闭合证据记录。
	CloseLesson(ctx context.Context, id uuid.UUID, req *LLCloseRequest) error

	// ===== 自动捕获（LL-03） =====

	// CaptureFromBug 从 Bug 自动创建 LL 条目草案（LL-03）。
	// SHALL 预填 source_ref、root_cause、severity。
	// SHALL 条目进入 open 状态，需人工审阅后确认。
	CaptureFromBug(ctx context.Context, bugRef string, rootCause string, severity LLSeverity) (*Lesson, error)

	// CaptureFromFMEA 从 FMEA 条目创建 LL 草案（售后闭环关联）。
	CaptureFromFMEA(ctx context.Context, fmeaItemID uuid.UUID, dtcCode string) (*Lesson, error)

	// ===== Test Seed 生成（LL-04） =====

	// GenerateTestSeed 生成知识驱动测试种子（LL-04）。
	// SHALL 在 closure_status 变为 closed 后自动调用。
	// SHALL 包含 root_cause 摘要、建议测试场景、推荐测试层级。
	// SHALL 存储在 evidence 模块，标记为 auto_generated。
	// SHOULD 检查已有覆盖，避免重复。
	GenerateTestSeed(ctx context.Context, lessonID uuid.UUID) (*LessonTestSeed, error)

	// ConfirmTestSeed reviewer 确认测试种子纳入正式用例集。
	ConfirmTestSeed(ctx context.Context, seedID uuid.UUID, reviewerID string) error

	// ===== DTC 关联（LL-05） =====

	// LinkDTCCodes 关联 DTC 编码。
	LinkDTCCodes(ctx context.Context, lessonID uuid.UUID, dtcCodes []string) error

	// CheckDTCAleriThreshold 检查 DTC 告警阈值并标记 pending_review。
	CheckDTCAleriThreshold(ctx context.Context, dtcCode string) error

	// ===== 售后闭环（LL-06） =====

	// ProcessAftermarketDTC 处理售后 DTC 回灌事件（LL-06 / CROSS-02）。
	// SHALL 查询 KB 和 FMEA 中该 DTC 关联条目。
	// SHALL 若不存在 LL 条目，自动创建 open 状态草案。
	// SHALL 存在时更新售后引用计数。
	// SHALL 记录审计日志（原始 DTC、售后工单 ID、处理结果）。
	ProcessAftermarketDTC(ctx context.Context, req *AftermarketDTCRequest) (*AftermarketDTCResult, error)

	// SimilarEventSearch 相似事件检索（LL-08 SHOULD）。
	// 基于语义相似度匹配历史 LL 条目，避免重复创建。
	SimilarEventSearch(ctx context.Context, description string, limit int) ([]*Lesson, error)
}

// ============================================================================
// FMEAService — FMEA 条目管理
// ============================================================================

// FMEAService 定义 FMEA 条目的完整管理接口。
// 覆盖 Spec: FMEA-01 ~ FMEA-09, PK-01 ~ PK-10
type FMEAService interface {
	// ===== FMEA 主记录 CRUD（FMEA-01） =====

	// CreateFMEAEntry 创建 FMEA 主记录。
	CreateFMEAEntry(ctx context.Context, req *CreateFMEAEntryRequest) (*FMEAEntry, error)

	// GetFMEAEntry 读取 FMEA 主记录（含所有 items）。
	GetFMEAEntry(ctx context.Context, id uuid.UUID) (*FMEAEntry, error)

	// UpdateFMEAEntry 更新 FMEA 主记录元数据。
	UpdateFMEAEntry(ctx context.Context, req *UpdateFMEAEntryRequest) (*FMEAEntry, error)

	// ListFMEAEntries 列出 FMEA 主记录。
	ListFMEAEntries(ctx context.Context, filter *FMEAEntryFilter) ([]*FMEAEntry, int64, error)

	// ===== FMEA Item CRUD（FMEA-01） =====

	// CreateFMEAItem 创建 FMEA 条目（失效模式明细）。
	// SHALL rpn_total 自动计算（severity × occurrence × detection）。
	// SHALL ap_priority 自动基于 AIAG-VDA AP 矩阵计算（FMEA-05）。
	// SHALL fmea_id 格式 "FMEA-YYYY-NNNN"。
	CreateFMEAItem(ctx context.Context, req *CreateFMEAItemRequest) (*FMEAItem, error)

	// GetFMEAItem 读取指定 FMEA 条目。
	GetFMEAItem(ctx context.Context, id uuid.UUID) (*FMEAItem, error)

	// UpdateFMEAItem 更新 FMEA 条目。
	// SHALL 自动重算 rpn_total。
	// SHALL 自动重算 ap_priority。
	// SHALL 当 ap_priority=H 且 safety_level=ASIL_B/C/D 时，强制要求措施有效性证据方可关闭（FMEA-04）。
	UpdateFMEAItem(ctx context.Context, req *UpdateFMEAItemRequest) (*FMEAItem, error)

	// UpdateFMEAItemStatus 更新 FMEA 条目的状态（6 状态链: open/analysis/action_planned/action_done/verified/closed）。
	// SHALL 遵守 FMEA 门禁（FMEA-04）。
	UpdateFMEAItemStatus(ctx context.Context, id uuid.UUID, status FMEAItemStatus) error

	// DeleteFMEAItem 软删除 FMEA 条目。
	DeleteFMEAItem(ctx context.Context, id uuid.UUID) error

	// ListFMEAItems 列出 FMEA 条目（支持按 entry/status/ap_priority 过滤）。
	ListFMEAItems(ctx context.Context, filter *FMEAItemFilter) ([]*FMEAItem, int64, error)

	// ===== AIAG-VDA Action Priority（FMEA-05） =====

	// CalculateAPPriority 基于 AIAG-VDA AP 矩阵计算优先级（H/M/L）。
	// SHALL 以 (ap_severity, ap_occurrence, ap_detection) 三元组查表。
	// SHALL 当 ap_priority=H 时触发 pipeline 高优先行动任务。
	CalculateAPPriority(severity, occurrence, detection uint8) FMEAActionPriority

	// GetAPMatrixVisualization 获取 AP 矩阵可视化数据（MAY）。
	GetAPMatrixVisualization(severity, occurrence, detection uint8) (*APMatrixCell, error)

	// ===== FMEA as Code — YAML（FMEA-02） =====

	// ImportFromYAML 从 YAML 字符串导入 FMEA 条目。
	// SHALL 经过完整 schema 校验。
	// SHALL 校验失败时返回详细错误报告（行号+字段+错误类型）。
	ImportFromYAML(ctx context.Context, yamlContent []byte, creatorID string) (*FMEAEntry, error)

	// ExportToYAML 将 FMEA 条目导出为 YAML 字符串。
	// SHALL 包含所有强制字段，含自动计算的 RPN 和 AP 优先级。
	ExportToYAML(ctx context.Context, entryID uuid.UUID) ([]byte, error)

	// ValidateFMEAYAML 校验 FMEA YAML 文件（CI 集成用）。
	// SHALL 返回行号级别的错误报告。
	ValidateFMEAYAML(yamlContent []byte) (*YAMLValidationReport, error)

	// ===== 跨 ECU 失效链（FMEA-03 / FMEA-06） =====

	// LinkCrossECUChain 在 FMEA 条目间建立跨 ECU 失效链。
	// SHALL 每个节点包含 ecu_id、signal_name、failure_mode、propagation_direction。
	LinkCrossECUChain(ctx context.Context, itemID uuid.UUID, links []CrossECULink) error

	// GetCrossECUChain 获取跨 ECU 失效链（含全部节点）。
	GetCrossECUChain(ctx context.Context, itemID uuid.UUID) ([]*FMEAItemCrossECU, error)

	// OnCrossECUChainUpdate 当链上任一节点控制措施变更时。
	// SHALL 自动级联标记链上所有相关 FMEA 条目为 open（FMEA-03）。
	OnCrossECUChainUpdate(ctx context.Context, changedItemID uuid.UUID) error

	// DiffCrossECUChain 跨 ECU 版本差异对比（FMEA-06）。
	DiffCrossECUChain(ctx context.Context, entryID uuid.UUID, versionA, versionB string) (*ChainDiffReport, error)

	// ===== 轻量增量 FMEA（FMEA-09） =====

	// ForkFMEAItem 派生 FMEA 条目（FMEA-09）。
	// SHALL 继承父条目全部字段，记录 parent_fmea_item_id。
	// SHALL 形成 FMEA 家族树。
	ForkFMEAItem(ctx context.Context, sourceItemID uuid.UUID, overrides *FMEAItemOverrides, creatorID string) (*FMEAItem, error)

	// GetFMEAFamilyTree 获取 FMEA 家族树。
	GetFMEAFamilyTree(ctx context.Context, itemID uuid.UUID) ([]*FMEAItem, error)

	// BatchDiffReview PR 级别的 FMEA 差异审查（FMEA-09 SHOULD）。
	BatchDiffReview(ctx context.Context, yamlBefore, yamlAfter []byte) (*FMETChangeSet, error)

	// ===== DTC → FMEA（FMEA-07） =====

	// LinkFMEADTCCodes 关联 DTC 编码。
	LinkFMEADTCCodes(ctx context.Context, itemID uuid.UUID, dtcCodes []string) error

	// GetDTCMatrixView 获取 DTC 失效模式矩阵视图（FMEA-07）。
	// SHALL 展示 DTC → 失效模式的一对多映射关系。
	GetDTCMatrixView(ctx context.Context, dtcCode string) (*DTCMatrixView, error)

	// ===== FMEA → Test → Telemetry（FMEA-08） =====

	// CreateTestRequirement 为高/中优先级 FMEA 创建测试需求。
	// SHALL 当 ap_priority=H/M 时自动调用。
	// SHALL 包含 failure_mode 和 recommended_action。
	CreateTestRequirement(ctx context.Context, itemID uuid.UUID) error

	// OnTestResultBackfill 测试结果回写 FMEA 条目。
	// SHALL 更新 current_control 有效性判定。
	OnTestResultBackfill(ctx context.Context, testMapID uuid.UUID, passed bool) error

	// OnTelemetryMatch 遥测数据匹配 FMEA 失效模式。
	// SHALL 通知条目负责人重新评估。
	OnTelemetryMatch(ctx context.Context, itemID uuid.UUID, telemetrySummary string) error

	// ===== PFMEA（PK-01 ~ PK-10） =====

	// CreatePFMEAItem 创建 PFMEA 条目（共享 FMEA 数据模型，fmea_scope="process", PK-01）。
	// SHALL 包含 process_step 等 PFMEA 强制字段。
	CreatePFMEAItem(ctx context.Context, req *CreatePFMEAItemRequest) (*FMEAItem, error)

	// BatchImportPFMEA 从过程流程图批量导入 PFMEA 草案（PK-09）。
	BatchImportPFMEA(ctx context.Context, input []byte, format string) ([]*FMEAItem, error)

	// LinkPFMEAtoDFMEA 关联 PFMEA 与 DFMEA（PK-04）。
	LinkPFMEAtoDFMEA(ctx context.Context, pfmeaItemID, dfmeaItemID uuid.UUID) error

	// ExportControlPlan 从 PFMEA 导出控制计划草案（PK-05 SHOULD）。
	ExportControlPlan(ctx context.Context, entryID uuid.UUID) ([]byte, error)

	// GenerateProcessCapabilityRequirement 批产验证证据需求（PK-07）。
	GenerateProcessCapabilityRequirement(ctx context.Context, itemID uuid.UUID) error

	// GeneratePFMEATestSeed PFMEA → Test Seed（PK-08）。
	GeneratePFMEATestSeed(ctx context.Context, itemID uuid.UUID) error
}

// ============================================================================
// KnowledgeStore — 存储层接口（与现有 store 模块的桥接层）
// ============================================================================

// KnowledgeStore 定义知识管理模块对持久化存储的所有操作。
// 作为 yuleOSH store 模块的子接口，复用 store.WithTx()、store.WithAudit() 等基础设施。
// 覆盖: 所有 KB / LL / FMEA 实体的持久化操作
type KnowledgeStore interface {
	// ===== 事务管理 =====

	// WithTx 在事务中执行操作（由 store 模块提供）。
	WithTx(ctx context.Context, fn func(ctx context.Context) error) error

	// ===== KB Article =====

	GetArticle(ctx context.Context, id uuid.UUID, includeDeleted bool) (*KbArticle, error)
	ListArticles(ctx context.Context, filter *ArticleFilter) ([]*KbArticle, int64, error)
	CreateArticle(ctx context.Context, a *KbArticle) error
	UpdateArticle(ctx context.Context, a *KbArticle) error
	SoftDeleteArticle(ctx context.Context, id uuid.UUID) error
	HardDeleteArticle(ctx context.Context, id uuid.UUID) error
	RestoreArticle(ctx context.Context, id uuid.UUID) error
	UpdateArticleStatus(ctx context.Context, id uuid.UUID, status KBStatus) error
	UpdateArticleConfidence(ctx context.Context, id uuid.UUID, confidence uint8) error
	UpdateCodePathStale(ctx context.Context, id uuid.UUID, stale bool) error
	SetArticleCodePathStale(ctx context.Context, articleID uuid.UUID, stale bool) error
	IncrementArticleVersion(ctx context.Context, id uuid.UUID) (int, error)

	// ===== KB Version =====

	CreateVersion(ctx context.Context, v *KbVersion) error
	GetVersion(ctx context.Context, articleID uuid.UUID, version int) (*KbVersion, error)
	ListVersions(ctx context.Context, articleID uuid.UUID) ([]*KbVersion, error)
	GetLatestVersion(ctx context.Context, articleID uuid.UUID) (*KbVersion, error)

	// ===== KB Audit Log =====

	CreateVersionAuditLog(ctx context.Context, l *KbVersionAuditLog) error
	ListVersionAuditLogs(ctx context.Context, articleID uuid.UUID) ([]*KbVersionAuditLog, error)

	// ===== KB — 关联查询 =====

	GetArticleByDTC(ctx context.Context, dtc string) ([]*KbArticle, error)
	GetArticleByCodePath(ctx context.Context, repo string, filePath string) ([]*KbArticle, error)
	GetArticleBySafetyGoal(ctx context.Context, safetyGoalID string) ([]*KbArticle, error)
	ListArticlesByStatus(ctx context.Context) (map[KBStatus]int64, error)
	ListArticlesByASIL(ctx context.Context) (map[SafetyLevel]int64, error)
	ListDebtQueueArticles(ctx context.Context) ([]*KbArticle, error)

	// ===== KB — DTC Map =====

	CreateDTCMap(ctx context.Context, m *KnowledgeDTCMap) error
	DeleteDTCMapByArticle(ctx context.Context, articleID uuid.UUID) error
	GetByDTCCode(ctx context.Context, dtc string) (*DTCSearchResult, error)

	// ===== KB — Test Map =====

	CreateTestMap(ctx context.Context, m *KnowledgeTestMap) error
	UpdateTestMapStatus(ctx context.Context, id uuid.UUID, status TestStatus) error
	ListTestMapByArticle(ctx context.Context, articleID uuid.UUID) ([]*KnowledgeTestMap, error)

	// ===== KB — Code Path =====

	CreateCodePath(ctx context.Context, p *KnowledgeCodePath) error
	DeleteCodePathByArticle(ctx context.Context, articleID uuid.UUID) error
	ListCodePathByArticle(ctx context.Context, articleID uuid.UUID) ([]*KnowledgeCodePath, error)
	FindArticlesByChangedPath(ctx context.Context, changedFiles []string) ([]*KbArticle, error)

	// ===== KB — Tags =====

	CreateTag(ctx context.Context, t *KnowledgeTag) error
	GetTagByName(ctx context.Context, name string) (*KnowledgeTag, error)
	ListTags(ctx context.Context, category uint8) ([]*KnowledgeTag, error)
	LinkArticleTag(ctx context.Context, articleID, tagID uuid.UUID) error
	UnlinkArticleTag(ctx context.Context, articleID, tagID uuid.UUID) error

	// ===== LL Lesson =====

	GetLesson(ctx context.Context, id uuid.UUID) (*Lesson, error)
	ListLessons(ctx context.Context, filter *LessonFilter) ([]*Lesson, int64, error)
	CreateLesson(ctx context.Context, l *Lesson) error
	UpdateLesson(ctx context.Context, l *Lesson) error
	UpdateLessonStatus(ctx context.Context, id uuid.UUID, status LLClosureStatus) error
	DeleteLesson(ctx context.Context, id uuid.UUID) error

	// ===== LL — Lesson Actions =====

	CreateLessonAction(ctx context.Context, a *LessonAction) error
	UpdateLessonAction(ctx context.Context, a *LessonAction) error
	ListLessonActions(ctx context.Context, lessonID uuid.UUID) ([]*LessonAction, error)

	// ===== LL — Test Seeds =====

	CreateTestSeed(ctx context.Context, s *LessonTestSeed) error
	UpdateTestSeedStatus(ctx context.Context, id uuid.UUID, status uint8, reviewerID string) error
	GetTestSeedByLesson(ctx context.Context, lessonID uuid.UUID) ([]*LessonTestSeed, error)

	// ===== LL — Audit Log =====

	CreateLLAuditLog(ctx context.Context, l *LLAuditLog) error
	ListLLAuditLogs(ctx context.Context, lessonID uuid.UUID) ([]*LLAuditLog, error)

	// ===== FMEA Entry =====

	GetFMEAEntry(ctx context.Context, id uuid.UUID) (*FMEAEntry, error)
	ListFMEAEntries(ctx context.Context, filter *FMEAEntryFilter) ([]*FMEAEntry, int64, error)
	CreateFMEAEntry(ctx context.Context, e *FMEAEntry) error
	UpdateFMEAEntry(ctx context.Context, e *FMEAEntry) error
	GetFMEAEntryBySystem(ctx context.Context, system string) (*FMEAEntry, error)
	GetFMEAEntryByHash(ctx context.Context, sourceHash string) (*FMEAEntry, error)

	// ===== FMEA Item =====

	GetFMEAItem(ctx context.Context, id uuid.UUID) (*FMEAItem, error)
	ListFMEAItems(ctx context.Context, filter *FMEAItemFilter) ([]*FMEAItem, int64, error)
	CreateFMEAItem(ctx context.Context, item *FMEAItem) error
	UpdateFMEAItem(ctx context.Context, item *FMEAItem) error
	DeleteFMEAItem(ctx context.Context, id uuid.UUID) error
	UpdateFMEAItemStatus(ctx context.Context, id uuid.UUID, status FMEAItemStatus) error
	UpdateFMEAItemConfidence(ctx context.Context, id uuid.UUID, confidence uint8) error
	ListFMEAItemsByDTC(ctx context.Context, dtc string) ([]*FMEAItem, error)

	// ===== FMEA Action =====

	CreateFMEAAction(ctx context.Context, a *FMEAAction) error
	UpdateFMEAAction(ctx context.Context, a *FMEAAction) error
	ListFMEAActions(ctx context.Context, itemID uuid.UUID) ([]*FMEAAction, error)

	// ===== FMEA — Cross ECU =====

	CreateCrossECULink(ctx context.Context, l *FMEAItemCrossECU) error
	DeleteCrossECULinksBySource(ctx context.Context, sourceItemID uuid.UUID) error
	GetCrossECUChain(ctx context.Context, itemID uuid.UUID) ([]*FMEAItemCrossECU, error)
	GetChainItemsBySource(ctx context.Context, itemID uuid.UUID) ([]*FMEAItem, error)

	// ===== FMEA — Audit Log =====

	CreateFMEAAuditLog(ctx context.Context, l *FMEAAuditLog) error
	ListFMEAAuditLogsByEntry(ctx context.Context, entryID uuid.UUID) ([]*FMEAAuditLog, error)
	ListFMEAAuditLogsByItem(ctx context.Context, itemID uuid.UUID) ([]*FMEAAuditLog, error)

	// ===== 置信度 =====

	CreateConfidenceSnapshot(ctx context.Context, s *ConfidenceSnapshot) error
	ListConfidenceSnapshots(ctx context.Context, entityType uint8, entityID uuid.UUID) ([]*ConfidenceSnapshot, error)
	UpdateConfidence(ctx context.Context, entityType uint8, entityID uuid.UUID, confidence uint8) error

	// ===== 搜索（Store 层面） =====

	FullTextSearch(ctx context.Context, query string, limit int, offset int) ([]*KbArticle, int64, error)
	SemanticSearch(ctx context.Context, embedding []float32, limit int) ([]*SearchResult, error)
	MixedSearch(ctx context.Context, query *SearchQuery) (*SearchResultSet, error)

	// ===== 使用统计（置信度衰减用） =====

	CountRecentUsage(ctx context.Context, entityType uint8, entityID uuid.UUID, days int) (int, error)
	GetLastAccessTime(ctx context.Context, entityType uint8, entityID uuid.UUID) (*time.Time, error)
}

// ============================================================================
// 请求 / 响应 DTO（配合接口使用）
// ============================================================================

// CreateArticleRequest 创建知识条目请求
type CreateArticleRequest struct {
	Title               string           `json:"title" validate:"required,max=200"`
	Summary             string           `json:"summary,omitempty"`
	Content             string           `json:"content" validate:"required"`
	Status              KBStatus         `json:"status,omitempty"`
	ASIL                SafetyLevel      `json:"safety_level" validate:"required"`
	AUTOSARLayer        AUTOSARLayer     `json:"autosar_layer,omitempty"`
	HWBom               []HWBomEntry     `json:"hw_bom,omitempty"`
	OTABinding          *OTABinding      `json:"ota_binding,omitempty"`
	DTCCodes            []string         `json:"dtc_codes,omitempty"`
	CodePaths           []CodePathEntry  `json:"code_paths,omitempty"`
	AuthorID            string           `json:"author_id" validate:"required"`
	ReviewerID          string           `json:"reviewer_id,omitempty"`
	Tags                []string         `json:"tags,omitempty"`
	ConfidenceDecayPolicy string         `json:"confidence_decay_policy,omitempty"`
	TCLDocSlot          *TCLDocSlot      `json:"tcl_doc_slot,omitempty"`
	SafetyGoals         []SafetyGoalLink `json:"safety_goals,omitempty"`
}

// UpdateArticleRequest 更新知识条目请求
type UpdateArticleRequest struct {
	ID                  uuid.UUID        `json:"id" validate:"required"`
	Title               string           `json:"title,omitempty"`
	Summary             string           `json:"summary,omitempty"`
	Content             string           `json:"content,omitempty"`
	Status              *KBStatus        `json:"status,omitempty"`
	ASIL                *SafetyLevel     `json:"safety_level,omitempty"`
	AUTOSARLayer        *AUTOSARLayer    `json:"autosar_layer,omitempty"`
	HWBom               []HWBomEntry     `json:"hw_bom,omitempty"`
	OTABinding          *OTABinding      `json:"ota_binding,omitempty"`
	DTCCodes            []string         `json:"dtc_codes,omitempty"`
	CodePaths           []CodePathEntry  `json:"code_paths,omitempty"`
	Tags                []string         `json:"tags,omitempty"`
	SafetyGoals         []SafetyGoalLink `json:"safety_goals,omitempty"`
	ChangeReason        string           `json:"change_reason"` // 版本变更原因
	ChangedBy           string           `json:"changed_by" validate:"required"`
}

// SubmitReviewRequest 提交审核请求
type SubmitReviewRequest struct {
	SubmittedBy string `json:"submitted_by" validate:"required"`
	Comment     string `json:"comment,omitempty"`
}

// ApproveRequest 审核通过请求
type ApproveRequest struct {
	ReviewerID   string   `json:"reviewer_id" validate:"required"`
	Comment      string   `json:"comment,omitempty"`
	SignOffToken string   `json:"sign_off_token,omitempty"` // 用于 ASIL B/C/D sign-off
	CoReviewers  []string `json:"co_reviewers,omitempty"`   // ASIL_D 第二评审人
}

// RejectRequest 驳回请求
type RejectRequest struct {
	ReviewerID string `json:"reviewer_id" validate:"required"`
	Reason     string `json:"reason" validate:"required"`
}

// ReinstateRequest 恢复请求
type ReinstateRequest struct {
	OperatorID string `json:"operator_id" validate:"required"`
	Reason     string `json:"reason" validate:"required"`
}

// ArticleFilter 知识条目过滤条件
type ArticleFilter struct {
	Statuses      []KBStatus      `json:"statuses,omitempty"`
	ASILs         []SafetyLevel   `json:"asil_levels,omitempty"`
	AUTOSARLayers AUTOSARLayer    `json:"autosar_layer,omitempty"`
	HWPlatforms   []string        `json:"hw_platforms,omitempty"`
	DTCCodes      []string        `json:"dtc_codes,omitempty"`
	AuthorID      string          `json:"author_id,omitempty"`
	Tags          []string        `json:"tags,omitempty"`
	ConfidenceMin *uint8          `json:"confidence_min,omitempty"`
	ConfidenceMax *uint8          `json:"confidence_max,omitempty"`
	IncludeDeleted bool           `json:"include_deleted,omitempty"`
	OTAVersion    string          `json:"ota_version,omitempty"`
	Keyword       string          `json:"keyword,omitempty"`
	Limit         int             `json:"limit,omitempty"`
	Offset        int             `json:"offset,omitempty"`
	SortBy        string          `json:"sort_by,omitempty"`  // "updated_at" | "confidence" | "title"
	SortOrder     string          `json:"sort_order,omitempty"` // "asc" | "desc"
}

// TestLinkInput 测试关联输入
type TestLinkInput struct {
	TestLayer  TestLayer  `json:"test_layer"`
	TestSuite  string     `json:"test_suite"`
	TestCaseID string     `json:"test_case_id"`
}

// HWPlatformFilter 硬件平台过滤
type HWPlatformFilter struct {
	Platform string `json:"platform,omitempty"`
	Chip     string `json:"chip,omitempty"`
	Version  string `json:"version,omitempty"`
}

// SearchQuery 搜索请求
type SearchQuery struct {
	Keywords      string         `json:"keywords,omitempty"`
	DTCCodes      []string       `json:"dtc_codes,omitempty"`
	Tags          []string       `json:"tags,omitempty"`
	ASILs         []SafetyLevel  `json:"asil_levels,omitempty"`
	AUTOSARLayers AUTOSARLayer   `json:"autosar_layer,omitempty"`
	HWPlatforms   []string       `json:"hw_platforms,omitempty"`
	Statuses      []KBStatus     `json:"statuses,omitempty"`
	EntityTypes   []uint8        `json:"entity_types,omitempty"` // 0:kb, 1:lesson, 2:fmea
	Limit         int            `json:"limit,omitempty"`
	Offset        int            `json:"offset,omitempty"`
	SortBy        string         `json:"sort_by,omitempty"`
	OTAVersion    string         `json:"ota_version,omitempty"`
	IncludeDeleted bool          `json:"include_deleted,omitempty"`
}

// SearchResult 单条搜索结果
type SearchResult struct {
	EntityType  uint8    `json:"entity_type"`   // 0:kb, 1:lesson, 2:fmea
	EntityID    uuid.UUID `json:"entity_id"`
	Title       string   `json:"title"`
	Snippet     string   `json:"snippet"`
	Score       float64  `json:"similarity_score"`
	Confidence  uint8    `json:"confidence"`
	Tags        []string `json:"tags,omitempty"`
	MatchedDTC  []string `json:"matched_dtc,omitempty"`
	MatchedPath []string `json:"matched_path,omitempty"`
}

// SearchResultSet 搜索结果集
type SearchResultSet struct {
	Results   []*SearchResult  `json:"results"`
	Total     int64            `json:"total"`
	DTCResults []interface{}   `json:"dtc_results,omitempty"`
}

// DTCSearchResultSet DTC 检索结果集
type DTCSearchResultSet struct {
	DTCCode     string           `json:"dtc_code"`
	Description string           `json:"description"`
	KBArticles  []*KbArticle     `json:"kb_articles"`
	Lessons     []*Lesson        `json:"lessons"`
	FMEAItems   []*FMEAItem      `json:"fmea_items"`
}

// DTCSearchResult 单条 DTC 检索结果（含跨实体聚合）
type DTCSearchResult struct {
	DTCCode     string         `json:"dtc_code"`
	Description string         `json:"dtc_description"`
	Source      uint8          `json:"source"`
	Weight      uint8          `json:"weight"`
	KBArticles  []*KbArticle   `json:"kb_articles,omitempty"`
	Lessons     []*Lesson      `json:"lessons,omitempty"`
	FMEAItems   []*FMEAItem    `json:"fmea_items,omitempty"`
}

// OTAPublishGateResult OTA 发布门禁检查结果
type OTAPublishGateResult struct {
	CanPublish bool     `json:"can_publish"`
	Blockers   []string `json:"blockers,omitempty"` // 未达标的条目列表
}

// ===== LL 相关 DTO =====

// CreateLessonRequest 创建 LL 条目请求
type CreateLessonRequest struct {
	Title       string     `json:"title" validate:"required"`
	Description string     `json:"description,omitempty"`
	RootCause   string     `json:"root_cause" validate:"required"`
	Category    LLCategory `json:"category" validate:"required"`
	Severity    LLSeverity `json:"severity" validate:"required"`
	SafetyLevel SafetyLevel `json:"safety_level"`
	Source      LLSource   `json:"source,omitempty"`
	SourceRef   string     `json:"source_ref,omitempty"`
	AuthorID    string     `json:"author_id" validate:"required"`
	AssigneeID  string     `json:"assignee_id,omitempty"`
	ArticleID   *uuid.UUID `json:"article_id,omitempty"`
	Tags        []string   `json:"tags,omitempty"`
}

// UpdateLessonRequest 更新 LL 条目请求
type UpdateLessonRequest struct {
	ID          uuid.UUID  `json:"id" validate:"required"`
	Title       string     `json:"title,omitempty"`
	Description string     `json:"description,omitempty"`
	RootCause   string     `json:"root_cause,omitempty"`
	Resolution  string     `json:"resolution,omitempty"`
	Category    *LLCategory `json:"category,omitempty"`
	Severity    *LLSeverity `json:"severity,omitempty"`
	AssigneeID  string     `json:"assignee_id,omitempty"`
	AppliedTo   []string   `json:"applied_to,omitempty"`
	UpdatedBy   string     `json:"updated_by" validate:"required"`
}

// LLTransitionRequest LL 状态转换请求
type LLTransitionRequest struct {
	NewStatus          LLClosureStatus `json:"new_status" validate:"required"`
	OperatorID         string          `json:"operator_id" validate:"required"`
	ActionDescription  string          `json:"action_description,omitempty"`
	VerificationMethod string          `json:"verification_method,omitempty"` // review/test/simulation/field_data/analysis
	SignOffBy          string          `json:"sign_off_by,omitempty"`         // ASIL B/C/D 第三方签字
}

// LLCloseRequest LL 关闭请求（含 ASIL 门禁）
type LLCloseRequest struct {
	OperatorID string `json:"operator_id" validate:"required"`
	SignOffBy  string `json:"sign_off_by,omitempty"`
	EvidenceID string `json:"evidence_id,omitempty"`
}

// LessonFilter LL 过滤条件
type LessonFilter struct {
	Statuses    []LLClosureStatus `json:"statuses,omitempty"`
	Severities  []LLSeverity      `json:"severities,omitempty"`
	Categories  []LLCategory      `json:"categories,omitempty"`
	SafetyLevels []SafetyLevel    `json:"safety_levels,omitempty"`
	AuthorID    string            `json:"author_id,omitempty"`
	AssigneeID  string            `json:"assignee_id,omitempty"`
	DTCCode     string            `json:"dtc_code,omitempty"`
	Source      *LLSource         `json:"source,omitempty"`
	Keyword     string            `json:"keyword,omitempty"`
	Limit       int               `json:"limit,omitempty"`
	Offset      int               `json:"offset,omitempty"`
}

// AftermarketDTCRequest 售后 DTC 回灌请求
type AftermarketDTCRequest struct {
	DTCCode      string `json:"dtc_code" validate:"required"`
	WOID         string `json:"wo_id" validate:"required"`
	VehicleModel string `json:"vehicle_model,omitempty"`
	OTAVersion   string `json:"ota_version,omitempty"`
	Mileage      int    `json:"mileage,omitempty"`
	Timestamp    string `json:"timestamp,omitempty"`
}

// AftermarketDTCResult 售后回灌结果
type AftermarketDTCResult struct {
	DTCCode      string `json:"dtc_code"`
	WOID         string `json:"wo_id"`
	NewLLCreated bool   `json:"new_ll_created"`
	LessonID     string `json:"lesson_id,omitempty"`
	AuditEntryID string `json:"audit_entry_id"`
	MatchedKB    int    `json:"matched_kb_articles"`
	MatchedFMEA  int    `json:"matched_fmea_items"`
}

// ===== FMEA 相关 DTO =====

// CreateFMEAEntryRequest 创建 FMEA 主记录请求
type CreateFMEAEntryRequest struct {
	Name        string     `json:"name" validate:"required"`
	Description string     `json:"description,omitempty"`
	System      string     `json:"system" validate:"required"`
	Subsystem   string     `json:"subsystem,omitempty"`
	Scope       FMEAScope  `json:"scope"`
	SafetyLevel SafetyLevel `json:"safety_level"`
	CreatorID   string     `json:"creator_id" validate:"required"`
	ArticleID   *uuid.UUID `json:"article_id,omitempty"`
}

// UpdateFMEAEntryRequest 更新 FMEA 主记录请求
type UpdateFMEAEntryRequest struct {
	ID          uuid.UUID  `json:"id" validate:"required"`
	Name        string     `json:"name,omitempty"`
	Description string     `json:"description,omitempty"`
	Status      *FMEAEntryStatus `json:"status,omitempty"`
	UpdatedBy   string     `json:"updated_by" validate:"required"`
}

// CreateFMEAItemRequest 创建 FMEA 条目请求
type CreateFMEAItemRequest struct {
	FMEAEntryID       uuid.UUID  `json:"fmea_entry_id" validate:"required"`
	FunctionDesc      string     `json:"function_desc" validate:"required"`
	Component         string     `json:"component" validate:"required"`
	Layer             string     `json:"layer,omitempty"`
	FailureMode       string     `json:"failure_mode" validate:"required"`
	FailureEffect     string     `json:"failure_effect" validate:"required"`
	FailureCause      string     `json:"failure_cause" validate:"required"`
	FailureMechanism  string     `json:"failure_mechanism,omitempty"`
	Severity          uint8      `json:"rpn_severity" validate:"required,min=1,max=10"`
	Occurrence        uint8      `json:"rpn_occurrence" validate:"required,min=1,max=10"`
	Detection         uint8      `json:"rpn_detection" validate:"required,min=1,max=10"`
	APSeverity        *uint8     `json:"ap_severity,omitempty"`
	APOccurrence      *uint8     `json:"ap_occurrence,omitempty"`
	APDetection       *uint8     `json:"ap_detection,omitempty"`
	CurrentControl    string     `json:"current_control,omitempty"`
	RecommendedAction string     `json:"recommended_action,omitempty"`
	DTCCodes          []string   `json:"dtc_codes,omitempty"`
	SafetyLevel       SafetyLevel `json:"safety_level"`
	AUTOSARLayer      AUTOSARLayer `json:"autosar_layer,omitempty"`
	ControlType       *ControlType `json:"control_type,omitempty"`
	CreatorID         string     `json:"creator_id" validate:"required"`
}

// UpdateFMEAItemRequest 更新 FMEA 条目请求
type UpdateFMEAItemRequest struct {
	ID                 uuid.UUID      `json:"id" validate:"required"`
	FailureMode        *string        `json:"failure_mode,omitempty"`
	FailureEffect      *string        `json:"failure_effect,omitempty"`
	FailureCause       *string        `json:"failure_cause,omitempty"`
	Severity           *uint8         `json:"rpn_severity,omitempty"`
	Occurrence         *uint8         `json:"rpn_occurrence,omitempty"`
	Detection          *uint8         `json:"rpn_detection,omitempty"`
	APSeverity         *uint8         `json:"ap_severity,omitempty"`
	APOccurrence       *uint8         `json:"ap_occurrence,omitempty"`
	APDetection        *uint8         `json:"ap_detection,omitempty"`
	CurrentControl     *string        `json:"current_control,omitempty"`
	RecommendedAction  *string        `json:"recommended_action,omitempty"`
	DTCCodes           []string       `json:"dtc_codes,omitempty"`
	Status             *FMEAItemStatus `json:"status,omitempty"`
	PlannedSeverity    *uint8         `json:"planned_severity,omitempty"`
	PlannedOccurrence  *uint8         `json:"planned_occurrence,omitempty"`
	PlannedDetection   *uint8         `json:"planned_detection,omitempty"`
	UpdatedBy          string         `json:"updated_by" validate:"required"`
	ChangeReason       string         `json:"change_reason,omitempty"`
}

// CreatePFMEAItemRequest 创建 PFMEA 条目请求
type CreatePFMEAItemRequest struct {
	CreateFMEAItemRequest
	FMEAScope          FMEAScope `json:"fmea_scope"` // 必须为 process
	ProcessStep        string    `json:"process_step" validate:"required"`
	ProcessParameter   string    `json:"process_parameter,omitempty"`
	ProcessMachine     string    `json:"process_machine,omitempty"`
	StationID          string    `json:"station_id,omitempty"`
	MaterialID         string    `json:"material_id,omitempty"`
}

// FMEAEntryFilter FMEA 主记录过滤
type FMEAEntryFilter struct {
	Systems     []string          `json:"systems,omitempty"`
	Scopes      []FMEAScope       `json:"scopes,omitempty"`
	Statuses    []FMEAEntryStatus `json:"statuses,omitempty"`
	SafetyLevels []SafetyLevel    `json:"safety_levels,omitempty"`
	CreatorID   string            `json:"creator_id,omitempty"`
	Limit       int               `json:"limit,omitempty"`
	Offset      int               `json:"offset,omitempty"`
}

// FMEAItemFilter FMEA 条目过滤
type FMEAItemFilter struct {
	EntryID      *uuid.UUID        `json:"entry_id,omitempty"`
	Statuses     []FMEAItemStatus  `json:"statuses,omitempty"`
	APPriorities []FMEAActionPriority `json:"ap_priorities,omitempty"`
	SafetyLevels []SafetyLevel     `json:"safety_levels,omitempty"`
	DTCCode      string            `json:"dtc_code,omitempty"`
	FMEAScope    *FMEAScope        `json:"fmea_scope,omitempty"`
	MinRPN       *int              `json:"min_rpn,omitempty"`
	MaxRPN       *int              `json:"max_rpn,omitempty"`
	Limit        int               `json:"limit,omitempty"`
	Offset       int               `json:"offset,omitempty"`
}

// FMEAItemOverrides 派生时覆盖的字段
type FMEAItemOverrides struct {
	FunctionDesc      string    `json:"function_desc,omitempty"`
	FailureMode       string    `json:"failure_mode,omitempty"`
	FailureEffect     string    `json:"failure_effect,omitempty"`
	FailureCause      string    `json:"failure_cause,omitempty"`
	Severity          *uint8    `json:"severity,omitempty"`
	Occurrence        *uint8    `json:"occurrence,omitempty"`
	Detection         *uint8    `json:"detection,omitempty"`
	CurrentControl    string    `json:"current_control,omitempty"`
	RecommendedAction string    `json:"recommended_action,omitempty"`
}

// YAMLValidationReport YAML 校验报告
type YAMLValidationReport struct {
	Valid    bool               `json:"valid"`
	Errors   []YAMLValidationError `json:"errors,omitempty"`
	Warnings []string           `json:"warnings,omitempty"`
	ItemCount int               `json:"item_count"`
}

// YAMLValidationError YAML 校验错误
type YAMLValidationError struct {
	Line    int    `json:"line"`
	Field   string `json:"field"`
	Message string `json:"message"`
}

// APMatrixCell AP 矩阵单元格
type APMatrixCell struct {
	Severity   uint8              `json:"severity"`
	Occurrence uint8              `json:"occurrence"`
	Detection  uint8              `json:"detection"`
	Priority   FMEAActionPriority `json:"priority"`
	Label      string             `json:"label"` // "H" / "M" / "L"
}

// ChainDiffReport 跨 ECU 链差异报告
type ChainDiffReport struct {
	AddedNodes   []CrossECULink `json:"added_nodes,omitempty"`
	RemovedNodes []CrossECULink `json:"removed_nodes,omitempty"`
	ModifiedNodes []struct {
		NodeID  uuid.UUID      `json:"node_id"`
		Before  CrossECULink `json:"before"`
		After   CrossECULink `json:"after"`
	} `json:"modified_nodes,omitempty"`
}

// DTCMatrixView DTC 失效模式矩阵视图
type DTCMatrixView struct {
	DTCCode     string `json:"dtc_code"`
	Description string `json:"description"`
	FMEAItems   []struct {
		ID           uuid.UUID `json:"id"`
		FailureMode  string    `json:"failure_mode"`
		FailureEffect string   `json:"failure_effect"`
		APPriority   string    `json:"ap_priority"`
		RPN          int       `json:"rpn_total"`
		System       string    `json:"system"`
	} `json:"fmea_items"`
}

// FMEATChangeSet FMEA 变更集（PR 差异审查用）
type FMEATChangeSet struct {
	Added   []*FMEAItem `json:"added"`
	Removed []*FMEAItem `json:"removed"`
	Modified []*struct {
		ItemID uuid.UUID   `json:"item_id"`
		Before *FMEAItem   `json:"before"`
		After  *FMEAItem   `json:"after"`
		Diffs  []string    `json:"diffs"`
	} `json:"modified"`
}
