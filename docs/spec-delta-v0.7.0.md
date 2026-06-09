# Spec-Delta: v0.6.1 → v0.7.0

> 基于 yo-analysis.md 分析报告 | 生成: 2026-06-10

---

## 版本变更

| 属性 | v0.6.1 | v0.7.0 |
|:-----|:-------|:-------|
| 核心交付 | 代码重构 + 安全加固 | LLM Agent 元年 + 工程质量补齐 |
| 测试数 | 783 | 目标 850+ |
| AI Agent 评分 | 5/10 | 目标 8/10 |

---

## Ralph Loop 执行模型

```
小明(PM) 拆解需求 → 并行子Agent → 交叉检视 → 质量门禁 → 报告
         │
         ├── 小克 👨‍💻: I1(LLM Agent) + I4(DB Migration) + I6(真实HIL)
         │
         └── 小马 🐴: I2(Evidence修复) + I3(追溯矩阵)
                   │
                   └── 交叉检视对方的代码和测试
```

---

## 🔥 P0 — AI Agent 核心能力（当前执行中）

### I1: LLM Agent Pipeline 内容生成 → 小克 👨‍💻

| Task | 内容 | 状态 |
|:-----|:-----|:----:|
| T1.1 | Prompt 模板工程 — 10 个 step 各自 prompt | 🔄 |
| T1.2 | PipelineStep 注入 LLM 调用 | 🔄 |
| T1.3 | Token 用量追踪 + 成本估算 | 🔄 |
| T1.4 | 硬错误模式（LLM 失败 → PipelineStepError） | 🔄 |
| T1.5 | Prompt 版本管理与 spec-delta 联动 | 🔄 |

### I2: Evidence Engine 修复 → 小马 🐴

| Task | 内容 | 状态 |
|:-----|:-----|:----:|
| T2.1 | 硬编码路径→最近 pipeline session 自动发现 | 🔄 |
| T2.2 | Pipeline 状态竞态修复（_save 时序） | 🔄 |
| T2.3 | 测试覆盖 | 🔄 |

### I3: 追溯矩阵升级 → 小马 🐴

| Task | 内容 | 状态 |
|:-----|:-----|:----:|
| T3.1 | Scenario-Ref 显式字段设计与解析器 | 🔄 |
| T3.2 | 两级匹配：精确 Ref → 关键词回退 | 🔄 |
| T3.3 | 匹配置信度标注 | 🔄 |
| T3.4 | 现有测试文件添加 Covers 标记 | 🔄 |

---

## 📦 P1 — 工程化补齐（下一波）

### I4: DB Migration 框架
- Alembic 或纯 SQL migration 脚本
- 支持 schema 版本演进

### I5: 发布打包
- `pip install yuleosh` 完善
- Docker Hub 自动构建

### I6: 真实 HIL 硬件测试
- Mock → OpenOCD/JLink 真实连接

---

## 质量门禁

| 门禁 | 标准 |
|:-----|:-----|
| 单元测试 | 全量通过，新增测试覆盖新代码 |
| 交叉检视 | 小克检视小马代码 + 小马检视小克代码 |
| Spec 验证 | `python3 src/spec/validate.py docs/spec.md --json` 0 errors |
| CI L1 | `make ci-layer1` 全绿 |

---

## 变更记录

| 时间 | 变更 | 内容 |
|:-----|:-----|:-----|
| 2026-06-09 | v0.6.1 | Pipeline重构 + 安全加固 + CLI argparse迁移（小克） |
| 2026-06-10 | v0.7.0 kickoff | Ralph Loop 启动 P0 I1/I2/I3 三线并行 |
