# 老陈专家评审 → 行动项提取报告

> **审查人**: 小马 🐴 (质量架构师)
> **基于**: 老陈专家评审报告 (2026-06-16) · yuleOSH v1.0.0 现有资产盘点
> **日期**: 2026-06-16
> **状态**: 待小明终审裁决

---

## 目录

- [A. 产品定位调整](#a-产品定位调整)
- [B. 定价策略重构](#b-定价策略重构)
- [C. ASPICE 合规检查清单](#c-aspice-合规检查清单)
- [D. 上市路径与质量准备](#d-上市路径与质量准备)
- [E. 开源版 vs 付费版分界线](#e-开源版-vs-付费版分界线)
- [F. 其他关键行动项](#f-其他关键行动项)
- [附录: 文档影响矩阵](#附录-文档影响矩阵)

---

## A. 产品定位调整

### A1: 产品叙事从"AI 嵌入式 DevOps 平台"改为"一站式 ASPICE 合规开发平台"

| 字段 | 内容 |
|:-----|:------|
| **老陈建议** | "AI 嵌入式 DevOps" 对目标受众（项目经理/质量经理/架构师）心智渗透力不够；应改为 **"一站式 A SPICE 合规开发平台"**，直击嵌入式团队"证据包通不过"的最大痛点。 |
| **当前评估** | 现有文档（spec-product-v1.md, pricing.html, README, startup-analysis.md, index.html）的定位语统一使用 "AI 嵌入式 DevOps 平台" 或类似表述。例如定价页 Hero 标题无明确定位语，index.html 和 README 使用"AI 驱动的嵌入式全生命周期平台"。**此定位已体现在基础能力中**（追溯矩阵、ASPICE 证据包、SHALL 全覆盖），但叙事出口（网站/README/营销物料）仍需要调整。 |
| **对齐建议** | **需要更新的文档清单**:
1. **README.md** — 首段定位语: 从"AI 嵌入式 DevOps 平台" → "一站式 ASPICE 合规开发平台"，副标题保留技术描述
2. **pricing.html** — Hero 区域 + 页面标题增加合规叙事
3. **index.html** — Hero/Value Proposition 重写
4. **spec-product-v1.md** — 顶层版本描述: 定位语更新，但 SHALL 条款不需要动（技术能力不变）
5. **site 其他营销页面** — 以及任何面向外部用户的 landing page
6. **yuleOSH-business-report.md** — 商业分析中的 Market Positioning 章节更新
7. **project-docs/startup-analysis.md** — S.U.P.E.R 分析的 Problem 段落精细化
**不需要动的文档**: RTM (acceptance-matrix-rtm.md)、spec.md (技术规范本体)、aspice-readiness-assessment.md（合规评估文档本身已使用 ASPICE 框架语言） |
| **优先级** | **P1** — 上市前必须完成（影响第一印象和转化率） |
| **影响范围** | 文档系统 (7 个文件) + 营销物料 + 社区传播 + 销售话术 |

---

### A2: 用户画像精细化 — 区分三类目标决策者

| 字段 | 内容 |
|:-----|:------|
| **老陈建议** | 真实用户不是"渴望现代化的嵌入式工程师"，而是三个独立角色：**项目经理/质量经理**（最怕证据包不过）→ **架构师**（关心工具链对接）→ **底层开发**（只管 QEMU 跑不跑得通）。现有定价/功能页面把所有人都当同一类人对待。 |
| **当前评估** | 定价页和 spec 没有区分用户画像分层。现有叙事偏向"开发者体验"，缺少"质量经理"角度的证据和管理叙事。 |
| **对齐建议** | 1. 在 landing page 增加 **"谁在使用 yuleOSH"** 三个人物画像卡片
2. 定价页 Pro/Enterprise 的描述文案分别面向工程负责人 vs 采购决策者
3. 营销内容准备三套角度: 质量经理（合规证据/追溯），架构师（集成/适配器），开发者（QEMU/CI）
4. spec-product-v1.md 的验收矩阵中增加场景关联的用户角色标签 |
| **优先级** | **P2** — 可在 P1 定位落地后迭代 |
| **影响范围** | 营销网站 + 定价页 + 社区内容策略 |

---

## B. 定价策略重构

### B1: Pro 档 ¥299 → ¥999/月

| 字段 | 内容 |
|:-----|:------|
| **老陈建议** | ¥299/月在汽车行业采购眼中 ≈ "个人爱好项目"。对比 Vector CANoe ¥5-15万 / dSPACE ¥30-80万，¥999/月 (≈$140) 仍是 1-5%，价格锚点合理。需配套增值能力: HIL 仿真配额 + 高级证据包 + ASPICE 模板库。 |
| **当前评估** | 当前定价页: Pro 显示 ¥299/月 (或 ¥2,999/年)。功能列表不含 HIL 仿真配额、不含 ASPICE 模板库。¥299 的 Pro 确实低于行业认知基线。**但需注意**: 团队账上烧钱窗口期可能短，¥299 的转化漏斗与 ¥999 可能有量级差异——需要测算价格弹性和转化预期（老陈提到 500 Free → 1 Pro 的心理准备）。 |
| **对齐建议** | **必须修改的资产**:
1. **pricing.html** — Pro 价格修改为 ¥999/月 (或 ¥9,999/年)，年付可保留 ¥9,999（约省17%），加上 "HIL 仿真配额" 和 "ASPICE 模板库" 作为升级理由
2. **yuleOSH-business-report.md** — 定价策略章节更新
3. **企业版商业方案** — 如有内部定价决策文档
**建议验证**: 在内部做一轮 A/B 测试（¥299 vs ¥999），看转换率预期。如果转化率下降超过 70%，需重新评估 |
| **优先级** | **P1** — 定价影响收入模型，上市前必须决策 |
| **影响范围** | SaaS 计费系统 + 定价页面 + 商业计划/投资人材料 + 销售材料 |

---

### B2: Enterprise 档增加 ¥298K/年 ASPICE 咨询服务包

| 字段 | 内容 |
|:-----|:------|
| **老陈建议** | ¥98K/年 → 在大企业采购安全感阈值之下。建议增加 "A SPICE 咨询服务包"，¥298K/年，含 2 次现场合规检查 + 证据包定制 + 一对一架构师支持——对比一个 ASPICE 咨询项目 30万起步，有竞争力。 |
| **当前评估** | 当前 Enterprise 档仅标注"定制/年"，功能列表不含咨询服务内容。无明确的咨询包定义。无服务交付 SLA 模板。 |
| **对齐建议** | 1. **pricing.html** — Enterprise 档增加两档: "Enterprise Base (¥98K/年)" + "Enterprise Plus (¥298K/年, 含咨询包)"
2. 定义咨询包的明确交付物: 2 次 on-site 合规检查 / 证据包定制 / 架构师对接 / 年度合规报告
3. 准备 **Enterprise SLA 模板**（目前无此文档）
4. 检查 Docker 私有化部署的对公能力: 人民币发票 / 增值税专票 / 年度合同
5. 准备 **人民币定价表** (满足中国整车厂/Tier 1 采购合规要求) |
| **优先级** | **P1** — 大企业 POC 阶段前必须准备好 |
| **影响范围** | 定价页面 + 合同模板 + 服务交付流程 + 技术支持团队配置 |

---

### B3: 中国汽车行业采购合规准备

| 字段 | 内容 |
|:-----|:------|
| **老陈建议** | 中国整车厂/Tier 1 不接受: 纯云 / 美元结算 / 月度订阅。必须支持: 私有化部署(Docker ✓) + 人民币发票 + 增值税专票 + 年度合同/买断选项 + 本地化合同模板。 |
| **当前评估** | 现有架构已支持 Docker 私有化部署 (Dockerfile, docker-compose.yml)。但: 无人民币定价表文档、无合同模板、无销售流程文档、无渠道商销售准备。Enterprise 档目前"联系销售"策略ok，但缺乏标准化的报价流程。 |
| **对齐建议** | 1. 准备 **"yuleOSH Enterprise 标准报价单"** (人民币, 含增值税) → 新文档
2. 准备 **本地化合同模板** (服务条款 / SLA / 数据保护) → 新文档
3. 调研是否需要代理/渠道商架构（dSPACE/Vector 渠道商模式）
4. 补充 **FAQ 页面**: 关于中国的部署模式 / 数据本地化 / 发票说明 |
| **优先级** | **P1** — 在大企业 POC 前必须就绪 |
| **影响范围** | 销售流程 + 合规/法务 + 财务 + 部署文档 |

---

## C. ASPICE 合规检查清单

### C1: 证据包引擎增加交互式 "ASPICE 合规检查清单"

| 字段 | 内容 |
|:-----|:------|
| **老陈建议** | 现有追溯矩阵和验收矩阵已有，但 A SPICE 不仅看"有文档"，还看"证据链合理性"。审核员会追问"为什么跳过了两层设计文档？"。建议在证据包里**按 SWE.1/SWE.2/SWE.3/SWE.4/SWE.5 自动勾选检查点**，告诉用户"你还差什么"。这个功能对质量经理比 AI pipeline 还值钱。 |
| **当前评估** | 现有资产:
- **aspice-readiness-assessment.md** — 已做了完整的 ASPICE 4.0 差距评估
- **acceptance-matrix-rtm.md** — SHALL 100% 覆盖, Deep Coverage 62.6%
- **spec.md** — 需求树已按 SYS→SW→Feature→Scenario→Task 结构化
- **spec-product-v1.md** — 已有验收矩阵
目前**缺乏**: 以下游视角驱动的检查清单（告诉用户按 ASPICE 4.0 PAM 的 BP 逐项自查"你还差什么"）。现有 evidence engine 生成的是"我有什么"，不是"你缺什么"。 |
| **对齐建议** | **强烈建议写入 spec**。在 spec-product-v1.md 中增加一个新模块:
- **REQ-ID: ASPICE-CHECK-001/002/...**
- The system SHALL provide an interactive ASPICE compliance checklist that maps evidence artifacts to SWE.1 through SWE.6 base practices
- The system SHALL flag gaps in the evidence chain (e.g., missing design document layer between requirement and test)
- The system SHALL output a gap report in the compliance evidence package
**需要更新的文档**:
1. **spec-product-v1.md** — 新增 ASPICE 检查清单模块 (SHALL 条款)
2. **acceptance-matrix-rtm.md** — 增加新模块的追踪行
3. **aspice-readiness-assessment.md** — 更新差距分析: 从"有证据包"到"能指导用户补缺"
4. **pricing.html** — Pro 功能列表增加这一项作为增值理由 |
| **优先级** | **P1** — 差异化竞争力核心，quality manager 购买关键决策因素 |
| **影响范围** | spec + evidence engine 代码 + ASPICE 评估文档 + 功能对比表 |

---

### C2: AI 生成结果的可解释性要求

| 字段 | 内容 |
|:-----|:------|
| **老陈建议** | A SPICE 审核员最不吃"不确定性"。AI 生成测试用例 → 审核员追问"覆盖逻辑是什么"→ AI 必须给出可追溯推理路径。现有 10 步 Pipeline 架构对，但需要确保每次生成有"为什么这么设计"的文本解释。 |
| **当前评估** | 现有 spec (RS-001/SWR-001) 要求 "map every SHALL to test case"，但未要求 AI Agent 输出推理路径文档。review engine 有 JSON 存档，但非面向审核员的可读推理路径。 |
| **对齐建议** | 1. 在 spec 中增加: "The system SHALL generate a human-readable reasoning trail for each AI-generated artifact, including coverage rationale per test case"
2. 建议走 **TCL2/TCL3 置信度评估**路径：ISO 26262-8 §8 要求工具本身可验证；建议拿真实的生成结果给 ASPICE 审核员看一次
3. 在 evidence engine 中增加 **"AI Reasoning Appendix"** 作为证据包的可选组件 |
| **优先级** | **P2** — 大企业 POC 之前需要完成 |
| **影响范围** | AI pipeline 输出格式 + evidence engine + spec 条款 + ASPICE 置信度文档 |

---

## D. 上市路径与质量准备

### D1: 三阶段上市路径 — 质量就绪度评估

| 阶段 | 老陈建议 | 当前质量准备状态 | 差距 | 建议行动 | 优先级 |
|:-----|:---------|:----------------|:----|:---------|:------|
| **🟢 Phase 1 (0-3月)** 初创/小团队 → 30 付费 Pro | GitHub Discussion + Discord + RISC-V 社区 + r/embedded | ✅ README 已含 MIT 开源 + GitHub Actions CI ✅ Dockerfile/docker-compose 可用 ❌ 无社区讨论区管道 (Discord/GitHub Discussion 未搭建) ❌ 无公开的 Demo 流程（5 分钟的 wow moment） | 缺社区运营基座 缺"哇"的 Demo | **P1**: 搭建 Discord/GitHub Discussion **P1**: 开发 Demo 流程（刹车灯用例，5分钟 Spec→ZIP） | **P1** |
| **🟡 Phase 2 (3-6月)** 中小 Tier 1 → 5 年付 Enterprise | 打 "ASPICE 合规 + 证据包 + TÜV/SGS/DEKRA 联合营销 + 免费合规评估报告" | ✅ aspice-readiness-assessment.md 已完整 ✅ acceptance-matrix-rtm.md 有追溯 ✅ pricing 页面含 Pro/Enterprise ❌ 无认证机构合作关系 ❌ 无免费合规评估工具 | 缺行业认证背书 缺 reference case | **P1**: 准备 3 个 reference case **P2**: 联络 TÜV/SGS/DEKRA 做联合营销 **P2**: 开发免费 ASPICE 合规评估功能 | **P1-P2** |
| **🔴 Phase 3 (6-12月)** 大企业 POC → 2-3 个试点 | 卖"ASPICE 合规升级辅助"非全量平台 + 14 天 POC 包 + 前三个免费但要 case study | ❌ 无 POC 流程文档 ❌ 无标准化 onboarding 流程 ❌ 无 Enterprise SLA 模板 ❌ HIL 深度不足 (Restbus/Fault Injection/Real-time IO) ❌ 无中大型 Tier 1 销售话术 | 大企业入场门槛高 | **P1**: 准备 Enterprise POC Kit（部署 + 集成 + SLA） **P2**: HIL 策略: 与 NI/dSPACE MiniBox 合作而非自研硬件 **P2**: 准备销售话术/竞品对决表 | **P1-P2** |

---

### D2: 销售周期风险 — 现金流预判

| 字段 | 内容 |
|:-----|:------|
| **老陈建议** | 大企业 POC 3-6 月 → 签合同再 3-6 月 → 回款 45-90 天。如果账上只够 12 个月，Sales 窗口可能比想象中短。建议先做高转化 Pro 用户 (500-1000) 再做 Enterprise (10-20)。 |
| **当前评估** | 现有商业报告 (business-report.md) 有市场分析但未做销售周期 vs 现金流压力测试。 |
| **对齐建议** | 1. 在 business-report.md 增加 **现金流压力测试章节**: 不同定价策略下的烧钱速率 vs 获客速度
2. 制定 **2-track 并行策略**: Track A 快速铺 Pro（自助转化，0 销售成本）Track B 铺 Enterprise（销售驱动，长周期）
3. 准备 **投资人/董事会报告** 的 KPI 框架: 月活 Pro 数 / Enterprise POC pipeline / MRR 增长率 |
| **优先级** | **P1** — 关系团队生存，需要立刻做财务模型 |
| **影响范围** | 商业计划 + 资金规划 + 团队配置优先级 |

---

### D3: Demo/"Wow Moment" 交付

| 字段 | 内容 |
|:-----|:------|
| **老陈建议** | 第一优先级不是画饼，而是**5 分钟交互式 Demo**: 用户输入"刹车灯 CAN 信号需求"→ AI 自动生成需求文档 / 架构设计 / 单元测试 / CI 执行 / 一键 ASPICE 证据包 ZIP。关键: 整个过程 ≤5 分钟，用户拿到 ZIP 的瞬间说"卧槽"。 |
| **当前评估** | 现有 pipeline 在 CLI 层面可运行，但缺少端到端的 SaaS Try-it Demo 页面。spec-product-v1.md 的模块 2 (SaaS Try-it Demo) 已规划但未完成完整实现。 |
| **对齐建议** | 1. **spec-product-v1.md 模块 2 (SaaS Try-it Demo)** 优先级提到 P1
2. Demo 流程必须是 **零配置"刹车灯"预设模板**，不要让用户配置
3. 证据包 ZIP 的下载按钮要做最显著的 CTA
4. 录制 2 分钟 screen recording 作为备用素材
5. 将此 Demo 嵌入: README / landing page / 社区帖子 |
| **优先级** | **P1** — Phase 1 获客的关键武器 |
| **影响范围** | frontend/ SaaS Try-it 实现 + CI pipeline + evidence engine + 营销页面 |

---

### D4: 竞争对决 — 公开对比数据

| 字段 | 内容 |
|:-----|:------|
| **老陈建议** | 用同一需求（雨刮控制）在 yuleOSH / BootLoop / 手动流程 三个路径跑，记录: 总时间 / 人工干预量 / 可追溯性 / ASPICE 合规评分。公开对比数据。 |
| **当前评估** | 未做此对比。无公开 benchmark 数据。 |
| **对齐建议** | 1. 在 Phase 1 (0-3月) 内完成此项对比
2. 产出: 1 页对比表格 + 2 分钟 screen recording
3. 在 GitHub 和社区发帖公开
4. 建议内部也跑 **yuleOSH vs 纯手动流程** 的对比（合规时间缩短百分比是核心指标） |
| **优先级** | **P2** — 社区信任建设的关键杠杆 |
| **影响范围** | 社区内容 + 销售材料 + Reference page |

---

## E. 开源版 vs 付费版分界线

### E1: 社区版 / SaaS / Enterprise 功能矩阵明确定义

| 字段 | 内容 |
|:-----|:------|
| **老陈建议** | MIT 许可证是双刃剑: 社区可 fork 贡献建立信任，但大企业会问"开源了为什么还要付费"。需要清晰界定: **开源版 = 基础 pipeline + QEMU SIL** / **SaaS 版 = 多租户 + 插件市场 + 高级证据包** / **Enterprise 版 = 私有化 + HIL 适配器 + SLA + 咨询**。当前分界线不够清晰。 |
| **当前评估** | 当前 pricing.html 的对比表已有三层区分，但:
- Free 档有基础 pipeline + 1 项目 + 3 用户 + 30 pipeline/月——这与"开源版自托管"之间的关系不清晰
- Pro 档含 Docker 自托管部署 —— 但开源版也可以 Docker 自托管
- Enterprise 档含 "HIL 适配器" 但未在对比表中单独列出
**问题**: 用户分不清"我自托管开源版"和"我买 Enterprise"的区别。 |
| **对齐建议** | 建议重新定义分层:
```
┌──────────────────────────────────────────────────────────────┐
│                     yuleOSH 功能分层                          │
├─────────────┬──────────────┬────────────────┬────────────────┤
│             开源社区版     │   SaaS Pro      │  Enterprise    │
│             (MIT)         │   (¥999/月)     │  (¥98K~298K/年)│
├─────────────┼──────────────┼────────────────┼────────────────┤
│ Pipeline    │ ✅ 基础 + QEMU│ ✅ 完整 + HIL   │ ✅ 完整        │
│ OpenSpec    │ ✅            │ ✅              │ ✅             │
│ CI/CD       │ Layer 1-3    │ ✅ 完整         │ ✅ 完整 + 定制  │
│ Evidence    │ 基础追溯矩阵  │ ✅ 高级证据包    │ ✅ 定制证据包   │
│ ASPICE审计   │ —            │ ✅ 检查清单      │ ✅ 检查清单+报告 │
│ 多租户       │ —            │ ✅              │ ✅             │
│ 插件市场     │ —            │ ✅              │ ✅             │
│ 自托管       │ ✅ Docker    │ ✅ Docker       │ ✅ Helm K8s    │
│ HIL 适配器   │ —            │ 有限配额         │ ✅ 无限         │
│ SLA          │ 社区         │ 邮件支持         │ 专属经理 + SLA  │
│ 咨询包       │ —            │ —               │ ✅ ¥298K       │
└─────────────┴──────────────┴────────────────┴────────────────┘
```
**具体行动**:
1. **pricing.html** — 增加第四列"开源社区版 (Free)"，把"自托管"划给开源版，Pro 版强调 SaaS 增值（多租户/插件市场/高级证据包）
2. **README.md** — 在"如何开始"部分增加清晰的能力矩阵
3. 确认 **MIT 开源版** 不包含: 多租户、HIL 适配器、ASPICE 检查清单、插件市场
4. 在 GitHub 仓库增加 **"付费版 vs 开源版" FAQ**
5. spec-product-v1.md 中体现分层能力约束 |
| **优先级** | **P1** — 消除免费用户困惑，避免开源版吃掉付费转化 |
| **影响范围** | pricing.html + README + GitHub repo + spec-product-v1.md + 社区 FAQ |

---

## F. 其他关键行动项

### F1: HIL 集成策略 — 不做硬件，做编排层

| 字段 | 内容 |
|:-----|:------|
| **老陈建议** | HIL 是 yuleOSH 最大风险点之一。当前 QEMU SIL 在功能验证够用，但集成测试需要真实 IO 板卡。**不要自己做 HIL 硬件**。和 NI / dSPACE MiniBox 合作，让 yuleOSH 作为测试编排层。 |
| **当前评估** | 现有 HIL 能力: 通过 Vector CANoe 适配器打通通信接口，但有明显深度不足。缺少 Restbus 仿真 / Fault Injection / Real-time IO / 程控电源 / 负载仿真。 |
| **对齐建议** | 1. 在 **architecture.md** 中明确 HIL 策略: yuleOSH 不做硬件，做编排层
2. 在 **spec-product-v1.md** 中增加 HIL 编排层的 SHALL 需求
3. 启动合作伙伴调研: NI / dSPACE MiniBox / Vector 的集成接口
4. 在 **aspice-readiness-assessment.md** 中更新 HIL 差距分析 |
| **优先级** | **P2** — Phase 2 之前需要确定策略 |
| **影响范围** | 架构文档 + spec + 合作伙伴关系 + 销售物料 |

---

### F2: Reference Case 准备 — 找 3 个"ASPICE 受害者"

| 字段 | 内容 |
|:-----|:------|
| **老陈建议** | 找 3 家小公司，以 ¥5,000（或免费）帮他们补 ASPICE 证据包。产出: 1 页 case study PDF + 2 分钟 screen recording + 公开技术博客。 |
| **当前评估** | 当前无 reference case，无 testimonial，无公开案例研究。 |
| **对齐建议** | 1. 在 Phase 1 启动时立刻寻找 3 家愿意的初创团队
2. 准备 **"ASPICE 证据包免费补"招募帖**（GitHub / 社区 / 微信群）
3. 模板化 case study 产出: PDF + video + blog
4. 签署 **case study 授权协议**（允许公开结果） |
| **优先级** | **P1** — Phase 2 销售时需要 |
| **影响范围** | 销售材料 + 社区内容 + 网站案例页 |

---

### F3: 社区攻占 — 垂直论坛发帖

| 字段 | 内容 |
|:-----|:------|
| **老陈建议** | 在 EEVblog / Hackaday / 嵌入式开发社区 / RISC-V 中文社区发帖。标题建议: "我写了一个开源工具链，一键生成 ASPICE 合规证据包，顺便帮你写代码和测试"。 |
| **当前评估** | 当前无社区运营计划文档。 |
| **对齐建议** | 1. 在 Phase 1 内发布 1-2 篇高质量长文（带 Demo 截图 + MIT 链接 + 免费 Pro 钩子）
2. 准备可复用的帖子模板（中文/英文两版）
3. 在 sprint 计划中加入"社区运营"任务项 |
| **优先级** | **P2** — Phase 1 中持续进行 |
| **影响范围** | 社区运营 + 内容创作 |

---

### F4: 竞品对决 Benchmark 数据

| 字段 | 内容 |
|:-----|:------|
| **老陈建议** | 用"雨刮控制"需求在 yuleOSH / BootLoop / 手动流程 三路径跑对比，公开数据。 |
| **当前评估** | 未做。无对比数据。 |
| **对齐建议** | 1. 在 sprint 计划中加入此项任务
2. 核心指标: 总时间 / 人工干预步数 / 追溯完整性 / ASPICE BP 覆盖率
3. 产出: 公开博客 + 对比表 + video |
| **优先级** | **P2** |
| **影响范围** | 营销内容 + 销售材料 + 社区信任 |

---

## 附录: 文档影响矩阵

以下矩阵显示每个行动项影响哪些现有文档，以及是否需要创建新文档。

### 需要修改的现有文档

| 文档 | 行动项 |
|:-----|:-------|
| **README.md** | A1(定位语) · E1(能力矩阵) |
| **pricing.html** | A1(定位语) · A2(画像文案) · B1(Pro价格) · B2(Enterprise咨询包) · B3(中国采购FAQ) · C1(检查清单功能) · E1(分层矩阵) |
| **index.html** | A1(定位语) · A2(用户画像卡片) · D3(Demo嵌入) |
| **spec-product-v1.md** | A1(版本描述) · A2(场景角色标签) · C1(新增检查清单模块) · C2(AI推理路径) · E1(分层约束) · F1(HIL编排) |
| **yuleOSH-business-report.md** | A1(定位调整) · B1(定价策略) · D2(现金流压力测试) |
| **aspice-readiness-assessment.md** | C1(检查清单差距更新) · F1(HIL差距更新) |
| **acceptance-matrix-rtm.md** | C1(新增模块的追踪行) |
| **architecture.md** | F1(HIL策略声明) |
| **project-docs/startup-analysis.md** | A1(定位语精细化) |

### 需要新建的文档/资产

| 新资产 | 行动项 | 说明 |
|:-------|:-------|:------|
| Enterprise SLA 模板 | B2 · D1 | 服务级别协议标准文档 |
| 人民币定价表 | B3 | 面向中国市场 |
| 本地化合同模板 | B3 | 服务条款 / 数据保护 |
| Enterprise POC Kit | D1 | 部署 + 集成 + 14 天流程文档 |
| 现金流压力测试模型 | D2 | 内部财务分析 |
| Case Study 模板 | F2 | PDF + video + blog 模板 |
| Case Study 授权协议 | F2 | 客户授权法律文书 |
| 社区发帖模板 | F3 | 中文/英文两版 |

---

## 优先级汇总

| 优先级 | 行动项数 | 关键依赖 |
|:------|:--------|:---------|
| **P1** (必须做) | 11 | A1, A2*部分, B1, B2, B3, C1, D1, D2, D3, E1, F2 — 其中 B1/B3/D2 需要外部输入（财务/法务） |
| **P2** (争取做) | 5 | C2, D4, F1, F3, F4 — 可在 Phase 2 对齐 |

**P1 项的关键风险**:
- **B1/B2 定价** 需要小明终审 + 财务测算
- **B3 中国采购合规** 需要法务/税务确认
- **D2 现金流模型** 需要团队账上数据
- **F2 Reference Case** 需要外部客户配合

---

*— 小马 🐴 质量架构师*
*2026-06-16 · 基于老陈专家评审报告 v1.0*
