# yuleOSH 定位语统一变更记录

> **编制**: 小马 🐴（质量架构师）
> **日期**: 2026-06-19
> **决策依据**: 定价折中路线（B1 ¥599/月 + B2 暂不做咨询包 + B3 独立部署/人民币）
> **参考来源**: `reports/pricing-decision-pack.md`、`reports/expert-assessment-lao-chen.md`（老陈审查）

---

## 核心定位（全局统一）

> **一站式 ASPICE 合规开发平台**

旧定位: "AI-Powered Embedded Development Pipeline" / "嵌入式AI开发全流程自动化平台"
新定位: **"一站式 ASPICE 合规开发平台"**

变更理由:
1. 老陈指出 "ASPICE 合规" 的承诺风险，建议改为 "合规辅助工具" / "合规证据包自动生成"
2. 折中方案定位为 **"一站式 ASPICE 合规开发平台"**——强调是辅助工具、平台能力，而非替代审计
3. 英文保留 "ASPICE-compliant embedded development platform"，加注 "assistance tool"

---

## 各文件变更明细

### 1. README.md

| 区域 | 变更内容 |
|:-----|:---------|
| H1 副标题 | 英文: `AI-Powered Embedded Development Pipeline` → `ASPICE-compliant development platform` 保持 |
| H1 副标题第三行 | 新增 "合规辅助工具" 标签 |
| Pricing & Editions 表格 | Pro: ¥999/月(¥9,999/年) → **¥599/月(¥5,999/年)** |
| Pricing & Editions 表格 | Enterprise: ¥99,800/yr+ → **¥98,000/yr** |
| Pricing & Editions 表格 | "Enterprise + ASPICE consulting" 行删除 |
| 中文版 "定价与版本" | Pro: ¥999/月(¥9,999/年) → **¥599/月(¥5,999/年)** |
| 中文版 "定价与版本" | Enterprise: ¥99,800/年起 → **¥98,000/年** |
| 底部 tagline | 增加 "ASPICE 合规辅助 · 证据包自动生成" |

### 2. pricing.html

| 区域 | 变更内容 |
|:-----|:---------|
| Hero 区标题 | `简单透明的定价` → `简单透明的定价 · ASPICE 合规辅助工具` |
| Hero 区副标题 | 增加合规叙事 |
| Pro 卡片价格 | ¥299/月 → **¥599/月** |
| Pro 卡片年付 | ¥2,999/年(省17%) → **¥5,999/年(省¥1,189)** |
| Pro 卡片描述 | `专业开发者·小团队` → `专业开发者·合规团队` |
| Enterprise 卡片价格 | `定制` → **¥98,000** |
| Enterprise 卡片描述 | `中大型企业·组织级部署` → `中大型企业·私有化部署` |
| Enterprise 功能列表 | 新增: "人民币合同模板 · 支持对公转账" |
| Free vs Pro vs Enterprise 对比表 | Pro 价格列更新 |

### 3. index.html

| 区域 | 变更内容 |
|:-----|:---------|
| Hero 区 H1 | `嵌入式AI开发全流程自动化平台` → H1 第一行 `一站式 ASPICE 合规开发`，第二行 `全流程自动化平台` |
| Hero 区副标题 | 增加合规叙事文字 |
| "Quick stats" 区 | 新增 "ASPICE 合规包" 指标 |
| Pricing Preview 区 Pro | ¥199/月 → **¥599/月** |
| Pricing Preview 区 Pro 功能 | 增加 "ASPICE 合规辅助" |
| Pricing Preview 区 Enterprise | `定制` → **¥98,000** |
| Features 区 | Feature #5 描述增强合规叙事 |

### 4. docs/pricing.md

| 区域 | 变更内容 |
|:-----|:---------|
| 首页简述 | 英文版首段增加 "assistance tool" 描述 |
| Pro 价格 | ¥999/月(¥9,999/年) → **¥599/月(¥5,999/年)** |
| Enterprise 价格 | ¥99,800/月起 → **¥98,000/年** |
| Enterprise + ASPICE 咨询 | 删除整行 |
| 功能对比表 | Pro: ¥999/月 → ¥599/月 |
| 功能对比表 | Enterprise: ¥99,800/月 → ¥98,000/年 |
| Enterprise + ASPICE 咨询列 | 删除 |
| "为什么 Pro 值 ¥999/月" 标题 | → "为什么 Pro 值 ¥599/月" |
| "为什么 Enterprise 值得投资" | ¥99,800/月起 → ¥98,000/年 |
| Enterprise + ASPICE 咨询包章节 | 整节删除 |
| 常见疑问 Q&A | 更新涉及咨询包价格的部分 |

### 5. docs/edition-matrix.md

| 区域 | 变更内容 |
|:-----|:---------|
| 总览表 | Pro: ¥999/月 → ¥599/月 |
| 总览表 | Enterprise: ¥99,800/yr → ¥98,000/yr |
| Enterprise + 咨询列 | 删除或调整为 "Enterprise (含合规)" |

### 6. docs/faq.md

检查涉及定价的 FAQ，更新为新的价格数字。

### 7. 404.html

无定位语变更（通用错误页），不修改。

### 8. pipeline.html / osh-fusion-architecture.html

如页眉/页脚/定价引用存在，统一更新数字。

---

## 定位话术对照表

| 场景 | 旧话术 | 新话术 |
|:-----|:-------|:-------|
| 一句话定位 | AI-powered embedded development pipeline | **一站式 ASPICE 合规开发平台** |
| 副标题 | Automotive SPICE compliant out of the box | ASPICE 合规辅助 · 证据包自动生成 |
| 核心价值主张 | 从需求到固件，全自动 | **从需求到合规证据包，全自动** |
| 目标用户 | 嵌入式开发者 | 质量经理 · 架构师 · 嵌入式开发者 |
| 竞品对比 | 对标 Vector/dSPACE | 寄生 Vector/dSPACE 生态，做管线编排层 |
| 定价信息 | ¥299/月 (Pro) | **¥599/月** (Pro) |

---

## 适用原则

1. **"合规辅助" 而非 "合规认证"** — 所有文案避免暗示 yuleOSH 可替代 intacs 正式审计
2. **"证据包自动生成" 而非 "合规交付"** — 强调工具辅助生成审计资料
3. **B2B 专业感** — 定价数字传递专业信号（¥599 而非 ¥299/¥199）
4. **分层清晰** — Free 引流 → Pro 主力 → Enterprise 大单，三层分明

---

## 2026-07-05 专家评审后二次定位调整 (v3)

> **编制**: 小明 🔥（项目经理）
> **决策依据**: 双专家评审综合评分 6.1/10，AI 工具专家 & 汽车电子嵌入式专家一致建议

### 核心定位（v3 更新）

> **嵌入式软件合规开发自动化平台（ASPICE SWE 辅助工具）**

旧定位: "一站式 ASPICE 合规开发平台"
新定位: **"嵌入式软件合规开发自动化平台（ASPICE SWE 辅助工具）"**

变更理由:
1. AI 工具专家指出 "一站式" 承诺过高，建议改为 "AI 辅助合规自动化"
2. 汽车电子专家指出 ASPICE 过程域覆盖不足 30%（仅 SWE.1~SWE.6），"一站式" 是误导性承诺
3. 双方一致认为竞品对标 Vector/dSPACE 是致命错误——功能和深度差 3 个数量级
4. 双方一致认为需要删除所有 ISO 26262 / 功能安全对外提及

### v3 关键变更

| 项目 | 旧 (v2) | 新 (v3) |
|:-----|:---------|:---------|
| 一句话定位 | 一站式 ASPICE 合规开发平台 | **嵌入式软件合规开发自动化平台（SWE 辅助）** |
| 核心价值主张 | 从需求到合规证据包，全自动 | **AI 辅助 SWE.1~SWE.6 全流程，合规证据一键生成** |
| 竞品对标 | Vector/dSPACE | **手工三件套（Jenkins+Excel+Jira）** |
| ISO 26262 | 方法论已集成 | **全部删除** |
| 功能描述 | AI Agent 全自动流水线 | **AI 辅助流水线，人工把关关键环节** |

### 受影响文件

| 文件 | 状态 |
|:-----|:-----|
| README.md | ✅ 已更新 |
| index.html | ✅ 已更新 |
| frontend/out/index.html | ⏳ 待更新 |
| docs/pricing.md | ✅ 已更新 |
| docs/positioning.md | ⏳ 待更新 |
| docs/user-personas.md | ⏳ 待更新 |
| pricing.html | 未修改（静态页，同上个版本） |

---

*本记录由小马 🐴 统一编制，供所有对外页面修改参考。实际修改请在 `docs/` 和根目录 HTML 文件中同步执行。*
