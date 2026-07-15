# yuleOSH Traceability Knowledge Graph — 架构设计

> **版本**: v0.1.0 (设计草案)
> **作者**: 小马 🐴 (质量架构师)
> **日期**: 2026-07-14
> **关联**: spec-knowledge-management.md v1.1.0, requirement-traceability-matrix.md v1

---

## 1. 核心概念

### 1.1 定位与边界

Traceability Knowledge Graph (TKG) 是 yuleOSH 的**追溯层**，以**有向图**形式追踪"需求→代码→测试"全链路。

它与现有知识管理模块（KB/LL/FMEA）**分工互补**而非重叠：

| 模块 | 职责 | 粒度 | 进化频率 |
|------|------|------|----------|
| 知识管理 (KB/LL/FMEA) | 领域知识沉淀、经验教训、失效分析 | 知识条目 | 人工驱动 |
| **TKG（本模块）** | 需求→代码→测试图的构建、查询、变化追踪 | SHALL/文件/函数 | **CI 自动驱动** |
| 追溯矩阵 (RTM) | 静态快照报告（TKG 的物化视图之一） | SHALL→测试行 | 按需生成 |

**关键原则**: TKG 自动从 CI 流水线中构建，人工零维护；RTM 是 TKG 的文本快照。

### 1.2 与现有知识管理模块的集成

TKG 不重复建设 KB/LL/FMEA 模块已有的 CRUD、状态机、版本快照、审计日志。它**依赖**知识管理模块的：

- `KnowledgeStore` — 复用 PostgreSQL 连接和事务管理
- `CROSS-03` 引用完整性 — TKG 节点引用 KB/FMEA 条目时走同一套完整性约束
- `CROSS-04` 审计日志 — TKG 的变化操作复用同一审计日志管道
- `CI-01~CI-05` CI/CD 钩子 — TKG 的自动构建挂载在现有 CI 管道上

**新增部分**:
- 图数据模型（节点、边、属性）
- 图查询层（Cypher / SQL-recursive-CTE / API）
- CI 驱动的自动构建 pipeline step
- 变更影响分析的 diff 引擎

---

## 2. 数据模型

### 2.1 节点类型

| 节点标签 | 含义 | 主标识 | 属性 |
|----------|------|--------|------|
| `Requirement` | 需求（SHALL/SHOULD/MAY 语句） | `req_id` (如 `RS-001-01`) | `statement`, `section`, `priority`, `phase`, `status`, `version`, `spec_source` |
| `CodeModule` | 代码模块/包 | `module_path` (如 `src/yuleosh/alm/`) | `language`, `lines`, `last_commit`, `last_modified` |
| `CodeFile` | 源代码文件 | `file_path` (如 `src/yuleosh/alm/traceability.py`) | `language`, `lines`, `hash`, `last_commit_sha`, `last_modified` |
| `CodeFunction` | 函数/方法/类 | `fully_qualified_name` (如 `yuleosh.alm.traceability.generate_matrix`) | `type`(function/method/class), `line_start`, `line_end`, `signature` |
| `TestFile` | 测试文件 | `file_path` (如 `tests/test_traceability.py`) | `language`, `lines`, `last_run_status`(pass/fail/skip), `last_run_time` |
| `TestFunction` | 测试函数/用例 | `fully_qualified_name` (如 `tests.test_traceability.test_shall_to_test_mapping`) | `line_start`, `line_end`, `last_status`, `last_duration_ms` |
| `SpecDoc` | 规范文档 | `doc_path` (如 `docs/spec.md`, `docs/software-requirements.md`) | `title`, `version`, `sections` |
| `KnowledgeArticle` | 知识条目（KB-14 关联） | `kb_id` (UUID) | `title`, `safety_level`, `confidence` — 复用 KB 数据 |
| `TestCase` | 测试用例（KB-10 关联） | `test_case_id` | `layer`(HIL/SIL/MIL/PIL/Unit), `status` — 复用 KnowledgeTestMap |

### 2.2 边类型

| 边类型 | 源→目标 | 含义 | 属性 | 双向？ |
|--------|---------|------|------|--------|
| `defines` | SpecDoc → Requirement | 规范文档定义某需求 | `section_ref`, `line_number` | ✓ `defined_by` |
| `implements` | CodeFile/CodeFunction → Requirement | 代码实现某需求 | `confidence`(自动推导), `verified_at` | ✓ `implemented_by` |
| `covers` | TestFile/TestFunction → Requirement | 测试覆盖某需求 | `method`(auto/manual), `verified_at`, `status`(pass/fail) | ✓ `covered_by` |
| `verifies` | TestFile/TestFunction → CodeFile/CodeFunction | 测试验证某代码 | `last_run_status`, `last_run_time` | ✓ `verified_by` |
| `depends_on` | Requirement → Requirement | 需求依赖（如上层需求→子需求） | `type`(parent/refines/conflicts) | — |
| `depends_on` | CodeFile → CodeFile | 代码依赖（import） | `type`(import/call/inherit) | — |
| `contains` | CodeModule → CodeFile | 模块包含文件 | — | ✓ `part_of` |
| `contains` | CodeFile → CodeFunction | 文件包含函数 | `line_range` | ✓ `part_of` |
| `contains` | TestFile → TestFunction | 测试文件包含测试函数 | `line_range` | ✓ `part_of` |
| `relates_to` | Requirement → KnowledgeArticle | 需求关联知识条目 | `type`(rationale/risk/guidance) | ✓ |
| `relates_to` | CodeFile → KnowledgeArticle | 代码关联知识条目 | `confidence_impact` | ✓ |
| `affects` | Requirement → CodeFile | 需求变更影响代码文件（CI 推导） | `change_type`(add/modify/delete), `detected_at`, `commit_sha` | — |

### 2.3 属性与版本快照

每个节点和边记录 `created_at` 和 `last_updated_at`。边的 `verified_at` 表示最后一次 CI 验证时间戳。

**快照机制**: TKG 不维护节点本身的版本历史（权责在 Spec 和 Code 的版本管理），但维护**边的状态快照**：每次 CI 构建生成一个 `graph_snapshot` 记录，记录所有边的当前状态。支持按构建 ID 查询历史图快照。

---

## 3. 存储方案对比

| 方案 | 优点 | 缺点 | 推荐场景 |
|------|------|------|----------|
| **Neo4j** | ✅ 原生图查询 (Cypher)，多跳遍历性能优<br>✅ 图算法（影响分析、最短路径）开箱即用 | ❌ 引入新基础设施，运维成本<br>❌ 与现有 PostgreSQL 栈不一致 | 图谱深度≥3 跳的复杂查询场景 |
| **PostgreSQL + CTE 递归** | ✅ 复用现有 store 模块<br>✅ 无新增基础设施<br>✅ 支持 JSONB 属性 | ❌ 3+ 跳递归 CTE 性能下降<br>❌ 图遍历表达能力有限 | 2 跳以内简单追溯 |
| **PostgreSQL + pgRouting + 边表** | ✅ 复用 PostgreSQL<br>✅ 支持路径搜索<br>✅ 无需新服务 | ❌ pgRouting 远不如 Cypher 灵活<br>❌ 图算法有限 | 中规模图谱 (<10K 节点) |
| **SQLite (纯文件)** | ✅ 零运维，文件级移动<br>✅ 可 git 版本控制 | ❌ 无并发写<br>❌ 查询性能差 | 本地开发/离线分析 |
| **飞书多维表格** | ✅ 业务团队友好<br>✅ 飞书生态集成 | ❌ 不支撑图查询<br>❌ 无自动化 API | 非技术团队的手动追溯查阅 |
| **纯 JSON/YAML** | ✅ git 可 diff<br>✅ 零依赖 | ❌ 查询需全量加载<br>❌ 一致性难保证 | 静态快照导出格式 |

### 3.1 推荐方案：双层架构

```
┌─────────────────────────────────┐
│     查询层：PostgreSQL 边表       │  ← 主存储，复用 store 模块
│   + 递归 CTE + GIN 索引          │
├─────────────────────────────────┤
│     分析层：Neo4j (可选)          │  ← 按需启动，用于复杂图分析
│     从 PostgreSQL 同步            │
├─────────────────────────────────┤
│     导出层：JSON/YAML             │  ← 静态快照，git 版本化
└─────────────────────────────────┘
```

**Phase 1 推荐**: 纯 PostgreSQL 边表 + 递归 CTE，零新增基础设施。
**Phase 2 扩展**: 按需接入 Neo4j（数据通过 CDC 同步）。

### 3.2 PostgreSQL 边表 Schema

```sql
-- 节点主表（多态）
CREATE TABLE kg_nodes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(20) NOT NULL CHECK (
        entity_type IN ('requirement','code_module','code_file','code_function',
                        'test_file','test_function','spec_doc','knowledge_article','test_case')
    ),
    entity_id   VARCHAR(255) NOT NULL,  -- 业务主键，如 req_id / file_path
    label       VARCHAR(255) NOT NULL,  -- 显示名
    properties  JSONB NOT NULL DEFAULT '{}',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (entity_type, entity_id)
);
CREATE INDEX idx_kg_nodes_type ON kg_nodes(entity_type);
CREATE INDEX idx_kg_nodes_gin ON kg_nodes USING GIN(properties jsonb_path_ops);

-- 边表
CREATE TABLE kg_edges (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID NOT NULL REFERENCES kg_nodes(id),
    target_id       UUID NOT NULL REFERENCES kg_nodes(id),
    edge_type       VARCHAR(20) NOT NULL CHECK (
        edge_type IN ('defines','implements','covers','verifies',
                      'depends_on','contains','relates_to','affects')
    ),
    properties      JSONB NOT NULL DEFAULT '{}',
    verified_at     TIMESTAMP,            -- 最近 CI 验证时间
    build_id        VARCHAR(64),          -- 来源构建 ID
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (source_id, target_id, edge_type)
);
CREATE INDEX idx_kg_edges_source ON kg_edges(source_id);
CREATE INDEX idx_kg_edges_target ON kg_edges(target_id);
CREATE INDEX idx_kg_edges_type ON kg_edges(edge_type);
CREATE INDEX idx_kg_edges_build ON kg_edges(build_id);

-- 图快照（每次 CI 构建生成）
CREATE TABLE kg_snapshots (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    build_id    VARCHAR(64) NOT NULL UNIQUE,
    built_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    node_count  INT NOT NULL,
    edge_count  INT NOT NULL,
    meta        JSONB NOT NULL DEFAULT '{}'
);
```

---

## 4. API 设计

### 4.1 RESTful API

```
GET  /api/v1/kg/nodes?type=requirement&active=true        — 查询节点
GET  /api/v1/kg/nodes/:id                                  — 获取单个节点
GET  /api/v1/kg/nodes/:id/edges?direction=out&type=covers  — 查询节点的出/入边
POST /api/v1/kg/query/trace                                — 追溯查询
POST /api/v1/kg/query/impact                                — 变更影响分析
GET  /api/v1/kg/snapshots                                  — 列出图快照
GET  /api/v1/kg/snapshots/:build_id                        — 获取特定快照
GET  /api/v1/kg/snapshots/:build_id/diff?since=:prev       — 快照差异
POST /api/v1/kg/build                                      — 手动触发重构
```

### 4.2 核心查询 API

#### 追溯查询 (Trace Query)

从需求变更追踪到受影响代码和测试：

```json
POST /api/v1/kg/query/trace
{
  "req_ids": ["RS-001-01", "SWR-001.1-01"],
  "direction": "downstream",  // upstream | downstream | both
  "max_depth": 3,
  "include_edges": ["implements", "covers", "verifies"]
}
→ {
  "nodes": [...],
  "edges": [...],
  "graph": { "nodes": [...], "edges": [...] }  // 完整子图
}
```

#### 变更影响分析 (Impact Analysis)

从代码变更追溯到关联需求和测试：

```json
POST /api/v1/kg/query/impact
{
  "changed_files": ["src/yuleosh/alm/traceability.py"],
  "change_type": "modify",  // add | modify | delete
  "include_affected_tests": true,
  "include_affected_reqs": true
}
→ {
  "affected_reqs": [
    {"req_id": "RS-001-02", "statement": "...", "confidence": "direct"}
  ],
  "affected_tests": [
    {"file": "tests/test_traceability.py", "functions": ["test_shall_to_test_mapping"]}
  ],
  "impact_summary": "1 requirement, 3 test functions affected"
}
```

### 4.3 GraphQL (可选增强)

```graphql
query {
  traceRequirement(reqId: "RS-001-01") {
    id, label, properties
    implements: edges(edgeType: implements, direction: out) {
      target { id, label, ... on CodeFile { language, lines } }
    }
    covers: edges(edgeType: covers, direction: out) {
      target { id, label, ... on TestFunction { lastStatus } }
    }
    dependsOn: edges(edgeType: depends_on, direction: out) {
      target { id, label }
    }
  }
}
```

### 4.4 边表查询（SQL 模式）

复杂查询通过递归 CTE：

```sql
-- 从需求 RS-001-01 出发，追踪到所有被影响代码和测试
WITH RECURSIVE trace AS (
    SELECT n.*, e.edge_type, 1 AS depth
    FROM kg_nodes n
    JOIN kg_edges e ON e.source_id = n.id
    WHERE n.entity_type = 'requirement' AND n.entity_id = 'RS-001-01'
    UNION ALL
    SELECT n.*, e.edge_type, t.depth + 1
    FROM trace t
    JOIN kg_edges e ON e.source_id = t.id
    JOIN kg_nodes n ON n.id = e.target_id
    WHERE t.depth < 5
)
SELECT DISTINCT * FROM trace WHERE entity_type IN ('code_file', 'test_function');
```

---

## 5. CI 集成方案（核心差异化能力）

### 5.1 自动构建流水线

```
[Pre-commit]           → 解析提交信息，标记受影响的 req/file
[Build / Test]         → 运行测试，收集测试结果（pass/fail/time）
[Post-build: TKG Step] → 增量构建知识图谱
[Post-build: Report]   → 生成变更影响分析报告
[Merge Gate]           → 根据 TKG 影响分析 + 门禁策略决定是否阻挡
```

### 5.2 增量构建算法

```
Input: 本次变更的 commit diff (changed_files)
Input: 测试运行结果 (test_results)

Step 1: Parse spec changes
  - 如果 changed_files 包含 *.spec.md → 解析 SHALL 语句
  - 对比上一快照 → 识别新增/修改/删除的需求节点
  - 更新 kg_nodes + kg_edges (defines 边)

Step 2: Parse code changes
  - 对每个 changed code_file (.py/.c/.go):
    - 提取函数/类定义 → 更新 code_function 节点
    - 分析 import 依赖 → 更新 depends_on 边
  - 对每个 changed test_file:
    - 提取 test_function → 更新节点
    - 匹配 SHALL ID 引用 → 更新 covers 边

Step 3: Map test results
  - 对每条测试结果:
    - 更新 TestFunction.verified_by → CodeFunction 边
    - 如果有 SHALL 引用 → 更新 covers 边状态 (pass/fail)

Step 4: Derive implements 边 (启发式)
  - 基于测试覆盖反向推导: 
    - 如果 FuncA 被测试 TestB 覆盖, 且 TestB 覆盖 ReqC → 推导 FuncA implements ReqC
  - 优先级: 显式声明 > CI 推导 > 启发式

Step 5: Generate snapshot
  - 创建 kg_snapshots 记录
  - 计算与上一快照的 diff
```

### 5.3 CI Pipeline 配置 (yuleOSH Step)

```yaml
# .yuleosh.yaml 中新增
knowledge_graph:
  enabled: true
  build:
    trigger: always  # always | on_spec_change | on_code_change
    derive_implements: true
    max_depth: 5
  impact_analysis:
    enabled: true
    report_format: comment  # comment | file | api
    auto_comment_pr: true
  merge_gates:
    - rule: "uncovered_requirement_change"
      action: warn  # warn | block
      max_allowed: 0
    - rule: "test_failure_on_critical_path"
      action: block
      max_allowed: 0
```

### 5.4 CI 输出示例 (PR Comment)

```
## 🔍 Traceability Impact Analysis

### 变更文件
- `src/yuleosh/alm/traceability.py` (modify)

### 受影响需求
| 需求 ID | 陈述 | 影响程度 |
|---------|------|----------|
| RS-001-02 | The SHALL support agent routing | direct |
| RS-002-01 | The SHALL maintain requirement tree | indirect |

### 受影响测试
| 测试文件 | 测试函数 | 最近状态 |
|----------|----------|----------|
| tests/test_traceability.py | test_shall_to_test_mapping | ✅ pass |
| tests/test_traceability.py | test_requirement_tree_hierarchy | ✅ pass |

### 覆盖率快照
- 总需求: 55 | 已覆盖: 55 (100%)
- 变更影响: 1 需求需要重新验证 ✅
```

---

## 6. 启动引导 (Bootstrap)

### 6.1 从现有 RTM 导入

现有 `requirement-traceability-matrix.md` 和 `req-test-mapping.json` 是一次性种子数据源：

```
Step 1: 解析 requirement-traceability-matrix.md → 创建所有 Requirement 节点
Step 2: 解析 req-test-mapping.json → 创建 TestFile 节点 + covers 边
Step 3: 扫描 src/ 目录 → 创建 CodeFile/CodeFunction 节点
Step 4: 扫描 tests/ 目录 → 创建 TestFunction 节点
Step 5: 基于矩阵映射 → 创建 covers/implements/verifies 边
Step 6: 运行测试 → 更新边状态
```

预计节点数：~55 Requirements + ~200 code files + ~150 test functions = ~400 节点
预计边数：根据映射关系 ~500 边

### 6.2 引导 CLI 工具

```bash
yuleosh kg bootstrap                     # 从 RTM + 代码扫描引导
yuleosh kg build                         # 增量构建（CI 用）
yuleosh kg query trace REQ-001           # 追溯查询
yuleosh kg query impact src/foo.py       # 影响分析
yuleosh kg snapshot list                 # 快照列表
yuleosh kg snapshot diff BUILD_A BUILD_B # 对比两个快照
yuleosh kg export --format json          # 导出 JSON
yuleosh kg export --format yaml          # 导出 YAML
```

---

## 7. 与 Spec 知识管理模块的集成点

| TKG 功能 | 集成点 |
|----------|--------|
| Requirement 节点 | 复用 spec 模块的 SpecEntry ID（KB-14 引用） |
| KnowledgeArticle 节点 | 通过 `relates_to` 边关联，复用 `KBServer.LinkSpecEntries` |
| CodePath 到 KB 的链接 | 复用 `KB-04` 的 `KnowledgeCodePath` 表 |
| 测试层映射 | 复用 `KB-10` 的 `KnowledgeTestMap` 表 |
| 审计日志 | 复用 `CROSS-04` 审计日志管道 |
| CI 钩子 | 复用 `CI-01~CI-05` 的钩子机制 |
| RBAC | 复用 `CROSS-05` 角色模型 |

---

## 8. 性能预估

| 规模 | 节点数 | 边数 | 查询响应 (CTE 递归) | 查询响应 (Neo4j) |
|------|--------|------|---------------------|-----------------|
| 当前 | ~400 | ~500 | <10ms | <5ms |
| 中型项目 | ~5K | ~20K | <50ms | <10ms |
| 大型项目 | ~50K | ~200K | <500ms | <50ms |
| 超大规模 | ~500K | ~2M | >2s (需优化) | <200ms |

> PostgreSQL 边表 + GIN 索引 + 递归 CTE 在 50K 节点以下足够；超过 50K 建议引入 Neo4j。
