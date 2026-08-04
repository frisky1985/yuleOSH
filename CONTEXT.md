# CONTEXT.md — yuleOSH 领域术语表

> 本文档是 yuleOSH 项目的**统一语言**（Ubiquitous Language）。所有 agent 在命名代码、测试、接口、评审时必须使用本表术语。
> 本文档**只含术语定义，不含实现细节**。实现决策见 `docs/adr/`。
> 更新规则：术语在会话中结晶后立即更新（domain-modeling 纪律），不批量攒。

## 核心概念

- **yuleOSH** — 面向嵌入式开发的 AI 辅助 ASPICE 工具：把自然语言需求转换为 CI/CD 就绪的固件项目，带 ASPICE 可追溯性。整个产品的名字。
- **Pipeline（流水线）** — 从 spec 到可验证固件的端到端流程。由多个 **stage** 组成，由 **orchestrator** 驱动。
- **Stage（阶段）** — pipeline 中的一个可执行步骤（解析 spec、生成代码、跑测试、评审等）。每个 stage 有明确的输入/输出 artifact。
- **Spec（规格）** — 用 OpenSpec 格式（RFC 2119 SHALL/SHOULD/MAY + GIVEN/WHEN/THEN 场景）书写的需求文档。产品从 spec 开始。
- **OpenSpec Engine（OpenSpec 引擎）** — 解析、校验、diff、追溯 spec 需求的引擎。核心输入是 spec 文件。
- **Artifact（产物）** — pipeline 各 stage 产生/消费的文件或结构化输出。stage 之间通过 artifact 交接，不靠重新推断。
- **Orchestrator（编排器）** — 驱动 pipeline 执行、派发 sub-agent、收集结果的组件。也指小明这个角色。
- **Session（会话）** — 一次 pipeline 运行的生命周期载体，保存 stage 产物与状态。
- **Requirement（需求）** — spec 中的一条 SHALL/SHOULD/MAY 条款，带唯一编号（如 SHALL-T1.1）。
- **Scenario（场景）** — spec 中的 GIVEN/WHEN/THEN 陈述，用于验证需求的可测试性。
- **Acceptance Matrix（验收矩阵）** — 把每条需求映射到测试用例的矩阵，判定"需求是否完成"。
- **Traceability（可追溯性）** — 需求 → 设计 → 代码 → 测试的链路可回溯，ASPICE SWE.1~SWE.6 审计证据的核心。

## Agent 角色（三人小队）

- **小明** — 项目经理/编排器。需求入口、流程编排、最终评审（业务价值维度）、争议仲裁。
- **小克** — 架构师/开发者/测试者。架构设计、代码开发、自测、技术债跟踪、根因分析。
- **小马** — 质量架构师/评审者。Spec 契约层、验收矩阵、前置架构评审、正式评审、变更影响分析、质量评分。

## CI 体系

- **Layer 1/2/3（CI 层）** — 分层 CI 检查。Layer 1 基础门禁（测试/lint/方法论），Layer 2 覆盖率，Layer 3 深度合规。
- **Gate（门禁）** — 阻断性检查。失败即 pipeline 停止。与 **warning**（不阻断）相对。
- **Loop Chain（循环链）** — CI 失败后自动修复-再验证的迭代机制，直到全绿。
- **Coverage Gate（覆盖率门禁）** — 覆盖率低于阈值的阻断检查。
- **MISRA** — 嵌入式 C/C++ 代码合规标准（MISRA C:2012 等），yuleOSH 内置规则集与偏差管理。
- **SWE.1~SWE.6** — ASPICE 系统工程流程级别，yuleOSH 辅助准备各层审计证据。

## 方法论（v3.10.1+ 契约）

- **Grilling（追问对齐）** — spec 前与需求方逐题澄清的环节。一次一问、带推荐答案、事实自查决策问人。见 `.yuleosh/agents/METHODOLOGY.md` §1。
- **Domain Model / CONTEXT.md（统一语言）** — 项目术语的权威来源。见 METHODOLOGY §2。
- **Two-Axis Review（双轴评审）** — Standards（规范+代码味道）与 Spec（忠实实现）两轴并行、分开报告。见 METHODOLOGY §3。
- **Tight Loop（调试回路）** — 诊断 bug 前必须建立的 red-capable 复现回路。见 METHODOLOGY §4。
- **Vertical Slice（垂直切片）** — 切穿所有层、独立可验证的工作单元，带 blocking edges。见 METHODOLOGY §5。
- **Blocking Edge（阻塞边）** — ticket 之间的依赖关系："此 ticket 被 X/Y/Z 阻塞，须等它们完成才能开工"。
- **Frontier（前沿）** — 所有依赖已完成、可立即开工的 ticket 集合。

## 常用缩写

- **HITL** — Human In The Loop，需要人参与的流程。
- **AFK** — Away From Keyboard，agent 可无人值守驱动。
- **ADR** — Architecture Decision Record，架构决策记录（`docs/adr/`）。
- **RCA** — Root Cause Analysis，根因分析。
- **P0/P1/P2** — 缺陷/评审发现的分级：P0 阻断、P1 重要、P2 建议。
- **QA** — 质量保证（评审/验收相关环节）。
