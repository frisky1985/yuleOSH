# yuleOSH Traceability Knowledge Graph — Spec 契约草案

> **版本**: v0.1.0 (草案)
> **状态**: 待审查
> **规范文体**: RFC 2119 (SHALL/SHALL NOT/SHOULD/MAY)
> **关联**: spec-knowledge-management.md v1.1.0
>
> 本 spec 定义 TKG 模块的 SHALL 需求。与知识管理模块（KB/LL/FMEA）不重叠的部分在此定义，重叠处（审计日志、RBAC、CI 钩子）引用现有 spec。

---

## 目录

1. [数据模型层](#1-数据模型层)
2. [构建层](#2-构建层)
3. [查询 API 层](#3-查询-api-层)
4. [CI/CD 集成层](#4-cicd-集成层)
5. [导入/导出层](#5-导入导出层)
6. [验收判定矩阵](#6-验收判定矩阵)

---

## 1. 数据模型层

### KG-01: 节点模型

**SHALL** — TKG SHALL 支持以下节点类型：
- `Requirement` — 需求（SHALL/SHOULD/MAY 语句）
- `CodeModule` — 代码模块/包
- `CodeFile` — 源代码文件
- `CodeFunction` — 函数/方法/类
- `TestFile` — 测试文件
- `TestFunction` — 测试用例/函数
- `SpecDoc` — 规范文档
- `KnowledgeArticle` — 知识条目（引用 KB 模块）
- `TestCase` — 测试用例（引用 KnowledgeTestMap）

**SHALL** — 每个节点 SHALL 包含以下基础属性：
- `id` (UUID) — 全局唯一标识
- `entity_type` (枚举) — 节点类型
- `entity_id` (字符串) — 业务主键（如 `RS-001-01`、`src/foo.py`）
- `label` (字符串) — 显示名
- `properties` (JSONB) — 类型特定属性
- `is_active` (布尔) — 软删除标记
- `created_at` / `updated_at` (时间戳)

**SHALL NOT** — 节点 SHALL NOT 物理删除。标记 `is_active=false` 为软删除。

### KG-02: 边模型

**SHALL** — TKG SHALL 支持以下边类型：
- `defines` / `defined_by` — 规范文档定义需求
- `implements` / `implemented_by` — 代码实现需求
- `covers` / `covered_by` — 测试覆盖需求
- `verifies` / `verified_by` — 测试验证代码
- `depends_on` — 依赖关系（需求↔需求、代码↔代码）
- `contains` / `part_of` — 包含关系（模块→文件→函数）
- `relates_to` — 关联关系（需求/代码↔知识条目）
- `affects` — 变更影响（CI 推导）

**SHALL** — 每条边 SHALL 包含以下基础属性：
- `id` (UUID)
- `source_id` (UUID, FK) — 源节点
- `target_id` (UUID, FK) — 目标节点
- `edge_type` (枚举)
- `properties` (JSONB) — 边特定属性
- `verified_at` (时间戳, 可选) — 最近 CI 验证时间
- `build_id` (字符串, 可选) — 来源构建

**SHALL** — 边的 `(source_id, target_id, edge_type)` SHALL 唯一。

### KG-03: 图快照

**SHALL** — 每次 CI 构建成功 SHALL 生成一个图快照记录（`kg_snapshots` 表）。

**SHALL** — 图快照 SHALL 记录：
- `build_id` (唯一)
- `built_at` (时间戳)
- `node_count` (整数)
- `edge_count` (整数)

**SHOULD** — 系统 SHOULD 支持基于 `build_id` 查询历史图状态的 diff（新增/修改/删除的节点和边）。

---

## 2. 构建层

### KG-10: 全量引导 (Bootstrap)

**SHALL** — 系统 SHALL 提供从现有追溯数据源的全量引导能力，输入源包括：
- `requirement-traceability-matrix.md`
- `req-test-mapping.json`
- 代码目录扫描结果
- 测试目录扫描结果

**SHALL** — 全量引导 SHALL 是幂等的：重复执行产生一致的图谱（建模数据不变时）。

**SHALL** — 全量引导 SHALL 报告总结（总节点数、总边数、各类型数量）。

### KG-11: 增量构建

**SHALL** — 系统 SHALL 提供增量构建能力，仅处理自上一快照以来发生变更的文件。

**SHALL** — 增量构建的输入 SHALL 是 commit diff 的 `changed_files` 列表和测试运行结果。

**SHALL** — 增量构建 SHALL 检测以下变更类型：
- Spec 文件变更 → 解析新增/修改/删除的 SHALL 语句
- 源代码文件变更 → 提取变更的函数/类定义
- 测试文件变更 → 提取变更的测试函数
- 测试结果变化 → 更新边的状态属性

**SHOULD** — 当增量构建检测到 spec 文件中 SHALL 语句的修改时，系统 SHOULD 在对应 Requirement 节点上标记 `has_pending_changes: true`。

**MAY** — 系统 MAY 支持从代码注释中解析显式追溯声明（如 `// covers SHALL-001` 或 `@traceability(req="RS-001-01")`），优先级高于启发式推导。

### KG-12: Implements 边推导

**SHALL** — 系统 SHALL 基于启发式规则推导 `implements` 边（当显式声明不存在时）：

1. 如果 `CodeFunction F` 被 `TestFunction T` 验证（`verifies` 边），且 `T` 覆盖 `Requirement R`（`covers` 边）→ 推导 `F implements R`
2. 如果 `CodeFile F` 包含函数 `F implements Requirement R` → 推导 `F implements R`
3. 如果代码注释中包含 `// implements SHALL-XXX` → 解析为显式 `implements` 边

**SHALL** — 启发式推导的边 SHALL 标记 `confidence` 属性：
- `explicit` — 显式声明（注释、配置）
- `derived` — 通过测试反向推导
- `heuristic` — 基于命名模式/文件结构推测

**SHOULD** — 系统 SHOULD 支持通过配置文件或注释显式声明 `implements` 关系，此时 SHALL 覆盖启发式推导。

### KG-13: 代码路径反向索引

**SHALL** — 系统 SHALL 在增量构建时，检查变更文件路径是否关联已有知识条目（复用 KB-04 的 `KnowledgeCodePath` 表）。

**SHOULD** — 当变更文件关联了知识条目时，系统 SHOULD 更新相关 `relates_to` 边的状态，并在构建报告中列出。

---

## 3. 查询 API 层

### KG-20: 追溯查询

**SHALL** — 系统 SHALL 提供从任意节点出发的追溯查询能力，支持指定：
- 起始节点（按 ID 或 entity_type + entity_id）
- 追溯方向：下游（`downstream`）、上游（`upstream`）、双向（`both`）
- 最大深度（默认 5，上限可配置）
- 边类型过滤（可选）

**SHALL** — 追溯查询结果 SHALL 包含：
- 子图的所有节点和边
- 每条边最近 CI 验证时间
- 节点的活跃状态

**SHALL** — 链式追溯的基准场景 SHALL 满足：
```
Requirement → (implements) → CodeFile → (contains) → CodeFunction
                                                        ↓ (verifies)
                                                      TestFunction → (covers) → Requirement
```

**SHALL** — 链式追溯 SHALL 通过 PostgreSQL 递归 CTE 实现，深度为 3 跳时响应时间 < 100ms（当前规模）。

### KG-21: 变更影响分析

**SHALL** — 系统 SHALL 提供基于文件变更的影响分析能力：
- 输入：一个或多个变更文件路径
- 输出：
  - 直接受影响的需求列表（该文件实现的需求）
  - 间接受影响的需求列表（依赖该文件的需求）
  - 相关测试列表（需要重新运行的测试）
  - 相关知识条目列表

**SHALL** — 影响分析 SHALL 区分 `direct`（直接实现边）和 `indirect`（通过依赖链）的影响等级。

**SHOULD** — 影响分析结果 SHOULD 按影响程度排序，并包含建议操作（需要重跑测试、需要人工审查）。

### KG-22: 图查询

**SHALL** — 系统 SHALL 支持以下元查询：
- 孤岛节点检测：无任何边的节点
- 扇出分析：入度/出度最大的节点
- 未覆盖需求列表：无 `covers` 边的 Requirement 节点
- 无主代码列表：无 `implements` 边的 CodeFile 节点

**SHOULD** — 系统 SHOULD 支持自定义图遍历模式（基于 edge_type 的路径模式匹配）。

---

## 4. CI/CD 集成层

### KG-30: CI 构建 Step

**SHALL** — 系统 SHALL 提供一个 CI pipeline step，在构建/测试阶段后执行知识图谱增量构建。

**SHALL** — CI 构建 Step SHALL 配置化（在 `.yuleosh.yaml` 中），支持以下配置：
```yaml
knowledge_graph:
  enabled: true
  build:
    trigger: always          # always | on_spec_change | on_code_change
    derive_implements: true
  impact_analysis:
    enabled: true
    report_format: comment    # comment | file | api
    auto_comment_pr: true
```

**SHALL** — 当 `trigger=always` 时，每次 CI 构建 SHALL 执行增量构建。

**SHALL** — 当 `auto_comment_pr=true` 时，系统 SHALL 在 PR 上自动评论变更影响分析报告。

### KG-31: PR 影响分析报告

**SHALL** — PR 影响分析报告 SHALL 包含以下章节：
1. **变更文件摘要** — 本次 PR 变更的文件列表
2. **受影响需求** — 每个变更文件直接/间接实现的需求 ID + 陈述摘要
3. **受影响测试** — 需要重新运行的测试文件/函数列表 + 最近状态
4. **覆盖率快照** — 当前总体覆盖率统计
5. **提醒** — 如发现未覆盖需求变更、FMEA 关联变更等

**SHALL** — 报告 SHALL 在 PR 评论中发布（`comment` 模式），或在构建产物中（`file` 模式）。

### KG-32: Merge Gate 集成

**SHOULD** — 系统 SHOULD 支持基于知识图谱的 merge gate 规则：

| 规则 | 默认动作 | 说明 |
|------|----------|------|
| `uncovered_requirement_change` | `warn` | 需求变更但无对应测试覆盖 |
| `test_failure_on_critical_path` | `block` | 关键路径测试失败 |
| `req_change_without_review` | `warn` | 需求变更未经过 spec 审查 |
| `fmea_impacted_module_change` | `warn` | 修改了有 FMEA 关联的模块 |

**SHALL NOT** — Merge gate SHALL NOT 在非技术 PR（文档、配置修改）上触发不必要的阻挡。

---

## 5. 导入/导出层

### KG-40: 导出

**SHALL** — 系统 SHALL 支持从知识图谱导出为以下格式：
- **Markdown** — 人类可读的追溯矩阵（与现有 RTM 格式兼容）
- **JSON** — 完整的图数据结构（nodes + edges 数组）
- **YAML** — git diff 友好的 YAML 格式

**SHALL** — 导出 SHALL 支持按条件过滤（按节点类型、边类型、构建快照）。

**SHOULD** — 系统 SHOULD 支持导出历史快照用于审计追溯。

### KG-41: 导入

**SHALL** — 系统 SHALL 支持从 JSON/YAML 导入图数据（用于离线编辑后回写）。

**SHALL** — 导入 SHALL 经过 schema 校验，校验失败时返回详细错误报告。

**SHALL** — 导入 SHALL 标记所有边为 `imported` 而非 `ci_derived`。

---

## 6. 验收判定矩阵

### ACC-KG-01: 全量引导

| | |
|------|------|
| **ID** | ACC-KG-01-01 |
| **GIVEN** | 一个已有 `requirement-traceability-matrix.md` 和 `req-test-mapping.json` 的项目 |
| **WHEN** | 用户执行 `yuleosh kg bootstrap` |
| **THEN** | 图谱包含 ≥55 个 Requirement 节点，每个 SHALL ID 有对应的 `covers` 边连接到测试文件 |

| | |
|------|------|
| **ID** | ACC-KG-01-02 |
| **GIVEN** | 同一项目 |
| **WHEN** | 重复执行 `yuleosh kg bootstrap` |
| **THEN** | 图谱节点数和边数与第一次执行一致（幂等） |

### ACC-KG-02: 追溯查询

| | |
|------|------|
| **ID** | ACC-KG-02-01 |
| **GIVEN** | 一个已引导的知识图谱 |
| **WHEN** | 用户查询 `RS-001-01` 的下游追溯 |
| **THEN** | 返回结果包含：实现该需求的代码文件、覆盖该需求的测试函数、以及验证代码的测试函数 |

| | |
|------|------|
| **ID** | ACC-KG-02-02 |
| **GIVEN** | 一个已引导的知识图谱 |
| **WHEN** | 用户查询 `test_traceability.py` 的上游追溯 |
| **THEN** | 返回结果包含：该测试文件覆盖的所有需求 ID、该测试文件验证的所有代码文件 |

### ACC-KG-03: 变更影响分析

| | |
|------|------|
| **ID** | ACC-KG-03-01 |
| **GIVEN** | 一个修改了 `src/yuleosh/alm/traceability.py` 的 PR |
| **WHEN** | CI 运行知识图谱增量构建 |
| **THEN** | PR 评论包含影响的 1+ 需求 ID 和 2+ 测试函数 |

| | |
|------|------|
| **ID** | ACC-KG-03-02 |
| **GIVEN** | 一个新增测试覆盖 `RS-002-01` 的 PR |
| **WHEN** | CI 运行知识图谱增量构建 |
| **THEN** | `RS-002-01` 的 `covers` 边新增一条，状态标记为 pass |

### ACC-KG-04: Merge Gate

| | |
|------|------|
| **ID** | ACC-KG-04-01 |
| **GIVEN** | 修改了 spec 中 `RS-003-01` 但未修改对应测试的 PR |
| **WHEN** | PR 尝试 merge |
| **THEN** | Merge gate 规则 `uncovered_requirement_change` 触发警告（如配置 block 则阻止 merge） |

### ACC-KG-05: 导出

| | |
|------|------|
| **ID** | ACC-KG-05-01 |
| **GIVEN** | 一个已引导的知识图谱 |
| **WHEN** | 用户执行 `yuleosh kg export --format markdown` |
| **THEN** | 输出的 Markdown 文件格式与现有 `requirement-traceability-matrix.md` 兼容 |
