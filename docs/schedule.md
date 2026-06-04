# OSH-Fusion 平台 · 排期与任务分解

> 小步快跑 · 每天交付 · 自动化精准狠
> 周期: 2026-06-04 ~ 2026-06-17 (14天)

---

## 🎯 迭代概览

```
Iter   日期       交付物                       验证方式
──────────────────────────────────────────────────────────
I-0    D1 (06/04)  本排期 + 平台骨架             结构评审 ✅
I-1    D1-2         spec-engine: OpenSpec 引擎   解析10个spec ✅
I-2    D2-4         agent-pipeline: 自动流水线    跑通SDD→DDD→TDD ✅
I-3    D4-6         ci-layer1: 开发验证CI         单步CI 通过 ✅
I-4    D7-9         review-engine: 审查矩阵       3-agent 并行审 ✅
I-5    D9-11        evidence-chain: 追溯+合规包   一键产出 ✅
I-6    D11-13       ci-layer2+3: 完整CI/CD        全链路跑通 ✅
I-7    D13-14       web-ui: 控制面板              可操作 ✅
──────────────────────────────────────────────────────────
每48小时一个可演示的增量
```

---

## 📦 Iteration 0: 骨架搭建 (D1 · 2026-06-04)

**目标**: 项目结构 + 平台 CLI 脚手架 + 本次排期

| Task | 类型 | 工时 | 负责人 | 验收标准 |
|:-----|:----:|:----:|:------|:---------|
| T0-1 创建项目骨架结构 | setup | 0.5h | 小明 | src/spec/ src/pipeline/ src/ci/ 存在 |
| T0-2 本排期文档完成 | docs | 0.5h | 小明 | 所有 iteration 已定义 |
| T0-3 定义平台 CLI 入口 | feature | 1h | Claude | `osh-cli init` 可运行 |

---

## 📦 Iteration 1: OpenSpec 引擎 (D1-D2)

**目标**: 能解析、校验、diff OpenSpec 规范文件

| Task | 类型 | 工时 | 负责人 | 验收标准 |
|:-----|:----:|:----:|:------|:---------|
| T1-1 spec parser: 解析 SHALL/SHOULD/MAY | feature | 2h | Claude | 解析 `spec.md` 输出 JSON 需求树 |
| T1-2 spec parser: GIVEN/WHEN/THEN 场景 | feature | 2h | Claude | 解析场景定义 |
| T1-3 spec-delta diff engine | feature | 2h | Claude | 对比两个 spec 版本，输出 +/- 标记 |
| T1-4 spec validator: 完整性校验 | feature | 2h | Claude | 检查覆盖率 > 98% |
| T1-5 需求树层级结构 | feature | 1h | Claude | SYS → SW → Feature 层级 |
| T1-6 单元测试 + 集成 | test | 1h | Claude | 10 个 spec 全通过 |
| T1-7 Hermes 规范审查 | review | 0.5h | Hermes | 对照 spec.md 逐条确认 |

---

## 📦 Iteration 2: Agent Pipeline (D2-D4)

**目标**: 小明→Hermes→Claude 自动流转跑通

| Task | 类型 | 工时 | 负责人 | 验收标准 |
|:-----|:----:|:----:|:------|:---------|
| T2-1 Pipeline 编排引擎: Session 管理 | feature | 3h | Claude | 创建/查看/推进/回退 Pipeline |
| T2-2 小明节点: spec 合规检查 | feature | 2h | 小明 | 自动校验 spec 完整性 |
| T2-3 小明节点: S.U.P.E.R 模板生成 | feature | 1h | 小明 | `osh-cli super` 输出模板 |
| T2-4 小明节点: 跨 agent 路由 | feature | 2h | 小明 | spec→Hermes / dev→Claude 自动路由 |
| T2-5 Hermes 节点: spec→prd 转换 | feature | 2h | Hermes | 接收 spec 输出 prd.md |
| T2-6 Claude 节点: sdd→arch 转换 | feature | 2h | Claude | 接收 prd 输出 architecture.md |
| T2-7 T00 三步法 templates | feature | 1h | Claude | feature/bugfix/refactor 模板 |
| T2-8 端到端: spec→arch 全链路测试 | test | 1h | 小明 | 输入 spec, 输出 arch |

---

## 📦 Iteration 3: CI Layer 1 (D4-D6)

**目标**: 每个 Commit 自动完成单元测试 + 覆盖率门禁

| Task | 类型 | 工时 | 负责人 | 验收标准 |
|:-----|:----:|:----:|:------|:---------|
| T3-1 pre-commit hook: plan-lint | feature | 1.5h | Claude | 阻非法 kind/T00 格式 |
| T3-2 pre-commit hook: clang-tidy | feature | 1.5h | Claude | C/C++ 风格检查 |
| T3-3 测试框架适配器 (GTest/Unity) | feature | 2h | Claude | 自动发现并运行测试 |
| T3-4 覆盖率收集器 | feature | 2h | Claude | gcov/lcov 集成, 输出% |
| T3-5 覆盖率门禁 (80% line / 98% cond) | feature | 1h | Claude | 不达标阻断 commit |
| T3-6 CI runner: 本地 git hook | feature | 2h | 小明 | hook 全自动安装 |
| T3-7 CI 日志收集 + 报告 | feature | 1h | Claude | 输出 test-report.md |

---

## 📦 Iteration 4: 审查矩阵 (D7-D9)

**目标**: 3 个 Agent 并行审查，blocking/非阻塞双轨

| Task | 类型 | 工时 | 负责人 | 验收标准 |
|:-----|:----:|:----:|:------|:---------|
| T4-1 per-task reviewer 调度器 | feature | 2h | 小明 | 按 task kind 路由到对应 agent |
| T4-2 architecture-reviewer agent | feature | 2h | Claude | 审查架构一致性 |
| T4-3 domain-modeling review agent | feature | 2h | Claude | 审查领域模型正确性 |
| T4-4 code-style review agent | feature | 2h | Hermes | 审查代码风格 |
| T4-5 coverage-guardian agent | feature | 1h | Hermes | 审查覆盖率数据 |
| T4-6 双轨: AI 自检(非阻塞) + 推表(阻塞) | feature | 2h | 小明 | 非阻塞不打断 worktree |
| T4-7 review 投票逻辑: 通过/退回/重试 | feature | 2h | Claude | 通过→merge, 退回→打包重试(5轮) |
| T4-8 review 结果 JSON 存档 | feature | 1h | Claude | 每个 review 存 JSON |

---

## 📦 Iteration 5: 证据链 (D9-D11)

**目标**: Release 自动产出追溯矩阵 + 合规包

| Task | 类型 | 工时 | 负责人 | 验收标准 |
|:-----|:----:|:----:|:------|:---------|
| T5-1 追溯矩阵生成器 | feature | 3h | Claude | Req→Design→Impl→Test 双向 |
| T5-2 需求覆盖率计算 | feature | 2h | Claude | SHALL 语句 → 对应测试用例 |
| T5-3 代码覆盖率报告 (line/branch/MCDC) | feature | 2h | Claude | 统一格式覆盖率报告 |
| T5-4 review 记录汇总 | feature | 1h | Claude | 所有 review JSON → 汇总.md |
| T5-5 合规包打包器 | feature | 2h | 小明 | `osh-cli compliance-pack` → zip |
| T5-6 ASPICE 审计模板 | feature | 1h | Hermes | 模板对齐 ASPICE 过程域 |

---

## 📦 Iteration 6: 完整 CI/CD (D11-D13)

**目标**: Layer 2 (MR) + Layer 3 (Release) 跑通

| Task | 类型 | 工时 | 负责人 | 验收标准 |
|:-----|:----:|:----:|:------|:---------|
| T6-1 Layer 2: 交叉编译链矩阵 | feature | 2h | Claude | ARM/RISC-V/x86 三重编译 |
| T6-2 Layer 2: MISRA-C/C++ checker | feature | 2h | Claude | 集成 cppcheck/other 规则 |
| T6-3 Layer 2: 集成测试 runner | feature | 2h | Claude | 组件交互测试 |
| T6-4 Layer 2: 内存安全检测 (ASan) | feature | 1h | Claude | Valgrind/ASan 集成 |
| T6-5 Layer 3: 系统测试 E2E runner | feature | 2h | Claude | Spec 场景逐条跑 |
| T6-6 Layer 3: 固件签名 + OTA 包 | feature | 2h | Claude | 生产级签名流程 |
| T6-7 Layer 3: 版本号管理 (SemVer) | feature | 1h | 小明 | 自动 version bump |
| T6-8 全链路端到端测试 | test | 2h | 小明 | Commit→MR→Release 全通 |

---

## 📦 Iteration 7: Web UI (D13-D14)

**目标**: 能看、能操作的 Web 控制面板

| Task | 类型 | 工时 | 负责人 | 验收标准 |
|:-----|:----:|:----:|:------|:---------|
| T7-1 Dashboard: Pipeline 状态 | feature | 2h | Claude | 可视化 SDD→DDD→TDD→CI/CD |
| T7-2 Dashboard: 需求树 | feature | 1.5h | Claude | 层级展开/收起 |
| T7-3 Dashboard: CI/CD 日志 | feature | 1.5h | Claude | 实时输出展示 |
| T7-4 Dashboard: 审查记录 | feature | 1h | Claude | Review JSON 可视化 |
| T7-5 Dashboard: 合规包导出 | feature | 1h | Claude | 一键下载 zip |

---

## 🔄 每日节奏

```
09:00 ── 回顾昨日进度 → 调整排期
09:30 ── 当天 Task 启动 (spawn agents)
12:00 ── 第一次 checkpoint
14:00 ── 继续推进 / 修复阻断
17:00 ── 当天集成验证
17:30 ── 日报告 (进度 + 阻塞 + 明天计划)
```

## 📊 依赖关系图

```
I-1 (spec-engine)
  └──→ I-2 (agent-pipeline) ──→ I-4 (review-engine)
        │                              │
        └──→ I-3 (ci-layer1) ─────────┘
              │                        │
              └──→ I-5 (evidence)─────┘
                    │
                    └──→ I-6 (full-ci/cd)
                          │
                          └──→ I-7 (web-ui)
```

**关键路径**: I-1 → I-2 → I-3 → I-5 → I-6 → I-7
**并行分支**: I-4 可与 I-3 并行

---

## 🛡️ 风险与缓解

| 风险 | 概率 | 影响 | 缓解策略 |
|:----|:----:|:----:|:---------|
| Agent 审查质量不稳定 | 中 | 高 | 5轮重试机制 + 人工兜底 |
| 交叉编译链依赖复杂 | 高 | 中 | Docker 容器化环境 |
| 时间过紧 | 中 | 高 | 严格每日 checkpoint, 可灵活裁切 |
| 需求变更 | 中 | 低 | OpenSpec delta 即变即追踪 |
