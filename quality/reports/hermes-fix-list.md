# 🐴 yuleOSH 定价页面修复清单

> 审查人：小马（质量架构师）
> 审查版本：v0.1.0
> 审查日期：2026-06-18
> 审查范围：`page.tsx`（首页） & `pricing/page.tsx`（定价页）

---

## P0 — 数据正确性问题（应尽快修复）

### 🔴 P0-1. GitHub 链接不一致

| 页面 | 当前 URL | 文件 × 行号 |
|------|----------|-------------|
| 首页 | `github.com/stefanji/yuleOSH` ❌ | `page.tsx L533`, `L563` |
| 定价页 | `github.com/frisky1985/yuleOSH` ✅ | `pricing/page.tsx L515`, `L539` |

**问题**：首页 Footer 和底部的 GitHub 链接指向 `stefanji/yuleOSH`，但 git origin 是 `frisky1985/yuleOSH`。`stefanji` 是开发阶段名称，未更新。

**修复**：`page.tsx` L533 和 L563 将 `stefanji` 替换为 `frisky1985`。

---

## P1 — CTA 文案一致性（共 11 处需统一）

### 问题：当前 8 种不同 CTA 变体，用户困惑

| 象限 | 变体 | 位置 |
|------|------|------|
| Free 档 | "免费开始" | 首页 How-it-works CTA、首页定价快照 Free 卡、定价页 Free 卡 |
| Free 档 | "免费注册，无需信用卡" | 首页 Hero 下方行内链接 |
| Pro 档 | "免费试用 Pro" | 首页定价快照 Pro 卡、定价页 Pro 卡 |
| Nav + Hero | "开始免费试用" | 首页导航栏 L51、首页 Hero 主按钮 L129 |
| Features + 底 CTA | "免费开始试用" | 首页 Features 区 L228、首页底部 CTA L522、**定价页底部 CTA** |
| Footer | "免费试用" | 首页 Footer L562、定价页导航栏 / Footer |
| Team | "选择 Team" | 首页定价快照、定价页 |
| Enterprise | "联系 Enterprise" / "联系 Enterprise 团队" | 首页 "联系 Enterprise" → 定价页 "联系 Enterprise 团队"（差"团队"二字） |

### ✅ 推荐统一方案

按「动词+价值主张+时间」结构统一，每档位一条，不重复：

| 档位 | 推荐 CTA（中文） | 推荐 CTA（English） | 意图 |
|------|------------------|---------------------|------|
| **Free** | **免费开始** | Get Started Free | 零成本入门，无需承诺 |
| **Team** | **选择 Team** | Choose Team | 直接转化决策 |
| **Pro** | **免费试用 Pro** | Try Pro Free | 试用驱动 → 自然升级 |
| **Enterprise** | **联系销售** | Contact Sales | 减少拒绝感（"联系 Enterprise 团队"太长） |

**通用 CTA（导航/底部/通栏）**：

| 用途 | 中文 | English |
|------|------|---------|
| 导航栏/Footer 登录前入口 | **免费试用** | Free Trial |
| Hero 按钮 / 底部通栏 | **免费开始试用** | Get Started Free |
| 行内链接（小而轻） | **免费注册 →** | Register Free → |

### 🛠️ 具体修改清单（11 处）

#### page.tsx（首页，7 处）

| # | 位置 | 行号 | 当前文案 | 改为 |
|---|------|------|----------|------|
| 1 | 导航栏注册按钮 | L51 | "开始免费试用" | "免费试用" |
| 2 | Hero 主按钮 | L129 | "开始免费试用" | "免费开始试用" |
| 3 | Features 区 CTA | L228 | "免费开始试用" | "免费开始试用" ✅ 无需修改 |
| 4 | How-it-works CTA | L272 | "免费开始" | "免费试用"（或沿用统一行内风格） |
| 5 | 定价快照 Free 卡按钮 | L417 | "免费开始" | "免费开始" ✅ 一致，无需修改 |
| 6 | 底部 CTA | L522 | "免费开始试用" | "免费开始试用" ✅ 无需修改 |
| 7 | Footer 免费试用 | L562 | "免费试用" | "免费试用" ✅ 一致，无需修改 |

**实际需修改的首页 CTA：**

| 位置 | 行号 | 修改 |
|------|------|------|
| 导航栏注册按钮 | L51 | `开始免费试用` → `免费试用` |
| Hero 主按钮 | L129 | `开始免费试用` → `免费开始试用` |
| How-it-works CTA | L272 | `免费开始` → `免费试用` |
| Hero 下方行内链接 | L187 | `免费注册，无需信用卡` 可保留（特异性文案不冲突） |

#### pricing/page.tsx（定价页，4 处 i18n 文案）

| # | i18n Key | 行号 | 当前中文 | 改为 | English |
|---|----------|------|----------|------|---------|
| 8 | `zh.nav.freeTrial` | L33 | "免费试用" | "免费试用" ✅ | "Free Trial" ✅ |
| 9 | `zh.plans[0].cta`  (Free) | L55 | "免费开始" | "免费开始" ✅ | "Get Started Free" ✅ |
| 10 | `zh.plans[2].cta` (Pro) | L95 | "免费试用 Pro" | "免费试用 Pro" ✅ | "Try Pro Free" ✅ |
| 11 | `zh.cta.freeTrial` | L143 | "免费开始试用" | "免费开始试用" ✅ | "Get Started Free" ✅ |

> 实际上定价页的 i18n CTA 方案已符合推荐方案。**主要问题在首页的硬编码 CTA**。

---

## P2 — Free 卡信息缺失

### 2a. 首页定价快照 Free 卡 — 缺成员限制

**文件**：`page.tsx` L397–L416（Pricing Snapshot → Free Card）

**当前 features**：
```
- 基础 Pipeline · 3 项目
- AI Code Review 基础
- ESP32/STM32 + QEMU
```

**问题**：只说"3 项目"，没有"1-3 人"成员限制。用户可能误以为 Free 团队人数无限。

**建议修改**（L403-411 区域）：
```
- 1-3 人 · 3 项目
- AI Code Review 基础
- ESP32/STM32 + QEMU
```
或在第一行改为 `"基础 Pipeline · 1-3 人 · 3 项目"`。

### 2b. 定价页 Free 卡 — 功能列表缺成员限制

**文件**：`pricing/page.tsx` zh.plans[0].features（L47-L53）

**当前 features（zh）**：
```
1. 基础 Pipeline（Spec → Code → Test → CI）
2. 3 个项目限制
3. AI Code Review 基础规则
4. ESP32 / STM32 模板 + QEMU SIL
5. 社区支持（GitHub Issues）
```

**问题**：Description 写了"适合 1-3 人"，但 feature 列表中无成员限制字段。"3 个项目限制"不等于"1-3 人成员限制"。

**建议**：在 feature list 第 2 行改为 `"3 个项目 · 1-3 人限制"`，或将成员限制作为第 1 行单独feature：
```
1. 基础 Pipeline（Spec → Code → Test → CI）
2. 1-3 人成员 · 3 个项目
...
```

**英文对应修改**（en.plans[0].features）：
```
1. Basic Pipeline (Spec → Code → Test → CI)
2. 1-3 members · 3 project limit
...
```

### 2c. 首页快照 vs 定价页 — Free 卡功能完整性

首页快照 Free 卡有 3 条 feature，定价页有 5 条。快照缺了：
- `"社区支持（GitHub Issues）"`

建议快照至少提到社区支持，可通过第 4 条简写为 `"社区支持"`。

---

## P3 — 首页定价快照国际化

### 问题
- 首页定价快照区块（page.tsx ~L380-L500）使用**硬编码中文**
- 定价页（pricing/page.tsx）有完整的 `zh-CN` / `en` i18n 双语支持（含语言切换按钮）

### 决策建议

| 选项 | 风险 | 推荐度 |
|------|------|--------|
| **A. 保持中文，仅在中文版展示** | 中文用户看到双语定价页 + 中文快照，体验一致 ✅ | ⭐ 推荐 |
| **B. 同步做成 i18n 快照** | 需从定价页引入 `zh`/`en` i18n 对象到首页，改动较大 | 预算充足时可选 |
| **C. 快照引用定价页组件** | 抽取 PricingCards 为公共组件，首页和定价页复用 | 最佳长期方案 |

**推荐**：当前阶段选 **A**（中文版本专享快照），因为：
1. 首页目前整体为中文（no i18n），保持统一
2. 国际版用户跳转 `/pricing` 能看到完整的英文定价页
3. 避免首页和定价页同步两份 i18n 数据

如果未来首页要做 i18n（如英文版 landing），则应选 **C** 方案。

---

## P4 — 其他 UI/UX 建议

### 4a. 首页 Hero Badge 文案过长（非 P0）

**文件**：`page.tsx` L103

**当前**：
```
🚗 ASPICE Compliant · 开源 · 14天免费试用 · Docker 自托管
```

建议精简为：
```
🚗 ASPICE Compliant · 开源 · 14天免费试用
```
"Docker 自托管"已在 Hero 下方描述中体现了。4 段过于密集。

### 4b. 定价快照 Team 卡与定价页 Team 卡对齐

首页快照 Team 列了 3 条 key features，定价页列了 7 条。当前一致性好，不需要动。但「三层 CI/CD 流水线」是 Team 和 Pro 都含有的，建议在快照 Team 卡中也显示，以强化对比差异。

略提即止。

### 4c. 导航栏 Hero 按钮高 48px vs 定价页导航栏按钮高 42px

- `page.tsx` 导航栏注册按钮：`min-h-[48px]`（L49）
- `pricing/page.tsx` 导航栏注册按钮：`min-h-[42px]`（L196）

两者高度不一致。建议统一为 `min-h-[42px]` 或 `min-h-[44px]`。

---

## 汇总：按优先级排序

| 优先级 | 项目 | 文件 | 行号参考 | 工作量 |
|--------|------|------|----------|--------|
| 🔴 P0 | GitHub 链接 `stefanji`→`frisky1985` | `page.tsx` | L533, L563 | 2 行 |
| 🟠 P1 | CTA：导航栏 `开始免费试用` → `免费试用` | `page.tsx` | L51 | 1 行 |
| 🟠 P1 | CTA：Hero 主按钮 `开始免费试用` → `免费开始试用` | `page.tsx` | L129 | 1 行 |
| 🟠 P1 | CTA：How-it-works `免费开始` → `免费试用` | `page.tsx` | L272 | 1 行 |
| 🟡 P2 | Free 卡缺成员限制「1-3 人」 | 首页快照 `page.tsx` | L403-411 | 1 行 |
| 🟡 P2 | Free 卡 feature list 缺成员限制 | 定价页 `pricing/page.tsx` | L48-L53 (zh) + 英文对应 | 2 行 |
| 🔵 P3 | 快照国际化决策（推荐保持中文） | `page.tsx` | L380-L500 | 0 行（决策） |
| ⚪ P4 | Hero Badge 文案精简 | `page.tsx` | L103 | 1 行 |
| ⚪ P4 | 导航栏按钮高度统一（48px vs 42px） | 两文件 | L49 vs L196 | 1 行 |

---

**总结重点**：
1. **P0-1**（GitHub 链接错误）是必须马上修的数据错误
2. **P1**（CTA 统一）主要问题在首页 3 处硬编码差异，定价页 i18n 方案本身已达标
3. **P2**（Free 卡成员限制）是两个页面共同的系统性遗漏
4. **P3**（国际化）当前阶段保持中文快照即可，不修
5. **P4**（UI 微调）可选优化
