# yuleOSH 项目简报 — 专家评审材料

> 版本: v1.0.0 GA | 最新提交: 983f3630 (2026-06-29)
> 定位: 一站式 ASPICE 合规开发平台

---

## 一、项目概述

yuleOSH 是**面向汽车嵌入式开发的 AI 驱动全生命周期平台**，从需求定义（OpenSpec）到审计证据包，一站式覆盖嵌入式开发全流程。

### 核心定位
> 一站式 ASPICE 合规开发平台（合规辅助工具）
> 英文: ASPICE-compliant embedded development platform (assistance tool)

### 目标用户
| 画像 | 角色 | 核心痛点 |
|:-----|:-----|:---------|
| 🛡️ 质量经理 | 负责 ASPICE 合规与审计 | 手工追溯矩阵 > 80h/次，审计靠 Excel |
| 🏗️ 架构师 | 嵌入式系统架构与工具链选型 | Jenkins/Vector/ALM 碎片化，集成成本高 |
| 👨‍💻 开发者 | 嵌入式固件开发与 CI | 手工 Review + 环境配置占 60% 时间 |

### 定价
- Free: 基础流水线 + 3 项目
- Pro: ¥599/月（¥5,999/年）
- Enterprise: ¥98,000/年（私有化部署）

---

## 二、技术架构

### 方法论底座（三位一体）
| 框架 | 回答 | 产出物 |
|:-----|:------|:-------|
| **OpenSpec** | 做什么？需求+验收标准 | spec.md + spec-delta.md |
| **Superpowers** | 为什么做？优先级 | startup-analysis.md + Rules |
| **Harness Engineering** | 谁来做？流水线编排 | Pipeline + Agent 编排 |

### 核心功能
1. **Agent 驱动的开发流水线**: SDD → DDD → TDD → CI/CD
2. **需求管理**: 需求树层级 (SYS→SW→Feature→Scenario→Task), RFC 2119 格式
3. **CI/CD 三层流水线**: Dev Verify → Integration Verify → System Verify
4. **MISRA-C/C++ 静态分析**: 185 条规则，偏差管理
5. **代码审查 Agent 矩阵**: 双轨审查（AI 自检 + Agent 审查）
6. **追溯与证据链**: 需求→设计→代码→测试双向追溯
7. **SIL 仿真测试**: QEMU 系统仿真 (ARM Cortex-M / RISC-V)
8. **HIL 硬件测试**: OpenOCD/JLink/pyOCD 统一烧录 + 串口断言
9. **Template Gallery**: 预置项目模板市场
10. **证据包一键生成**: `yuleosh ev pack` 生成合规证据 ZIP

### 技术栈
- **后端**: Python, CLI (argparse), Async Pipeline
- **前端**: Web Dashboard (static HTML + JS)
- **存储**: SQLite → PostgreSQL (v6 Store 层)
- **CI**: GitHub Actions + 自研 Pipeline Engine
- **静态分析**: MISRA + Semgrep + Clang-Tidy
- **安全**: JWT + bcrypt + Rate Limiting
- **支付**: Stripe 集成 + 用量计量
- **打包**: Docker + pip install

---

## 三、项目历程

### 已完成的 Sprint / Phase

| 阶段 | 范围 | 状态 |
|:-----|:------|:------|
| v0.1.0~v0.9.0 | 核心引擎、CLI、Dashboard、Pipeline | ✅ 完成 |
| v1.0.0 GA | Dashboard 2.0 / SaaS 底座 / Stripe | ✅ 完成 |
| Phase 2.1 | GSCR合规 / Checkpoint Engine / 三级指针 | ✅ 完成 |
| Phase 2.2 | 超大模块拆分 / 追溯矩阵 / Docker 稳定性 / 覆盖冲刺 | ✅ 完成 |
| CL2 专家评审 | 老陈四轮审查 → 88/100 正式通过 ✅ | ✅ 完成 |

### 最新指标 (Phase 2.2 结束时)
- **总测试数**: 269 通过
- **全局覆盖率**: 15.40%
- **Python 文件数**: 430+
- **SHALL 需求覆盖**: 55 个，100% 映射到测试
- **CL2 就绪度**: 88/100 ✅

### 覆盖最差的模块（待攻坚）
| 模块 | 覆盖率 | 行数 |
|:-----|:-------|:-----|
| `testgen/` | 0% | 435 |
| `preview/` | 0% | 516 |
| `review/run.py` | 8% | 244 |
| `ci/kpi/*` | 0% | ~1,247 |
| `evidence/*` | 0-15% | ~800 |
| `ci/misra_report/*` | ~10% | ~1,659 |

---

## 四、ASPICE 合规状态

### 已覆盖的过程域
- **SWE.1** (软件需求分析): 需求树层级 + 追溯 ✅
- **SWE.2** (软件架构设计): MISRA + 架构审查 ✅
- **SWE.3** (软件详细设计): OpenSpec DD + 编码规范 ✅
- **SWE.4** (软件单元验证): 单元测试 + 覆盖率 ≥ AL2 ✅
- **SWE.5** (软件集成验证): SIL + 集成测试 ≥ AL2 ✅
- **SWE.6** (合格性测试): 三段式 Evidence ✅

### ASPICE 成熟度
- AL1+（SWE.4/SWE.5 达 AL2）

### ISO 26262 功能安全
- ⚠️ 方法论已集成（HARA → FSR → TSR → Safety Case）
- 尚未在代码层面实现 ASIL 等级标注

---

## 五、竞品对标 (2026-06)

| 维度 | dSPACE | Vector | yuleOSH |
|:-----|:--------|:--------|:---------|
| 定位 | HIL/SIL 硬件+仿真 | 总线/诊断/ECU 工具链 | 合规开发全流程平台 |
| 部署 | 私有化(硬件绑定) | 私有化(license) | 云端SaaS / 私有化 |
| AI | 无原生 AI | 有限自动化 | 全流程 AI Agent 编排 |
| 定价 | ¥100万+/套 | ¥50-200万/年工具链 | ¥0.6-9.8万/年 |
| 目标客户 | Tier 1 整车厂 | ECU 开发者/Tier 1 | Tier 2/中小团队 |
| 定位策略 | 高端硬件+咨询 | 工具链垄断 | 性价比+合规自动化 |

### 战略建议（已沉淀）
- P0: 颠覆路线 — AI 全自动流水线替代 Manual
- P1: 行业选择 — 先攻 Tier 2 / 中小企业
- P1: 插件市场 — 开放适配器生态
- P2: 寄生增长 — 与 Vector/dSPACE 互补

---

## 六、技术债务 (最新)

| 优先级 | 数量 | 示例 |
|:-------|:-----|:------|
| P0 (阻塞) | 4 | 覆盖基线配置失效 / evidence 模块碎片 / spec 版本声明 |
| P1 (重要) | 5 | store_pg 覆盖 <85% / ci/run 覆盖 / flash/ui 拆分 |
| P2 (建议) | 5 | E2E 集成测试 / ci 拆分 / 配置统一 |
| P3 (可选) | 4 | validate 拆分 / VS Code 扩展 / 认证体系 / SIL Kit |

---

## 七、当前项目状态 (2026-07-05)

### 系统状态
- 三名 AI Agent 均离线（上次活跃 ~06-29）
- 最新代码已推送到 GitHub
- 需确认：公司注册地址、基础设施部署区域
- CI Pipeline 可在 GitHub Actions 上运行

### 下一步方向（待决策）
1. **覆盖率攻坚**: 攻 `ci/kpi/` 和 `evidence/` 模块
2. **VS Code 扩展**: 提供更好的 IDE 集成
3. **认证体系**: ISO 26262 功能安全认证准备
4. **产品化**: 完善 SaaS Onboarding / Landing Page 优化
5. **AI Benchmark**: Agent 智能基准评测
