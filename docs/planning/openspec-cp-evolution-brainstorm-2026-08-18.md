# 头脑风暴：OpenSpec CP 演进 + TDD 顺序 + 前期追问 — yuleOSH pipeline 吸收三方优势补齐

> **日期**: 2026-08-18
> **状态**: 头脑风暴完成，待推进（P0 先落）
> **关联**: `docs/planning/openspec-spec-management-2026-08-18.md`（8/18 已集成静态结构）
> **调研**: OpenSpec 官方 OPSX 工作流（Fission-AI/OpenSpec main 分支 2026-08 实测）

## 1. 背景：三方优势吸收的差距盘点

8/18 已集成：OpenSpec 静态规范结构（目录聚合校验 / 契约抽取 / spec-files 索引 /
骨架生成 / RULES §12）+ harness coding 全要素（三角色 / sprint-contract /
checkpoint / 验收）+ superpowers 质量门禁类（4 重审查 / 反 sycophancy / 契约机制）。

**三块缺口**（按优先级）：

| 缺口 | 缺什么 | 为什么重要 |
|:--|:--|:--|
| **P0 OpenSpec CP 演进** | changes/ 提案目录 + 评审门禁 + 归档/演进闭环 | 规范只会"一次性写对"不能"随需求演进"——汽车项目需求变更频繁，ASPICE 要求变更可追溯 |
| **P1 TDD 顺序** | pipeline 不是 test-first | codegen 先生成代码再规划测试 → 测试易"适配代码"而非"定义行为"（历史教训：测试锁定 bug 行为） |
| **P2 前期追问** | 无 grill-me 式"设计假设被挑战"步骤 | claude-review 只审已产出物，不追问"需求理解对不对"——前期假设错误成本最高 |

## 2. OpenSpec 官方 OPSX 机制调研（防幻觉，已抓 README + opsx.md）

官方新工作流 = **artifact-guided**（动作不是阶段）：

```
proposal → specs → design → tasks → implement
```

- 目录：`openspec/changes/<change-id>/{proposal.md, specs/, design.md, tasks.md}`
- 动作：`/opsx:propose`（创建变更包）→ `/opsx:apply`（实现 tasks）→
  `/opsx:archive`（归档到 `changes/archive/<date>-<id>/` + 更新 specs）
- 可配置：`openspec/config.yaml`（context + per-artifact rules 注入，50KB 上限）
- 哲学：**fluid not rigid / iterative not waterfall / easy not complex /
  brownfield + greenfield**——正是 yuleOSH 需要的演进形态
- 核心价值点：proposal 含"为什么改"；tasks 是机器可校验清单；archive 是变更证据链

## 3. 方案对比（A/B/C × 三缺口）

### 3.1 P0 — CP 演进机制

| 方案 | 做法 | 优点 | 缺点 |
|:--|:--|:--|:--|
| **A 完整对齐官方** | `.osh/changes/` + propose/apply/archive CLI + config 注入 + 模板系统 | 官方标准、生态兼容、未来可升级 | 重（2-3 天）；config/模板系统对 yuleOSH 是 YAGNI |
| **B 轻量 CP（推荐）** | `.osh/changes/<id>/` 固定结构 + `spec cp` CLI（propose 校验 / review 状态 / archive）+ pipeline `spec-cp-review` 门禁步骤 + RULES §13 | 1 天内可交付；机器可校验；进 pipeline 有门禁；证据链完整 | 不做 config 注入/模板自定义（YAGNI） |
| **C 纯文档化** | 只写 RULES 流程，人/agent 手工执行 | 零代码 | 无机器校验、无门禁、容易走样 |

**推荐 B**：官方 changes/ 目录结构做标准（未来可迁），但只实现 propose 校验 +
review 状态机 + archive 动作 + pipeline 门禁，砍掉 config/模板系统。

### 3.2 P1 — TDD 顺序

| 方案 | 做法 | 优点 | 缺点 |
|:--|:--|:--|:--|
| **A 完全 TDD** | test-planning 移到 development 前，强制先写测试骨架 | 最正宗 | 改 pipeline 顺序，codegen 流程大改，风险高 |
| **B test-planning 前置（推荐）** | test-planning 移到 development 前，development 实现后 self-test 直接跑；development 引用测试计划 | 改动可控；测试先定义行为 | 需要处理存量顺序断言 |
| **C 门禁式** | 顺序不动，test-planning 加"测试必须断言行为而非适配代码"检查 | 最轻 | 治标不治本，codegen 仍先写代码 |

**推荐 B**：test-planning 前置到 development 前，development 实现后测试直接执行。
配合现有 RED→GREEN 铁律形成完整 TDD 闭环。

### 3.3 P2 — 前期追问（grill-me）

| 方案 | 做法 | 优点 | 缺点 |
|:--|:--|:--|:--|
| **A 新增 challenge 步骤** | super-analysis 后加"假设挑战"LLM 步骤（spec 假设逐条追问） | 独立、清晰 | 多一步 LLM 成本 |
| **B 复用 claude-review（推荐）** | claude-review 的 prompt 加"先挑战 spec 假设再评方案"指令 | 零新步骤；外部 agent 独立判断 | 依赖 claude CLI 可用 |
| **C 并入 prd-review** | prd-review 要求先列假设风险再评 PRD | 最轻 | 挑战深度有限 |

**推荐 B**：改 claude-review 的 prompt 模板，要求先挑战 spec 假设（需求完整性/
边界/可测试性）再评方案，复用现有外部 agent 机制。

### 3.4 P3 — research / prototype（本期不做，留扩展入口）

- 设计：profile 里加可选 `research` / `spike` 步骤（默认关闭，YAGNI）
- 本期只留 pipeline 步骤注册位，不实现 handler

## 4. 推荐推进顺序

1. **P0-B 先落**（1 天）：`.osh/changes/` 结构 + `spec cp` CLI + `spec-cp-review`
   门禁步骤 + RULES §13 + 模板同步 + 测试 + 全量回归
2. **P1-B 次落**（0.5 天）：test-planning 前置 + 顺序断言迁移 + 回归
3. **P2-B 再落**（0.5 天）：claude-review prompt 挑战指令 + 测试 + 回归
4. **P3** 留扩展位，不实现

## 5. P0-B 原子需求拆解（RULES §11 格式）

| ID | 原子需求 | 验收标准 |
|:--|:--|:--|
| CP-01 | `.osh/changes/<id>/` 目录结构规范（proposal.md + tasks.md 必填，design.md/specs/ 可选）落 RULES §13 | RULES §13 含目录结构 + 必填/可选文件定义 |
| CP-02 | `yuleosh spec cp propose <id>` CLI：校验 proposal.md 格式（frontmatter + 章节 + tasks 清单可解析） | 合法 CP 通过；缺 frontmatter/tasks 报错；单测覆盖 |
| CP-03 | CP 状态机：`proposed → approved → implemented → archived`，`spec cp status` / `spec cp approve` / `spec cp archive` | 状态转换正确；archive 移动目录 + 更新 spec 基线 |
| CP-04 | pipeline 新增 `spec-cp-review` 步骤：扫描 `.osh/changes/` 未批准 CP，调用 LLM 评审（对齐 spec/契约/影响面） | 有未批准 CP 时步骤产出评审报告；无 CP 时 skipped；mock 测试绿 |
| CP-05 | 门禁：存在 `approved` 但未 `implemented` 的 CP 时，codegen/development 步骤阻断 | 门禁触发测试绿（RED 先写） |
| CP-06 | `spec cp archive` 后 spec.md 自动同步（CP specs/ 增量合并）或至少显式警告 | 合并或警告路径测试绿 |
| CP-07 | RULES §13 + 模板同步（模板源头 + 仓库副本 + methodology init 挂载） | 两处一致 |
| CP-08 | 全量回归绿（无契约漂移） | 全量通过 |

## 6. 决策记录

- **砍掉**：config.yaml 注入、模板自定义系统（官方 OPSX 的 schema 定制对 yuleOSH 是 YAGNI）
- **保留**：官方 changes/ 目录命名与归档格式（`archive/<date>-<id>/`），未来可对齐官方 CLI
- **衔接**：CP 的 tasks.md 与 RULES §11 需求原子化联动——CP tasks = 原子需求清单，验收逐项
