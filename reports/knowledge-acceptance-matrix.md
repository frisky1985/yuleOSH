# yuleOSH 知识管理模块 — 验收判定矩阵

> **版本**: v1.1.0  
> **日期**: 2026-06-20  
> **关联 Spec**: `spec-knowledge-management.md` (v1.1.0)  
> **规范**: 每条 SHALL 条目配套 GIVEN/WHEN/THEN 判定场景  

---

## 目录

- [KB 模块验收判定](#kb-模块验收判定)
- [LL 模块验收判定](#ll-模块验收判定)
- [FMEA 模块验收判定](#fmea-模块验收判定)
- [CI/CD 验收判定](#cicd-验收判定)
- [仪表盘验收判定](#仪表盘验收判定)
- [跨模块验收判定](#跨模块验收判定)

---

## KB 模块验收判定

### KBS-01: 知识条目基础 CRUD

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KBS-01-01 |
| **GIVEN** | 一个已认证的用户 |
| **WHEN** | 该用户创建一个新的知识条目，填写 title、content、safety_level 并提交 |
| **THEN** | 系统返回 201 Created，包含完整的条目 JSON（含自动生成的 id、created_at、version = 1.0.0、confidence = 100） |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KBS-01-02 |
| **GIVEN** | 一条已存在且被其他模块引用的知识条目 |
| **WHEN** | 用户执行物理删除操作 |
| **THEN** | 系统拒绝操作，返回 409 Conflict，并提示该条目存在引用依赖 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KBS-01-03 |
| **GIVEN** | 一条未被任何模块引用的知识条目 |
| **WHEN** | 用户执行逻辑删除操作 |
| **THEN** | 系统返回 200 OK，将 is_deleted 标记设为 true，deleted_at 记录当前时间，常规搜索不再返回该条目 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KBS-01-04 |
| **GIVEN** | 创建知识条目的 API 请求缺少 author_id 字段或 reviewer_id 字段 |
| **WHEN** | 用户提交创建请求 |
| **THEN** | 系统返回 400 Bad Request，错误信息包含 "author_id is required" 或 "reviewer_id is required"，并阻止创建 |

---

### KBS-02: 知识条目标识

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KBS-02-01 |
| **GIVEN** | 一条新创建的知识条目 |
| **WHEN** | 分配其 id |
| **THEN** | id 为 UUID v4 格式，在整个生命周期中保持不变 |

---

### KBS-03: 知识条目元数据结构

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KBS-03-01 |
| **GIVEN** | 创建知识条目的 API 请求 |
| **WHEN** | 请求中缺少 safety_level 字段 |
| **THEN** | 系统返回 400 Bad Request，错误信息包含 "safety_level is required" |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KBS-03-02 |
| **GIVEN** | 创建知识条目的 API 请求 |
| **WHEN** | 请求中包含了 tcl_doc_slot 字段且格式正确 |
| **THEN** | 系统接受并存储该字段，不校验其内容是否为空（预留字段） |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KBS-03-03 |
| **GIVEN** | 创建知识条目的 API 请求 |
| **WHEN** | 请求中包含了 hw_bom 字段（JSONB 数组格式：[{"platform":"TDA4VM","chip":"TDA4VM-Q1","version":"1.2"}]） |
| **THEN** | 系统接受并存储该字段，支持按 JSONB 路径进行过滤和组合筛选 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KBS-03-04 |
| **GIVEN** | 新创建的知识条目 |
| **WHEN** | 查询其 confidence 字段 |
| **THEN** | confidence 为整数 100（范围 0-100），非浮点数

---

### KB-01: 语义多模态搜索

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-01-01 |
| **GIVEN** | 知识库中存在多条条目，其中一条标题包含 "电池过压保护"，另一条标题包含 "空调控制逻辑" |
| **WHEN** | 用户输入自然语言查询 "锂电池过充保护怎么办" 执行语义搜索 |
| **THEN** | 搜索结果排序中，"电池过压保护" 条目排在 "空调控制逻辑" 之前，且搜索结果包含 similary_score 字段 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-01-02 |
| **GIVEN** | 两条 confidence 不同的条目，一条 confidence=100，另一条 confidence=40，两者语义相似度相同 |
| **WHEN** | 执行语义搜索 |
| **THEN** | confidence=100 的条目排在 confidence=40 的条目之前 |

---

### KB-02: ASIL 等级属性与生命周期门禁

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-02-01 |
| **GIVEN** | 一条 safety_level=ASIL_B 的知识条目当前状态为 review |
| **WHEN** | 用户尝试将其状态从 review 切换为 approved |
| **THEN** | 系统检查是否存在至少一次独立评审记录；若无，返回 403 Forbidden，提示 "ASIL B 条目要求至少一次独立评审" |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-02-02 |
| **GIVEN** | 一条 safety_level=ASIL_D 的知识条目 |
| **WHEN** | 用户提交该条目从 review 到 approved 的转换 |
| **THEN** | 系统要求至少两名不同 reviewer 的 sign-off 记录，缺少时返回 403 Forbidden |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-02-03 |
| **GIVEN** | 一条 safety_level=QM 的知识条目 |
| **WHEN** | 用户直接将其状态从 draft 切换为 approved |
| **THEN** | 系统允许该操作，无需评审记录 |

---

### KB-03: 版本快照链

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-03-01 |
| **GIVEN** | 一条知识条目，已执行两次更新 |
| **WHEN** | 用户查询版本历史 |
| **THEN** | 系统返回三个版本记录（v1.0.0, v1.0.1, v1.0.2），每个版本包含该时刻的完整内容拷贝 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-03-02 |
| **GIVEN** | 一条知识条目当前版本为 v1.0.5 |
| **WHEN** | 用户执行回滚到 v1.0.3 |
| **THEN** | 系统创建一个 v1.0.6 版本，其内容与 v1.0.3 完全一致，而非直接修改现有版本 |

---

### KB-04: 代码路径反向索引

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-04-01 |
| **GIVEN** | 一条知识条目关联了源代码路径 `src/thermal/battery_monitor.c` |
| **WHEN** | 用户提交一次修改该文件的 commit（pre-commit 阶段检测到文件变更） |
| **THEN** | 系统将相关知识条目的 confidence 下调 10（0-100 标尺），并标记 code_path_stale 为 true |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-04-02 |
| **GIVEN** | 一条知识条目绑定了三个源文件路径 |
| **WHEN** | 用户通过反向查询接口输入 `src/thermal/battery_monitor.c` |
| **THEN** | 系统返回该路径关联的所有知识条目列表 |

---

### KB-05: HW BOM 标签系统（多平台 JSONB）

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-05-01 |
| **GIVEN** | 知识条目设置了 hw_bom=[{"platform":"TDA4VM","chip":"TDA4VM-Q1","version":"1.2"}] |
| **WHEN** | 用户在 HW BOM 过滤器中通过 JSONB 路径选择 chip=`TDA4VM-Q1` |
| **THEN** | 系统返回所有 JSONB 数组中包含匹配 chip 值的知识条目 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-05-02 |
| **GIVEN** | 三条条目分别绑定不同硬件平台：A=[{platform:"TDA4VM"}], B=[{platform:"S32K"}], C=[{platform:"TDA4VM"},{platform:"S32K"}] |
| **WHEN** | 用户按 platform="TDA4VM" 过滤 |
| **THEN** | 系统返回条目 A 和 C（多平台条目通过匹配），不返回条目 B |

---

### KB-06: DTC 一级检索维度

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-06-01 |
| **GIVEN** | 知识条目关联了 DTC `P0101` |
| **WHEN** | 用户在 DTC 搜索入口输入 `P0101` |
| **THEN** | 系统返回该知识条目，且结果页展示关联的 FMEA 条目和 LL 条目计数 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-06-02 |
| **GIVEN** | 知识条目关联了 DTC `P0101`、`P0102`、`P0103` |
| **WHEN** | 用户在 DTC 搜索入口输入 `P01`（前缀模糊） |
| **THEN** | 系统返回所有关联 `P01xx` 系列 DTC 的知识条目 |

---

### KB-07: 知识置信度衰减

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-07-01 |
| **GIVEN** | 一条知识条目，`confidence=90`（0-100 标尺），策略为 `usage_based`，在评估周期内无引用命中 |
| **WHEN** | 衰减评估 cron 执行（24 小时后） |
| **THEN** | `confidence` 变为 88（每周期移除 2 点），其他字段不变 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-07-02 |
| **GIVEN** | 一条知识条目，`confidence=32`，策略为 `usage_based`，在最近的评估周期内持续无引用命中 |
| **WHEN** | 衰减评估连续执行两次 |
| **THEN** | `confidence` 降至 28，系统自动将条目加入"知识债务审查队列" |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-07-03 |
| **GIVEN** | 一条知识条目，`confidence=80`，策略为 `usage_based`，在某评估周期内有引用或搜索命中 |
| **WHEN** | 衰减评估 cron 执行 |
| **THEN** | 衰减计数器重置，`confidence` 保持不变（仍为 80） |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-07-04 |
| **GIVEN** | 创建知识条目时指定了 `linear` 或 `step` 衰减策略 |
| **WHEN** | 系统执行 schema 校验 |
| **THEN** | 系统拒绝，返回错误信息 "仅支持 usage_based 衰减策略，linear/step 已废弃" |

---

### KB-08: 置信度衰减恢复

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-08-01 |
| **GIVEN** | 一条 `confidence=20`（0-100 标尺）、状态为 `deprecated` 的知识条目 |
| **WHEN** | 人工审查后，用户切换状态为 `approved` 或 `published` |
| **THEN** | `confidence` 重置为 100，deacy 周期重新开始，审计日志记录操作人和时间 |

---

### KB-09: OTA 版本双轨绑定

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-09-01 |
| **GIVEN** | 一条知识条目绑定了 OTA 版本 `OTA-1.2.0` |
| **WHEN** | OTA 版本升级到 `OTA-2.0.0`，系统触发版本迁移 |
| **THEN** | 旧条目（`OTA-1.2.0`）标记为 `deprecated`，新条目（`OTA-2.0.0`）创建为副本，`confidence=80`（0-100 标尺） |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-09-02 |
| **GIVEN** | 知识库中存在分别绑定 `OTA-1.2.0` 和 `OTA-2.0.0` 的知识条目 |
| **WHEN** | 用户在搜索中选择目标 OTA 版本为 `OTA-2.0.0` |
| **THEN** | 搜索结果优先展示 `OTA-2.0.0` 绑定的条目 |

---

### KB-10: 五层测试映射

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-10-01 |
| **GIVEN** | 一条知识条目关联了 3 个 HIL 测试用例和 2 个 Unit 测试用例 |
| **WHEN** | 用户查看知识条目详情页 |
| **THEN** | 详情页展示 HIL 层（3用例，包含 pass/fail/not_run 统计）和 Unit 层（2用例，统计数据） |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-10-02 |
| **GIVEN** | 一条知识条目的 Unit 测试层级出现一个 fail 结果 |
| **WHEN** | 测试结果回写 |
| **THEN** | 系统自动将该知识条目的 confidence 下调 15（0-100 标尺，下限 0） |

---

### KB-11: AUTOSAR 层级映射

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-11-01 |
| **GIVEN** | 一条知识条目绑定了 ASW 和 RTE 两个 AUTOSAR 层级 |
| **WHEN** | 用户在过滤器中选择 ASW |
| **THEN** | 系统返回该条目（因为 ASW 包含在集合中） |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-11-02 |
| **GIVEN** | 知识条目 A 绑定 {ASW, RTE}，条目 B 绑定 {BSW} |
| **WHEN** | 用户选择 ASW + RTE 组合过滤 |
| **THEN** | 返回条目 A 和包含 ASW 或 RTE 的所有条目；不返回仅含 BSW 的条目 |

---

### KB-13: 知识条目审核流程

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-13-01 |
| **GIVEN** | 一条知识条目当前状态为 `draft` |
| **WHEN** | 用户提交审核 |
| **THEN** | 状态变为 `review_pending`，pipeline 审批任务自动触发，审计日志记录操作人和时间 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-13-02 |
| **GIVEN** | 一条知识条目当前状态为 `review_pending` |
| **WHEN** | 审核通过 |
| **THEN** | 状态变为 `approved`，审计日志记录审核人和时间 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-13-03 |
| **GIVEN** | 一条知识条目当前状态为 `approved` |
| **WHEN** | 用户执行发布操作 |
| **THEN** | 状态变为 `published` |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-13-04 |
| **GIVEN** | 一条知识条目当前状态为 `published` |
| **WHEN** | 用户标记过期 |
| **THEN** | 状态变为 `deprecated` |

### KB-14: 知识条目与 spec 模块追溯

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-14-01 |
| **GIVEN** | 一个已发布的知识条目关联了 spec 条目 SP-42 |
| **WHEN** | SP-42 的内容发生版本变更 |
| **THEN** | 系统向知识条目作者发送一致性审查通知，包含旧版/新版 diff 摘要 |

---

### KB-15: ASIL 等级与版本发布的绑定

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KB-15-01 |
| **GIVEN** | OTA 版本 `OTA-2.0.0` 绑定了 3 条 ASIL_D 知识条目，其中 1 条状态不是 approved 或 published |
| **WHEN** | 用户执行发布批准 |
| **THEN** | 系统阻止发布操作，返回发布检查报告，列出未达标的知识条目及其 safety_level |

### KBS-16: 安全目标（Safety Goal）与 HARA 追溯

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KBS-16-01 |
| **GIVEN** | 一条知识条目关联了安全目标 `SG-BRAKE-001` |
| **WHEN** | 用户通过安全目标 ID 反向检索 |
| **THEN** | 系统返回所有关联 `SG-BRAKE-001` 的知识条目清单 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KBS-16-02 |
| **GIVEN** | 安全目标 `SG-BRAKE-001` 发生了版本变更 |
| **WHEN** | 系统检测到变更 |
| **THEN** | 系统向关联知识条目的作者发送一致性审查通知，包含变更摘要 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-KBS-16-03 |
| **GIVEN** | 一条知识条目绑定了安全目标和 HARA 分析条目 |
| **WHEN** | 用户在详情页查看知识条目 |
| **THEN** | 详情页展示关联的安全目标清单，含 safety_goal_id、hazard_id 和 asil_decomposition（如适用） |

---

## LL 模块验收判定

### LL-01: LL 条目基础结构

| 条目 | 内容 |
|------|------|
| **ID** | ACC-LL-01-01 |
| **GIVEN** | 一个已认证的用户 |
| **WHEN** | 用户创建一个新的 LL 条目，包含 title、description、root_cause、category、severity（枚举含 catastrophic）等字段 |
| **THEN** | 系统返回 201 Created，包含完整的 LL 条目，closure_status 默认为 open（8 状态生命周期），created_at 为当前时间 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-LL-01-02 |
| **GIVEN** | 创建 LL 条目的请求缺少 root_cause 字段 |
| **WHEN** | 用户提交 |
| **THEN** | 系统返回 400 Bad Request，"root_cause is required" |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-LL-01-03 |
| **GIVEN** | 创建 LL 条目的请求中 severity 设为 `catastrophic` |
| **WHEN** | 用户提交 |
| **THEN** | 系统接受该值（5 级严重度：info/minor/major/critical/catastrophic）

---

### LL-02: LL 条目的 ASIL 门禁

| 条目 | 内容 |
|------|------|
| **ID** | ACC-LL-02-01 |
| **GIVEN** | 一条 LL 条目，safety_level=ASIL_B，当前 closure_status=verified |
| **WHEN** | 用户尝试将其 closure_status 从 verified 切换为 closed |
| **THEN** | 系统要求第三方签字确认记录，缺少时返回 403 Forbidden，提示 "ASIL B LL 闭合需要独立签字确认" |

---

### LL-03: 自动捕获 — Bug → LL 回灌

| 条目 | 内容 |
|------|------|
| **ID** | ACC-LL-03-01 |
| **GIVEN** | 一个 Bug 被标记为 root_cause_identified，且 root_cause 字段已填写 |
| **WHEN** | CI 钩子检测到状态变更 |
| **THEN** | 系统自动创建一条 LL 条目草案，source_ref 指向该 Bug，root_cause 预填 Bug 中的根因，status=open，并通知 Bug 负责人审阅 |

---

### LL-04: LL → Test Seed

| 条目 | 内容 |
|------|------|
| **ID** | ACC-LL-04-01 |
| **GIVEN** | 一条 LL 条目的 closure_status 从 verified 切换为 closed |
| **WHEN** | 状态变更完成 |
| **THEN** | 系统在 evidence 模块中自动生成一条"知识驱动测试种子"记录，包含 LL 的 root_cause、建议测试场景、推荐测试层级，并标记为 auto_generated |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-LL-04-02 |
| **GIVEN** | 系统已生成 auto_generated 测试种子 |
| **WHEN** | reviewer 查看该种子 |
| **THEN** | reviewer 可确认并转化为正式测试用例，或标记为已覆盖、或拒绝删除 |

---

### LL-05: DTC 关联

| 条目 | 内容 |
|------|------|
| **ID** | ACC-LL-05-01 |
| **GIVEN** | 一条 LL 条目关联了 DTC `P0101` |
| **WHEN** | 用户在 KB 模块中执行 DTC 搜索 `P0101` |
| **THEN** | 搜索结果中包含该 LL 条目（与 KB 条目并列返回） |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-LL-05-02 |
| **GIVEN** | 一条 LL 条目关联了 DTC `P0101`，且该 DTC 的售后计数超过了告警阈值 |
| **WHEN** | 系统运行 DTC 阈值检查 |
| **THEN** | 该 LL 条目标记为 `pending_review`，通知 assigned_to 用户 |

---

### LL-06: 售后闭环 — DTC → FMEA → LL 自动回灌

| 条目 | 内容 |
|------|------|
| **ID** | ACC-LL-06-01 |
| **GIVEN** | 售后工单系统上报 DTC `U0100` 命中，且 KB 和 FMEA 中均有该 DTC 的条目 |
| **WHEN** | 回灌管道处理该事件 |
| **THEN** | 系统检查 KB 和 FMEA 条目后，若不存在针对该 DTC 的 LL 条目，自动创建一条 open 状态的 LL 条目，source_ref 指向售后工单 ID，并记录审计日志 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-LL-06-02 |
| **GIVEN** | 售后工单系统上报 DTC `U0100` 命中 |
| **WHEN** | 回溯管道处理时发现已存在关联该 DTC 的 LL 条目 |
| **THEN** | 系统不创建新条目，仅更新现有 LL 条目的售后引用计数，并记录审计日志 |

---

### LL-07: LL 闭环节点

| 条目 | 内容 |
|------|------|
| **ID** | ACC-LL-07-01 |
| **GIVEN** | 一条 LL 条目当前 closure_status 为 open |
| **WHEN** | 用户按 8 状态链（open→investigating→action_planned→implemented→mitigated→verified→closed）逐步转换 |
| **THEN** | 每一步记录 transition_timestamp、operator、action_description、verification_method |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-LL-07-02 |
| **GIVEN** | 一条 LL 条目从 verified 切换为 closed |
| **WHEN** | 闭合完成 |
| **THEN** | 系统在 evidence 模块中生成"LI 知识闭合证据记录"，包含闭合时间、措施描述、验证方式 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-LL-07-03 |
| **GIVEN** | 一条 LL 条目，当前状态为 open |
| **WHEN** | 用户直接将其标记为 rejected 并填写驳回原因 |
| **THEN** | 系统允许该操作；从 rejected 状态可重新切换为 open 重新发起分析 |

---

### LL-08: LL 搜索与分类

| 条目 | 内容 |
|------|------|
| **ID** | ACC-LL-08-01 |
| **GIVEN** | 知识库中存在 10 条 LL 条目，分布在不同 category、severity 下 |
| **WHEN** | 用户在 LL 界面上选择 category=design、severity=critical |
| **THEN** | 系统仅返回同时满足两个过滤条件的 LL 条目 |

---

## FMEA 模块验收判定

### FMEA-01: FMEA 条目基础结构

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-01-01 |
| **GIVEN** | 创建 FMEA 条目的请求 |
| **WHEN** | 请求中缺少 failure_mode 字段 |
| **THEN** | 系统返回 400 Bad Request，"failure_mode is required" |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-01-02 |
| **GIVEN** | 创建 FMEA 条目的请求包含所有必要字段 |
| **WHEN** | 用户提交 |
| **THEN** | 系统返回 201 Created，fmea_id 格式为 "FMEA-YYYY-NNNN"，rpn_total 自动计算为 severity × occurrence × detection，status 默认为 open（6 状态生命周期：open/analysis/action_planned/action_done/verified/closed） |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-01-03 |
| **GIVEN** | 创建 FMEA 条目的请求包含 ap_severity=8, ap_occurrence=4, ap_detection=6 |
| **WHEN** | 用户提交 |
| **THEN** | 系统根据 AIAG-VDA AP 矩阵自动计算 ap_priority="H"（高优先） |

---

### FMEA-02: FMEA as Code（YAML 格式）

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-02-01 |
| **GIVEN** | 一个合规的 FMEA YAML 文件包含一个或多个 FMEA 条目 |
| **WHEN** | 用户通过 CLI/API 执行导入 |
| **THEN** | 系统解析 YAML，通过 schema 校验，在 store 中创建对应的 FMEA 条目 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-02-02 |
| **GIVEN** | 一个不合规的 YAML 文件（如 rpn_severity=15 超出 1-10 范围） |
| **WHEN** | 用户执行导入 |
| **THEN** | 系统拒绝导入，返回详细错误报告包含行号和错误类型 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-02-03 |
| **GIVEN** | 存储中的一批 FMEA 条目 |
| **WHEN** | 用户请求 YAML 导出 |
| **THEN** | 系统生成完整的 YAML 文件，包含所有强制字段，rpn_total 为自动计算值，ap_priority 为 AIAG-VDA 矩阵计算结果 |

---

### FMEA-03: 跨 ECU 失效链定义

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-03-01 |
| **GIVEN** | 一个 FMEA 条目定义了跨 ECU 失效链（ECU_BMS → ECU_VCU → ECU_BMS） |
| **WHEN** | 用户查看 FMEA 详情页 |
| **THEN** | 页面展示有向图可视化，包含 3 个节点和 2 条有向边，每个节点显示 ecu_id、signal_name、failure_mode |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-03-02 |
| **GIVEN** | 一条跨 ECU 失效链包含 3 个节点，节点 2 的控制措施被更新 |
| **WHEN** | 节点更新提交 |
| **THEN** | 系统自动将链上所有 3 个节点的状态标记为 open（需重新分析），通知所有节点负责人重新评审 |

---

### FMEA-04: ASIL 等级的 FMEA 门禁

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-04-01 |
| **GIVEN** | 一条 FMEA 条目，ap_priority=H，safety_level=ASIL_C |
| **WHEN** | 用户尝试将其状态从 action_done 切换为 verified |
| **THEN** | 系统要求附加"措施有效性验证证据"（来自 evidence 模块），缺少时返回 403 Forbidden |

---

### FMEA-05: AIAG-VDA Action Priority

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-05-01 |
| **GIVEN** | 多条 FMEA 条目，各有不同的 ap_severity, ap_occurrence, ap_detection |
| **WHEN** | 系统创建/更新条目 |
| **THEN** | 系统基于 AIAG-VDA AP 矩阵自动计算 ap_priority（H/M/L），H 级在仪表盘高亮标识 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-05-02 |
| **GIVEN** | 一条 FMEA 条目，ap_priority=H |
| **WHEN** | 系统创建该条目后 |
| **THEN** | 系统在 pipeline 中自动触发高优先行动任务 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-05-03 |
| **GIVEN** | 一条 FMEA 条目，ap_severity=9, ap_occurrence=3, ap_detection=5 |
| **WHEN** | 用户查看 AP 矩阵可视化面板 |
| **THEN** | 面板展示该 S/O/D 组合在 AP 矩阵中的落点（M 级 - 中优先） |

---

### FMEA-06: 跨 ECU 失效链版本管理

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-06-01 |
| **GIVEN** | 一条跨 ECU 失效链当前为 v1.0.3 |
| **WHEN** | 链上任一节点被修改并提交 |
| **THEN** | 整条链生成新版本快照 v1.0.4，系统支持对比 v1.0.3 和 v1.0.4 的节点级别 diff |

---

### FMEA-07: DTC → FMEA 映射

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-07-01 |
| **GIVEN** | 多条 FMEA 条目关联了 DTC `P0101` |
| **WHEN** | 用户在 DTC 搜索入口输入 `P0101` 并选择查看 FMEA 映射 |
| **THEN** | 系统展示"DTC 失效模式矩阵"视图，展示 `P0101` → 各 FMEA 失效模式的一对多映射 |

---

### FMEA-08: FMEA → Test → Telemetry 闭环

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-08-01 |
| **GIVEN** | 一条 FMEA 条目，ap_priority=H |
| **WHEN** | 该条目状态变更为 action_planned |
| **THEN** | 系统在 evidence 模块中自动创建一条测试需求记录，包含 failure_mode 和 recommended_action |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-08-02 |
| **GIVEN** | 一条 FMEA 条目关联的测试用例执行通过，遥测数据中未发现匹配模式 |
| **WHEN** | 测试结果回写 FMEA |
| **THEN** | FMEA 条目的 current_control 有效性判定更新为 "effective" |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-08-03 |
| **GIVEN** | 遥测数据中检测到与某 FMEA 失效模式匹配的模式 |
| **WHEN** | 系统执行遥测匹配检查后 |
| **THEN** | 系统自动通知该 FMEA 条目的负责人，附加遥测数据摘要，要求重新评估 |

---

### FMEA-09: 轻量增量 FMEA

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-09-01 |
| **GIVEN** | 一条已存在的 FMEA 条目（ID: FMEA-2026-0042） |
| **WHEN** | 用户执行派生操作 |
| **THEN** | 系统创建一个新的 FMEA 条目，所有字段继承自父条目，parent_fmea_id 设为 FMEA-2026-0042，允许用户覆盖任意字段 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-FMEA-09-02 |
| **GIVEN** | PR 中修改了一个 FMEA YAML 文件 |
| **WHEN** | CI-FMEA 阶段执行 |
| **THEN** | PR comment 展示本次变更新增 2 条、修改 1 条、删除 0 条 FMEA 条目的差异摘要 |

### PK-01: PFMEA 基础需求

| 条目 | 内容 |
|------|------|
| **ID** | ACC-PK-01-01 |
| **GIVEN** | 创建一条 PFMEA 条目，设置 fmea_scope="process" |
| **WHEN** | 用户提交 |
| **THEN** | 系统返回 201 Created，条目归属 PFMEA 类别，共享 FMEA 通用字段模型 |

### PK-02: PFMEA 强制字段

| 条目 | 内容 |
|------|------|
| **ID** | ACC-PK-02-01 |
| **GIVEN** | 创建 PFMEA 条目时缺少 process_step 字段 |
| **WHEN** | 用户提交 |
| **THEN** | 系统返回 400 Bad Request，"PFMEA 条目必须包含 process_step" |

### PK-03: PFMEA 过程要素分析

| 条目 | 内容 |
|------|------|
| **ID** | ACC-PK-03-01 |
| **GIVEN** | 一条 PFMEA 条目描述了"焊锡温度超出范围"的失效原因 |
| **WHEN** | 用户创建该条目时标注了方法要素标签 [M]ethod |
| **THEN** | 系统接受该标签，failure_cause 字段记录过程要素分析结果 |

### PK-04: PFMEA 与 DFMEA 的追溯

| 条目 | 内容 |
|------|------|
| **ID** | ACC-PK-04-01 |
| **GIVEN** | 一条 PFMEA 条目关联了 DFMEA 条目 FMEA-2026-0042 |
| **WHEN** | FMEA-2026-0042 的控制措施更新 |
| **THEN** | 系统通知 PFMEA 条目负责人 |

### PK-05: PFMEA 与 Control Plan 关联

| 条目 | 内容 |
|------|------|
| **ID** | ACC-PK-05-01 |
| **GIVEN** | 一条 PFMEA 条目标注了 current_control 的控制类型为 preventive |
| **WHEN** | 用户请求控���计划草稿导出 |
| **THEN** | 系统生成包含该控制措施的初步控���计划文档 |

### PK-06: PFMEA Action Priority

| 条目 | 内容 |
|------|------|
| **ID** | ACC-PK-06-01 |
| **GIVEN** | 一条 PFMEA 条目，ap_priority=H |
| **WHEN** | 创建后 |
| **THEN** | 系统在 pipeline 中创建纠正措施任务，任务完成（verified）前不可跳过 |

### PK-07: PFMEA 批产验证

| 条目 | 内容 |
|------|------|
| **ID** | ACC-PK-07-01 |
| **GIVEN** | 一条 PFMEA 条目状态变为 verified |
| **WHEN** | 状态变更完成 |
| **THEN** | 系统在 evidence 模块中自动创建设备/工装的初始过程能力研究证据需求 |

### PK-08: PFMEA → Test Seed

| 条目 | 内容 |
|------|------|
| **ID** | ACC-PK-08-01 |
| **GIVEN** | 一条 PFMEA 条目，ap_priority=H |
| **WHEN** | 创建后 |
| **THEN** | 系统自动生成过程测试种子，包含失效模式、相关工位和推荐检验方法 |

### PK-09: PFMEA 批量导入

| 条目 | 内容 |
|------|------|
| **ID** | ACC-PK-09-01 |
| **GIVEN** | 用户上传一个过程流程图 CSV/YAML 文件，包含多个工序定义 |
| **WHEN** | 执行批量导入 |
| **THEN** | 系统为每个工序生成一条 PFMEA 条目草案（status=open），保留工序间的顺序关系 |

### PK-10: PFMEA DFMEA 统一仪表盘

| 条目 | 内容 |
|------|------|
| **ID** | ACC-PK-10-01 |
| **GIVEN** | 知识库中存在 DFMEA 和 PFMEA 条目 |
| **WHEN** | 用户在仪表盘选择按 fmea_scope 过滤 |
| **THEN** | 仪表盘分别展示 DFMEA 和 PFMEA 的数量及统计指标 |

---

## CI/CD 验收判定

### CI-01: Pre-commit 钩子

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CI-01-01 |
| **GIVEN** | 代码变更涉及 `src/thermal/battery_monitor.c`，该文件关联了一条标记了 code_path_stale 的知识条目 |
| **WHEN** | pre-commit 执行 |
| **THEN** | 输出 WARNING 信息 "KB-<ID>: 知识条目关联的代码路径已变更，请审查该条目"，提交继续执行 |

---

### CI-02: Commit-msg 钩子

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CI-02-01 |
| **GIVEN** | 提交信息中包含 `KB-550e8400` 引用，且该 ID 在系统中存在 |
| **WHEN** | commit-msg 钩子执行 |
| **THEN** | 校验通过，系统自动在 KB 条目中追加变更日志 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CI-02-02 |
| **GIVEN** | 提交信息中包含 `FMEA-2026-9999`，该 ID 在系统中不存在 |
| **WHEN** | commit-msg 钩子执行 |
| **THEN** | 系统阻断提交（blocker 级别），提示 "FMEA-ID FMEA-2026-9999 在系统中不存在" |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CI-02-03 |
| **GIVEN** | 提交涉及 .c 代码变更但提交信息中无任何知识引用 |
| **WHEN** | commit-msg 钩子执行 |
| **THEN** | 系统输出 WARNING "代码变更建议引用关联知识条目（KB-xxx / LL-xxx / FMEA-xxx）"，不阻断提交 |

---

### CI-03: PR 检查

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CI-03-01 |
| **GIVEN** | PR 中包含 FMEA YAML 变更 |
| **WHEN** | PR check 执行 |
| **THEN** | 执行 YAML schema 校验，通过 comment（如 "✅ FMEA YAML 校验通过，共解析 3 条，其中新增 1 条"）汇报结果 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CI-03-02 |
| **GIVEN** | PR 中的代码变更影响了有关联 FMEA 条目的模块（如 src/can/ 关联 FMEA-2026-0012） |
| **WHEN** | PR check 执行 |
| **THEN** | PR comment 中展示 "⚠️ 本次代码变更影响以下 FMEA 条目：FMEA-2026-0012" |

---

### CI-04: Merge 门禁

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CI-04-01 |
| **GIVEN** | 有一条 FMEA 条目 safety_level=ASIL_D、status=open（未被 analysis 或更高阶段确认） |
| **WHEN** | 用户执行 merge 操作 |
| **THEN** | 系统阻止 merge，返回 "ASIL_D FMEA 条目 FMEA-2026-0042 处于 open 状态，不允许合并" |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CI-04-02 |
| **GIVEN** | 有一条 LL 条目因 DTC 售后计数阈值被标记为 pending_review |
| **WHEN** | 用户执行 merge 操作 |
| **THEN** | 系统阻止 merge，返回 "LL 条目 LL-0042 因售后 DTC 回灌需审阅，不允许合并" |

---

### CI-05: Regression 测试映射报告

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CI-05-01 |
| **GIVEN** | Regression 阶段完成 |
| **WHEN** | 知识-测试映射报告生成 |
| **THEN** | 报告按知识条目分组列出：条目 KB-0042 → HIL: pass, SIL: pass, MIL: not_run, PIL: not_run, Unit: fail |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CI-05-02 |
| **GIVEN** | 一条知识条目的所有五层测试均为 pass |
| **WHEN** | Regression 报告处理完毕 |
| **THEN** | 系统将该知识条目的 confidence 上调 5（0-100 标尺，上限 100） |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CI-05-03 |
| **GIVEN** | 一条知识条目的 Unit 测试层级出现 fail |
| **WHEN** | Regression 报告处理完毕 |
| **THEN** | 系统将该知识条目的 confidence 下调 15（0-100 标尺，下限 0） |

---

## 仪表盘验收判定

### DASH-01: 核心指标

| 条目 | 内容 |
|------|------|
| **ID** | ACC-DASH-01-01 |
| **GIVEN** | 知识库中共有 50 条知识条目，状态为 published=25, approved=5, draft=10, review_pending=2, deprecated=5, archived=3 |
| **WHEN** | 用户加载仪表盘 |
| **THEN** | 仪表盘展示总量 50，按 6 状态分解的柱状图，及平均置信度（整体和按 ASIL 等级） |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-DASH-01-02 |
| **GIVEN** | 存在 3 条未关闭的 critical LL 条目 |
| **WHEN** | 用户查看仪表盘 |
| **THEN** | 仪表盘展示未关闭 LL 总数及按 severity 分解的数据，critical 级高亮显示 |

---

### DASH-02: 置信度衰减趋势

| 条目 | 内容 |
|------|------|
| **ID** | ACC-DASH-02-01 |
| **GIVEN** | 系统运行了 7 天的衰减评估 |
| **WHEN** | 用户选择查看置信度趋势图（按周） |
| **THEN** | 图表展示 7 个数据点，可切换按 ASIL 等级或按模块过滤 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-DASH-02-02 |
| **GIVEN** | 某知识条目的 confidence 在一周内从 85 降至 74（降幅 > 10） |
| **WHEN** | 衰减评估完成 |
| **THEN** | 系统自动向该条目负责人发送通知，包含衰减趋势摘要 |

---

### DASH-03: 知识覆盖率

| 条目 | 内容 |
|------|------|
| **ID** | ACC-DASH-03-01 |
| **GIVEN** | 知识库中 50% 条目有 HIL 测试映射，30% 有 Unit 测试映射 |
| **WHEN** | 用户加载覆盖率面板 |
| **THEN** | 面板展示整体覆盖率（示例 55%）和按层级分解的覆盖率柱状图 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-DASH-03-02 |
| **GIVEN** | 有 5 条知识条目没有任何测试层级关联 |
| **WHEN** | 用户查看"零测试覆盖"列表 |
| **THEN** | 系统列出这 5 条知识条目及其 safety_level 和创建时间 |

---

### DASH-04: 售后闭环统计

| 条目 | 内容 |
|------|------|
| **ID** | ACC-DASH-04-01 |
| **GIVEN** | 系统运行了 30 天，记录了 500 次 DTC 命中 |
| **WHEN** | 用户加载售后闭环面板 |
| **THEN** | 面板展示 DTC 命中趋势折线图、DTC→FMEA→LL 回灌完成率（如 85%）、未回灌 DTC 清单 |

---

## 跨模块验收判定

### CROSS-01: TCL 预留接口

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CROSS-01-01 |
| **GIVEN** | 一条知识条目包含空的 tcl_doc_slot 字段 |
| **WHEN** | 用户通过 API 查询该条目 |
| **THEN** | tcl_doc_slot 字段存在但值为空，不影响其他功能运行 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CROSS-01-02 |
| **GIVEN** | 一条知识条目中 tcl_doc_slot 被误设为非预留用途的数据 |
| **WHEN** | schema 校验阶段 |
| **THEN** | 系统不阻止，但发出 warning（预留字段仅用于 TCL 认证文档） |

---

### CROSS-02: DTC → FMEA → LL 全链自动回灌

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CROSS-02-01 |
| **GIVEN** | 售后系统上报 DTC `P0101` |
| **WHEN** | 全链回灌执行 |
| **THEN** | 管道自动完成：检查 KB（DTC 关联知识条目）→ 检查 FMEA（关联失效模式）→ 创建 LL 草案（若没有）→ 记录审计日志 → 更新仪表盘统计 |

---

### CROSS-03: 模块间引用完整性

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CROSS-03-01 |
| **GIVEN** | KB 条目被 LL 条目引用，FMEA 条目被 KB 条目引用 |
| **WHEN** | 用户尝试物理删除被引用的 KB 条目 |
| **THEN** | 系统返回 409 Conflict，"条目存在交叉引用，无法物理删除" |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CROSS-03-02 |
| **GIVEN** | KB 条目被 LL 条目引用 |
| **WHEN** | 用户执行软删除（逻辑删除） |
| **THEN** | 系统允许操作，已删除条目在交叉引用关系中仍可访问 |

---

### CROSS-04: 审计日志

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CROSS-04-01 |
| **GIVEN** | 用户创建一条 KB 条目，修改一次 LL 条目状态，更新一条 FMEA 条目的 current_control |
| **WHEN** | 审计日志查询 |
| **THEN** | 返回 3 条日志记录，每条包含操作人 user_id、操作时间、操作类型（create/status_transition/update）、条目 ID、变更前后关键字段摘要 |

---

### CROSS-05: 权限模型

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CROSS-05-01 |
| **GIVEN** | 一个 role=reader 的用户 |
| **WHEN** | 该用户尝试编辑一条知识条目 |
| **THEN** | 系统返回 403 Forbidden，提示"无编辑权限" |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CROSS-05-02 |
| **GIVEN** | 一个 role=reviewer 的用户 |
| **WHEN** | 该用户查看系统自动生成的 auto_generated 测试种子 |
| **THEN** | 该用户可进行确认/标记已覆盖/删除操作 |

| 条目 | 内容 |
|------|------|
| **ID** | ACC-CROSS-05-03 |
| **GIVEN** | 一个 role=contributor 的用户 |
| **WHEN** | 该用户查看系统自动生成的 auto_generated 测试种子 |
| **THEN** | 该用户只可查看，无法执行确认/删除操作 |

---

> **变更记录**
> | 版本 | 日期 | 变更内容 | 作者 |
> |------|------|---------|------|
> | v1.0.0 | 2026-06-20 | 初始验收矩阵 | 小马 🐴 |
> | v1.1.0 | 2026-06-20 | 老陈审查对齐：LL 8 状态（含 mitigated，ACC-LL-01~07）、KB 6 状态（ACC-KB-13）、FMEA 6 状态 + AP（ACC-FMEA-01/04/05/08）、SMALLINT 置信度（ACC-KB-07/08/09/10、ACC-CI-05）、HW BOM JSONB（ACC-KB-05）、CI-02 新增验收（ACC-CI-02-01~03）、PFMEA PK-01~10、KBS-16 HARA/安全目标（ACC-KBS-16-01~03）、DASH-01 状态枚举更新 | 小马 🐴 |
