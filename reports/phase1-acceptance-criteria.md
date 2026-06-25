# yuleOSH 知识管理模块 — Phase 1 验收标准

> **版本**: v1.0  
> **日期**: 2026-06-20  
> **关联 Spec**: `spec-knowledge-management.md` (v1.1.0)  
> **关联 ACC**: `knowledge-acceptance-matrix.md` (v1.1.0)  
> **关联 Phase 1**: Tech §9.1（48 人·天）  
> **格式**: GIVEN / WHEN / THEN  

---

## 目录

- [KB CRUD + 元数据 + 标识](#kb-crud--元数据--标识)
- [KB 状态机 + ASIL 门禁](#kb-状态机--asil-门禁)
- [KB 版本快照链](#kb-版本快照链)
- [KB HW BOM 标签](#kb-hw-bom-标签)
- [KB DTC 检索](#kb-dtc-检索)
- [KB 置信度衰减](#kb-置信度衰减)
- [KB 安全目标追溯](#kb-安全目标追溯)
- [LL 基础 CRUD + 闭环节点](#ll-基础-crud--闭环节点)
- [LL 搜索与分类](#ll-搜索与分类)
- [FMEA 基础 CRUD + RPN + AP](#fmea-基础-crud--rpn--ap)
- [FMEA YAML 导入/导出](#fmea-yaml-导入导出)
- [FMEA 跨 ECU 失效链](#fmea-跨-ecu-失效链)
- [PFMEA](#pfmea)
- [CI/CD 集成](#cicd-集成)
- [知识债务仪表盘](#知识债务仪表盘)
- [审计日志](#审计日志)
- [权限模型](#权限模型)
- [跨模块引用完整性](#跨模块引用完整性)
- [TCL 预留接口](#tcl-预留接口)

---

## KB CRUD + 元数据 + 标识

### ACC-KBS-01-01: 创建知识条目

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一个已认证的用户 |
| **WHEN** | 该用户创建一个新的知识条目，填写 title、content、safety_level 并提交 |
| **THEN** | 系统返回 201 Created，包含完整的条目 JSON（含自动生成的 id、created_at、version = 1.0.0、confidence = 100） |

### ACC-KBS-01-02: 被引用的条目拒绝物理删除

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条已存在且被其他模块引用的知识条目 |
| **WHEN** | 用户执行物理删除操作 |
| **THEN** | 系统拒绝操作，返回 409 Conflict，并提示该条目存在引用依赖 |

### ACC-KBS-01-03: 逻辑删除

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条未被任何模块引用的知识条目 |
| **WHEN** | 用户执行逻辑删除操作 |
| **THEN** | 系统返回 200 OK，将 is_deleted 标记设为 true，deleted_at 记录当前时间，常规搜索不再返回该条目 |

### ACC-KBS-01-04: 缺少必填字段拒绝创建

| 属性 | 值 |
|------|-----|
| **GIVEN** | 创建知识条目的 API 请求缺少 author_id 字段 |
| **WHEN** | 用户提交创建请求 |
| **THEN** | 系统返回 400 Bad Request，错误信息包含 "author_id is required"，并阻止创建 |

### ACC-KBS-02-01: UUID 标识

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条新创建的知识条目 |
| **WHEN** | 分配其 id |
| **THEN** | id 为 UUID v4 格式，在整个生命周期中保持不变 |

### ACC-KBS-03-01: 缺少 safety_level 拒绝

| 属性 | 值 |
|------|-----|
| **GIVEN** | 创建知识条目的 API 请求 |
| **WHEN** | 请求中缺少 safety_level 字段 |
| **THEN** | 系统返回 400 Bad Request，错误信息包含 "safety_level is required" |

### ACC-KBS-03-02: TCL 预留字段存储

| 属性 | 值 |
|------|-----|
| **GIVEN** | 创建知识条目的 API 请求 |
| **WHEN** | 请求中包含了 tcl_doc_slot 字段且格式正确 |
| **THEN** | 系统接受并存储该字段，不校验其内容是否为空（预留字段） |

### ACC-KBS-03-03: HW BOM JSONB 存储

| 属性 | 值 |
|------|-----|
| **GIVEN** | 创建知识条目的 API 请求 |
| **WHEN** | 请求中包含了 hw_bom 字段（JSONB 数组格式：[{"platform":"TDA4VM","chip":"TDA4VM-Q1","version":"1.2"}]） |
| **THEN** | 系统接受并存储该字段，支持按 JSONB 路径进行过滤和组合筛选 |

### ACC-KBS-03-04: 置信度整数类型

| 属性 | 值 |
|------|-----|
| **GIVEN** | 新创建的知识条目 |
| **WHEN** | 查询其 confidence 字段 |
| **THEN** | confidence 为整数 100（范围 0-100），非浮点数 |

---

## KB 状态机 + ASIL 门禁

### ACC-KB-13-01: Draft → Review Pending

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条知识条目当前状态为 draft |
| **WHEN** | 用户提交审核 |
| **THEN** | 状态变为 review_pending，pipeline 审批任务自动触发，审计日志记录操作人和时间 |

### ACC-KB-13-02: Review Pending → Approved

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条知识条目当前状态为 review_pending |
| **WHEN** | 审核通过 |
| **THEN** | 状态变为 approved，审计日志记录审核人和时间 |

### ACC-KB-13-03: Approved → Published

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条知识条目当前状态为 approved |
| **WHEN** | 用户执行发布操作 |
| **THEN** | 状态变为 published |

### ACC-KB-13-04: Published → Deprecated

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条知识条目当前状态为 published |
| **WHEN** | 用户标记过期 |
| **THEN** | 状态变为 deprecated |

### ACC-KB-02-03: QM 条目直接审批

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条 safety_level=QM 的知识条目 |
| **WHEN** | 用户直接将其状态从 draft 切换为 approved |
| **THEN** | 系统允许该操作，无需评审记录 |

---

## KB 版本快照链

### ACC-KB-03-01: 版本历史

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条知识条目，已执行两次更新 |
| **WHEN** | 用户查询版本历史 |
| **THEN** | 系统返回三个版本记录（v1.0.0, v1.0.1, v1.0.2），每个版本包含该时刻的完整内容拷贝 |

### ACC-KB-03-02: 回滚创建新版本

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条知识条目当前版本为 v1.0.5 |
| **WHEN** | 用户执行回滚到 v1.0.3 |
| **THEN** | 系统创建一个 v1.0.6 版本，其内容与 v1.0.3 完全一致，而非直接修改现有版本 |

---

## KB HW BOM 标签

### ACC-KB-05-01: JSONB 硬件平台过滤

| 属性 | 值 |
|------|-----|
| **GIVEN** | 知识条目设置了 hw_bom=[{"platform":"TDA4VM","chip":"TDA4VM-Q1","version":"1.2"}] |
| **WHEN** | 用户在 HW BOM 过滤器中通过 JSONB 路径选择 chip=`TDA4VM-Q1` |
| **THEN** | 系统返回所有 JSONB 数组中包含匹配 chip 值的知识条目 |

### ACC-KB-05-02: 多平台组合匹配

| 属性 | 值 |
|------|-----|
| **GIVEN** | 三条条目分别绑定不同硬件平台：A=[{platform:"TDA4VM"}], B=[{platform:"S32K"}], C=[{platform:"TDA4VM"},{platform:"S32K"}] |
| **WHEN** | 用户按 platform="TDA4VM" 过滤 |
| **THEN** | 系统返回条目 A 和 C（多平台条目通过匹配），不返回条目 B |

---

## KB DTC 检索

### ACC-KB-06-01: DTC 精确匹配

| 属性 | 值 |
|------|-----|
| **GIVEN** | 知识条目关联了 DTC `P0101` |
| **WHEN** | 用户在 DTC 搜索入口输入 `P0101` |
| **THEN** | 系统返回该知识条目，且结果页展示关联的 FMEA 条目和 LL 条目计数 |

### ACC-KB-06-02: DTC 前缀模糊匹配

| 属性 | 值 |
|------|-----|
| **GIVEN** | 知识条目关联了 DTC `P0101`、`P0102`、`P0103` |
| **WHEN** | 用户在 DTC 搜索入口输入 `P01`（前缀模糊） |
| **THEN** | 系统返回所有关联 `P01xx` 系列 DTC 的知识条目 |

---

## KB 安全目标追溯

### ACC-KBS-16-01: 安全目标反向检索

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条知识条目关联了安全目标 `SG-BRAKE-001` |
| **WHEN** | 用户通过安全目标 ID 反向检索 |
| **THEN** | 系统返回所有关联 `SG-BRAKE-001` 的知识条目清单 |

### ACC-KBS-16-03: 详情页展示安全目标

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条知识条目绑定了安全目标和 HARA 分析条目 |
| **WHEN** | 用户在详情页查看知识条目 |
| **THEN** | 详情页展示关联的安全目标清单，含 safety_goal_id、hazard_id 和 asil_decomposition（如适用） |

---

## KB 置信度衰减

### ACC-KB-07-01: Usage-based 衰减

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条知识条目，`confidence=90`（0-100 标尺），策略为 `usage_based`，在评估周期内无引用命中 |
| **WHEN** | 衰减评估 cron 执行（24 小时后） |
| **THEN** | `confidence` 变为 88（每周期移除 2 点），其他字段不变 |

### ACC-KB-07-03: 命中断衰减

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条知识条目，`confidence=80`，策略为 `usage_based`，在某评估周期内有引用或搜索命中 |
| **WHEN** | 衰减评估 cron 执行 |
| **THEN** | 衰减计数器重置，`confidence` 保持不变（仍为 80） |

### ACC-KB-07-04: 废弃策略拒绝

| 属性 | 值 |
|------|-----|
| **GIVEN** | 创建知识条目时指定了 `linear` 或 `step` 衰减策略 |
| **WHEN** | 系统执行 schema 校验 |
| **THEN** | 系统拒绝，返回错误信息 "仅支持 usage_based 衰减策略，linear/step 已废弃" |

### ACC-KB-08-01: 审查后置信度重置

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条 `confidence=20`（0-100 标尺）、状态为 `deprecated` 的知识条目 |
| **WHEN** | 人工审查后，用户切换状态为 `approved` 或 `published` |
| **THEN** | `confidence` 重置为 100，decay 周期重新开始，审计日志记录操作人和时间 |

---

## LL 基础 CRUD + 闭环节点

### ACC-LL-01-01: 创建 LL 条目

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一个已认证的用户 |
| **WHEN** | 用户创建一个新的 LL 条目，包含 title、description、root_cause、category、severity（枚举含 catastrophic）等字段 |
| **THEN** | 系统返回 201 Created，包含完整的 LL 条目，closure_status 默认为 open（8 状态生命周期），created_at 为当前时间 |

### ACC-LL-01-02: 缺少 root_cause 拒绝

| 属性 | 值 |
|------|-----|
| **GIVEN** | 创建 LL 条目的请求缺少 root_cause 字段 |
| **WHEN** | 用户提交 |
| **THEN** | 系统返回 400 Bad Request，"root_cause is required" |

### ACC-LL-01-03: 接受 catastrophic 严重度

| 属性 | 值 |
|------|-----|
| **GIVEN** | 创建 LL 条目的请求中 severity 设为 `catastrophic` |
| **WHEN** | 用户提交 |
| **THEN** | 系统接受该值（5 级严重度：info/minor/major/critical/catastrophic） |

### ACC-LL-07-01: 8 状态转换链

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条 LL 条目当前 closure_status 为 open |
| **WHEN** | 用户按 8 状态链（open→investigating→action_planned→implemented→mitigated→verified→closed）逐步转换 |
| **THEN** | 每一步记录 transition_timestamp、operator、action_description、verification_method |

### ACC-LL-07-02: 闭合时生成证据记录

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条 LL 条目从 verified 切换为 closed |
| **WHEN** | 闭合完成 |
| **THEN** | 系统在 evidence 模块中生成 "LI 知识闭合证据记录"，包含闭合时间、措施描述、验证方式 |

### ACC-LL-07-03: 驳回与重开

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条 LL 条目，当前状态为 open |
| **WHEN** | 用户直接将其标记为 rejected 并填写驳回原因 |
| **THEN** | 系统允许该操作；从 rejected 状态可重新切换为 open 重新发起分析 |

---

## LL 搜索与分类

### ACC-LL-08-01: 按 category + severity 过滤

| 属性 | 值 |
|------|-----|
| **GIVEN** | 知识库中存在 10 条 LL 条目，分布在不同 category、severity 下 |
| **WHEN** | 用户在 LL 界面上选择 category=design、severity=critical |
| **THEN** | 系统仅返回同时满足两个过滤条件的 LL 条目 |

---

## FMEA 基础 CRUD + RPN + AP

### ACC-FMEA-01-01: 缺少 failure_mode 拒绝

| 属性 | 值 |
|------|-----|
| **GIVEN** | 创建 FMEA 条目的请求 |
| **WHEN** | 请求中缺少 failure_mode 字段 |
| **THEN** | 系统返回 400 Bad Request，"failure_mode is required" |

### ACC-FMEA-01-02: 创建含 RPN 自动计算

| 属性 | 值 |
|------|-----|
| **GIVEN** | 创建 FMEA 条目的请求包含所有必要字段 |
| **WHEN** | 用户提交 |
| **THEN** | 系统返回 201 Created，fmea_id 格式为 "FMEA-YYYY-NNNN"，rpn_total 自动计算为 severity × occurrence × detection，status 默认为 open（6 状态生命周期：open/analysis/action_planned/action_done/verified/closed） |

### ACC-FMEA-01-03: AIAG-VDA AP 自动计算

| 属性 | 值 |
|------|-----|
| **GIVEN** | 创建 FMEA 条目的请求包含 ap_severity=8, ap_occurrence=4, ap_detection=6 |
| **WHEN** | 用户提交 |
| **THEN** | 系统根据 AIAG-VDA AP 矩阵自动计算 ap_priority="H"（高优先） |

### ACC-FMEA-05-01: AP 优先级自动计算 + 高亮标识

| 属性 | 值 |
|------|-----|
| **GIVEN** | 多条 FMEA 条目，各有不同的 ap_severity, ap_occurrence, ap_detection |
| **WHEN** | 系统创建/更新条目 |
| **THEN** | 系统基于 AIAG-VDA AP 矩阵自动计算 ap_priority（H/M/L），H 级在仪表盘高亮标识 |

### ACC-FMEA-05-02: AP=H 触发 pipeline 任务

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条 FMEA 条目，ap_priority=H |
| **WHEN** | 系统创建该条目后 |
| **THEN** | 系统在 pipeline 中自动触发高优先行动任务 |

---

## FMEA YAML 导入/导出

### ACC-FMEA-02-01: 合规 YAML 导入

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一个合规的 FMEA YAML 文件包含一个或多个 FMEA 条目 |
| **WHEN** | 用户通过 CLI/API 执行导入 |
| **THEN** | 系统解析 YAML，通过 schema 校验，在 store 中创建对应的 FMEA 条目 |

### ACC-FMEA-02-02: 不合规 YAML 拒绝 + 详细错误报告

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一个不合规的 YAML 文件（如 rpn_severity=15 超出 1-10 范围） |
| **WHEN** | 用户执行导入 |
| **THEN** | 系统拒绝导入，返回详细错误报告包含行号和错误类型 |

### ACC-FMEA-02-03: YAML 导出

| 属性 | 值 |
|------|-----|
| **GIVEN** | 存储中的一批 FMEA 条目 |
| **WHEN** | 用户请求 YAML 导出 |
| **THEN** | 系统生成完整的 YAML 文件，包含所有强制字段，rpn_total 为自动计算值，ap_priority 为 AIAG-VDA 矩阵计算结果 |

---

## FMEA 跨 ECU 失效链

### ACC-FMEA-03-01: 失效链有向图可视化

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一个 FMEA 条目定义了跨 ECU 失效链（ECU_BMS → ECU_VCU → ECU_BMS） |
| **WHEN** | 用户查看 FMEA 详情页 |
| **THEN** | 页面展示有向图可视化，包含 3 个节点和 2 条有向边，每个节点显示 ecu_id、signal_name、failure_mode |

### ACC-FMEA-03-02: 控制措施变更级联标记

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条跨 ECU 失效链包含 3 个节点，节点 2 的控制措施被更新 |
| **WHEN** | 节点更新提交 |
| **THEN** | 系统自动将链上所有 3 个节点的状态标记为 open（需重新分析），通知所有节点负责人重新评审 |

---

## PFMEA

### ACC-PK-01-01: 创建 PFMEA

| 属性 | 值 |
|------|-----|
| **GIVEN** | 创建一条 PFMEA 条目，设置 fmea_scope="process" |
| **WHEN** | 用户提交 |
| **THEN** | 系统返回 201 Created，条目归属 PFMEA 类别，共享 FMEA 通用字段模型 |

### ACC-PK-02-01: 缺少 process_step 拒绝

| 属性 | 值 |
|------|-----|
| **GIVEN** | 创建 PFMEA 条目时缺少 process_step 字段 |
| **WHEN** | 用户提交 |
| **THEN** | 系统返回 400 Bad Request，"PFMEA 条目必须包含 process_step" |

### ACC-PK-06-01: PFMEA AP=H → pipeline 任务

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条 PFMEA 条目，ap_priority=H |
| **WHEN** | 创建后 |
| **THEN** | 系统在 pipeline 中创建纠正措施任务，任务完成（verified）前不可跳过 |

### ACC-PK-09-01: PFMEA 批量导入

| 属性 | 值 |
|------|-----|
| **GIVEN** | 用户上传一个过程流程图 CSV/YAML 文件，包含多个工序定义 |
| **WHEN** | 执行批量导入 |
| **THEN** | 系统为每个工序生成一条 PFMEA 条目草案（status=open），保留工序间的顺序关系 |

### ACC-PK-10-01: DFMEA/PFMEA 统一仪表盘过滤

| 属性 | 值 |
|------|-----|
| **GIVEN** | 知识库中存在 DFMEA 和 PFMEA 条目 |
| **WHEN** | 用户在仪表盘选择按 fmea_scope 过滤 |
| **THEN** | 仪表盘分别展示 DFMEA 和 PFMEA 的数量及统计指标 |

---

## CI/CD 集成

### ACC-CI-01-01: Pre-commit 代码路径警告

| 属性 | 值 |
|------|-----|
| **GIVEN** | 代码变更涉及 `src/thermal/battery_monitor.c`，该文件关联了一条标记了 code_path_stale 的知识条目 |
| **WHEN** | pre-commit 执行 |
| **THEN** | 输出 WARNING 信息 "KB-<ID>: 知识条目关联的代码路径已变更，请审查该条目"，提交继续执行 |

### ACC-CI-02-01: Commit-msg 有效 KB-ID 通过

| 属性 | 值 |
|------|-----|
| **GIVEN** | 提交信息中包含 `KB-550e8400` 引用，且该 ID 在系统中存在 |
| **WHEN** | commit-msg 钩子执行 |
| **THEN** | 校验通过，系统自动在 KB 条目中追加变更日志 |

### ACC-CI-02-02: Commit-msg 无效 FMEA-ID 阻断

| 属性 | 值 |
|------|-----|
| **GIVEN** | 提交信息中包含 `FMEA-2026-9999`，该 ID 在系统中不存在 |
| **WHEN** | commit-msg 钩子执行 |
| **THEN** | 系统阻断提交（blocker 级别），提示 "FMEA-ID FMEA-2026-9999 在系统中不存在" |

### ACC-CI-02-03: 代码变更无引用的警告

| 属性 | 值 |
|------|-----|
| **GIVEN** | 提交涉及 .c 代码变更但提交信息中无任何知识引用 |
| **WHEN** | commit-msg 钩子执行 |
| **THEN** | 系统输出 WARNING "代码变更建议引用关联知识条目（KB-xxx / LL-xxx / FMEA-xxx）"，不阻断提交 |

### ACC-CI-03-01: PR FMEA YAML 校验

| 属性 | 值 |
|------|-----|
| **GIVEN** | PR 中包含 FMEA YAML 变更 |
| **WHEN** | PR check 执行 |
| **THEN** | 执行 YAML schema 校验，通过 comment（如 "✅ FMEA YAML 校验通过，共解析 3 条，其中新增 1 条"）汇报结果 |

### ACC-CI-03-02: PR 影响 FMEA 条目展示

| 属性 | 值 |
|------|-----|
| **GIVEN** | PR 中的代码变更影响了有关联 FMEA 条目的模块（如 src/can/ 关联 FMEA-2026-0012） |
| **WHEN** | PR check 执行 |
| **THEN** | PR comment 中展示 "⚠️ 本次代码变更影响以下 FMEA 条目：FMEA-2026-0012" |

### ACC-CI-04-01: Merge 阻止 ASIL_D FMEA 未确认

| 属性 | 值 |
|------|-----|
| **GIVEN** | 有一条 FMEA 条目 safety_level=ASIL_D、status=open（未被 analysis 或更高阶段确认） |
| **WHEN** | 用户执行 merge 操作 |
| **THEN** | 系统阻止 merge，返回 "ASIL_D FMEA 条目 FMEA-2026-0042 处于 open 状态，不允许合并" |

### ACC-CI-04-02: Merge 阻止 LL 待审查

| 属性 | 值 |
|------|-----|
| **GIVEN** | 有一条 LL 条目因 DTC 售后计数阈值被标记为 pending_review |
| **WHEN** | 用户执行 merge 操作 |
| **THEN** | 系统阻止 merge，返回 "LL 条目 LL-0042 因售后 DTC 回灌需审阅，不允许合并" |

---

## 知识债务仪表盘

### ACC-DASH-01-01: 核心指标展示

| 属性 | 值 |
|------|-----|
| **GIVEN** | 知识库中共有 50 条知识条目，状态为 published=25, approved=5, draft=10, review_pending=2, deprecated=5, archived=3 |
| **WHEN** | 用户加载仪表盘 |
| **THEN** | 仪表盘展示总量 50，按 6 状态分解的柱状图，及平均置信度（整体和按 ASIL 等级） |

### ACC-DASH-01-02: LL 严重度分解

| 属性 | 值 |
|------|-----|
| **GIVEN** | 存在 3 条未关闭的 critical LL 条目 |
| **WHEN** | 用户查看仪表盘 |
| **THEN** | 仪表盘展示未关闭 LL 总数及按 severity 分解的数据，critical 级高亮显示 |

### ACC-DASH-03-02: 零测试覆盖清单

| 属性 | 值 |
|------|-----|
| **GIVEN** | 有 5 条知识条目没有任何测试层级关联 |
| **WHEN** | 用户查看"零测试覆盖"列表 |
| **THEN** | 系统列出这 5 条知识条目及其 safety_level 和创建时间 |

---

## 审计日志

### ACC-CROSS-04-01: 操作审计日志

| 属性 | 值 |
|------|-----|
| **GIVEN** | 用户创建一条 KB 条目，修改一次 LL 条目状态，更新一条 FMEA 条目的 current_control |
| **WHEN** | 审计日志查询 |
| **THEN** | 返回 3 条日志记录，每条包含操作人 user_id、操作时间、操作类型（create/status_transition/update）、条目 ID、变更前后关键字段摘要 |

---

## 权限模型

### ACC-CROSS-05-01: Reader 不可编辑

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一个 role=reader 的用户 |
| **WHEN** | 该用户尝试编辑一条知识条目 |
| **THEN** | 系统返回 403 Forbidden，提示"无编辑权限" |

### ACC-CROSS-05-02: Reviewer 可确认测试种子

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一个 role=reviewer 的用户 |
| **WHEN** | 该用户查看系统自动生成的 auto_generated 测试种子 |
| **THEN** | 该用户可进行确认/标记已覆盖/删除操作 |

### ACC-CROSS-05-03: Contributor 不可确认种子

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一个 role=contributor 的用户 |
| **WHEN** | 该用户查看系统自动生成的 auto_generated 测试种子 |
| **THEN** | 该用户只可查看，无法执行确认/删除操作 |

---

## 跨模块引用完整性

### ACC-CROSS-03-01: 被引用条目拒绝物理删除

| 属性 | 值 |
|------|-----|
| **GIVEN** | KB 条目被 LL 条目引用，FMEA 条目被 KB 条目引用 |
| **WHEN** | 用户尝试物理删除被引用的 KB 条目 |
| **THEN** | 系统返回 409 Conflict，"条目存在交叉引用，无法物理删除" |

### ACC-CROSS-03-02: 软删除允许

| 属性 | 值 |
|------|-----|
| **GIVEN** | KB 条目被 LL 条目引用 |
| **WHEN** | 用户执行软删除（逻辑删除） |
| **THEN** | 系统允许操作，已删除条目在交叉引用关系中仍可访问 |

---

## TCL 预留接口

### ACC-CROSS-01-01: 空 TCL 字段不影响功能

| 属性 | 值 |
|------|-----|
| **GIVEN** | 一条知识条目包含空的 tcl_doc_slot 字段 |
| **WHEN** | 用户通过 API 查询该条目 |
| **THEN** | tcl_doc_slot 字段存在但值为空，不影响其他功能运行 |

---

## 汇总统计

| 模块 | Phase 1 ACC 条目数 |
|------|:------------------:|
| KB CRUD + 元数据 + 标识 | 9 |
| KB 状态机 + ASIL 门禁 | 5 |
| KB 版本快照链 | 2 |
| KB HW BOM 标签 | 2 |
| KB DTC 检索 | 2 |
| KB 安全目标追溯 | 2 |
| KB 置信度衰减 | 4 |
| LL 基础 CRUD + 闭环节点 | 6 |
| LL 搜索与分类 | 1 |
| FMEA 基础 CRUD + RPN + AP | 5 |
| FMEA YAML 导入/导出 | 3 |
| FMEA 跨 ECU 失效链 | 2 |
| PFMEA | 5 |
| CI/CD 集成 | 8 |
| 知识债务仪表盘 | 3 |
| 审计日志 | 1 |
| 权限模型 | 3 |
| 跨模块引用完整性 | 2 |
| TCL 预留接口 | 1 |
| **合计** | **66** |
