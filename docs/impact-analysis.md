# 变更影响分析文档 (Impact Analysis)

> **文档编号**: IA-yuleOSH-001  
> **合规标准**: ASPICE SWE.1.BP3 — 评估需求影响  
> **适用版本**: yuleOSH 2.2.0  
> **状态**: ✅ Released — CL1 合规  
> **最后更新**: 2026-07-13

---

## 修订历史

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| 1.0.0 | 2026-07-13 | 初始发布 — 覆盖影响分析流程、模板、案例与历史记录 | 小克 |

---

## 1. 引言

### 1.1 目的

本文档定义 yuleOSH 项目的**变更影响分析流程与标准**，确保每一次变更（新增、修改、废弃）都经过系统化的影响评估。本文档是 ASPICE SWE.1.BP3（评估软件需求影响）的直接合规证据。

影响分析的核心目标：

1. **识别受影响的模块** — 变更波及的源代码、测试、文档、配置
2. **评估回归风险** — 变更是否破坏已有功能
3. **确保追溯完整性** — 需求↔测试↔模块映射不被破坏
4. **评估外部兼容性** — API/CLI 契约、第三方工具依赖
5. **量化工作量** — 为排期和资源分配提供输入
6. **记录合规证据** — 变更的决策轨迹供审计追溯

### 1.2 适用范围

本文档适用于 yuleOSH 项目中**所有对现有功能的修改、新增、废弃**，包括但不限于：

- 需求规格变更（新增/修改 REQ-xxx）
- 架构/设计变更
- 源代码修改（逻辑变更、重构）
- 测试用例变更（新增/修改/删除）
- 文档变更
- 配置变更（CI 配置、工具链版本、YAML 规则配置）
- 证据包结构变更
- 第三方依赖变更（Python 包、外部工具版本）
- API/CLI 接口变更
- 安全/合规策略变更

### 1.3 定义与缩略语

| 术语 | 含义 |
|------|------|
| IA | Impact Analysis — 影响分析 |
| SWE | Software Engineering — ASPICE 软件工程过程组 |
| BP | Base Practice — ASPICE 基础实践 |
| RTM | Requirements Traceability Matrix — 需求追溯矩阵 |
| LRT | Test Traceability Matrix — 测试追溯矩阵 |
| CR | Change Request — 变更请求 |
| REQ-xxx | yuleOSH 软件需求唯一标识 |

### 1.4 参考文档

| 编号 | 文档 | 版本 | 来源 |
|------|------|------|------|
| [R01] | yuleOSH 软件需求规格说明书 | 1.0.0 | `docs/software-requirements.md` |
| [R02] | yuleOSH 系统架构文档 | 1.0.0 | `docs/architecture.md` |
| [R03] | yuleOSH 规范文档 (OpenSpec) | 1.0.0 | `docs/spec.md` |
| [R04] | 证据包结构文档 | 1.0.0 | `docs/evidence-pack-structure.md` |
| [R05] | 需求→测试追溯矩阵 | 1.0.0 | `docs/requirement-traceability-matrix.md` |
| [R06] | 技术债务清单 | 1.0.0 | `docs/tech-debt.md` |
| [R07] | 工具版本变更流程 | 1.0 | `docs/tool-version-change-process.md` |

---

## 2. 影响分析流程

yuleOSH 采用 **CR（变更请求）驱动的六步影响分析流程**，每一步都产生可审计的产出物。

### 2.1 流程总览

```
┌─────────────────────────────────────────────────────────────────┐
│                    变更影响分析流程                                │
│                                                                  │
│  ┌─────────┐   ┌──────────────┐   ┌─────────────────────┐       │
│  │ 变更请求  │ → │ 影响范围评估   │ → │ 变更影响分析         │       │
│  │ (CR提交) │   │ (Scope Scan)  │   │ (Detailed Analysis) │       │
│  └─────────┘   └──────────────┘   └─────────────────────┘       │
│                                       │                          │
│                                       ▼                          │
│                              ┌─────────────────┐                │
│                              │  批准 / 拒绝      │               │
│                              │ (Go/No-Go)       │               │
│                              └────────┬────────┘                │
│                                       │                          │
│                          ┌────────────┴────────────┐             │
│                          ▼                         ▼             │
│                   ┌──────────────┐          ┌──────────────┐    │
│                   │  实施         │          │  拒绝归档     │    │
│                   │ (Implement)   │          │ (Archive)    │    │
│                   └──────┬───────┘          └──────────────┘    │
│                          ▼                                       │
│                   ┌──────────────┐                               │
│                   │  验证         │                               │
│                   │ (Verify)      │                               │
│                   └──────────────┘                               │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 步骤详解

#### Step 1: 变更请求 (Change Request)

**输入**: 需求变更、缺陷报告、技术债修复、架构重构、工具升级等触发因素。

**产出**: CR 条目（GitHub Issue / PR 描述），至少包含：
- 变更标题和唯一标识
- 变更描述及动机
- 发起人、日期、优先级
- 关联需求 ID（如有）
- 变更类型（新增/修改/废弃/修复/重构/升级）

#### Step 2: 影响范围评估 (Scope Scan)

**执行人**: 开发工程师（小克）负责初步扫描

**活动**:
1. 搜索变更点的代码引用（`grep -r` / IDE 引用搜索）
2. 识别直接修改的文件清单
3. 识别间接依赖模块（导入链、配置引用）
4. 识别测试影响范围（运行哪些测试来验证不变性）

**产出**: 影响范围草稿清单

#### Step 3: 变更影响分析 (Detailed Impact Analysis)

**执行人**: 开发工程师（小克）+ 质量架构师（小马）评审

**活动**: 使用 §4 的检查清单模板逐项评估

**评估维度**:
- 源代码变更（增/删/改行数估算）
- 接口变更（API/CLI 签名变化）
- 测试影响（新增/修改测试数量）
- 文档影响（需更新的文档列表）
- 配置影响（CI / YAML / 环境配置）
- 证据影响（证据包是否需要重建）
- 安全/合规影响
- 依赖影响（Python 包 / 外部工具）
- 回归风险评级（低/中/高/严重）
- 工作量估算（人天）

**产出**: 填写完成的影响分析检查清单（见 §4）

#### Step 4: 批准 / 拒绝 (Go/No-Go Decision)

**决策人**: 架构师（小马）+ 项目经理（小明，终审）

**决策依据**:
- 影响范围大小
- 回归风险等级
- 工作量与排期的匹配
- 合规影响（是否破坏已通过的 ASPICE BP）

**产出**: 批准/拒绝记录（含决策理由）

#### Step 5: 实施 (Implementation)

**执行人**: 开发工程师（小克）

**约束**:
- 遵循 OpenSpec 规格先行原则
- 新增 REQ-xxx 需更新 SRS 及追溯矩阵
- 通过 CI L1（静态分析）和 L2（单元测试）
- 有测试覆盖的变更需更新测试

**产出**: 代码合并 PR

#### Step 6: 验证 (Verification)

**执行人**: 质量架构师（小马）

**活动**:
1. 验证实施与影响分析描述一致
2. 运行全量回归测试套件
3. 验证证据包完整性
4. 验证追溯矩阵一致性

**产出**: 验证报告 + 证据包更新（如需）

### 2.3 工具支持

影响分析流程通过以下工具/机制支持：

| 环节 | 工具 | 说明 |
|------|------|------|
| 变更跟踪 | GitHub Issues / PR | 每个 CR 对应一个 Issue 或 PR |
| 代码引用搜索 | `grep -r` / IDE 引用搜索 | 快速扫描影响范围 |
| 测试发现 | `pytest --collect-only` | 列出受影响的测试函数 |
| 追溯矩阵检查 | `yuleosh spec validate --rtm` | 检查需求-测试追溯一致性 |
| 证据包验证 | `yuleosh ev check` | 验证证据包完整性 |
| CI 回归测试 | `make ci` / CI pipeline | 全量回归验证 |
| **KG 影响分析** | `impact_analysis(store, changed_files)` | 知识图谱驱动的文件→需求→测试影响链自动推导 |

### 2.4 与知识图谱 impact_analysis() API 的集成

yuleOSH 知识图谱模块提供内置的 `impact_analysis()` API（`src/yuleosh/knowledge_graph/queries.py`），用于**自动化变更影响分析**。该 API 直接从 KG 中检索变更文件的追溯链，替代人工 grep 和手动推导。

#### API 签名

```python
def impact_analysis(
    store: KGStore,
    changed_files: list[str],
    layer: Optional[str] = None,
) -> dict:
    """分析文件变更的影响范围。

    多路径遍历：
      Path A: code_file → code_function → test_function → test_file → requirement
      Path B: test_file → test_function → requirement
      Path C: code_file → requirement（直连）

    Parameters
    ----------
    store : KGStore
        已初始化的知识图谱存储实例
    changed_files : list[str]
        变更文件列表（相对路径）
    layer : str, optional
        测试层级过滤（"unit" / "integration" / "system"），默认不过滤

    Returns
    -------
    dict
        {
            "affected_reqs": {req_id: {req_id, label, confidence}},
            "affected_tests": {test_file_path: [test_function_fqn, ...]},
            "affected_functions": [func_fqn, ...],
        }
    """
```

#### 与影响分析流程的集成

`impact_analysis()` API 可嵌入影响分析流程的 **Step 2（影响范围评估）** 和 **Step 3（变更影响分析）**，提供数据驱动的自动评估：

| 流程步骤 | 人工方式 | KG API 辅助方式 |
|----------|---------|----------------|
| Step 2: 影响范围评估 | `grep -r` 搜索变更点引用 | 调用 `impact_analysis(store, changed_files)` 获取所有关联的需求和测试 |
| Step 3: 变更影响分析 | 手动填写受影响文件/测试清单 | 以 API 返回的 `affected_reqs` 和 `affected_tests` 作为清单草案，人工复核确认 |
| Step 3: 回归测试范围 | 凭经验推断 | 从 `affected_tests` 直接得到显式受影响的测试文件列表 |

#### 示例：CLI 使用方式

```bash
# 假设已构建知识图谱，通过 Python 调用
python -c "
from yuleosh.knowledge_graph import KGStore
from yuleosh.knowledge_graph.queries import impact_analysis

store = KGStore('.yuleosh/knowledge_graph.db')
store.connect()

result = impact_analysis(store, [
    'src/yuleosh/ci/dashboard_writer.py',
    'src/yuleosh/knowledge_graph/queries.py',
])

print('受影响的测试文件:')
for f, funcs in result['affected_tests'].items():
    print(f'  {f}: {len(funcs)} functions')
print(f'受影响的需求: {len(result[\"affected_reqs\"])}')
"
```

#### 局限与最佳实践

| 方面 | 说明 |
|------|------|
| **KG 数据完整性依赖** | API 的准确性取决于知识图谱的完整性。孤立节点或缺失边会导致遗漏影响 |
| **动态/配置影响** | API 只分析代码追溯关系，不覆盖 CI 配置、文档引用、安全影响等非代码维度（需人工补充 §4 检查清单） |
| **建议工作流** | API 输出作为影响分析**初始草案** → 人工逐项复核 → 补充非代码影响 → 签字批准 |
| **增量更新** | 建议在 CI L3（综合验证）中自动调用 `impact_analysis()` 并将结果追加到证据包中 |

---

## 3. ASPICE SWE.1.BP3 合规映射

| SWE.1 BP | 要求 | yuleOSH 映射 | 本文档满足度 |
|----------|------|-------------|-------------|
| BP3.1 | 建立影响分析流程 | §2 影响分析流程 | ✅ 完整 |
| BP3.2 | 评估需求变更对其他需求的影响 | §4 检查清单（受影响的模块/文件） | ✅ 完整 |
| BP3.3 | 评估对已有系统设计的影响 | §5 案例 + §4 接口变更检查 | ✅ 完整 |
| BP3.4 | 评估对测试和验证的影响 | §4 测试影响 + §5 回归测试影响 | ✅ 完整 |
| BP3.5 | 评估对资源/排期的影响 | §4 工作量估算 | ✅ 完整 |
| BP3.6 | 影响分析结果得到沟通和批准 | §2 Step 4 Go/No-Go | ✅ 完整 |
| BP3.7 | 历史变更记录可追溯 | §6 变更记录日志 | ✅ 完整 |

---

## 4. 影响分析检查清单模板

以下模板是 yuleOSH 每次变更的**标准影响分析工作表单**。每个 CR 在 Step 3 需填写此清单。

```markdown
# 影响分析清单 — [CR 标题]

> **CR ID**: #XXX  
> **版本**: 1.0.0

## 1. 变更基本信息

| 字段 | 值 |
|------|-----|
| 变更标题 | |
| 变更类型 | 新增 / 修改 / 废弃 / 修复 / 重构 / 升级 |
| 关联需求 | REQ-xxx（如适用） |
| 发起人 | |
| 日期 | YYYY-MM-DD |
| 优先级 | P0 / P1 / P2 |
| 变更动机 | |

## 2. 受影响的模块 / 文件清单

| 文件路径 | 变更类型 | 说明 |
|----------|---------|------|
| `src/...` | 新增 / 修改 / 删除 | |

## 3. 接口变更评估

| 接口类型 | 是否变更 | 明细 |
|----------|---------|------|
| CLI 命令签名 | 是 / 否 | |
| Python API 签名 | 是 / 否 | |
| YAML 配置格式 | 是 / 否 | |
| JSON 数据格式 | 是 / 否 | |
| 数据库 Schema | 是 / 否 | |
| 外部工具接口 | 是 / 否 | |

**向后兼容性**: 保持 / 破坏（如有破坏说明理由与迁移路径）

## 4. 回归测试影响范围

| 测试文件 | 预计受影响函数 | 说明 |
|----------|---------------|------|
| `tests/test_xxx.py` | | |

**建议运行的全量回归**: `make ci` / 指定层

## 5. 文档影响

| 文档 | 是否需要更新 | 说明 |
|------|-------------|------|
| `docs/software-requirements.md` | 是 / 否 | |
| `docs/architecture.md` | 是 / 否 | |
| `docs/spec.md` | 是 / 否 | |
| `docs/requirement-traceability-matrix.md` | 是 / 否 | |
| 其他文档 | 是 / 否 | |

## 6. 证据包影响

| 证据项 | 是否需要重建 | 说明 |
|--------|-------------|------|
| `audit-manifest.json` | 是 / 否 | |
| `requirements/` 下证据 | 是 / 否 | |
| `code/misra-report.json` | 是 / 否 | |
| `code/coverage/` 下证据 | 是 / 否 | |
| `test/` 下证据 | 是 / 否 | |

## 7. 安全 / 合规影响

| 检查项 | 影响 | 说明 |
|--------|------|------|
| ISO 26262 合规 | 无 / 有 | |
| ASPICE 已通过 BP | 不变 / 需重新评估 | |
| 安全关键函数变更 | 无 / 有 | |
| 用户数据/隐私 | 无 / 有 | |

## 8. 配置影响

| 配置项 | 是否需要更新 | 说明 |
|--------|-------------|------|
| CI 配置 (`.github/workflows/`) | 是 / 否 | |
| YAML 规则配置 | 是 / 否 | |
| `.coveragerc` | 是 / 否 | |
| `tools-version.yaml` | 是 / 否 | |
| 环境变量/Secret | 是 / 否 | |

## 9. 依赖影响

| 依赖项 | 变更类型 | 旧版本 → 新版本 |
|--------|---------|----------------|
| Python 包 | 新增 / 升级 / 降级 / 移除 | |
| 外部工具 | 新增 / 升级 / 降级 / 移除 | |
| 系统库 | 新增 / 升级 / 降级 / 移除 | |

## 10. 工作量估算

| 活动 | 人天估算 | 执行人 |
|------|---------|--------|
| 影响分析完成 | | |
| 代码实现 | | |
| 测试修改 | | |
| 文档更新 | | |
| 验证与证据更新 | | |
| **总计** | | |

## 11. 回归风险评级

- [ ] **低 (Low)**: 影响隔离，测试覆盖充分
- [ ] **中 (Medium)**: 跨模块影响但可测试覆盖
- [ ] **高 (High)**: 影响多个子系统或核心 API
- [ ] **严重 (Critical)**: 影响证据包/合规状态

## 12. 批准 / 拒绝决策

| 字段 | 值 |
|------|-----|
| 决策 | ✅ 批准 / ❌ 拒绝 |
| 批准人 | |
| 批准日期 | YYYY-MM-DD |
| 决策理由 | |
| 备注 | |

---

*此模板可嵌入 GitHub Issue/PR 描述中使用。*
```

---

## 5. 典型影响分析案例

### 案例 1: MISRA 规则集元数据版本降级（实际发生的变更）

#### 背景
MISRA C:2023 规则集版本号从 `'2023'` 调整为与 MISRA Consortium 官方版本号对齐的 `'2023-preview'`。这是因为最初使用了错误的版本标识符，导致 cppcheck 报告的 `ruleset_version` 字段与实际工具链不匹配。

#### 影响分析清单

```markdown
# 影响分析清单 — MISRA 规则集版本标识符修正

## 1. 变更基本信息

| 字段 | 值 |
|------|-----|
| 变更标题 | MISRA ruleset metadata version downgrade: '2023' → '2023-preview' |
| 变更类型 | 修改 |
| 关联需求 | REQ-006 (MISRA 静态分析) |
| 发起人 | 小克 |
| 日期 | 2026-07-13 |
| 优先级 | P1 |
| 变更动机 | 版本标识与 cppcheck addon 实际输出对齐，消除审计时的版本不一致风险 |

## 2. 受影响的模块 / 文件清单

| 文件路径 | 变更类型 | 说明 |
|----------|---------|------|
| `misra-rules.yaml` | 修改 | `meta.version` 字段变更，YAML 元数据更新 |
| `src/yuleosh/ci/rulesets/misra-rules.yaml` | 修改 | 同上，同步更新 |
| `tests/test_compliance.py` | 修改 | 版本断言需要同步更新 |
| `tests/ci/test_rulesets.py` | 修改 | mock 数据中的 ruleset_version 需要同步 |

## 3. 接口变更评估

| 接口类型 | 是否变更 | 明细 |
|----------|---------|------|
| CLI 命令签名 | 否 | CLI 未暴露 ruleset_version |
| Python API 签名 | 否 | `ruleset_version` 仅供内部读取 |
| YAML 配置格式 | 否 | 字段名不变，仅值变化 |
| JSON 数据格式 | 否 | 证据包中的 `ruleset_version` 字段名不变 |
| 数据库 Schema | 否 | 版本字段类型不变 |
| 外部工具接口 | 否 | cppcheck addon 输出格式不变 |

**向后兼容性**: ✅ 保持 — 仅字符串值变化，字段名和结构不变

## 4. 回归测试影响范围

| 测试文件 | 预计受影响函数 | 说明 |
|----------|---------------|------|
| `tests/test_compliance.py` | `test_load_misra_rules` (断言 `'2023-preview'`) | version 断言值需更新 |
| `tests/test_compliance.py` | `test_ruleset_metadata` | metadata 版本检查 |
| `tests/ci/test_rulesets.py` | `test_ruleset_loading` | mock YAML 数据中的 version |
| `tests/ci/test_rulesets.py` | `test_classify_rule_*` (4 个测试函数) | fixture 需要更新 mock 数据 |

**影响说明**: 4 个 `test_classify_rule_*` 测试函数使用了 fixture 中硬编码的规则集版本号，需要同步更新 fixture 数据。

**建议运行**: `make ci` 全量回归

## 5. 文档影响

| 文档 | 是否需要更新 | 说明 |
|------|-------------|------|
| `docs/software-requirements.md` | 否 | 需求描述不涉及版本号具体值 |
| `docs/architecture.md` | 否 | 架构不依赖版本号 |
| `docs/misra-2023-roadmap.md` | **是** | 文中引用 MISRA 版本号处需同步 |
| `docs/misra-rules-index.md` | 否 | 索引内容不依赖 meta.version |
| `docs/misra-verification-plan.md` | 否 | 验证计划以规则 ID 为准 |

## 6. 证据包影响

| 证据项 | 是否需要重建 | 说明 |
|--------|-------------|------|
| `audit-manifest.json` | **是** | SHA-256 因文件变更而改变 |
| `code/misra-report.json` | **是** | 报告中的 `ruleset_version` 字段需要更新 |
| `requirements/` 下证据 | 否 | 无影响 |
| `code/coverage/` 下证据 | 否 | 覆盖率数据不变 |
| `test/` 下证据 | 否 | 测试结果不变 |

## 7. 安全 / 合规影响

| 检查项 | 影响 | 说明 |
|--------|------|------|
| ISO 26262 合规 | 无 | 无功能安全影响 |
| ASPICE 已通过 BP | 不变 | 不影响任何 BP |
| 安全关键函数变更 | 无 | 仅元数据字符串变更 |
| 用户数据/隐私 | 无 | 不涉及用户数据 |

## 8. 配置影响

| 配置项 | 是否需要更新 | 说明 |
|--------|-------------|------|
| CI 配置 (`.github/workflows/`) | 否 | CI 逻辑不变 |
| YAML 规则配置 | **是** | 主规则文件和 src 下同步文件 |
| `.coveragerc` | 否 | 覆盖率排除规则不变 |
| `tools-version.yaml` | 否 | 工具版本不变 |
| 环境变量/Secret | 否 | 无影响 |

## 9. 依赖影响

| 依赖项 | 变更类型 | 说明 |
|--------|---------|------|
| Python 包 | 无 | 不影响任何包依赖 |
| 外部工具 | 无 | cppcheck 版本不变 |
| 系统库 | 无 | 无影响 |

## 10. 工作量估算

| 活动 | 人天估算 | 执行人 |
|------|---------|--------|
| 影响分析完成 | 0.2 | 小克 |
| YAML 文件修改 | 0.05 | 小克 |
| 测试修复（fixture + 断言） | 0.3 | 小克 |
| 文档更新 | 0.1 | 小克 |
| 证据包重建 | 0.1 | 小克 |
| 验证（回归测试） | 0.1 | 小马 |
| **总计** | **0.85** | |

## 11. 回归风险评级

- [x] **低 (Low)**: 仅字符串值变化，所有受影响测试可显式定位和修复
- [ ] 中 (Medium)
- [ ] 高 (High)
- [ ] 严重 (Critical)

## 12. 批准 / 拒绝决策

| 字段 | 值 |
|------|-----|
| 决策 | ✅ 批准 |
| 批准人 | 小马 |
| 批准日期 | 2026-07-13 |
| 决策理由 | 版本号对齐消除审计风险，影响范围清晰可控，回归风险低 |
| 备注 | 注意同步更新 src 目录下的复制文件，避免两个文件不一致 |
```

#### 实际变更后的验证结果

| 检查项 | 结果 |
|--------|------|
| YAML 文件已更新 | ✅ `misra-rules.yaml` + `src/yuleosh/ci/rulesets/misra-rules.yaml` |
| 测试断言已更新 | ✅ 4 个 test_classify_rule 测试 fixture 已修复 |
| 文档已同步 | ✅ `docs/misra-2023-roadmap.md` 中版本引用已更新 |
| 证据包已重建 | ✅ misra-report.json 中的 `ruleset_version` 同步更新 |
| 全量回归测试通过 | ✅ `make ci` — 1944 tests, 0 failed |

---

### 案例 2: ASPICE SRS 文档创建（新增功能）

#### 背景
根据 Push 9 评审意见，yuleOSH 缺少 SWE.1.BP1（软件需求定义）的正式 SRS 文档。创建 `docs/software-requirements.md` 作为新的合规证据文档。

#### 影响分析清单

```markdown
# 影响分析清单 — ASPICE SWE.1 SRS 文档创建

## 1. 变更基本信息

| 字段 | 值 |
|------|-----|
| 变更标题 | 新增 docs/software-requirements.md（ASPICE SWE.1 合规文档） |
| 变更类型 | 新增 |
| 关联需求 | REQ-001 (需求结构化管理), REQ-004 (需求变更追踪), REQ-028 (ASPICE 合规检查器) |
| 发起人 | 小明（项目经理） |
| 日期 | 2026-07-13 |
| 优先级 | P0 |
| 变更动机 | Push 9 评审指出 SRS 文档缺失导致 SWE.1.BP1 不通过 |

## 2. 受影响的模块 / 文件清单

| 文件路径 | 变更类型 | 说明 |
|----------|---------|------|
| `docs/software-requirements.md` | **新增** | SRS 主文档，42 个 REQ-xxx |
| `docs/requirement-traceability-matrix.md` | **修改** | RTM 引用 SRS 文档编号 |
| `docs/evidence-pack-structure.md` | 不影响 | 证据包结构不依赖 SRS 文档路径 |
| `src/yuleosh/evidence/` | 不影响 | 证据生成逻辑不变 |

## 3. 接口变更评估

| 接口类型 | 是否变更 | 明细 |
|----------|---------|------|
| CLI 命令签名 | 否 | 无 CLI 变更 |
| Python API 签名 | 否 | 无 API 变更 |
| YAML 配置格式 | 否 | 无配置变更 |
| JSON 数据格式 | 否 | 证据包格式不变 |
| 数据库 Schema | 否 | 无 Schema 变更 |
| 外部工具接口 | 否 | 无外部工具接口变更 |

**向后兼容性**: ✅ 保持 — 文档系统是新增的静态内容

## 4. 测试影响范围

| 测试文件 | 预计受影响函数 | 说明 |
|----------|---------------|------|
| `tests/test_compliance.py` | `test_compliance_has_traced_requirements` | **新增测试**：验证每一条 REQ-xxx 都有对应的测试追溯 |
| `tests/test_swe1_documentation.py` | `test_srs_file_exists` | **新增测试**：验证 SRS 文档存在且满足最低行数要求 |
| `tests/test_swe1_documentation.py` | `test_req_count_threshold` | **新增测试**：验证 REQ-xxx 数量 ≥ 30 |
| `tests/test_swe1_documentation.py` | `test_bp_mapping` | **新增测试**：验证 SWE.1 BP 映射完整 |

**影响说明**: 新增 4 个验证测试以自动化 SRS 合规检查

**建议运行**: `make ci` 全量回归

## 5. 文档影响

| 文档 | 是否需要更新 | 说明 |
|------|-------------|------|
| `docs/software-requirements.md` | **新增** | 新文档 |
| `docs/architecture.md` | **修改** | 在引用文档列表中增加 SRS 条目 |
| `docs/spec.md` | **修改** | 在参考文档中增加 SRS 引用 |
| `docs/requirement-traceability-matrix.md` | **修改** | 增加对 REQ-xxx 的完整 RTM 映射 |
| `docs/impact-analysis.md` | **修改** | 本文档需要记录此次变更（即本条） |
| `docs/review-swe1-software-requirements.md` | **新增** | 审查人（小马）出具审查报告 |

## 6. 证据包影响

| 证据项 | 是否需要重建 | 说明 |
|--------|-------------|------|
| `audit-manifest.json` | **是** | 新增文件需要更新 manifest |
| `requirements/spec.md` | **是** | 新增 SRS 文件内容 |
| `requirements/traceability.json` | **是** | 更新追溯矩阵数据 |
| 其他证据 | 否 | 代码、测试、覆盖率证据不变 |

## 7. 安全 / 合规影响

| 检查项 | 影响 | 说明 |
|--------|------|------|
| ISO 26262 合规 | 无直接影响 | 文档本身不改变功能安全证据 |
| ASPICE 已通过 BP | **SWE.1.BP1/B2/B3 从失败→通过** | SRS 文档填补了需求分析阶段的关键缺失 |
| 安全关键函数变更 | 无 | 纯文档变更 |
| 用户数据/隐私 | 无 | 不涉及用户数据 |

## 8. 配置影响

| 配置项 | 是否需要更新 | 说明 |
|--------|-------------|------|
| CI 配置 (`.github/workflows/`) | **是** | 新增合规检查步骤：验证 SRS 完整性 |
| `.coveragerc` | 否 | 覆盖率配置不变 |
| `tests/conftest.py` | **修改** | 需要添加 SRS 文档路径 fixture |

## 9. 依赖影响

| 依赖项 | 变更类型 | 说明 |
|--------|---------|------|
| Python 包 | 无 | 不需要新增依赖 |
| 外部工具 | 无 | 无变化 |

## 10. 工作量估算

| 活动 | 人天估算 | 执行人 |
|------|---------|--------|
| 影响分析完成 | 0.2 | 小克 |
| SRS 文档撰写 | 1.5 | 小克 |
| RTM 更新 | 0.3 | 小克 |
| 合规测试开发（4 个测试） | 0.5 | 小克 |
| CI 配置更新 | 0.1 | 小克 |
| 审查 & 修复 | 0.5 | 小马 + 小克 |
| 证据包重建 | 0.2 | 小克 |
| **总计** | **3.3** | |

## 11. 回归风险评级

- [x] **低 (Low)**: 新增文档不影响任何现有代码逻辑；新增测试是独立的合规检查
- [ ] 中 (Medium)
- [ ] 高 (High)
- [ ] 严重 (Critical)

## 12. 批准 / 拒绝决策

| 字段 | 值 |
|------|-----|
| 决策 | ✅ 批准 |
| 批准人 | 小明 |
| 批准日期 | 2026-07-13 |
| 决策理由 | P0 优先级 — 填补 SWE.1 合规空白，无回归风险，工作量可控 |
| 备注 | 42 个需求标识编号连续（REQ-001 ~ REQ-042），无断裂 |
```

---

### 案例 3: CI 流水线覆盖率门禁配置变更

#### 背景
技术债务 P0-3 指出 `.coveragerc` 中 `omit` 排除了 5K+ 行核心代码（hardware、cross、sil、llm/client 等模块），导致覆盖率报告具有误导性。需要调整覆盖率配置以包含这些模块。

#### 简化影响分析

| 检查项 | 评估结果 |
|--------|---------|
| **变更类型** | 修改 |
| **关联需求** | REQ-032 (测试覆盖率), REQ-036 (可配置性) |
| **受影响文件** | `.coveragerc`, `src/yuleosh/hardware/*`, `src/yuleosh/cross/*`, `src/yuleosh/sil/*`, `src/yuleosh/llm/client.py` |
| **测试影响** | 需为新增纳入覆盖的 5K+ 行代码编写测试，预计新增 200-300 个测试用例 |
| **接口变更** | 无 — 仅覆盖率度量范围变化 |
| **文档影响** | `docs/architecture.md` 中覆盖率章节需更新；`docs/software-requirements.md` REQ-032 验证方式需补充；`docs/tech-debt.md` 需标记 P0-3 已修复 |
| **证据影响** | 证据包中的 `code/coverage/coverage-summary.json` 数据将显著变化 |
| **安全影响** | 无 |
| **回归风险** | **高** — 被排除的 5K+ 行代码从未被测试覆盖，纳入后可能出大量测试失败 |
| **工作量估算** | ~10 人天（含测试编写） |
| **批准** | ✅ 批准 — 分阶段执行，先修复 hardware 模块（Week 1），再修复 cross/sil（Week 2-3），最后 llm/client（Week 4） |
| **备注** | 建议设置临时阈值（line ≥ 50%，branch ≥ 40%）以避免一次 CI 全线飘红 |

---

## 6. 变更记录日志

以下列出 yuleOSH 项目历史上重要的变更及相应的影响分析摘要。

### CR-001: MISRA 规则集版本号调整 (`'2023'` → `'2023-preview'`)

| 字段 | 值 |
|------|-----|
| 变更日期 | 2026-07-13 |
| 变更类型 | 修改 |
| 影响分析参见 | §5 — 案例 1 |
| 受影响文件 | 4 个源码文件 + 2 个测试文件 + 1 个文档 |
| 回归风险 | 低 |
| 工作量 | 0.85 人天 |
| 批准人 | 小马 |
| 状态 | ✅ 已实施并验证 |

### CR-002: ASPICE SWE.1 SRS 文档创建

| 字段 | 值 |
|------|-----|
| 变更日期 | 2026-07-13 |
| 变更类型 | 新增 |
| 影响分析参见 | §5 — 案例 2 |
| 受影响文件 | 新增 1 个文档 + 修改 3 个文档 + 新增 4 个测试 |
| 回归风险 | 低 |
| 工作量 | 3.3 人天 |
| 批准人 | 小明 |
| 状态 | ✅ 已实施并验证 |

### CR-003: 覆盖率配置修正（解除核心模块排除）

| 字段 | 值 |
|------|-----|
| 变更日期 | 2026-06-29 |
| 变更类型 | 修改 |
| 影响分析参见 | §5 — 案例 3 |
| 受影响文件 | `.coveragerc`, `src/yuleosh/hardware/*`, `src/yuleosh/cross/*`, `src/yuleosh/sil/*`, `src/yuleosh/llm/client.py` |
| 回归风险 | 高（分阶段执行） |
| 工作量 | ~10 人天 |
| 批准人 | 小明 |
| 状态 | 🔄 进行中 — Stage 1 (hardware) 已完成 |

### CR-004: 工具版本升级 — cppcheck 2.16 → 2.17.1

| 字段 | 值 |
|------|-----|
| 变更日期 | 2026-06-19 |
| 变更类型 | 升级 |
| 关联流程 | `docs/tool-version-change-process.md` — L2 (次要升级) |
| 受影响文件 | `.yuleosh/config/tools-version.yaml`, `misra-rules.yaml` (新增字段) |
| 受影响模块 | `src/yuleosh/ci/misra_report/` — MISRA 报告工具链 |
| 测试影响 | MISRA 基准测试结果需重新收集；`benchmark/results/` 下的所有 raw 结果需回归 |
| 回归测试 | 运行全量 MISRA 基准测试（`benchmark/scripts/run-misra-benchmark.sh`），对比 FP/FN 变化 |
| 文档影响 | `docs/tool-version-change-process.md` 示例更新 |
| 证据影响 | 证据包中 misra-report.json 工具版本字段更新 |
| 接口变更 | 无 — cppcheck CLI 命令兼容 |
| 安全影响 | 低 — cppcheck 2.17.1 修复了若干 MISRA FP，无安全风险 |
| 回归风险 | 中 — MISRA 检测结果可能变化（FP/FN 分布改变） |
| 工作量 | 1.5 人天 |
| 批准人 | 小马 |
| 状态 | ✅ 已实施（变更记录于 `.yuleosh/config/tools-version.yaml`） |

### CR-005: `src/yuleosh/evidence/manifest.py` 证据包 SHA-256 签名增强

| 字段 | 值 |
|------|-----|
| 变更日期 | 2026-06-19 |
| 变更类型 | 修改 |
| 关联需求 | REQ-012 (证据包生成), REQ-013 (证据完整性) |
| 受影响文件 | `src/yuleosh/evidence/manifest.py`, `src/yuleosh/evidence/pack.py` |
| 测试影响 | `tests/test_evidence_manifest.py`, `tests/test_evidence_pack.py` — 断言 SHA-256 算法和输出格式 |
| 文档影响 | `docs/evidence-pack-structure.md` — 签名算法描述更新 |
| 证据影响 | **重大** — 所有已有的 `audit-manifest.json` 按新算法重新生成 |
| 接口变更 | 无 — `yuleosh evidence pack` CLI 命令签名不变 |
| 回归风险 | 中 — 文件列表/哈希顺序不一致可能导致新旧 manifest 对比失败 |
| 工作量 | 1.0 人天 |
| 批准人 | 小马（架构评审）、小明（终审） |
| 状态 | ✅ 已实施 |

### CR-006: RAG 知识库引擎从基于文件的索引迁移为 SQLite 向量存储

| 字段 | 值 |
|------|-----|
| 变更日期 | 2026-06-25 |
| 变更类型 | 重构 |
| 关联需求 | REQ-021 (RAG 知识库), REQ-022 (规则检索) |
| 受影响文件 | `src/yuleosh/kb/` 下 6 个文件重构，新增 `src/yuleosh/kb/vector_store.py` |
| 测试影响 | `tests/test_kb.py` 重写（mock 数据从文件读取改为 SQLite 内存数据库） |
| 接口变更 | Python API 签名变化：`KBQuery(query, top_k=5)` → `KBQuery(text, top_k=5, use_semantic=True)` |
| 文档影响 | `docs/architecture.md` 知识层描述更新；`docs/software-requirements.md` REQ-021 实现模块更新 |
| 配置影响 | `.yuleosh/ci-config.yaml` 新增 `kb.storage: sqlite` 配置项 |
| 证据影响 | 无 — 知识库是运行时组件，不影响证据包结构 |
| 依赖影响 | 新增 Python 包：`chromadb>=0.5.0`, `sentence-transformers>=2.3.0` |
| 回归风险 | **高** — 核心检索引擎替换，所有 RAG 相关功能需要回归 |
| 工作量 | 5.0 人天 |
| 批准人 | 小马（架构评审 + 影响分析评审） |
| 状态 | ✅ 已实施 |
| 备注 | 保留基于文件的索引作为降级方案（fallback），通过配置开关控制 |

### CR-007: Web Dashboard 多租户认证机制

| 字段 | 值 |
|------|-----|
| 变更日期 | 2026-06-25 |
| 变更类型 | 新增 |
| 关联需求 | REQ-015 (Dashboard), REQ-016 (多租户认证), REQ-042 (安全认证) |
| 受影响文件 | 新增 `src/yuleosh/ui/auth.py`, 新增 `src/yuleosh/ui/middleware.py`，修改 `src/yuleosh/ui/server.py` |
| 测试影响 | 新增 `tests/test_ui_auth.py`, `tests/test_ui_middleware.py`；修改 `tests/test_ui_server_smoke.py` |
| 接口变更 | CLI 新增 `yuleosh ui --auth-mode <none|jwt|oauth2>` 参数；所有 API handler 注入 `request.user` |
| 文档影响 | `docs/software-requirements.md` REQ-016/042 实现模块补充；`docs/quick-start.md` 启动参数更新 |
| 依赖影响 | 新增 Python 包：`bcrypt>=4.1.0`, `pyjwt>=2.8.0` |
| 回归风险 | **高** — 所有 API handler 都经过用户注入重构 |
| 工作量 | 4.0 人天 |
| 批准人 | 小明 |
| 状态 | ✅ 已实施 |

### CR-008: PyPI 依赖降级 — `typing-extensions` 版本回退以修复 CI 兼容性

| 字段 | 值 |
|------|-----|
| 变更日期 | 2026-06-29 |
| 变更类型 | 降级 |
| 受影响文件 | `pyproject.toml` (非锁定依赖), `requirements.txt` (锁定)、`Pipfile.lock` (锁定) |
| 测试影响 | 全量 CI 回归验证 |
| 回归风险 | 中 |
| 工作量 | 0.3 人天 |
| 批准人 | 小克 |
| 状态 | ✅ 已实施 |
| 备注 | 降级为 `typing-extensions>=4.9.0,<4.12.0`；4.12.0 在 Python 3.13 下存在 `get_type_hints` 兼容性问题 |

### CR-009: MISRA 2023 升级规划 — 规则索引文档新增

| 字段 | 值 |
|------|-----|
| 变更日期 | 2026-07-05 |
| 变更类型 | 新增 |
| 关联需求 | REQ-006 (MISRA 静态分析), REQ-031 (合规检查器) |
| 受影响文件 | 新增 `docs/misra-2023-roadmap.md`；修改 `docs/misra-rules-index.md` (扩充为 30 条规则) |
| 测试影响 | 无 — 文档变更不涉及源代码 |
| 文档影响 | 架构文档 `docs/architecture.md` 中 MISRA 支持版本描述更新 |
| 回归风险 | 无 |
| 工作量 | 2.0 人天 |
| 批准人 | 小明 |
| 状态 | ✅ 已发布 — 状态 DRAFT，待 MISRA 迁移 Sprint 启动 |

### CR-010: 架构文档重构 — 从无文档到 ASPICE SWE.2 合规

| 字段 | 值 |
|------|-----|
| 变更日期 | 2026-07-13 |
| 变更类型 | 新增 |
| 关联需求 | REQ-002 (架构设计) |
| 受影响文件 | 新增 `docs/architecture.md` (660 行) |
| 测试影响 | 新增 `tests/test_swe2_documentation.py` (验证架构文档存在且完整) |
| 接口变更 | 无 |
| 回归风险 | 低 |
| 工作量 | 3.0 人天 |
| 批准人 | 小明 |
| 状态 | ✅ 已实施 |

### CR-011: Push 9/10 技术债务修复 — `pipeline/stages.py` 模块重构

| 字段 | 值 |
|------|-----|
| 变更日期 | 2026-07-13 |
| 变更类型 | 重构 |
| 关联需求 | REQ-004 (流水线编排), 关联 P0-4 |
| 受影响文件 | `src/yuleosh/pipeline/stages.py` (拆分) |
| 测试影响 | 全部 pipeline 测试回归 |
| 接口变更 | `_call_llm`, `_parse_spec` 等函数迁移为 `pipeline/llm.py` 中的公共函数 |
| 回归风险 | 高 — 20+ 模块依赖于 `stages.py` 中的私有函数 |
| 工作量 | 3.0 人天 |
| 批准人 | 小马（架构评审） |
| 状态 | 🔄 待实施 |

### 案例 4: 知识图谱变更对 Dashboard SWE Status 的影响

#### 背景

知识图谱（KG）模块新增 `dashboard_writer.py` 中的 `_swe_status_from_kg()` 方法，使 Dashboard 能够从 KG 追溯数据中获取 ASPICE SWE 阶段状态，替代原有的文件探针方式。此变更影响 CI 流水线末端 Dashboard 数据显示逻辑。

#### 变更描述

- **新增方法**: `dashboard_writer._swe_status_from_kg()` — 通过 KG 查询 `get_aspice_coverage()` 和 `get_confirmation_trace()` 获取 SWE.4/SWE.5/SWE.8/SWE.10 状态
- **修改逻辑**: `write_swe_status()` 调用链中优先使用 KG 数据，KG 不可用时降级到文件探针
- **三级降级策略**: KG DB 不存在 → `{}` | 模块不可导入 → `_check_kg_available()` return False → `{}` | 查询异常 → try/except → `{}`

#### 影响分析清单

```markdown
# 影响分析清单 — KG → Dashboard SWE Status 接入

## 1. 变更基本信息

| 字段 | 值 |
|------|-----|
| 变更标题 | KG → Dashboard SWE Status 接入 |
| 变更类型 | 新增（增强） |
| 关联需求 | REQ-010 (SWE 状态追溯), REQ-015 (Dashboard) |
| 发起人 | 小克 |
| 日期 | 2026-07-15 |
| 优先级 | P1 |
| 变更动机 | Dashboard 从文件探针升级为 KG 语义数据驱动，提升 ASPICE SWE 状态判定的准确性 |

## 2. 受影响的模块 / 文件清单

| 文件路径 | 变更类型 | 说明 |
|----------|---------|------|
| `src/yuleosh/ci/dashboard_writer.py` | **修改** | 新增 `_swe_status_from_kg()` + 修改 `write_swe_status()` |
| `src/yuleosh/knowledge_graph/queries.py` | 影响（只读） | 依赖 `get_aspice_coverage()` 和 `get_confirmation_trace()` |
| `src/yuleosh/knowledge_graph/__init__.py` | 影响（只读） | 依赖 `get_store()`, `get_confirmation_trace()`, `list_snapshots()`, `get_graph_stats()` |
| `tests/ci/test_dashboard_kg_integration.py` | **新增** | 16 个测试覆盖 SWE phase 判定 + 降级场景 |

## 3. 接口变更评估

| 接口类型 | 是否变更 | 明细 |
|----------|---------|------|
| CLI 命令签名 | 否 | `yuleosh ui`, `yuleosh ci run` 命令签名不变 |
| Python API 签名 | **是** | `write_swe_status()` 内部调用链新增 `_swe_status_from_kg()` |
| Dashboard JSON 格式 | **是** | `swe-status.jsonl` 中的 status 值从文件探针推导变为 KG 语义推导 |
| 数据库 Schema | 否 | Dashboard 存储格式不变（JSONL 行） |
| CI 层输出格式 | 否 | `.osh/ci/layer*.json` 输出格式不变 |

**向后兼容性**: ✅ 保持 — KG 不可用时自动降级到原有文件探针行为，输出格式不变

## 4. 回归测试影响范围

| 测试文件 | 预计受影响函数 | 说明 |
|----------|---------------|------|
| `tests/ci/test_dashboard_kg_integration.py` | 全部 16 个测试（新增） | SWE phase 判定 + 降级 + 幂等写入 |
| `tests/ci/test_report_pipeline.py` | 涉及 `run_dashboard_update()` 的测试 | 端到端验证 Dashboard 更新流程 |

**建议运行**: `make ci` 全量回归（确保降级不影响已有 Dashboard 功能）

## 5. 文档影响

| 文档 | 是否需要更新 | 说明 |
|------|-------------|------|
| `docs/architecture.md` | **是** | 架构层描述中新增 Dashboard → KG 数据流 |
| `docs/impact-analysis.md`（本文档） | **是** | 记录本次变更的影响分析 |
| `docs/integration-strategy.md` | **是** | 新增 Dashboard 在 CI 流水线末端的位置说明 |

## 6. 证据包影响

| 证据项 | 是否需要重建 | 说明 |
|--------|-------------|------|
| `audit-manifest.json` | **是** | 新增测试文件和修改的源码文件 |
| `code/coverage/` | **是** | 新增 16 个测试的覆盖率 |
| `test/test-results.json` | **是** | 新增测试结果 |

## 7. 安全 / 合规影响

| 检查项 | 影响 | 说明 |
|--------|------|------|
| ISO 26262 合规 | 无 | Dashboard 显示层变更，不影响关键安全逻辑 |
| ASPICE 已通过 BP | 不变 | SWE.4/SWE.5/SWE.8/SWE.10 的判定准确度提升 |
| 安全关键函数变更 | 无 | 不涉及安全关键代码 |
| 用户数据/隐私 | 无 | Dashboard 不存储用户 PII |

## 8. 配置影响

| 配置项 | 是否需要更新 | 说明 |
|--------|-------------|------|
| CI 配置 (`.github/workflows/`) | 否 | CI 调度不变 |
| YAML 规则配置 | 否 | 无规则变更 |
| 环境变量/Secret | 否 | KG DB 路径自动发现 |

## 9. 依赖影响

| 依赖项 | 变更类型 | 说明 |
|--------|---------|------|
| Python 包 | 无 | 不新增外部依赖 |
| 外部工具 | 无 | 不依赖外部工具 |

## 10. 工作量估算

| 活动 | 人天估算 | 执行人 |
|------|---------|--------|
| 影响分析完成 | 0.2 | 小克 |
| `_swe_status_from_kg()` 实现 | 0.8 | 小克 |
| `write_swe_status()` 改造 | 0.3 | 小克 |
| 16 个测试编写 | 1.0 | 小克 |
| 文档更新 | 0.3 | 小克 |
| 全量回归 & 验证 | 0.4 | 小马 |
| **总计** | **3.0** | |

## 11. 回归风险评级

- [x] **中 (Medium)**: Dashboard 输出格式不变但数据来源切换；KG 不可用的降级路径已测试覆盖
- [ ] 低 (Low)
- [ ] 高 (High)
- [ ] 严重 (Critical)

## 12. 批准 / 拒绝决策

| 字段 | 值 |
|------|-----|
| 决策 | ✅ 批准 |
| 批准人 | 小马 |
| 批准日期 | 2026-07-15 |
| 决策理由 | SWE 状态判定从文件探针升级为 KG 语义数据；三级降级策略确保向后兼容；16 测试全通过；回归风险可控 |
| 备注 | 需同步更新 `docs/architecture.md` 中的数据流图和 `docs/integration-strategy.md` 中的 Dashboard 部分 |
```

#### 实际变更验证结果

| 检查项 | 结果 |
|--------|------|
| 代码实现 | ✅ `dashboard_writer.py` — `_swe_status_from_kg()` + 三级降级 |
| 16 个测试全通过 | ✅ 覆盖全部 SWE phase + 边界 + 降级场景 |
| 向后兼容 | ✅ CLI/输出格式/构造函数全向后兼容 |
| CI L3 回归 | ✅ `run_dashboard_update()` 端到端验证通过 |
| 证据包可重建 | ✅ 新增 test_dashboard_kg_integration.py 在覆盖率中体现 |

---

## 7. 变更影响分析检查清单（速查表）

以下为快速参考表，供每次变更时逐项检查。

| # | 检查项 | 说明 | 评估方式 |
|---|--------|------|---------|
| ⚡ | **源文件变更** | 列出所有新增、修改、删除的源文件 | `git diff --name-only` |
| 🔌 | **接口变更** | CLI 参数、Python API 签名、YAML 格式、JSON 格式、DB Schema | 比较前后数据格式 |
| 🧪 | **测试影响** | 需要新增/修改/删除的测试文件及测试函数 | `pytest --collect-only` 对比 |
| 📝 | **文档影响** | SRS、架构文档、Spec、RTM、快速开始、FAQ | 逐文档检查引用变更点 |
| ⚙️ | **配置影响** | CI workflow、YAML 配置、coveragerc、工具版本 | `git diff` 配置文件 |
| 🧩 | **证据影响** | audit-manifest、misra-report、coverage、test-results | 证据包结构检查 |
| 🔒 | **安全影响** | ISO 26262、已通过 ASPICE BP、用户数据、隐私 | 功能安全清单检查 |
| 📦 | **依赖影响** | Python 包新增/升级/降级、外部工具版本 | `pip freeze`, `tools-version.yaml` |
| 📏 | **Code Style / Linting** | 是否引入新 warning、MISRA 违规、格式化问题 | `make lint`, `make check-misra` |
| 🔄 | **追溯矩阵影响** | RTM 中需求↔测试↔模块映射是否需更新 | `yuleosh spec validate --rtm` |
| ⏱️ | **性能影响** | 是否改变算法复杂度、内存占用、Token 消耗 | 性能基线对比 |
| 📊 | **CI pipeline 影响** | 流水线步骤是否增删、步骤顺序是否变化 | Pipeline 配置 diff |
| 🚢 | **部署影响** | Docker 镜像、K8s 部署配置、桌面应用打包 | 部署脚本检查 |
| 🗃️ | **数据迁移影响** | 是否需要数据迁移脚本、Schema 升级 | 数据兼容性检查 |
| 🌐 | **本地化影响** | Dashboard UI 文本、错误消息、文档语言 | 国际化字符串检查 |

---

## 8. 附录 A — 影响分析模板速查模板（PR 模板）

以下 Markdown 模板可直接嵌入 GitHub PR 描述中使用：

```markdown
## 变更影响分析

### 变更类型
- [ ] 新增功能
- [ ] 修改/增强
- [ ] 缺陷修复
- [ ] 重构
- [ ] 工具升级/降级
- [ ] 文档

### 影响范围
- 修改文件数: ___
- 新增文件数: ___
- 受影响模块: ___

### 接口兼容性
- [ ] CLI 向后兼容
- [ ] API 向后兼容
- [ ] 配置格式兼容
- [ ] 存在破坏性变更（请说明: ___）

### 回归测试
- [ ] `make ci` 全量测试
- [ ] 仅受影响模块测试
- [ ] 额外集成测试（请说明: ___）

### 文档更新
- [ ] `docs/software-requirements.md` — 更新 REQ-xxx: ___
- [ ] `docs/architecture.md`
- [ ] `docs/requirement-traceability-matrix.md`
- [ ] 其他: ___

### 证据包
- [ ] 需要重建证据包
- [ ] 不需要重建

### 回归风险
- [ ] 低 — 影响隔离，测试覆盖充分
- [ ] 中 — 跨模块但可测试覆盖
- [ ] 高 — 影响多个子系统/核心API

### 工作量
- 估算: ___ 人天

### 审批
- [ ] 需要架构师批准（小马）
- [ ] 需要项目经理批准（小明）

---

<!-- 审批栏由审批人填写 -->
**决策**: ✅ 批准 / ❌ 拒绝
**批准人**: ___ | **日期**: ___
```

---

## 9. 附录 B — 变更影响分析的常见场景与应对策略

| 场景 | 典型触发 | 应对策略 |
|------|---------|---------|
| **需求新增** | 客户新要求 / ASPICE 空白发现 | 新增 REQ-xxx → RTM 更新 → 代码实现 → 测试新增 → 文档更新 → 证据包重建 |
| **需求修改** | 规格评审改进建议 | 分析现有依赖 → 评估回溯影响 → 决定是否创建新版本需求 |
| **缺陷修复** | 测试发现 / 代码审查 / 客户反馈 | 创建测试复现 → 修复 → 回归 → 更新 RTM 测试引用 |
| **架构重构** | 技术债务识别 / 性能优化 | 架构评审 → 影响分析 → 分阶段实施 → 回归 → 证据一致性验证 |
| **工具升级** | 新版本发布 / 安全补丁 | 运行基准对比 → test results 对比 → 决定兼容性 |
| **第三方依赖变更** | 依赖漏洞 / 许可证变更 | 替换分析 → 新依赖的功能等效性验证 → 全量回归 |
| **文档合规补全** | 审计发现 | 补充文档 → 添加自动化验证测试 → 更新证据包 |

---

*文档结束 — yuleOSH 影响分析合规证据，ASPICE SWE.1.BP3 满足。*
