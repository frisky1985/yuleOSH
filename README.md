# yuleOSH — 嵌入式AI开发全流程平台 🚀

> **y**ou **u**nify **L**ifecyc**E** of **O**penSpec + **S**uperpowers + **H**arness Engineering

一站式嵌入式AI开发平台，从需求到开发再到测试的**持续集成、持续测试**全自动流水线。AI Agents 编排作业，支持线上自定义配置或默认配置，让嵌入式开发团队能**快速实施、快速产品化、快速迭代**。

---

## 🔱 核心理念：三位一体

| 框架 | 回答的问题 | 核心产出 |
|:-----|:----------|:---------|
| **OpenSpec** | 做什么？需求是什么？验收标准？ | `spec.md` + `spec-delta.md` |
| **Superpowers** | 为什么做？怎么做？优先做什么？ | 14 Rules + S.U.P.E.R 分析 |
| **Harness Engineering** | 谁来做？怎么流转？ | Agent Pipeline + 3-Layer CI/CD |

## 🏗️ 平台架构

```
                    ┌──────────────────────────┐
                    │    OpenSpec Layer         │ ← 需求定义层
                    │   SHALL/SHOULD/MAY + Delta │
                    └──────────┬───────────────┘
                               ▼
                    ┌──────────────────────────┐
                    │   Superpowers Layer        │ ← 规则引擎层
                    │   14 Rules + Agent 审查    │
                    └──────────┬───────────────┘
                               ▼
                    ┌──────────────────────────┐
                    │ Harness Engineering Layer │ ← 调度执行层
                    │   Agent Pipeline + CI/CD  │
                    └──────────────────────────┘

CI/CD 三层流水线 (ASPICE 对齐):
  Layer 1: 开发验证 (Commit / SWE.4)
  Layer 2: 集成验证 (MR / SWE.5)
  Layer 3: 系统验证 (Release / SWE.6 + SYS.5 + SYS.6)
```

## 🚀 快速开始

```bash
# 1. 验证 OpenSpec 规范
yuleosh spec validate docs/spec.md

# 2. 运行全流程 Pipeline (小明→Hermes→Claude 自动流转)
yuleosh pipeline run docs/spec.md

# 3. 运行 CI 验证
yuleosh ci run 1   # Layer 1: 开发验证
yuleosh ci run 2   # Layer 2: 集成验证
yuleosh ci run 3   # Layer 3: 系统验证

# 4. 自动审查
yuleosh review auto
yuleosh review task "my-feature" feature

# 5. 生成 ASPICE 审计合规包
yuleosh evidence pack
```

## 📦 目录结构

```
yuleOSH/
├── docs/                    # 项目文档
│   ├── spec.md              # OpenSpec 规范
│   ├── startup-analysis.md  # S.U.P.E.R 分析
│   └── schedule.md          # 排期规划
├── src/
│   ├── spec/                # OpenSpec 引擎 (解析/校验/Diff)
│   ├── pipeline/            # Agent Pipeline 编排器
│   ├── ci/                  # CI/CD 三层流水线
│   ├── review/              # Agent 审查矩阵
│   ├── evidence/            # 追溯矩阵 + 合规包
│   └── ui/                  # Web Dashboard
├── tests/                   # 测试用例
├── .osh/                    # 运行时数据 (pipeline/ci/review/evidence)
└── osh-fusion-architecture.html  # 架构图
```

## 🔧 CLI 命令

| 命令 | 功能 |
|:----|:------|
| `yuleosh init [dir]` | 初始化项目 |
| `yuleosh spec validate <file>` | 验证 OpenSpec (SHALL/SCENARIO/覆盖度) |
| `yuleosh spec diff <old> <new>` | 需求变更追踪 |
| `yuleosh pipeline run <spec>` | 运行全流程 Agent 流水线 |
| `yuleosh pipeline status` | 查看 Pipeline 状态 |
| `yuleosh review auto` | 自动审查变更 |
| `yuleosh review task <name> [kind]` | 审查特定任务 |
| `yuleosh ci run <layer>` | 运行 CI 层 (1/2/3) |
| `yuleosh evidence pack` | 生成 ASPICE 合规包 |

## 🌐 Dashboard

```bash
yuleosh ui start
# → http://localhost:8080
```

## 🧪 当前状态

- ✅ OpenSpec 规范: **100% 覆盖度** (7 需求, 3 场景, 20 SHALL)
- ✅ 单元测试: **13 passed**, 覆盖率 **82.1%**
- ✅ Agent 审查: **4 Agent 并行** (架构/领域/风格/覆盖)
- ✅ CI/CD: **3 层流水线** 全部通过
- ✅ 合规包: **一键导出** (追溯矩阵 + 审查记录 + 覆盖率)

## 🎯 适用场景

- 嵌入式 MCU/SoC 开发团队
- ASPICE 合规项目 (SYS.3 → SWE.6)
- 需要 AI Agent 辅助开发的敏捷团队
- 从需求到测试全链路自动化的产线

## 📄 许可

MIT License
