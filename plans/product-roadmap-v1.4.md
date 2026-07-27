# yuleOSH 产品路线图 v1.4 → v2.0

> **愿景**: AI 驱动的 AUTOSAR 量产开发平台 — 让嵌入式团队在 SaaS 上一天完成从需求到验证
>
> **核心价值**: 对标 Vector MICROSAR + dSPACE + Polarion 的工具链，用 5% 的成本 + AI 自动化 + 闭环质量体系，让中国 Tier-2/创业公司能快速量产合规的 AUTOSAR ECU

---

## 一、现状基线 (v3.2.1 / CL3)

### ✅ 已完成

| 领域 | 能力 | 成熟度 |
|:-----|:-----|:------:|
| Pipeline | CI L1/L2/L3 + 检查点引擎 | CL3 88/100 |
| MISRA | 规则库 185条 + 自动检查 + 偏差管理 | Required 清零 |
| ASPICE | SWE.1~SWE.6 追溯 + 证据链 | AL1+ |
| ISO 26262 | HARA / DFA / FMEDA / FSR / TSR | 文档全覆盖 |
| Safety | ASIL B 分解 + MPU 分区 + 工具链限制 | 文档就绪 |
| Dashboard | SaaS 仪表盘 v2.0 (Landing/Doc/Pricing/Login) | 在线可访 |
| Loop Eng | 四个闭环 (缺陷→需求 / 现场→FMEA / KPI→RCA / KG自进化) | 首创 |
| LLM Agent | 小克+小马 双 Agent 自动编排 | 实战验证 |
| MockHAL | 内存注册表替代硬件寄存器，macOS 可测 MCAL | 新 |
| yuleASR BSW | MCAL 9/9 模块可编译，部分 70%+ 覆盖 | 推进中 |
| BSW 模块 | MCAL 21 + ECUAL 29 + Services 44 模块结构 | 框架就绪 |

### ❌ 明确不做的 (P0，当前有挑战)

| 项目 | 原因 | 替代方案 |
|:-----|:------|:---------|
| Linux GCC CI 容器化 | 需要 Docker + Ubuntu CI Runner 基础设施 | MockHAL 补偿 macOS 侧测试 |
| HIL/SIL 硬件在环 | 需要 dSPACE SCALEXIO 或同等硬件 | 软模拟 + MockHAL 做 CI 级验证 |
| 多架构支持 (>S32K312) | 需要多块开发板 + 交叉工具链矩阵 | 架构抽象层 + CMake 条件编译 |
| 实时 OS (FreeRTOS/OSEK) | 与 AUTOSAR OS 深度绑定 | 现有 SchM/Os 模块框架可用 |

---

## 二、Phase 1: P1 项目 (预计 3-4 周)

### ▸ P1-1: yuleASR ARXML→RTE 生成完整化 (2周)

**目标**: 从「手写 BSW 代码」到「ARXML 配置驱动代码生成」

#### 现状
- yuleASR-Configurator v0.2.3 已存在（React 19 + TypeScript）
- 支持 CAN/ADC/MCU/DEM/DCM 等 10+ BSW 模块的 Web 配置界面
- 已生成 ARXML 解析 + C 代码生成 + 配置验证

#### 需要完成的

| # | 工作项 | 产出 | 估时 |
|:-:|:-------|:-----|:----:|
| RTE-1 | ARXML→RTE C 代码生成器（SWC 框架代码） | `tools/code_generators/rte/` | 3d |
| RTE-2 | RTE 生成器接入 yuleOSH pipeline stage | `stages/rte_generation.py` | 1d |
| RTE-3 | 从 yuleASR-Configurator 输出直接驱动 RTE 生成 | 端到端 ARXML→编译通过 | 2d |
| RTE-4 | 生成代码的 MISRA 合规检查 | pipeline RTE stage 加 MISRA check | 1d |
| RTE-5 | 模板 SWC 示例（BCM 门控/灯光/雨刮/电源） | `templates/bcm/` | 3d |
| RTE-6 | 文档: RTE 工作流 + 配置方法 | `docs/workflows/rte-workflow.md` | 1d |

**验收标准**: 一个 BCM Demo，从 yuleASR-Configurator 配置 → ARXML → RTE 生成 → 编译零错误 → MISRA check 通过

#### 路径
```
yuleASR-Configurator (Web UI)
        ↓ ARXML
yuleOSH ARXML Parser 
        ↓ Internal IR
RTE Code Generator
        ↓ .c/.h
yuleOSH CI Compile + MISRA Check
        ↓ ✅
BCM SWC + BSW 完整可编译
```

---

### ▸ P1-2: ISO 26262 TCL 工具认证文档 (1周)

**目标**: 让客户采购决策时能认可 yuleOSH 的「工具可信度」

#### 核心内容

| # | 工作项 | 产出 | 估时 |
|:-:|:-------|:-----|:----:|
| TCL-1 | 工具分类：yuleOSH 各 stage 的 TCL (Tool Confidence Level) 评估 | `docs/safety/tcl-assessment.md` | 1d |
| TCL-2 | 每个 pipeline stage 的故障检测覆盖率 | 矩阵表：stage → 可检测故障 → 覆盖率% | 1d |
| TCL-3 | 证据链可信度论证 | 证据数据来源→处理→存储→呈现，各环节可信度分析 | 1d |
| TCL-4 | 工具限制定期评估流程 | 每个 Release 前重新评估 | 0.5d |
| TCL-5 | 第三方工具依赖分析 (cppcheck/lcov/gcovr) | 每个工具版本 + 已知限制 | 0.5d |

**为什么重要**: 
- 不提供 TCL 文档，ISO 26262 审核员直接判不合格
- Vector 的 MICROSAR 通过 AUTOSAR PP+ 认证，天然有 TCL
- yuleOSH 需要自己补这个文档才能进入量产供应链

**验收标准**: 
- 所有 8 个 pipeline stage 的 TCL 评估完成
- 证据链的故障覆盖矩阵 ≥ 90%
- 文档可以提交给 ISO 26262 审核员

---

### ▸ P1-3: yuleASR-Configurator Pipeline 集成 (1周)

**目标**: 配置工具 → pipeline 一键触发

| # | 工作项 | 产出 | 估时 |
|:-:|:-------|:-----|:----:|
| CFG-1 | Configurator 导出配置→yuleOSH pipeline 触发 | API endpoint `/pipeline/trigger` | 2d |
| CFG-2 | pipeline 运行状态→Configurator 回显 | WebSocket 实时状态 | 1d |
| CFG-3 | 配置验证规则自动检查 | `yuleosh validate-config` CLI | 1d |
| CFG-4 | 多模块并行配置导出支持 | 批量配置 API | 1d |

**验收标准**: 
- yuleASR-Configurator 上配置完 → 点按钮 → pipeline 自动跑完
- 状态实时回显到 Web 界面

---

## 三、Phase 2: P2 项目 (预计 3-4 周)

### ▸ P2-1: 量产模板库 + 一键启动 (2周)

**目标**: 新项目从「配置 1 周」到「配置 1 小时」

#### 预置模板

| 模板 | 适用场景 | MCU | ASIL | BSW 模块数 |
|:-----|:---------|:----|:----:|:----------:|
| BCM (车身控制器) | 门控/灯光/雨刮/电源 | S32K312 | QM~ASIL B | 8~12 |
| DCU (域控制器) | 区域网关/车身域 | S32K344 | ASIL B | 15~20 |
| VCU (整车控制器) | 动力域/扭矩管理 | S32K324 | ASIL C~D | 12~18 |
| BMS (电池管理) | 电池监控/均衡 | S32K314 | ASIL C~D | 10~15 |
| EPS (电动助力转向) | 转向控制 | S32K312 | ASIL D | 8~10 |

| # | 工作项 | 产出 | 估时 |
|:-:|:-------|:-----|:----:|
| TPL-1 | 模板引擎 CLI: `yuleosh init --template bcm` | CLI 子命令 + 模板加载器 | 2d |
| TPL-2 | BCM 全模板（Spec/Safety/CI/Config） | `templates/bcm/*` | 2d |
| TPL-3 | DCU 全模板 | `templates/dcu/*` | 2d |
| TPL-4 | 模板参数化（MCU/ASIL/通信协议可配置） | Jinja2 模板变量系统 | 1d |
| TPL-5 | 模板文档 + 快速入门指南 | `docs/templates/` | 1d |

#### 一键启动流程
```
yuleosh init --template bcm --mcu S32K312 --asil B
  → 创建项目目录
  → 生成 spec.md（预置 SHALL）
  → 生成 safety-concept.md（预置 HARA）
  → 生成 ci-config.yaml（预置 gate）
  → 生成 .yuleosh/（预置 pipeline config）
  → git init + first commit
  → yuleosh ci run 1 自动触发生成验证
```

**验收标准**: 30 秒内完成 `yuleosh init --template bcm` → `yuleosh ci run 1` 全绿

---

### ▸ P2-2: Loop Engineering 产品化 (1.5周)

| # | 工作项 | 产出 | 估时 |
|:-:|:-------|:-----|:----:|
| LPE-1 | Dashboad Loop 1 可视化（缺陷→需求回溯轨迹） | UI Widget | 2d |
| LPE-2 | Dashboad Loop 2 可视化（现场→FMEA 影响链） | UI Widget | 2d |
| LPE-3 | Dashboad Loop 3 可视化（KPI→RCA→改进闭环率） | UI Widget + 趋势图 | 2d |
| LPE-4 | Loop 4 KG 自进化 Dashboard（置信度趋势） | UI Widget | 1d |
| LPE-5 | EventBus 持久化 + 重放（生产级可靠性） | PostgreSQL/Redis backend | 2d |

**验收标准**: Dashboard 上 4 个 Loop Widget 可交互查看 → 点击可追溯源头

---

### ▸ P2-3: VS Code 扩展 (2周)

| # | 工作项 | 产出 | 估时 |
|:-:|:-------|:-----|:----:|
| VSC-1 | 扩展脚手架 + yuleosh CLI 集成 | `.vscode/` | 1d |
| VSC-2 | 内嵌 MISRA 违规标注（诊断+快速修复） | Language Server Protocol | 3d |
| VSC-3 | 内嵌 Pipeline 状态面板 | Tree View | 2d |
| VSC-4 | 内嵌证据链预览 | WebView | 2d |
| VSC-5 | 一键 `yuleosh init` + `ci run` 按钮 | Status Bar | 1d |
| VSC-6 | 发布到 VS Code Marketplace | 市场发布 | 1d |

**验收标准**: 编辑器内就能看到 MISRA 红线、Pipeline 进度、一键跑 CI

---

### ▸ P2-4: SaaS 多租户 + 团队协作 (1.5周)

| # | 工作项 | 产出 | 估时 |
|:-:|:-------|:-----|:----:|
| SAAS-1 | 多租户数据隔离（Project → Org 层级） | 数据库 schema 重构 | 2d |
| SAAS-2 | 角色权限模型（Admin/Developer/Reviewer/Auditor） | RBAC + middleware | 1d |
| SAAS-3 | 项目管理看板（Kanban: 需求→开发→审查→测试→发布） | Dashboard 新页面 | 2d |
| SAAS-4 | 审计日志（谁在什么时候做了什么） | Event sourcing | 1d |
| SAAS-5 | 用量计量 API → Stripe 计费 | Metered billing | 2d |

**验收标准**: 3 人团队各自登录 → 同一项目多角色协作 → 有完整审计足迹

---

### ▸ P2-5: 竞品对标功能补齐 (1周)

来自 6 月 12 日 dSPACE/Vector 对标分析的未完成项：

| # | 功能 | 对标 | 估时 |
|:-:|:-----|:-----|:----:|
| CMP-1 | 需求管理看板（类 Vector PREEvision） | 需求条目/版本/状态/变更历史 | 2d |
| CMP-2 | 测试用例管理库（复用、参数化、回归选择） | 测试分类/标签/历史结果 | 2d |
| CMP-3 | 集成 3rd-party 工具（Jira/Polarion/GitLab） | 通过 EventBus 插件式接入 | 1d |
| CMP-4 | 自动生成客户审计报告（ASPICE 维度） | PDF/HTML 报告模板 | 1d |

---

## 四、Phase 3: 中长期愿景 (P3+，不可承诺时间)

| 项目 | 描述 | 战略价值 |
|:-----|:------|:---------|
| AI 自动 MISRA 修复 | LLM 分析违规根因 → 自动出 diff → 人工确认 | 核心竞争力 |
| AI 测试用例生成 | 从 SHALL 需求自动生成 GIVEN/WHEN/THEN 测试 | 核心竞争力 |
| 智能仿真评估 | MockHAL → Virtual ECU → 自动生成覆盖率报告 | 对标 dSPACE |
| 认证体系 | ISO 26262 TCL 证书 + ASPICE AL3 预评估 | 市场信任 |
| 插件市场 | 第三方开发者可上架 tools/stages/templates | 生态护城河 |
| 开源 Core | Pipeline 引擎开源，企业版收费 | 流量入口 |
| AI Benchmark | Pipeline 效率基线（对比纯手动流程） | 销售工具 |

---

## 五、竞品定位矩阵

```
                   高端完整
                      ↑
            Vector MICROSAR ●
                           dSPACE SCALEXIO ●
                                     ● EB tresos
                       ● Polarion ALM
          ● Azure DevOps
                      ● GitLab
                      ● Qt Axivion
    投入多 ←—————————————→ 投入少
                      ● yuleOSH (目标位)
                      ● yuleOSH (当前位)
                      ↓
                    轻量快速
```

### yuleOSH 差异化定位

| 维度 | 竞品痛點 | yuleOSH 解法 |
|:-----|:---------|:-------------|
| 价格 | Vector 单 seat €15~50K/年 | 开源 Core + SaaS 免费层 |
| 上手 | Polarion/GitLab 配置以月计 | `yuleosh init --template` 30秒 |
| MISRA 修复 | Axivion 只报错不修 | yuleOSH Agent 自动修/偏差 |
| 质量闭环 | 竞品都是被动工具链 | Loop Engineering 主动闭环 |
| ASPICE 合规 | 需要外部咨询师 + 数月准备 | Pipeline 内置证据链，一键生成审计报告 |
| AI 集成 | 所有竞品都没有 LLM agent | 小克+小马 实战已验证 |

---

## 六、版本规划与时间线

```
v1.3.0 ─── v1.4.0 ─── v1.5.0 ─── v1.6.0 ─── v2.0.0
 (今天)    (2周后)    (4周后)    (6周后)    (8周后)
   │          │          │          │          │
   │    P1-1 RTE生成    P2-1 模板库  P2-3 VS Code  P2-4 多租户
   │    P1-2 TCL文档    P2-2 Loop UI  P2-5 对标补齐  P2-4 计费系统
   │    P1-3 Config集成 ───────────────┘          P2-4 审计日志
   └────────────────────────────────────────────────── 全功能 GA
```

### 里程碑

| 版本 | 时间 | 关键交付 | 目标用户 |
|:-----|:----:|:---------|:---------|
| v1.4.0 | T+2周 | RTE 生成 + TCL 文档 + Config 集成 | 内部/种子用户 |
| v1.5.0 | T+4周 | 量产模板 + Loop Dashboard | 早期试用客户 |
| v1.6.0 | T+6周 | VS Code + 竞品对标补齐 | Beta 客户 |
| v2.0.0 | T+8周 | SaaS 多租户 + 计费 + 审计 | GA 发布 |

---

## 七、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|:-----|:----:|:----:|:---------|
| ARXML→RTE 生成器复杂度超预期 | 🟡 中 | 🔴 高 | 先支持 BCM 子集，逐步扩展其他模板 |
| TCL 认证文档不被审核员接受 | 🟢 低 | 🟡 中 | 咨询老陈做预评审 |
| yuleASR-Configurator 与 yuleOSH 对接 API 不兼容 | 🟡 中 | 🔴 高 | 先做独立 CI stage 验证，不做深度集成，逐步对接 |
| 模板覆盖面不够广 | 🟢 低 | 🟢 低 | 模板参数化 + 用户可自行扩展 |
| VS Code LSP MISRA 标注延迟 | 🟡 中 | 🟢 低 | 先做简单的 CLI 集成，LSP 放 P3 |

---

> **一句话总结**: yuleOSH v1.4 路线图 = RTE 生成 (从手写变自动) + TCL 认证 (让客户敢买) + 模板库 (从1周变30秒) → 让中国 Tier-2/创业公司能用 5% 成本做到 Vector MICROSAR 80% 的能力。
