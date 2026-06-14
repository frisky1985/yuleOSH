# yuleOSH 质量提升 Sprint 计划 (v1.0.1)

> **版本**: v1.0.1 | **状态**: APPROVED  
> **维护人**: 小马 🐴 (质量架构师)  
> **参考文档**: docs/aspice-readiness-assessment.md, docs/rtm-spec.md  
> **最后更新**: 2026-06-14  
> **规范文体**: RFC 2119 (SHALL / SHOULD / MAY)

---

## 1. 概述

### 1.1 目的

本文档定义 yuleOSH v1.0.1 质量提升 Sprint 的详细执行计划。本计划基于三方评估 89/100 的差距分析，以及 ASPICE readiness assessment 识别的差距项，将改进任务分为三个 Sprint 迭代。

### 1.2 范围

本文档涵盖以下 ASPICE 过程域的质量提升任务：

- **SWE.4** — 软件单元验证（分支覆盖攻坚）
- **SWE.5** — 软件集成与集成测试（CI pipeline 增强）
- **SWE.6** — 软件确认与发布（E2E + 证据包）
- **SUP.9** — 变更管理（RTM 门禁集成）
- **SUP.10** — 配置管理（CI/CD 平台化）

### 1.3 术语定义

| 术语 | 定义 |
|:----|:-----|
| **SHALL** | 强制性要求 — 未完成将阻塞 Sprint 验收 |
| **SHOULD** | 推荐性要求 — 优先完成，可延迟但需记录理由 |
| **MAY** | 可选要求 — 在资源允许时完成 |
| **RTM** | Requirements Traceability Matrix — 需求追溯矩阵 |
| **ASPICE** | Automotive SPICE — 汽车软件过程改进和能力评估模型 |
| **AL** | Assessment Level — ASPICE 评估等级 |

### 1.4 总体目标

| 指标 | Sprint 1 目标 | Sprint 2 目标 | Sprint 3 目标 |
|:----|:------------:|:------------:|:------------:|
| 行覆盖率 | ≥80% | ≥85% | ≥90% |
| 分支覆盖率 | ≥70% | ≥75% | ≥80% |
| RTM SHALL 覆盖率 | ≥85% | ≥90% | ≥95% |
| ASPICE SWE.4 | AL1 全部 + AL2 ≥50% | AL2 ≥70% | AL2 ≥80% |
| 无 FAIL 测试 | 100% PASS | 100% PASS | 100% PASS |

---

## 2. Sprint 1 — 分支覆盖攻坚（高优先级）

> **Sprint 周期**: 2026-Q3 Weeks 1-4  
> **Sprint 目标**: 分支覆盖提升 + RTM 门禁 CI 集成

### 2.1 任务详细说明

#### T-01: store_pg.py 分支覆盖提升

| 属性 | 内容 |
|:----|:------|
| **需求 ID** | SPRINT1-T01 |
| **类型** | SHALL |
| **描述** | store_pg.py 分支覆盖从 53% 提升至 ≥85% |
| **负责人** | 小克 🐰 (后端) |
| **依赖** | psycopg2 mock（需要 mock 数据库连接） |
| **ASPICE 关联** | SWE.4 (BP3 — 分支覆盖) |
| **验收条件** | 分支覆盖率 ≥85%，行覆盖率 ≥95%，分支测试覆盖所有 if-else/异常路径 |

**具体行动计划：**

1. 创建 `tests/test_store_pg_coverage.py` 测试文件
2. mock psycopg2 连接：mock `store_pg.DatabaseManager.__init__()` 避免真实数据库依赖
3. 覆盖以下分支路径：
   - ✅ 正常连接和查询路径
   - ✅ 连接失败异常路径
   - ✅ 查询结果为空路径
   - ✅ 数据插入成功/失败路径
   - ✅ 事务回滚路径
   - ✅ 连接池耗尽异常路径
   - ✅ 所有 else/elif 分支
4. 运行 `pytest --cov=src/yuleosh/store_pg.py --cov-branch` 验证

#### T-02: ci/run.py 分支与行覆盖提升

| 属性 | 内容 |
|:----|:------|
| **需求 ID** | SPRINT1-T02 |
| **类型** | SHALL |
| **描述** | ci/run.py 分支覆盖 16%→≥85%，行覆盖 83%→≥95% |
| **负责人** | 小克 🐰 (后端) |
| **依赖** | mock subprocess 调用 |
| **ASPICE 关联** | SWE.4 (BP3), SWE.5 (BP5) |
| **验收条件** | 分支覆盖 ≥85%，行覆盖 ≥95% |

**具体行动计划：**

1. 使用 `unittest.mock.patch` 或 `pytest-subprocess` mock 所有 subprocess 调用
2. mock 以下系统命令：
   - `python -m pytest` (测试执行)
   - `coverage` (覆盖率采集)
   - `cross/*.sh` (交叉编译脚本)
3. 覆盖分支路径：
   - ✅ 各 CI 层 (L0→L1→L2→L2.5→L3) 的配置加载和执行分支
   - ✅ 配置缺失的 fallback 路径
   - ✅ 各层 PASS/FAIL 状态分支
   - ✅ 超时处理分支
   - ✅ 错误处理和日志记录分支
4. 确保每个 if-else 和 try-except 都有正反路径覆盖

#### T-03: evidence/pack.py 分支覆盖提升

| 属性 | 内容 |
|:----|:------|
| **需求 ID** | SPRINT1-T03 |
| **类型** | SHALL |
| **描述** | evidence/pack.py 分支覆盖提升至 ≥80% |
| **负责人** | 小克 🐰 (后端) |
| **依赖** | mock IO/zip 操作 |
| **ASPICE 关联** | SWE.4 (BP3), SWE.6 (BP5) |
| **验收条件** | 分支覆盖 ≥80%，证据打包所有路径覆盖 |

**具体行动计划：**

1. mock `zipfile.ZipFile` 和 `os.walk`
2. 覆盖分支路径：
   - ✅ 空 evidence 目录打包路径
   - ✅ 多级目录递归打包路径
   - ✅ 文件 IO 失败异常路径
   - ✅ 超过大小限制的文件跳过路径
   - ✅ 元数据文件生成路径
3. 对证据包的目录结构和文件完整性进行断言验证

#### T-04: RTM 门禁 CI 集成

| 属性 | 内容 |
|:----|:------|
| **需求 ID** | SPRINT1-T04 |
| **类型** | SHALL |
| **描述** | 验收矩阵 RTM 门禁脚本集成到 CI pipeline |
| **负责人** | 小马 🐴 (质量架构师) |
| **依赖** | ci-rtm-check.sh 脚本就绪 |
| **ASPICE 关联** | SWE.4 (BP5-BP7), SUP.9 (BP3) |
| **验收条件** | CI 的 evidence job 中增加 RTM 检查步骤，执行 `bash docs/ci-rtm-check.sh` |

**具体行动计划：**

1. 编写 `docs/ci-rtm-check.sh` 脚本 — ✅ 已完成
2. 在 `.github/workflows/ci.yml` 的 evidence job 中添加 RTM 检查步骤 — ✅ 已完成
3. RTM 检查步骤 SHALL:
   - 验证 SHALL 语句覆盖率 ≥80%
   - 输出未覆盖 SHALL 清单
   - 门禁失败时阻塞 PR 合并
4. RTM 检查 SHOULD:
   - 检查 SHOULD 覆盖率 ≥50%（仅警告，不阻塞）
   - 检查 Rogue 测试（未关联需求的测试）
5. 验收矩阵 (`docs/acceptance-matrix-rtm.md`) SHALL 保持与 RTM 检查结果一致

#### T-05: ASPICE 过程文档完善

| 属性 | 内容 |
|:----|:------|
| **需求 ID** | SPRINT1-T05 |
| **类型** | SHALL |
| **描述** | ASPICE 过程文档补充 SWE.1/2/3 执行计划 |
| **负责人** | 小马 🐴 (质量架构师) |
| **ASPICE 关联** | SWE.1, SWE.2, SWE.3 |
| **验收条件** | SWE.1/2/3 在 aspice-readiness-assessment.md 中有完整的差距分析和执行计划 |

**具体行动计划：**

1. 补充 SWE.1 差距分析和执行计划 — ✅ 已完成
2. 补充 SWE.2 差距分析和执行计划 — ✅ 已完成
3. 补充 SWE.3 差距分析和执行计划 — ✅ 已完成
4. 更新文档版本为 v1.1.0

#### T-06: Sprint 计划正式化

| 属性 | 内容 |
|:----|:------|
| **需求 ID** | SPRINT1-T06 |
| **类型** | SHOULD |
| **描述** | 将 root 级 sprint 计划迁移至 `docs/sprint-v1.0.1-plan.md`，使用规范文体 |
| **负责人** | 小马 🐴 (质量架构师) |
| **验收条件** | `docs/sprint-v1.0.1-plan.md` 使用 SHALL/SHOULD/MAY 规范语言 |

### 2.2 Sprint 1 验收门禁

| 门禁指标 | 阈值 | 检验方法 | 类型 |
|:---------|:----:|:---------|:----:|
| store_pg.py 分支覆盖 | ≥85% | `pytest --cov-branch` | SHALL |
| ci/run.py 分支覆盖 | ≥85% | `pytest --cov-branch` | SHALL |
| ci/run.py 行覆盖 | ≥95% | `pytest --cov` | SHALL |
| evidence/pack.py 分支覆盖 | ≥80% | `pytest --cov-branch` | SHALL |
| 全局行覆盖 | ≥80% | `pytest --cov` | SHALL |
| RTM CI 门禁 | 通过 | `bash docs/ci-rtm-check.sh` | SHALL |
| ASPICE 文档完整性 | SWE.1-6 均有执行计划 | 人工审阅 | SHALL |
| 全部测试通过 | 100% PASS | `pytest` | SHALL |

### 2.3 Sprint 1 风险与缓解

| 风险 | 可能性 | 影响 | 缓解 |
|:-----|:------:|:----:|:-----|
| psycopg2 mock 复杂度过高 | 🟡 中 | 高 | 先 mock DatabaseManager 顶层接口 |
| subprocess mock 不稳定 | 🟡 中 | 中 | 使用 `pytest-subprocess` 库 |
| RTM 检查在缺少 rtm 模块时退化 | 🟢 低 | 低 | ci-rtm-check.sh 已有 fallback 逻辑 |

---

## 3. Sprint 2 — E2E + 架构优化（中优先级）

> **Sprint 周期**: 2026-Q3 Weeks 5-8  
> **Sprint 目标**: E2E 全流程集成测试 + 模块架构拆分

### 3.1 任务详细说明

#### T-07: E2E 全流程集成测试

| 属性 | 内容 |
|:----|:------|
| **需求 ID** | SPRINT2-T07 |
| **类型** | SHALL |
| **描述** | 实现全 mock 的 E2E 集成测试 pipeline→CI→evidence |
| **负责人** | 小克 🐰 (后端) |
| **ASPICE 关联** | SWE.5 (BP3-BP5), SWE.6 (BP1) |
| **验收条件** | E2E 测试覆盖 pipeline run→CI verify→evidence pack 全链路 |

**验收标准：**

- ✅ pipeline flow: `spec → AI review → CI trigger`
- ✅ CI flow: `L0 → L1 → L2 → L2.5 → L3`
- ✅ evidence flow: `collect → pack → upload`
- ✅ 所有外部调用（API, subprocess）使用 mock
- ✅ 测试时间 ≤ 30s

#### T-08: pipeline/run.py 模块拆分

| 属性 | 内容 |
|:----|:------|
| **需求 ID** | SPRINT2-T08 |
| **类型** | SHOULD |
| **描述** | pipeline/run.py 从 938 行拆分至 <500 行 |
| **负责人** | 小克 🐰 (后端) |
| **ASPICE 关联** | SWE.2 (BP1 — 架构设计) |
| **验收条件** | pipeline/run.py ≤ 500 行，功能模块化 |

**拆分建议：**

```
pipeline/
├── run.py        ← 主入口 (≤100 行)
├── stages.py     ← 各 pipeline stage 定义
├── orchestrator.py ← 流程编排
└── config.py     ← 配置加载
```

#### T-09: ci/run.py 模块拆分

| 属性 | 内容 |
|:----|:------|
| **需求 ID** | SPRINT2-T09 |
| **类型** | SHOULD |
| **描述** | ci/run.py 从 895 行拆分至 <500 行 |
| **负责人** | 小克 🐰 (后端) |
| **ASPICE 关联** | SWE.2 (BP1) |
| **验收条件** | ci/run.py ≤ 500 行，功能模块化 |

**拆分建议：**

```
ci/
├── run.py        ← 主入口 (≤100 行)
├── layer1.py     ← L0/L1 单元测试层
├── layer2.py     ← L2/L2.5 集成测试层
├── layer3.py     ← L3 系统测试层
└── gates.py      ← 门禁检查
```

#### T-10: STP/SPDP 过程文档

| 属性 | 内容 |
|:----|:------|
| **需求 ID** | SPRINT2-T10 |
| **类型** | SHALL |
| **描述** | 编写 STP (Software Test Plan) 和 SPDP (Software Product Development Plan) 文档 |
| **负责人** | 小马 🐴 (质量架构师) |
| **ASPICE 关联** | SWE.4 (BP1), SWE.5 (BP1-BP2) |
| **验收条件** | STP 和 SPDP 文档就位，纳入 docs/ |

### 3.2 Sprint 2 验收门禁

| 门禁指标 | 阈值 |
|:---------|:----:|
| E2E 集成测试通过 | 100% |
| ci/run.py 行数 | <500 |
| pipeline/run.py 行数 | <500 |
| STP 文档 | 已审阅 |
| SPDP 文档 | 已审阅 |

---

## 4. Sprint 3 — 长期提升（低优先级）

> **Sprint 周期**: 2026-Q4  
> **Sprint 目标**: CI pipeline 平台化 + 自动化门禁

### 4.1 任务详细说明

#### T-11: GitHub Actions 集成测试

| 属性 | 内容 |
|:----|:------|
| **需求 ID** | SPRINT3-T11 |
| **类型** | SHOULD |
| **描述** | 验证 GitHub Actions CI pipeline 完整运行 |
| **验收条件** | CI workflow 从触发到完成无人工干预 |

#### T-12: RTM 门禁 GitHub Action

| 属性 | 内容 |
|:----|:------|
| **需求 ID** | SPRINT3-T12 |
| **类型** | MAY |
| **描述** | 将 RTM 门禁封装为可复用的 GitHub Action |
| **验收条件** | GitHub Action Marketplace 可检索 |

#### T-13: 贡献者测试指南完善

| 属性 | 内容 |
|:----|:------|
| **需求 ID** | SPRINT3-T13 |
| **类型** | SHOULD |
| **描述** | 完善 `docs/contributor-testing-guide.md` |
| **验收条件** | 指南覆盖测试编写、RTM 映射、CI 流程 |

---

## 5. 依赖与前置条件

### 5.1 Sprint 1 依赖

| 依赖项 | 类型 | 截止 | 关键路径 |
|:-------|:-----|:----|:--------:|
| psycopg2 mock 方案确认 | 技术决策 | Sprint 1 W1 | ✅ 是 |
| subprocess mock 库安装 | 工具安装 | Sprint 1 W1 | ✅ 是 |
| rtm-spec.md 审批通过 | 文档 | Sprint 1 W0 | ⛔ 否 |

### 5.2 Sprint 2 依赖

| 依赖项 | 类型 | 截止 | 关键路径 |
|:-------|:-----|:----|:--------:|
| Sprint 1 全部 PASS | 质量门禁 | Sprint 2 W0 | ✅ 是 |
| 模块拆分方案评审 | 架构评审 | Sprint 2 W2 | ✅ 是 |

### 5.3 Sprint 3 依赖

| 依赖项 | 类型 | 截止 | 关键路径 |
|:-------|:-----|:----|:--------:|
| Sprint 2 全部 PASS | 质量门禁 | Sprint 3 W0 | ✅ 是 |

---

## 6. 验收矩阵

### 6.1 Sprint 1 验收矩阵

| 需求 ID | SHALL/SHOULD/MAY | 验收条件 | 负责人 | 状态 |
|:--------|:--------------:|:---------|:------|:----:|
| SPRINT1-T01 | SHALL | store_pg.py 分支覆盖 ≥85% | 小克 🐰 | 🟡 进行中 |
| SPRINT1-T02 | SHALL | ci/run.py 分支覆盖 ≥85%, 行覆盖 ≥95% | 小克 🐰 | 🟡 进行中 |
| SPRINT1-T03 | SHALL | evidence/pack.py 分支覆盖 ≥80% | 小克 🐰 | 🟡 进行中 |
| SPRINT1-T04 | SHALL | CI evidence job 增加 RTM 检查步骤 | 小马 🐴 | 🟢 已完成 |
| SPRINT1-T05 | SHALL | ASPICE SWE.1/2/3 执行计划补充 | 小马 🐴 | 🟢 已完成 |
| SPRINT1-T06 | SHOULD | docs/sprint-v1.0.1-plan.md 规范文体 | 小马 🐴 | 🟢 已完成 |

### 6.2 Sprint 2 验收矩阵

| 需求 ID | SHALL/SHOULD/MAY | 验收条件 | 负责人 | 状态 |
|:--------|:--------------:|:---------|:------|:----:|
| SPRINT2-T07 | SHALL | E2E 全流程集成测试 | 小克 🐰 | ⚪ 未开始 |
| SPRINT2-T08 | SHOULD | pipeline/run.py < 500 行 | 小克 🐰 | ⚪ 未开始 |
| SPRINT2-T09 | SHOULD | ci/run.py < 500 行 | 小克 🐰 | ⚪ 未开始 |
| SPRINT2-T10 | SHALL | STP/SPDP 文档 | 小马 🐴 | ⚪ 未开始 |

### 6.3 Sprint 3 验收矩阵

| 需求 ID | SHALL/SHOULD/MAY | 验收条件 | 负责人 | 状态 |
|:--------|:--------------:|:---------|:------|:----:|
| SPRINT3-T11 | SHOULD | GHA CI 完整运行 | 小克 🐰 | ⚪ 未开始 |
| SPRINT3-T12 | MAY | RTM GitHub Action 发布 | 小马 🐴 | ⚪ 未开始 |
| SPRINT3-T13 | SHOULD | 贡献者指南完善 | 小马 🐴 | ⚪ 未开始 |

---

## 7. 版本历史

| 版本 | 日期 | 变更说明 | 审批人 |
|:----|:----|:---------|:------|
| v1.0.0 | 2026-06-14 | 初始版本：基于三方评估 89/100 差距分析 | 小马 🐴 |
| v1.0.1 | 2026-06-14 | Sprint 1 任务细化：补充 T-04/05/06 具体验收条件；改为 RFC 2119 规范文体 | 小马 🐴 |

---

*本文档使用 RFC 2119 规范语言：SHALL（强制）、SHOULD（推荐）、MAY（可选）。所有 SHALL 级要求未完成将阻塞 Sprint 验收。*
