# Push 10 Step 3 审查报告 — ASPICE SWE.1 软件需求文档

> **审查人**: 小马 (Hermes) | **审查日期**: 2026-07-13
> **审查对象**: `docs/software-requirements.md` (660 行, 42 REQ-xxx)
> **文档版本**: 1.0.0 | **状态**: ⚠️ 有条件通过

---

## 一、必须通过清单 (8/8)

### ✅ 1. 📋 行数 ≥ 300
**660 行** — 通过。远超阈值，结构完整。

### ✅ 2. 🆔 REQ-xxx ≥ 30 个
**42 个唯一标识** (REQ-001 ~ REQ-042) — 通过。编号连续，无断裂。

### ✅ 3. 📐 需求格式完整
每个需求包含全部 6 个属性：
- **描述** ✓
- **优先级** ✓ (P0/P1/P2 三级)  
- **来源** ✓ (设计理念 / 标准 / 需求)
- **实现模块** ✓ (精确到具体 .py 文件或目录)
- **验证方式** ✓ (测试 / 审查 / 演示)
- **状态** ✓ (全部 Implemented)

结构一致，格式规范，无残缺条目。

### ✅ 4. 🎯 ASPICE SWE.1 BP 映射
附录 A 逐条对照全部 7 个 SWE.1 BP，映射清晰：

| BP | 映射 | 评价 |
|----|------|------|
| BP1 定义软件需求 | 本文档全部 REQ-xxx | 完整 |
| BP2 结构化需求内容 | REQ-001, REQ-002 | 合理 |
| BP3 评估需求影响 | REQ-004 (Spec-Diff) | 合理 |
| BP4 定义验证准则 | 各 REQ 的"验证方式" | 良好实践 |
| BP5 双向可追溯性 | §5 追溯矩阵 | 完整 |
| BP6 确保一致性 | REQ-028 (合规检查器) | 合理 |
| BP7 沟通已批准的软需 | Git + Dashboard | 可接受 |

**Minor 建议**: BP7 映射为 "Git 分发 + Dashboard 展示"。ASPICE BP7 更强调"to affected parties with their implications"。建议补充在 release note 或审批邮件中注明受影响方的沟通机制。

### ✅ 5. 📊 需求追溯矩阵
§5 提供完整的 7 列追溯表：
`REQ-ID → 需求名称 → 功能域 → 实现模块 → 验证方式 → 测试文件 → 状态`

双向追溯能力清晰：需求↔模块↔验证方式均有覆盖，并附 §5.1 覆盖统计摘要。

### ✅ 6. 🔍 功能域覆盖
文档 §1.2 范围声明覆盖 10 个域，其中必须覆盖的 7 个域全部到位：

| 域 | 对应 REQ | 覆盖 |
|----|----------|------|
| OpenSpec | REQ-001 ~ REQ-004 | ✅ |
| CI | REQ-005 ~ REQ-008 | ✅ |
| AI Review | REQ-009 ~ REQ-011 | ✅ |
| Evidence | REQ-012 ~ REQ-014 | ✅ |
| Dashboard | REQ-015 ~ REQ-018 | ✅ |
| ALM | REQ-019 ~ REQ-020 | ✅ |
| RAG | REQ-021 ~ REQ-022 | ✅ |

额外覆盖 Cross/Benchmark/Engine/Compliance/Desktop/AUTOSAR 等域，超出最低要求。

### ✅ 7. 📝 非功能需求 ≥ 5
**8 条非功能需求** (REQ-035 ~ REQ-042)，覆盖：
- 兼容性: Python ≥ 3.10, 单机部署, 双存储后端
- 性能: Token 预算限流, API 速率限制
- 安全: 密码认证(bcrypt + JWT), API Key 管理
- 可配置: 覆盖率门禁, 多 LLM 提供者

### ⚠️ 8. ✅ 真实状态核实 (有条件通过)

#### 源码文件核实
- 核心模块文件 28/29 个 **存在** ✅
- 唯一缺失 `src/yuleosh/spec/__init__.py` — Python 3.3+ 隐式命名空间包，**非阻塞** ✅
- 功能代码均有实质内容（非占位符）

#### 测试文件引用失准 ⚠️
RTM 和 REQ 块中引用的 **5 个测试文件名与实际文件不符**：

| 文档中引用 | 实际文件 | 严重程度 |
|-----------|---------|---------|
| `tests/test_spec_validate.py` | `tests/test_spec_validate_ext.py` / `test_spec_validate_deep.py` | Minor |
| `tests/test_spec_delta.py` | `tests/test_spec_diff_ext.py` | Minor |
| `tests/test_review_dual.py` | 不存在 (双轨审查逻辑在 `src/yuleosh/review/run.py`) | Minor |
| `tests/test_ui_server.py` | `tests/test_ui_server_smoke.py` / `tests/test_ui_server_deep.py` | Minor |
| `tests/ci/test_kpi.py` | `tests/test_kpi.py` | Minor |

此外，REQ-001/002 的描述中引用的测试函数名 `test_openspec_format`、`test_rfc2119_format` 在实际测试文件中**不存在**。实际使用的是 `test_parse_requirement_basic`、`test_parse_should_may_statements` 等。

REQ-028 (ASPICE 合规检查器) 验证方式仅写 "测试"，未指定具体测试文件名。

**结论**: 真实状态基本可信，但追溯引用需同步更新。**不阻塞**。

---

## 二、质量加分 (2/2)

### ✅ 9. 修订历史
版本 1.0.0 / 日期 2026-07-13 / 作者 小克 — 格式规范。

### ✅ 10. 附录
- **附录 A**: SWE.1 BP 对照表 (覆盖 7/7 BP)
- **附录 B**: 关键术语表

---

## 三、额外发现的改进点

### 3.1 测试自动化覆盖率
RTM 自报测试覆盖率 **62%** (26/42 有测试文件)，16 个需求 (38%) 仅靠 "审查 / 演示" 验证。

| 域 | 测试覆盖 | 备注 |
|----|---------|------|
| OpenSpec | ✅ 有测试 | 文件名需更新 |
| CI | ✅ 有测试 | 良好 |
| AI Review | ⚠️ 部分测试 | REQ-010 仅审查 |
| Evidence | ✅ 有测试 | 良好 |
| Dashboard | ⚠️ 部分测试 | REQ-016/017 仅审查 |
| ALM | ⚠️ 审查/演示 | REQ-019/020 |
| RAG | ⚠️ 审查/演示 | REQ-021/022 |
| Cross | ⚠️ 审查/演示 | REQ-023 仅审查 |
| Benchmark | ⚠️ 审查/演示 | 可接受(P2) |
| Non-func | ⚠️ 部分测试 | REQ-036/041 仅审查 |

对 P0 需求建议自动化测试全覆盖，对未来 ASPICE CL2/CL3 审计更有利。

### 3.2 REQ-034 域归类
REQ-034 (HIL/SIL 适配层) 在第 3 节归类为 "J. 其他核心功能" (Adapter 域)。但在第 6 行 RTM 的"功能域"列标注为 "Adapter"。需要确认此归类是否与 §1.2 范围中明确列出的域一致 — §1.2 有列出 HIL/SIL 吗？§1.2 只写了 "Cross 编译/烧录（JLink / OpenOCD / pyOCD、SIL 仿真）"。SIL 在 Cross 中提及，但 HIL/SIL 适配层单独成类。建议统一到 Cross 域下或在 §1.2 中补充 Adapter 域。

### 3.3 需求变更历史
§6 变更历史部分目前仅一条初始发布记录。建议为 ASPICE 审计友好起见，扩展为支持多版本变更追踪的模板（已具备结构，内容尚待积累）。

---

## 四、验收结论

### ⚠️ **有条件通过 — 列出 minor 建议**

| 编号 | 问题 | 类型 | 处理建议 |
|------|------|------|---------|
| ① | 5 个测试文件引用名与实际不符 | Minor - 追溯一致性 | 更新 RTM 和 REQ 描述中的测试文件名以匹配实际文件 |
| ② | 测试函数名 (`test_openspec_format` 等) 不存在 | Minor - 引用准确性 | 同步更新为实际函数名 |
| ③ | REQ-028 验证方式仅写"测试"未指定文件 | Minor - 可追溯性 | 补充具体测试文件引用 |
| ④ | BP7 映射可加强 | Minor - 充分性 | 补充"告知受影响方及影响的沟通机制"说明 |

### 不阻塞的理由
- 代码已实现，功能验证可执行
- 追溯矩阵结构完整，仅具体文件名需要同步
- 附录和 BP 映射完整
- 文档达到了 ASPICE SWE.1 合规的基本要求

### 建议修复后升级状态
小克更新测试文件引用后，本报告结论可升级为 **✅ 通过**。

---

*审查完毕。文档格式规范、内容充实、BP 映射完整。文件名引用的失准是唯一可修复的质量瑕疵。*
