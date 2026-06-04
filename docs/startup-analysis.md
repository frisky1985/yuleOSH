# S.U.P.E.R 启动分析：OSH-Fusion 嵌入式开发平台

> 2026-06-04 | 作者: 小明

---

## S — Situation (场景理解)

**现状**:
- DK Hub SaaS v2.0 已在开发中（三条 Track 并行，06/03-06/13）
- 已有完整的 Agent 三人小队（小明 + Hermes + Claude）协作体系
- 已有 OpenSpec + Superpowers + Harness Engineering 方法论底座（已固化）
- 当前基建全部是 CLI/agent 驱动，缺少可视化的 Web 平台
- 嵌入式团队要落地 ASPICE 合规，但现有工具链（Codebeamer/Polarion）太重、太贵

**痛点**:
- 没有统一平台：需求在飞书/文档，代码在 Git，审查在聊天，证据靠人工
- ASPICE 审计准备成本极高（手动整理追溯矩阵 + 评审记录）
- 嵌入式项目依赖复杂（交叉编译链、HIL、MISRA），没有自动化门禁

## U — Understanding (深层需求)

**用户真正要的不是"又一个 ALM 平台"，而是**:
1. **把合规自动化** — 不靠人写文档，靠 Agent + Rules 自动产出 ASPICE 证据
2. **把流程可编程** — 不靠咨询公司定流程，靠代码定义规则
3. **降低嵌入式的准入门槛** — 让小团队也能承受 ASPICE 的合规成本
4. **Dogfooding 验证** — 先用 OSH-Fusion 方法论做这个平台本身，验证它是否真的可行

## P — Problem (核心问题)

**如何用 OSH-Fusion 方法，在 2 周内搭建一个可用的嵌入式开发 MVP？**

约束条件：
- 我们自己在做这个平台本身 → Dogfooding
- DK Hub SaaS v2.0 并行不冲突
- 必须出可演示/可使用的实体，不只是文档

## E — Execution (执行方案)

### 核心策略：先做引擎，再做界面

不要先做 UI，先做 **Pipeline 引擎**。CLI 可运行 → Web 加壳。
这也是 Superpowers 的原有模式：CLI commands → 以后做 UI。

### MVP 范围（2 周）

```
Week 1: Pipeline 引擎
  ├── spec-engine: OpenSpec 解析/校验/Delta 追踪
  ├── task-orchestrator: Agent 流水线编排
  └── ci-engine: 三层 CI/CD 骨架

Week 2: 审查 + 证据链
  ├── review-engine: Agent 矩阵调度
  ├── evidence-collector: 追溯矩阵 + 合规包
  └── web-ui: 基础控制面板
```

## R — Resources (资源评估)

| 资源 | 情况 |
|:----|:------|
| ✨ 小明 | Orchestrator + CI/CD |
| 🔮 Hermes | 需求/产品 + 审查 |
| 💻 Claude | 引擎开发 + 集成 |
| ⏱ 时间 | 2 周 MVP，每天迭代 |
| 🔧 工具 | OpenClaw + Agent 桥 + Git |

## P — Priority (优先级判断)

```
P0 ── 必须：Pipeline 引擎能跑通
  ├── spec engine (OpenSpec 解析 + 校验)
  ├── agent pipeline (PM→Product→Dev 自动流转)
  └── CI layer 1 (单元测试 + 覆盖率)

P1 ── 重要：审查 + 证据
  ├── per-task auto-reviewer
  ├── traceability matrix
  └── CI layer 2 (交叉编译 + 静态分析)

P2 ── 加分：界面 + 证据链
  ├── web UI (React dashboard)
  ├── CI layer 3 (系统测试 + 合规包)
  └── multi-target support
```
