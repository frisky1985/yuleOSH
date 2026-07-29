# ASPICE SWE.2 — 软件架构设计 证据文档

## 1. 已识别的软件架构组件

| 组件 | 描述 | 责任人 | 状态 |
|:----|:-----|:------|:----:|
| ALM 追溯引擎 | 需求→代码双向追溯 | yuleOSH | ✅ |
| 知识图谱引擎 | KGs 存储、查询、合并 | yuleOSH | ✅ |
| Pipeline 引擎 | CI/CD 多阶段执行 | yuleOSH | ✅ |
| 安全分析 | FMEA/FTA/DFA | yuleOSH | ✅ |
| CLI 接口 | 命令行管理与用户交互 | yuleOSH | ✅ |

## 2. 架构视图

- 分层架构: Presentation → Application → Domain → Infrastructure
- 依赖方向: 外层依赖内层，禁止反向依赖
- 模块间通过事件总线 (SystemEventBus) 解耦

## 3. 关键接口

| 接口 | 类型 | 描述 |
|:----|:----|:-----|
| PipelineSession | Data Class | 流水线执行上下文 |
| KPIStore | Protocol | KPI 数据持久化 |
| EventBus | Abstract | 异步事件通知 |

## 4. 架构决策记录

- ADR-001: 使用事件驱动架构解耦流水线步骤
- ADR-002: 知识图谱采用 PostgreSQL + JSONB 存储
- ADR-003: 追溯矩阵采用双向链接，支持正向/逆向追溯
