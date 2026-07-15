# yuleOSH 知识图谱模块 — ASPICE 专家评审报告

> **评审日期**: 2026-07-14
> **评审对象**: yuleOSH Traceability Knowledge Graph (TKG)
> **评审人**: 小马 🐴 (ASPICE 专家，15+ 年经验，参与 Bosch/Continental/Vector 评估)
> **参考标准**: ASPICE v3.1 — SWE.4（软件验证）、SWE.5（软件确认）、SYS.4/SYS.5（系统层级追溯）
> **代码版本**: v0.1.0 实现（P0 + P1-1 子集）
> **当前图谱规模**: ~11,000 节点 / ~13,000 边

---

## 执行总结

yuleOSH 知识图谱（TKG）在**概念层面**展示了良好的 ASPICE 追溯意识：设计了需求→代码→测试的边类型体系、CI 驱动的增量构建方案，以及 merge gate 门禁机制。这比大多数零追溯的嵌入式项目领先一步。

然而，从**ASPICE 严格视角**审视，TKG 当前实现存在若干根本性缺口，使其**尚不能满足 ASPICE SWE.4/SWE.5 的证据要求**。核心问题不在工程实现质量（代码质量尚可），而在**追溯模型本身的设计缺陷**与**验证确认语义的混淆**。

### 综合评分

| 维度 | 评分 | 评级 |
|------|------|------|
| SWE.4 验证追溯对齐 | **32/100** | 🔴 不满足（根本性缺口） |
| SWE.5 确认追溯对齐 | **28/100** | 🔴 不满足（语义混淆） |
| SYS.4/SYS.5 对齐 | **15/100** | 🔴 不满足（无系统层级概念） |
| 数据模型合理性 | **55/100** | 🟡 基础框架合理但关键语义缺失 |
| CI 集成成熟度 | **45/100** | 🟡 架构设计好，实现不完整 |
| 缺口覆盖度 | **35/100** | 🔴 多个 ASPICE 必要追溯域完全缺失 |
| 数据完整性（可测试性） | **50/100** | 🟡 基础 CRUD 测试覆盖好，但业务语义测试不足 |
| **综合评分** | **37/100** | 🔴 **不通过 — 需重大修正确认后重新评审** |

### 条件结论

本次评审结论为：**不通过，有条件再审**。通过条件见末尾"改进条件"。

---

## 1. SWE.4 验证追溯对齐（32/100）🔴

### 1.1 ASPICE SWE.4 要求

SWE.4（Software Verification）的核心需求是：
- BP1: 开发验证策略，定义验证准则
- BP2: 建立软件详细设计与验证准则的双向追溯
- BP3: **软件详细设计→软件单元验证** 的追溯性
- BP4: 执行单元验证并记录结果
- BP5: 验证结果与验证准则的一致性

> SWE.4 的关键追溯对是：**软件详细设计 ↔ 单元验证（单元测试）**

### 1.2 当前 TKG 实现分析

TKG 当前的数据模型没有 `SoftwareDetailDesign`（软件详细设计）节点类型。它的 `Requirement` 节点对应的是**系统/软件需求**级别的 SHALL 语句（如 `RS-001-01`、`SWR-001.1-01`）。

SWE.4 的追溯链应当是：

```
软件详细设计（SWE.3 产出） ──covers──→ 单元测试（验证）
```

而当前 TKG 的模型是：

```
系统需求（RS/SWR） ──────covers──→ 测试函数
```

**根本性问题**：TKG 将 SWE.4（验证）和 SWE.5（确认）的追溯语义混淆到了同一个 `covers` 边中。单元测试验证的是软件详细设计（SWE.3），不是系统需求（SYS.3）。系统需求对测试的追溯属于 SWE.5 确认。

### 1.3 具体证据

**证据 1**: `models.py` 中 `ENTITY_TYPES` 定义

```python
ENTITY_TYPES = frozenset({
    "requirement",     # 无区分的"需求"类型
    ...
})
# models_pg.py 同样无 SoftwareDetailDesign 类型
```

系统需求（`RS-xxx`）、软件需求（`SWR-xxx`）、软件详细设计（`SWD-xxx`）全部被归到同一个 `requirement` 类型中。ASPICE 要求严格区分这三层。

**证据 2**: `queries.py` 中的 `trace_by_req_id` 使用单一边类型关系

```python
nodes, edges = store.trace_downstream(req_node.id, max_depth=3)
```

不区分 `covers` 边是因哪个测试层级（单元/集成/系统）创建的。同一张边连接需求→测试函数，混淆了验证与确认。

**证据 3**: `importer.py` 的 RTM 解析将需求→测试函数直接映射为 `covers` 边

```python
# 创建 covers 边: Requirement → TestFunction
store.upsert_edge(Edge(
    source_id=req_nid,
    target_id=tfn_nid,
    edge_type="covers",
    properties={
        "source": "requirement-traceability-matrix.md",
        "status": row["status"],
    },
))
```

没有对测试层级（Unit/Integration/System）做任何标记，导致 `covers` 边语义模糊。

### 1.4 修复方向（P0）

| 问题 | 建议修复 |
|------|----------|
| 缺少 `SoftwareDetailDesign` 类型 | 新增节点类型 `sw_design_element`，用例：SWD-001.1-01 |
| `covers` 边未区分测试层级 | 在 `properties` 中加入 `test_layer: unit/integration/system/e2e` |
| 验证与确认语义混淆 | 保留 `covers` 为验证边，新增 `validates` 边用于确认追溯 |
| RTM 不区分 SWE.4/SWE.5 | RTM 解析时增加测试层级判断，自动分配正确的边类型 |

---

## 2. SWE.5 确认追溯对齐（28/100）🔴

### 2.1 ASPICE SWE.5 要求

SWE.5（Software Qualification Testing / 软件确认）的核心需求：
- BP1: 建立确认测试策略，包含回归策略
- BP2: **建立软件需求与确认测试的双向追溯**
- BP3: 执行确认测试并记录结果
- BP4: **软件需求 → 集成测试 → 确认测试** 的全链覆盖率

> SWE.5 的关键追溯对是：**软件需求 ↔ 集成测试 / 确认测试**，且必须区分测试层级

### 2.2 当前 TKG 实现分析

TKG 当前的数据模型存在以下问题：

1. **无测试层级区分** — `TestFunction` 节点没有 `test_layer` 属性（单元/集成/系统/e2e），无法区分 SWE.5 要求的集成测试与 SWE.4 要求的单元测试
2. **无集成测试→单元测试的层次关系** — ASPICE 要求集成测试对单元测试的验证能力做"封闭"，当前无模型支撑
3. **`verifies` 边语义单一** — 仅记录"测试函数→代码函数"，未携带验证层级的上下文

### 2.3 具体证据

**证据 1**: `models.py` 中 `TestFunction` 的 properties 定义

```python
tf_node = Node(
    entity_type="test_function",
    entity_id=tfn_fqn,
    label=test_function,
    properties={
        "file_path": tf_path_clean,
        "source": "requirement-traceability-matrix.md",
    },
)
```

无 `test_layer`、`is_regression`、`verification_base`（验证依据是哪个设计元素）等 ASPICE 必需属性。

**证据 2**: `coverage_importer.py` 创建的 `verifies` 边

```python
store.upsert_edge(Edge(
    source_id=tfn.id,
    target_id=cfn.id,
    edge_type="verifies",
    properties={
        "source": "coverage_importer",
        "covered_function": cfn.label,
        "covered_lines": sorted(...),
    },
))
```

没有 `test_layer: integration` 或 `swe5_requirement: SWR-001.1-01` 等确认测试上下文标记。

**证据 3**: 图谱中实际数据确认

```
当前图谱边分布:
  contains:  11,488  (文件结构)
  covers:       182  (需求→测试)
  verifies:   1,361  (测试→代码函数)
  implements:     0  ❌ 完全缺失！无法建立"代码实现需求"的追溯
  defines:        0  ❌ 完全缺失！无法从规范文档查需求
  affects:        0  ❌ 完全缺失！CI 变更影响边未实现
```

`implements` 边数量为 0 意味着 TKG **完全无法回答"哪些代码实现了哪个需求"** 这个 ASPICE 最基础的追溯问题。

### 2.4 修复方向（P1+）

| 问题 | 建议修复 |
|------|----------|
| 无测试层级 | TestFunction.properties 增加 `test_layer: unit/integration/system/e2e` |
| 无 `implements` 边 | 实现 KG-12 推导规则（当前为零） |
| 无测试分层追溯 | 新增 `subsumes` 边（集成测试覆盖单元测试范围） |
| 无回归策略支撑 | Snapshot 间 diff 支持标记回归测试必要性 |

---

## 3. SYS.4/SYS.5 系统层级追溯对齐（15/100）🔴

### 3.1 ASPICE SYS 层级要求

- **SYS.4**: 系统集成测试 → 验证系统架构
- **SYS.5**: 系统确认测试 → 验证系统需求

TKG 当前完全没有系统级的概念：
- 无 `HILTest` / `SILTest` / `IntegrationTest` 节点类型
- 无 `SystemRequirement` 与 `SoftwareRequirement` 的追溯（`depends_on` 边未用于层级依赖）
- 无 `verification_criteria` 属性支撑 SYS.4/SYS.5 的验证准则追溯

### 3.2 对 yuleOSH 的实际影响

yuleOSH 是一个嵌入式框架（有 C 代码、HIL/SIL 测试），SYS 层级追溯是必备的。当前图谱中：

| 所需 SYS 层追溯 | 当前状态 |
|----------------|----------|
| 系统需求 → 软件需求 | 无（全混在 `requirement` 类型中） |
| 系统架构 → 系统集成测试 | 无（无系统架构节点） |
| HIL 测试结果追溯 | 无（`TestCase` 节点在 models_pg.py 中定义了类型但从未创建实例） |
| SIL 测试结果追溯 | 无 |
| DTC（售后故障）追溯 | 路线图 P3 才有 |

**关键发现**: `models_pg.py` 定义了 `test_case` 和 `knowledge_article` 节点类型，但 `models.py`（SQLite 实现）中**没有**。这意味着：

```python
# models.py (SQLite) 中
ENTITY_TYPES = frozenset({
    "requirement", "code_module", "code_file", "code_function",
    "test_file", "test_function", "spec_doc",
})

# models_pg.py (PostgreSQL) 中
ENTITY_TYPES = frozenset({
    "requirement", "code_module", "code_file", "code_function",
    "test_file", "test_function", "spec_doc",
    "knowledge_article", "test_case",  # 额外支持
})
```

两个后端的数据模型**不一致**，`test_case` 和 `knowledge_article` 节点在 SQLite 中无法创建。如果在本地开发和 PostgreSQL 生产间切换，部分追溯数据会丢失。

### 3.3 修复方向

| 问题 | 建议修复 |
|------|----------|
| 无系统层需求 | 节点新增 `system_requirement` + `sw_requirement` 子类型，或新增独立的节点枚举值 |
| 无集成测试节点 | 新增 `integration_test` 节点类型 |
| HIL/SIL 无追溯 | 通过 `test_case` 类型搭载 HIL/SIL 测试信息（模型必须对齐） |
| 后端模型不一致 | `models.py` 与 `models_pg.py` 的 ENTITY_TYPES/EDGE_TYPES 必须完全同步 |
| 无系统架构追溯 | 新增 `system_architecture` 节点类型 |

---

## 4. 数据模型合理性（55/100）🟡

### 4.1 基础框架评分

节点/边/快照的三层设计是合理的，与 Neo4j/有向图概念对齐。

| 评估项 | 评分 | 备注 |
|--------|------|------|
| 节点类型覆盖面 | 5/10 | 缺 `sw_design_element`, `system_requirement`, `integration_test` |
| 边类型覆盖面 | 4/10 | 缺 `validates`, `subsumes`, `traces_to`；`implements` 边类型定义了但零使用 |
| 属性设计 | 6/10 | `properties` JSONB 灵活但无强制 schema，`verified_at` 好 |  
| 快照机制 | 7/10 | `kg_snapshots` 设计好，但当前实际构建次数为零（无 CI 集成生成的快照） |
| 幂等性 | 8/10 | `UPSERT` 语义实现正确，有证据 |
| 版本追溯 | 3/10 | 边快照虽有设计但未真正实现版本 diff |
| 前后端一致性 | 3/10 | SQLite 和 PostgreSQL 模型不同步 |
| **小计** | **36/70** | |

### 4.2 关键设计缺陷

**缺陷 1**: `implements` 边存在但零使用

```python
# store_pg.py 中影响分析使用了 implements 边
AND e.edge_type IN ('implements', 'covers')
# 期望有 implements 边，但 importer.py 从未创建
```

这意味着当前 PostgreSQL 版的 `impact_analysis` 在生产环境中**永远只走 `covers` 路径**，无法回答"这个代码修改影响了哪个需求"（ASPICE SWE.5 BP2 的核心追问）。

**缺陷 2**: 启发式 `implements` 推导的风险谱系不完整

`importer.py` 中的 `_merge_test_functions` 将测试函数节点按 label 合并，但合并后的 `_merged_from` 标记记录在边的 `properties` 中作为不透明的 JSONB 字段，无法通过 SQL 查询。如果需要审计"哪个源头节点合并到了哪里"，需要全部扫描，无法高效回答 ASPICE 评估中的追溯检查。

**缺陷 3**: 代码扫描的 AST 缺失 `implements` 声明解析

`code_scanner.py` 的 `FunctionCollector` 能完美解析 Python 函数/类/方法，但没有解析注释中的 `// implements SHALL-XXX` 或 `@traceability` 装饰器，即使 KG-12 明确说了 MAY 支持。这是文档（spec draft）和实现之间的差距。

### 4.3 数据质量验证

从当前数据库中提取的统计：

```sql
-- 未覆盖的需求（无 covers 边）
SELECT COUNT(*) FROM kg_nodes WHERE entity_type='requirement'
  AND is_active=1 AND id NOT IN (
    SELECT DISTINCT source_id FROM kg_edges WHERE edge_type='covers'
  );
-- 结果: 4 个需求无测试覆盖 ❌

-- 孤立代码文件（无任何边）
SELECT COUNT(*) FROM kg_nodes WHERE entity_type='code_file'
  AND is_active=1 AND id NOT IN (
    SELECT source_id FROM kg_edges UNION SELECT target_id FROM kg_edges
  );
-- 结果: 31 个代码文件无任何关联 ❌

-- implements 边
SELECT COUNT(*) FROM kg_edges WHERE edge_type='implements';
-- 结果: 0 ❌

-- 实际 vs spec 预期对齐
-- spec 预期 RS-001-01 应连接 tests/test_engine.py, 但 db 实际...
-- 需要进一步验证数据完整性
```

4 个孤立需求和 31 个孤立代码文件是 ASPICE 审核的高风险项，表明导入/合并流程存在数据丢失。

---

## 5. CI 集成成熟度（45/100）🟡

### 5.1 架构设计评分

CI 集成方案（kg-architecture.md §5）是目前文档中设计得最好的部分。

| 评估项 | 评分 | 备注 |
|--------|------|------|
| 增量构建算法设计 | 7/10 | Step 1-5 清晰，但 spec 变更检测过于简化 |
| `ci_hook.py` 实现 | 6/10 | 自动 bootstrap 机制好，但无增量构建逻辑 |
| `git_hook_check.py` | 7/10 | 安装/卸载/版本管理完备 |
| 实际部署 | 2/10 | 当前 `kg_snapshots` 表为 0 条记录，说明 CI 集成从未实际运行 |
| Merge gate 设计 | 5/10 | 架构文档有但代码未实现 |
| PR 影响分析报告 | 3/10 | `ci_hook.py` 可以返回影响分析但未实现 PR comment 发布 |
| 隔夜全量重建 | 0/10 | R1 缓解方案未实现 |
| **小计** | **30/70** | |

### 5.2 关键发现

**证据 1**: 当前 `kg_snapshots` 表为零记录

```bash
sqlite3 .yuleosh/knowledge_graph.db "SELECT COUNT(*) FROM kg_snapshots;"
# → 0
```

这意味着所有的知识图谱数据只存在于直接 commit 的导数库中，从未经过 CI 管道生成快照。如果团队问"上次 CI 验证了哪个构建的追溯一致性"，答案是"从来没有"。

**证据 2**: `ci_hook.py` 的 `kg_ci_append()` 没有实现增量构建

```python
def kg_ci_append(store: KGStore, build_id: str,
                 changed_files=None, meta=None) -> dict:
    # ...
    # 只做了：检查空图 → 自动 bootstrap → 创建 snapshot
    # 没有：diff 分析、增量更新节点、推导 implements 边
```

架构文档 §5.2 的增量构建算法有 5 个步骤，`ci_hook.py` 大约实现了 **1/5**（仅 snapshot + 影响分析查询）。

**证据 3**: 文件过滤逻辑仅支持 `.py`

```python
def _filter_project_files(files: list[str]) -> list[str]:
    result = []
    for f in files:
        if f.startswith("src/yuleosh/") and f.endswith(".py"):
            result.append(f)
        elif f.startswith("tests/") and f.endswith(".py"):
            result.append(f)
    return result
```

yuleOSH 包含 C 代码（`src/fault-inject/src/*.c`）、配置文件、头文件等。这些变更**完全不会**触发知识图谱更新，意味着修改 C 代码对追溯的影响从不被检测。

### 5.3 在 ASPICE 语境下的意义

ASPICE 现场评估通常会检查：
1. CI 中是否存在追溯检查步骤？→ 有脚本（ci_hook.py），但未真正集成
2. 是否每次构建都生成可追溯证据？→ 从未生成过 `kg_snapshots`
3. 追溯是否在代码合并前自动验证？→ Merge gate 未实现
4. 是否有超时降级机制？→ 文档写了，代码未实现

CI 集成当前是**概念可行、实现零起点**的状态。如果今天被问"构建自动追溯的证据在哪"，答案是零。

---

## 6. 缺口分析（35/100）🔴

### 6.1 ASPICE 必需但 TKG 未覆盖的追溯域

| 追溯域 | ASPICE 关联 | TKG 状态 | 重要性 |
|--------|-------------|----------|--------|
| SWE.1 软件需求→SWE.2 软件架构 | 架构设计和需求双向追溯 | ❌ 缺失 | P0 |
| SWE.2 软件架构→SWE.3 详细设计 | 详细设计满足架构 | ❌ 缺失 | P0 |
| SWE.3 详细设计→SWE.4 单元测试 | 详细设计被验证 | ❌ 缺失（混淆在需求→测试中） | P0 |
| SWE.4 单元测试→SWE.3 详细设计 | 追溯反向 | ❌ 缺失 | P0 |
| SWE.5 确认测试→SWE.1 软件需求 | 需求被确认 | ❌ 缺失（边类型混淆）| P0 |
| SYS.3 系统需求→SYS.5 系统确认 | 系统级 | ❌ 无系统层概念 | P1 |
| SYS.4 系统集成→SYS.2 系统架构 | 架构被集成验证 | ❌ 无系统层概念 | P1 |
| 变更→受影响需求/测试 | 变更管理 | 🟡 仅影响分析 API 基础实现 | P1 |
| 安全需求→安全机制 | ISO 26262 | ❌ 无 `safety_level` 溯源 | P2 |
| FMEA→设计→验证 | 功能安全 | ❌ 路线图 P3 才有 | P3 |

### 6.2 文档与实现的差距

| 文档规范 | 实现状态 | 差距评级 |
|----------|----------|----------|
| KG-12: implements 边推导 | 未实现，零条边 | 🔴 P0 |
| KG-11: 增量构建 | 未实现 | 🔴 P0 |
| KG-20: 追溯查询 API | 基本实现，但无 `direction=both` | 🟡 P1 |
| KG-21: 变更影响分析（direct/indirect） | 仅 `queries.py` 实现，`impact_analysis()` 无间接影响等级 | 🟡 P1 |
| KG-22: 孤岛节点检测 | 已实现 | ✅ |
| KG-30: CI build step | 仅 `ci_hook.py` 外壳 | 🔴 P0 |
| KG-31: PR 影响报告 | 未实现 | 🔴 P0 |
| KG-32: Merge gate | 未实现 | 🔴 P0 |
| KG-40: 导出（Markdown/JSON/YAML） | 未实现 | 🟡 P1 |
| KG-41: 导入的 schema 校验 | 未实现 | 🟡 P1 |

### 6.3 ASPICE 评估者会问（可能被问到的现场问题）

```
Q1: 请展示从「软件需求 SWR-001.1」到「实现它的代码」的追溯。
→ 当前无法展示 — implements 边为零。

Q2: 请展示从「测试函数 test_pipeline_run」到「被验证的详细设计元素」的追溯。
→ 无法展示 — 无 SoftwareDetailDesign 节点，单元测试直接挂在需求节点上。

Q3: 上次 CI 构建的追溯快照在哪里？
→ 无法展示 — kg_snapshots 表为零，没有快照。

Q4: 需求 RS-... 的 covers 边是 unit test 还是 integration test 的？
→ 无法区分 — 无 test_layer 属性。

Q5: 变更这个文件会影响哪些已验证的需求？
→ 部分可以 — 影响分析有基础实现，但无 implements 边所以路径不完整。

Q6: 请展示从集成测试到单元测试的层次追溯。
→ 无法展示 — 无集成测试节点类型。
```

这些问题任意一个出现在 ASPICE 评估中，都可能导致对该过程的 **NC（不符合项）** 判定。

---

## 7. 数据可测试性（50/100）🟡

### 7.1 测试覆盖评分

| 测试维度 | 行数 | 评分 | 备注 |
|----------|------|------|------|
| KGStore CRUD | ~150 行 | 7/10 | 基础增删改查覆盖好 |
| 导入器 | ~120 行 | 6/10 | RTM/JSON 导入有测试，但缺少边界条件测试 |
| 查询 API | ~80 行 | 5/10 | 基础追溯有测试，但缺少负载、边缘查询测试 |
| CI Hook | ~60 行 | 4/10 | 大部分测试用 mock git，缺少真实 CI 集成测试 |
| Git Hook | ~120 行 | 7/10 | 安装/卸载/版本管理测试覆盖好 |
| 代码扫描器 | ~150 行 | 7/10 | AST 解析覆盖好（含嵌套类、async 函数） |
| 覆盖率导入器 | ~70 行 | 4/10 | 路径匹配不可靠，缺少边界测试 |
| Merge 函数 | ~100 行 | 6/10 | 合并逻辑有测试，但缺少大规模合并的性能测试 |
| **小计** | **~850 行** | **5.75/10** | |

### 7.2 测试缺口

**缺口 1**: 无追溯完整性测试

没有针对 `Req_A → Test_B → Code_C` 完整链路的端到端测试（`test_merge_restores_full_chain` 是唯一的逼近案例）。ASPICE 关心的不是单个 CRUD 操作是否正确，而是**追溯链是否可闭合**。

**缺口 2**: 无数据一致性验证

没有测试验证：
- 所有节点 `is_active` 时是否有至少一条边
- 所有 Requirement 节点的 `covers` 边数是否与 RTM 一致
- `implements` 边的目标是否存在且类型正确

**缺口 3**: 无性能基准测试

`kg-architecture.md §8` 的性能预估（500ms @ 50K 节点）完全未经验证。当前实际数据不到 100K，但：

- SQLite BFS 的 `trace_downstream` 没有递归限制之外的防御性保护
- 没有测试 `impact_analysis` 在满载~11K 节点时的真实延迟

**缺口 4**: 测试数据规模远小于生产

```python
# test fixtures 中最大的数据量：
# 5 个需求 + 5 个测试文件 + 每个文件 2 个测试函数
# → 约 15 个节点
# → 生产环境约 11,000 个节点
# → 差 3 个数量级！
```

测试数据没有覆盖"生产规模"的图谱，`trace_downstream` 在 11K 节点下的 BFS 性能完全未验证。

### 7.3 测试改进建议

| 优先级 | 建议 | 说明 |
|--------|------|------|
| P0 | 端到端追溯链测试 | 插入完整链（Req → Test → Code → Implements → Req），验证查询闭环 |
| P0 | 数据一致性断言 | 每个 import 后验证节点数、边数、孤立节点数符合预期 |
| P1 | 性能基准测试 | 在当前 11K 节点库上跑 trace/impact 查询，记录耗时 |
| P1 | 错误注入测试 | 模拟 coverage 文件格式错误、AST 解析错误、RTM 格式错误 |
| P2 | 大规模节点合并测试 | 100+ 重复 test_function 的 merge 性能测试 |

---

## 8. 改进建议（分级）

### 🔴 P0 — 必须解决（阻塞 ASPICE 合规）

1. **[P0] implements 边必须非零** — `KG-12` 的推导规则（基于 covers×verifies 反向推导）必须实现。零 `implements` 边意味着"代码→需求"追溯完全断裂。
2. **[P0] 区分 SWE.4 验证 vs SWE.5 确认的边语义** — `covers` 边必须携带 `test_layer`（unit/integration/system），并新增 `validates` 边类型用于 SWE.5 确认追溯。或者至少将 `covers` 边按测试层级拆分。
3. **[P0] CI 集成从零到一** — 在任意 CI pipeline 中实际部署 `ci_hook.py`，生成至少一条 `kg_snapshots` 记录。当前 0 快照是不合格状态。
4. **[P0] 新增 SoftwareDetailDesign 节点类型** — SWE.3（详细设计）到 SWE.4（单元测试）的追溯是 ASPICE 硬性要求，当前完全缺失。
5. **[P0] 减少孤立节点** — 修复导入/合并流程，消除当前 4 个无 covers 的需求和 31 个孤立代码文件。

### 🟡 P1 — 高优先级（影响评估可信度）

6. **[P1] 增量构建引擎** — 实现 `kg-architecture.md §5.2` 的全部 5 个步骤。当前 `ci_hook.py` 只做了 snapshot 这一步。
7. **[P1] 测试层级元数据** — 所有 `TestFunction` 节点增加 `test_layer` 属性。`req-test-mapping.json` 和 RTM 导入时根据文件路径/命名规则自动推断。
8. **[P1] `models.py` 与 `models_pg.py` 模型同步** — 两端的 `ENTITY_TYPES` 和 `EDGE_TYPES` 必须完全一致，消除数据丢失窗口。
9. **[P1] Merge gate 最小实现** — 至少实现 `uncovered_requirement_change` 的 `warn` 级别规则。
10. **[P1] 性能基准并优化** — 在当前 ~11K 节点库上跑通 `trace_downstream` 并确认 < 100ms。
11. **[P1] 非 Python 文件支持** — `_filter_project_files` 扩展至 `.c`、`.h`、`.cfg` 等 yuleOSH 涉及的文件类型。
12. **[P1] 端到端追溯链测试** — 测试完整的 `Req → Test → Code → Req` 闭环追溯。

### 🔵 P2 — 中优先级（建议本迭代完成）

13. **[P2] 增量构建超时降级** — 实现 `kg-risk-analysis.md R5` 的超时→`partial: true`→隔夜补全机制。
14. **[P2] 显式追溯声明解析** — `code_scanner.py` 支持解析注释中的 `// implements SHALL-xxx` 和 `@traceability` 装饰器。
15. **[P2] Snapshot 快照 diff** — 实现 `KG-03 SHOULD` 的跨 snapshot diff（新增/修改/删除节点和边）。
16. **[P2] 隔夜全量重建** — 实现 `kg-risk-analysis.md R1` 缓解方案的定时一致性审计。
17. **[P2] 导出功能** — 实现 `KG-40` 的 Markdown/JSON/YAML 导出。

### ⚪ P3 — 低优先级（可选）

18. **[P3] Neo4j 同步管道**
19. **[P3] 可视化仪表盘**
20. **[P3] DTC → Requirement → Code → Test 全链追溯**

---

## 9. ASPICE 评估风险雷达

```
                    SWE.4 需求→代码追溯 (32/100)
                         │
                         │
    SYS.5 系统确认 ───────┤─────── SWE.5 确认追溯 (28/100)
    (15/100)              │
                         │
                         │
    CI 成熟度 (45/100) ───┴─── 数据模型 (55/100)
```

当前 TKG 最接近 ASPICE 合规的是**数据模型和 CI 架构的概念层**（文档做得好），而**实现层（边类型覆盖、CI 部署、增量构建）远未就绪**。

---

## 10. 改进条件（Conditional Pass Conditions）

若需要在下次评审中获得**有条件通过**，以下条件必须全部满足：

### Condition A: 追溯链可闭合
```
通过测试验证：
  插入完整追溯链：
    Requirement RS-001-01 → covers → TestFunction test_foo::test_bar
    TestFunction test_foo::test_bar → verifies → CodeFunction engine::bar
    CodeFunction engine::bar → implements → Requirement RS-001-01
  验证：trace_by_req_id("RS-001-01") 返回完整子图（含代码函数和测试函数）
  验证：impact_analysis(["src/engine.py"]) 返回 RS-001-01 作为受影响需求
```

### Condition B: CI 集成已验证
```
至少有 1 条 kg_snapshots 记录由 ci_hook.py 通过 CI 管道生成
```

### Condition C: 测试层级区分
```
所有 covers 边的 properties 中包含 test_layer 标记（unit/integration/system）
```

### Condition D: 孤立节点清零
```
重复 import 后：
  - 无 covers 的需求数 = 0（所有需求至少有一个测试覆盖）
  - 无边的代码文件数 = 0
  - 无边的测试文件数 = 0（每个测试文件至少被一个需求覆盖）
```

### Condition E: SWE.4 / SWE.5 边语义分离
```
covers 边携带 test_layer 属性
新增 validates 边用于 SWE.5 确认追溯（或等价的语义区分方案）
```

> ⚠️ 重要提示：以上条件仅用于"有条件通过"评审。要实现完整的 ASPICE SWE.4/SWE.5 合规，还需要额外满足 §3（SYS 层级）、§6（缺口分析）中的 P0/P1 改进建议。

---

## 附录 A: 本次评审中需再确认的问题

| # | 问题 | 当前状态 |
|---|------|----------|
| 1 | `importer._merge_test_functions` 的唯一性保障 | 按 label 合并，但 label 可能跨文件重复（来自不同模块的同名测试函数） |
| 2 | `store_pg.impact_analysis` 的 `depends_on` 查询 | 当前 SQL 仅查 1-hop，架构文档说的是 N-hop |
| 3 | `kg-architecture.md §8` 性能预估的验证方法 | 未提供基准测试代码 |
| 4 | SQLite 后端 `trace_downstream` 使用 Python BFS vs PostgreSQL 使用 SQL CTE | 两端的语义等价性未测试 |
| 5 | CI 管道中 TKG step 的真实执行时间 | 无基准数据 |

## 附录 B: 核心代码索引

| 文件 | 路径 | 评分原因 |
|------|------|----------|
| `store.py` | `knowledge_graph/store.py` | ✅ CRUD 实现规范；❌ Python BFS 无 CTE |
| `models.py` | `knowledge_graph/models.py` | ⚠️ 实体类型缺 SWD/SystemReq/IntegrationTest |
| `queries.py` | `knowledge_graph/queries.py` | ⚠️ 影响分析缺乏间接影响等级 |
| `importer.py` | `knowledge_graph/importer.py` | ⚠️ 不创建 `implements` 边 |
| `code_scanner.py` | `knowledge_graph/code_scanner.py` | ✅ AST 解析优秀 |
| `coverage_importer.py` | `knowledge_graph/coverage_importer.py` | ⚠️ 路径匹配逻辑不稳定 |
| `ci_hook.py` | `knowledge_graph/ci_hook.py` | ⚠️ 骨架完成但增量构建引擎未实现 |
| `git_hook_check.py` | `knowledge_graph/git_hook_check.py` | ✅ 功能完备 |
| `store_pg.py` | `knowledge_graph/store_pg.py` | ⚠️ impact_analysis 使用 CTE 但仅 1-hop 依赖 |
| `models_pg.py` | `knowledge_graph/models_pg.py` | 🔴 与 `models.py` ENTITY_TYPES 不同步 |
| `queries_pg.py` | `knowledge_graph/queries_pg.py` | ⚠️ 正确但缺少端到端追溯测试 |

---

*报告结束。评审结论：不通过。请在下次评审前完成 P0 条件的修复。*
