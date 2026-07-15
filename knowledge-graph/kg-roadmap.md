# yuleOSH Traceability Knowledge Graph — 实现路线图

> **版本**: v0.1.0
> **日期**: 2026-07-14
> **关联**: kg-architecture.md, kg-spec-draft.md

---

## 总览

### 增量价值原则

每一步都是**独立可交付**的增量，不依赖后续步骤。每一步产出：
- 可查询的图谱片段
- 自动化的 CI 反馈
- 立即可见的业务价值

### 阶段总览

| 阶段 | 名称 | 周期 | 增量价值 |
|------|------|------|----------|
| P0 | RTM 导入 + 基础查询 | 3-5天 | 已有追溯数据可查询 |
| P1 | CI 增量构建 + PR 影响分析 | 5-7天 | 代码变更自动影响分析 |
| P2 | 需求变更追踪 + 门禁 | 3-5天 | 需求变更自动验证 |
| P3 | 深度集成 | 5-7天 | 知识管理模块 + 仪表盘 |

---

## P0: RTM 导入 + 基础查询 (3-5天)

### 目标
从现有的 `requirement-traceability-matrix.md` + `req-test-mapping.json` 构建初始图谱，提供基础查询 API。

### 交付物

**Day 1–2: 数据库 schema + 导入脚本**
- [ ] 创建 `kg_nodes`, `kg_edges`, `kg_snapshots` 表（复用 PostgreSQL 现有链接）
- [ ] 实现 `bootstrap` CLI 命令，从 RTM 导入
  - 解析 requirement-traceability-matrix.md → Requirement 节点
  - 解析 req-test-mapping.json → TestFile/TestFunction 节点 + covers 边
- [ ] 解析 RTM 中的 SHALL ID → 测试文件/函数映射关系
- [ ] 创建 `kg_snapshots` 初始快照

**Day 3–5: 基础查询 API**
- [ ] 实现 REST API 端点
  - `GET /api/v1/kg/nodes` — 节点查询（按类型、ID 过滤）
  - `GET /api/v1/kg/nodes/:id/edges` — 节点边查询
  - `POST /api/v1/kg/query/trace` — 追溯查询
- [ ] 实现递归 CTE 查询（需求→测试 的 2 跳追溯）
- [ ] CLI 命令：`yuleosh kg query trace REQ-ID`
- [ ] CLI 命令：`yuleosh kg export --format json`

### 验证标准
- [x] 现有 55 个 SHALL 节点全部导入
- [x] 每个 SHALL 节点至少有一条 `covers` 边连接测试函数
- [x] 通过 API 查询 `RS-001-01` 返回其关联测试列表
- [x] 通过 API 查询 `test_traceability.py` 返回其关联需求列表
- [x] 递归 CTE 查询延迟 < 50ms

### 无新增基础设施
- 纯 PostgreSQL + 已有 store 模块
- 纯 Go 实现（复用现有接口模式）

---

## P1: CI 增量构建 + PR 影响分析 (5-7天)

### 目标
在 CI 中自动检测代码变更，增量更新图谱，并在 PR 自动评论影响分析报告。

### 交付物

**Day 1–3: 增量构建引擎**
- [ ] 实现增量构建算法核心（见架构文档 §5.2）
  - spec 变更检测（*.spec.md 差异分析）
  - 代码文件变更函数提取
  - 测试结果映射
- [ ] 实现 `implements` 边推导（基于测试覆盖反向推导）
- [ ] 增量 snapshot 生成与 diff 计算
- [ ] CLI 命令：`yuleosh kg build`（增量）
- [ ] CLI 命令：`yuleosh kg snapshot diff A B`

**Day 4–5: PR 集成**
- [ ] yuleOSH CI step 配置（`knowledge_graph.build` 区块）
- [ ] PR 自动影响分析评论
  - 变更文件列表 → 受影响需求列表
  - 受影响测试列表 + 最近状态
  - 覆盖率快照摘要
- [ ] 首次全量构建后自动 baseline

**Day 6–7: 影响分析 API + CLI**
- [ ] `POST /api/v1/kg/query/impact` — 变更影响分析
- [ ] CLI：`yuleosh kg query impact <file_path>`
- [ ] 如果影响分析发现未覆盖需求变更 → warn/block（配置化）

### 验证标准
- [x] 修改一个代码文件后提交 → PR 评论显示受影响的 1+ 需求和 2+ 测试
- [x] 新增测试覆盖 → 图谱自动更新 `covers` 边状态
- [x] `verifies` 边反映测试 pass/fail 状态
- [x] 增量构建时间 < 30s（对于 ~400 节点图谱）

### 关键设计决策
- **增量 vs 全量**: 增量构建，除非 bootstrap 或 schema 变更
- **推导 vs 显式**: 优先显式声明（代码注释中 `// covers SHALL-001`），无声明时启发式推导
- **异步 vs 同步**: 增量构建异步执行，但影响分析报告生成同步到 PR 线程

---

## P2: 需求变更追踪 + 门禁 (3-5天)

### 目标
当 spec 需求变更时，自动追踪到受影响的代码文件和测试，并在 merge gate 层提供门禁。

### 交付物

**Day 1–2: 需求变更检测**
- [ ] Spec 文件变更解析器（识别 SHALL 新增/修改/删除）
- [ ] 需求节点版本追踪（spec 变更 → 更新 Requirement 节点）
- [ ] 需求变更的级联边标记（`affects` 边生成）

**Day 2–3: 测试结果反馈闭环**
- [ ] 测试执行结果自动回写到 `covers` / `verifies` 边
- [ ] 当测试 fail → 边状态标记 `status: fail`
- [ ] CLI 命令：`yuleosh kg query trace REQ-ID --include-status`

**Day 3–4: Merge Gate 集成**
- [ ] 配置化 merge gate 规则
  - `uncovered_requirement_change`: 需求变更但无测试覆盖 → block
  - `test_failure_on_critical_path`: 关键路径测试失败 → block
  - `req_change_without_review`: 需求变更未审核 → warn
- [ ] Merge gate 与现有 CI 管道集成（CI-04 扩展）

**Day 4–5: 导出与报告**
- [ ] 基于知识图谱生成 RTM 报告（替代当前的静态 RTM 文件）
- [ ] 导出格式：Markdown（人类可读）、JSON（机器可读）、YAML（git diff 友好）
- [ ] `yuleosh kg report rtm` — 从图谱实时生成追溯矩阵

### 验证标准
- [x] 修改 spec 中的一个 SHALL → 图谱自动识别并标记变更
- [x] Merge gate 挡住无测试覆盖的需求变更
- [x] 测试失败后，对应的 `covers` 边标记为 fail
- [x] `yuleosh kg report rtm` 输出与现有 RTM 一致（但自动生成）

---

## P3: 深度集成 (5-7天)

### 目标
与知识管理模块（KB/LL/FMEA）双向链接，提供可视化仪表盘和高级图分析能力。

### 交付物

**Day 1–2: 知识管理模块集成**
- [ ] `relates_to` 边：Requirement ↔ KnowledgeArticle
- [ ] KB-14 的 Spec 条目关联自动同步到图
- [ ] KB-10 的测试映射自动同步到图
- [ ] FMEA 跨 ECU 失效链映射到图（跨 ECU 连线）

**Day 2–3: 可视化仪表盘**
- [ ] 知识图谱可视化（前端 D3.js / vis-network）
  - 力导向图展示需求↔代码↔测试
  - 按类型着色（需求=蓝、代码=绿、测试=黄）
  - 边状态着色（pass=绿、fail=红、部分=橙）
- [ ] 变更影响热力图
- [ ] 覆盖率仪表盘集成（DASH-03 扩展）

**Day 3–4: 图分析能力**
- [ ] 最短路径查询：需求→代码→测试 最短路
- [ ] 孤立节点检测：无测试覆盖的需求、无需求关联的代码
- [ ] 扇出分析：一个需求影响了多少测试（测试效率度量）
- [ ] 扇入分析：一段代码被多少需求依赖（安全优先级）

**Day 4–5: Neo4j 同步（可选）**
- [ ] 数据同步管道（PostgreSQL → Neo4j）
- [ ] Neo4j Cypher 查询支持
- [ ] 性能基准测试：CTE vs Cypher

**Day 5–7: 售后闭环**
- [ ] DTC → Requirement → Code → Test 全链追溯
- [ ] 售后事件（DTC 命中）自动标记受影响的需求/代码
- [ ] 仪表盘售后统计（DASH-04 扩展）

### 验证标准
- [x] 仪表盘展示完整的需求↔代码↔测试图谱
- [x] 孤立节点检测发现未被测试覆盖的需求
- [x] DTC 追溯可沿"DTC → FMEA → Requirement → Code → Test"全链路
- [x] Neo4j 同步延迟 < 1s（如启用）

---

## 依赖关系

```
P0 ──→ P1 ──→ P2 ──→ P3
  │       │       │
  │       └───────┴── 共享增量构建引擎
  │
  └── 依赖现有：store 模块、spec 模块
      P1 依赖：CI 管道、commit-msg/PR 钩子
      P2 依赖：merge gate 框架
      P3 依赖：知识管理模块、dashboard 框架
```

---

## 资源估算

| 阶段 | 开发 | 测试 | 文档 |
|------|------|------|------|
| P0 | 2人×3天 | 1人×1天 | 1人×0.5天 |
| P1 | 2人×5天 | 1人×2天 | 1人×1天 |
| P2 | 1人×4天 | 1人×1天 | 1人×0.5天 |
| P3 | 2人×5天 | 1人×2天 | 1人×1天 |
| **合计** | **~30人天** | | |

---

## 风险与缓解

| 风险 | 可能 | 影响 | 缓解 |
|------|------|------|------|
| 增量构建在大型 PR 上超时 | 中 | 中 | 超时后降级为全量隔夜构建 |
| 启发式 `implements` 推导误报 | 高 | 低 | 推导结果标记 `confidence: heuristic`，人工确认后升级 |
| 递归 CTE 在复杂查询上性能差 | 中 | 中 | 限制递归深度（默认 5），添加 `max_depth` 参数 |
| CI 管道新增步骤影响总时间 | 中 | 低 | 增量构建异步执行，PR 评论通过回调更新 |
