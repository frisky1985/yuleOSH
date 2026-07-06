# yuleOSH 功能清单

> **嵌入式软件合规开发自动化平台**
> AI 辅助 · SWE 全流程 · 证据包一键生成
> 版本: v1.0.0 · Python ≥3.10 · MIT License

---

## 一、核心能力总览

| 能力域 | 能力数 | 说明 |
|:-------|:------:|:-----|
| 🧠 **OpenSpec 需求引擎** | 6 | 结构化需求 → 验证 → 变更追踪 → 状态机 |
| 🤖 **AI Agent 流水线** | 10 步 | 需求→设计→编码→审查→测试 全自动编排 |
| 🔍 **代码审查** | 4× 并行 | 架构/领域/风格/覆盖率 四维审查矩阵 |
| ⚙️ **CI/CD 引擎** | 3 层 | 单元验证 → 集成验证 → 系统验证 |
| 📋 **合规 & 证据** | 7 项 | ASPICE SWE.1~SWE.6 全流程 |
| 🔌 **硬件事物** | 3 种 | OpenOCD / JLink / esptool 烧录调试 |
| 🌐 **SaaS Dashboard** | 12+ 端点 | 实时监控 + 多租户 + 定价计费 |
| 🛠️ **CLI 命令** | 22 个 | 覆盖项目完整生命周期 |
| 🔗 **AUTOSAR 集成** | 2 项 | ARXML 解析 + SWC Stub 生成 |
| 📚 **知识库 (RAG)** | 3 类 | MISRA 规则 / 嵌入式最佳实践 / 经验教训 |

---

## 二、逐模块功能详情

### 🧠 1. OpenSpec 需求引擎

| 功能 | 描述 | 状态 |
|:----|:-----|:----:|
| Structured Requirements | SHALL/SHOULD/MAY 关键字语法 + GIVEN/WHEN/THEN 场景描述 | ✅ |
| Hierarchical IDs | 系统级(SYS) → 软件级(SW) → 功能级(FEATURE) 多层级 | ✅ |
| Auto-Validation | 需求格式自动校验，ID 唯一性检查 | ✅ |
| Version Diff | 版本间变更差异分析 + 影响范围评估 | ✅ |
| State Machine | PROPOSED → APPROVED → IMPLEMENTED → VERIFIED | ✅ |
| Spec Mapping | 需求→架构→代码→测试 双向追溯 | ✅ |

### 🤖 2. AI Agent Pipeline (10 步全自动)

| 步骤 | 阶段 | 产出物 |
|:----|:-----|:-------|
| P1 | Startup Analysis (S.U.P.E.R.) | `startup-analysis.md` |
| P2 | OpenSpec 需求结构化 | `spec.md` |
| P3 | 软件设计说明 (SDD) | `sdd.md` |
| P4 | 详细设计说明 (DDD) | `ddd.md` |
| P5 | 代码生成 | 完整的 C/Python 项目结构 |
| P6 | 测试规划 | `test-plan.md` |
| P7 | 4-Agent 并行代码审查 | `review-report.md` |
| P8 | CI 运行 (3 层) | CI 报告 |
| P9 | 证据包生成 | `evidence-bundle/` (ZIP) |
| P10 | 最终报告 | `final-report.md` |

- LLM 无关设计：支持 DeepSeek / Claude / GPT-4o 切换
- Token 预算预检：内置 TokenBudget Checker
- 成本日志：CostLogger (JSONL 格式)

### 🔍 3. 4-Agent 并行代码审查

| 审查维度 | 审查内容 | 覆盖项 |
|:---------|:---------|:------:|
| 🏗️ 架构审查 | 模块依赖、接口一致性、设计模式 | 8 项检查 |
| 🧪 领域审查 | 嵌入式领域规则、MCU 选型适配 | 12 项检查 |
| ✨ 代码风格 | MISRA C 准则、命名规范、单一出口 | 10 项检查 |
| 📊 覆盖率审查 | 分支/行/函数覆盖率审核 | 6 项检查 |
| 📐 资源预测 | 栈/堆/Flash/RAM 使用量估算 | 4 项分析 |

### ⚙️ 4. CI/CD 引擎 — 3 层自动化验证

| 层级 | 名称 | 触发条件 | 包含 |
|:----:|:-----|:---------|:-----|
| 🔵 L1 | 开发验证 | 每次提交 | 单元测试 + 覆盖率门禁 + lint |
| 🟡 L2 | 集成验证 | MR/PR 合并 | 交叉编译 + MISRA 静态分析 + 性能基线 |
| 🟤 L2.5 | AI 审查 | MR/PR 合并 | 4-Agent 并行审查 |
| 🔴 L3 | 系统验证 | Release 标签 | 系统测试 + 证据包 + 合规检查 |

**关键技术指标：**
- 交叉编译支持: ARM GCC / RISC-V GCC
- MISRA C 静态分析: cppcheck 集成，180+ 条规则自动检查
- 覆盖率门禁: 可配置 fail_under 阈值
- 检查点断点续跑: Pipeline 任意点可注入续跑

### 📋 5. 合规 & 证据管理 (ASPICE SWE.1~SWE.6)

| 功能 | 覆盖标准 | 说明 |
|:-----|:---------|:-----|
| SWE.1 需求分析 | ASPICE | 需求结构化 + 评审记录 |
| SWE.2 架构设计 | ASPICE | 架构文档生成 + 评审 |
| SWE.3 详细设计 | ASPICE | 详细设计 + 接口定义 |
| SWE.4 单元验证 | ASPICE | 单元测试 + MC/DC 分析 |
| SWE.5 集成与测试 | ASPICE | 集成测试 + 回归 |
| SWE.6 合格性测试 | ASPICE | 系统测试 + 验收判定 |
| 证据包一键生成 | ISO 26262 | 6 子目录 + SHA-256 签名 + RSA 校验 |
| 自检报告 | self-assessment | 18 BP 评估矩阵 |
| 差距分析 | G-50 | 自动识别未达标过程域 |
| 追溯矩阵 | — | 需求→设计→代码→测试 全链路追溯 |

**证据包结构：**
- `ci-results/` — CI 层结果
- `misra-reports/` — MISRA 分析报告
- `trend-data/` — KPI/趋势数据
- `coverage/` — 测试覆盖率
- `reviews/` — 审查工件
- `traceability/` — 追溯矩阵
- `audit-manifest.json` + SHA-256 哈希

### 🔌 6. 硬件集成

| 平台 | 烧录工具 | 调试器 | HIL |
|:-----|:---------|:-------|:---:|
| ESP32 / ESP32-S3 | esptool | idf-monitor + GDB | ✅ |
| STM32 (F4/H7/G0) | OpenOCD | OpenOCD + GDB | ✅ |
| ARM Cortex-M (任意) | JLinkExe | JLinkGDBServer | ✅ |
| 自定义平台 | Plugin API | Plugin API | ✅ |
| SIL (无硬件模式) | QEMU | 断言检查 | ✅ |

### 🌐 7. SaaS Dashboard

| 功能 | 技术栈 | 说明 |
|:-----|:-------|:-----|
| 实时项目监控 | Next.js + Python HTTP | Web UI |
| 多租户隔离 | JWT + PostgreSQL | 组织/项目/用户 三层 |
| 项目列表 | REST API | 合规进度总览 |
| SWE 合规状态 | REST API | SWE.1~SWE.6 进度雷达 |
| 差距分析 | REST API | 13+ 项差距追踪 |
| 覆盖率趋势 | REST API | 线/分支/函数 覆盖率图表 |
| MISRA 违规趋势 | REST API | 每周违规统计 + 分布 |
| 证据包一键生成 | REST API | 异步生成 + 状态轮询 |
| 定价页 | 静态页面 | ¥599/月 Pro + ¥98,000/年 Enterprise |
| 3 个 Landing Page | 静态页面 | Tier 2 场景: 审计准备/预算/审查瓶颈 |
| Onboarding 三步流 | 静态页面 | 初始化 → 扫描 → Dashboard |
| CI 结果查看 | REST API | 分层 CI 结果展示 |

**Dashboard 数据真实性：** 所有 7 个端点 100% 真实数据读取，零假数据。

### 🛠️ 8. CLI 命令 (22 个)

| 命令 | 功能 |
|:-----|:-----|
| `yuleosh init` | 初始化项目目录 |
| `yuleosh project` | 项目管理 |
| `yuleosh template` | 项目模板管理 |
| `yuleosh spec` | OpenSpec 需求管理 |
| `yuleosh pipeline` | Agent 流水线管理 |
| `yuleosh review` | 代码审查管理 |
| `yuleosh ci` | CI 流水线管理 |
| `yuleosh ev` | ASPICE 合规与差距检查 |
| `yuleosh evidence` | CL2 证据包生成与校验 |
| `yuleosh config` | 配置管理 |
| `yuleosh stats` | 项目统计 |
| `yuleosh demo` | 创建并运行 Demo |
| `yuleosh traceability` | 追溯矩阵管理 |
| `yuleosh hook` | Git Hook 管理 |
| `yuleosh kb` | 知识库管理 |
| `yuleosh coverage` | 覆盖率管理 |
| `yuleosh audit` | CL2 审计证据管理 |
| `yuleosh autosar` | AUTOSAR 管理 (解析/生成 Stub) |
| `yuleosh swe6` | SWE.6 合格性测试管理 |
| `yuleosh misra` | MISRA C:2023 合规管理 |
| `yuleosh kpi` | KPI 基线管理 |
| `yuleosh ui` | 启动 Web Dashboard |

### 🔗 9. AUTOSAR 集成 (Phase 1+2)

| 功能 | 说明 |
|:-----|:------|
| ARXML 解析器 | AUTOSAR XML Schema 解析 + SWC 组件提取 |
| SWC Stub 生成器 | 支持: CanSm (4 stubs) + CanIf (7 stubs) |
| BSW 模块覆盖 | CanSm, CanIf 完整验证 |
| 集成闭环 | ARXML 解析 → Stub 生成 → yuleOSH 管道集成 |

### 📚 10. 知识库 (RAG 底座)

| 类型 | 内容 | 用途 |
|:-----|:-----|:-----|
| MISRA 规则索引 | 30 条核心规则详解 | AI 审查时的规则参考 |
| 嵌入式最佳实践 | UART/I2C/SPI 实现指南 | 代码生成参考 |
| 经验教训 | 历史缺陷/根因追踪 | 代码审查辅助 |
| FMEA 管理 | 失效模式/后果/探测度 | 安全分析 |
| 智能检索 | `source='misra_analysis'` 过滤 | Dashboard 实时违规展示 |

### 🧪 11. AI Agent Benchmark

| 指标 | 数据 |
|:-----|:-----|
| 测试用例总数 | 27 (12 easy + 10 medium + 5 hard) |
| 规则覆盖 | Dir 4.1, 10.1, 11.3, 8.13, 18.6, 19.1, 21.3, 22.1 等 |
| 运行模式 | 3 次/任务，统计平均 |
| 稳定性 | 100% success rate (30 次 DeepSeek V4 Flash API) |
| 输出格式 | Markdown 报告 |

### 🔧 12. 其他支持模块

| 模块 | 功能 |
|:-----|:------|
| Preview Engine | 提交前的预分析 + 评分 (0-10) |
| Test Generation | 从 Spec 场景自动生成测试脚手架 |
| Plugin System | 类型注册 + 沙箱执行 |
| Cross Module | ARM/RISC-V 交叉编译支持 |
| SIL Adapter | QEMU 软件在环 + 断言检查 |
| Hooks System | Task-Init Hook、Git Hook 自动触发 |
| Usage Metering | SaaS 用量计量 + Stripe 支付网关 |
| Store Backend | SQLite (本地) / PostgreSQL (生产) 双引擎 |

---

## 三、技术栈

| 类别 | 技术 |
|:-----|:-----|
| 语言 | Python 3.10+, C (嵌入式固件) |
| 前端 | Next.js (TypeScript) |
| 数据库 | SQLite (本地) / PostgreSQL (生产) |
| LLM | DeepSeek V4 / Claude / GPT-4o (可切换) |
| IDE 集成 | VS Code + pyright + pytest |
| 部署 | Docker Compose / pip 一键安装 |
| CI | 内置 3 层 CI 引擎 (无外部依赖) |
| OS | macOS / Linux / Docker |

---

## 四、快速启动 (客户演示话术)

```bash
# 3 命令，2 分钟，从零到合规固件
pip install yuleosh
yuleosh init my-project
yuleosh pipeline run docs/spec.md
```

**客户可以当场看到的：**
1. spec.md → SDD → DDD → C Code 全自动生成
2. 4-Agent 并行审查报告
3. 3 层 CI 验证结果
4. 证据包一键生成 (SHA-256 签名)
5. Dashboard 实时状态

---

## 五、质量指标

| 指标 | 数值 |
|:-----|:----:|
| 总测试数 | 3,310+ (含参数化) |
| 全局 C 覆盖率 | 22.06% (核心模块 ≥80%) |
| MISRA 规则映射率 | ~99% (原 0.3%) |
| ASPICE 自检 | 18 BP: 12 pass, 3 partial, 3 fail |
| 专家评分 (AI) | 7.9/10 |
| 专家评分 (汽车嵌入式) | 8.0/10 |
| CI 回归测试 | 144 passed, 0 failed |

---

*文档版本: 2026-07-06 · 适用于客户演示和商务沟通*
