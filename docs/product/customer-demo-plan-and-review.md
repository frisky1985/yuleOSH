# 🚀 yuleOSH 客户 Demo：Plan → Dev → Review 全流程

> **适用对象**：嵌入式开发团队 / ASPICE 合规团队
> **演示时长**：15 分钟
> **核心场景**：从自然语言需求到合规审查的端到端自动化

---

## 场景设定

> **"我想为 BCM Demo 增加 HIL 测试，验证门控、灯光、雨刮三个模块在硬件在环环境下的行为。"**

传统做法：写需求文档 → 评审 → 开发 → 手写测试 → 手动审查 → 追溯矩阵 → 拧巴。

yuleOSH 做法：一句话 → Ultra-Plan 出方案 → 确认 → 自动执行 → Review 审查 → 证据入库。

---

## Part 1：Ultra-Plan — 一句话出方案（3 min）

### 输入

```bash
$ yuleosh plan "为 BCM Demo 增加 HIL 测试，覆盖门控、灯光、雨刮三个模块"
```

### 输出

```
📋 Ultra-Plan: BCM Demo HIL 测试支持
══════════════════════════════════════

目标: 为 BCM Demo 门控/灯光/雨刮增加 HIL 测试

背景:
  ├─ 项目: BCM Demo (C语言嵌入式)
  ├─ 源文件: 28个 .c/.h 文件
  ├─ 已有测试: 12个 SIL 测试用例
  ├─ MISRA 已知率: ~95%
  └─ KG 追溯: ✅ implements 边已验证, validates 边已就位

技术方案:
  基于 yuleASR MCAL 层搭建 HIL 测试台架，
  复用现有 SIL 框架，扩展硬件在环场景。

步骤:
  [1] 小克 👨‍💻   HIL 测试框架搭建       2.0h
       ✅ 验证: HIL 测试可编译运行
  [2] 小克 👨‍💻   门控 HIL 用例开发       1.5h    依赖: [1]
       ✅ 验证: 3个门控 HIL 用例通过
  [3] 小克 👨‍💻   灯光+雨刮 HIL 用例开发   2.0h    依赖: [1]
       ✅ 验证: 6个 HIL 用例通过
  [4] 小马 🐴     HIL 覆盖审查             1.0h    依赖: [2,3]
       ✅ 验证: HIL layer 在 KG 中可追溯
  ────────────────────────────────────────────────
  总计: ~6.5h | 4 步骤 | 2 agents

风险:
  ⚠️  HIL 硬件台架可用性（需确认 yuleASR MCAL 配置）
  ⚠️  SIL→HIL 用例迁移可能有 20% 需重写

前置条件:
  🔧 yuleASR BSW 已部署
  🔧 HIL 硬件仿真器已连接
```

> 💡 **亮点**：底层自动读取 KG 追溯数据（implements/validates 边完整性）、扫描项目结构、按 agent 能力分配步骤、每个步骤自带验证条件。**零人工分析，3秒出方案。**

### 确认执行

```bash
# 审查计划内容后，一键确认执行
$ yuleosh plan --apply

✅ Plan approved! Injecting into CheckpointEngine...
  Step 1/4:  HIL 测试框架搭建  → 小克 👨‍💻  ... ✅
  Step 2/4:  门控 HIL 用例     → 小克 👨‍💻  ... ✅
  Step 3/4:  灯光+雨刮 HIL 用例 → 小克 👨‍💻  ... ✅
  Step 4/4:  HIL 覆盖审查      → 小马 🐴   ... ✅
```

`--apply` 将 Plan 注入 `CheckpointEngine`，自动按依赖顺序分配 agent 执行。支持 checkpoint 续跑（中途断网？重跑自动从断点恢复）。

---

## Part 2：代码审查 — Review 引擎（3 min）

### 自动审查

```bash
# 审查最近变更
$ yuleosh review auto

🔍 Auto-Review: recent changes (2 files changed)
═══════════════════════════════════════════════

Track A (AI Self-Check — non-blocking):
  ✅ [info]    bcm_door.c:45    命名风格一致
  ✅ [info]    bcm_light.c:122  函数长度 < 50行
  ⚠️  [minor]  bcm_door.c:78   缺少空指针检查: p_hal_config
  ℹ️  [info]    bcm_light.c:15  添加了 MIT 许可头部

Track B (Auto-Review — blocking):
  ✅ [pass]    MISRA Rule 8.2:  所有函数有原型声明
  ✅ [pass]    MISRA Rule 10.1: 无隐式类型转换
  ✅ [pass]    MISRA Rule 15.5: 函数单出口
  ✅ [pass]    MISRA Rule 16.1: switch 有 default 分支
  ────────────────────────────────────────────────
  Pass: 4 | Fail: 0 | Total: 4

📊 KG Impact Analysis:
  → 变更影响 2 个需求 (SWR-004.1, SWR-004.3)
  → 追溯链完整 ✅ (implements → covers → verifies)
```

> 💡 **亮点**：双轨审查同时跑——Track A 快速反馈（代码风格、常见缺陷），Track B 阻塞式审查（MISRA 规则、安全违规）。自动触发 KG 影响分析，告诉你"改了哪里、影响了哪个需求"。

### 审查指定任务

```bash
$ yuleosh review task bcm-hil-phase1

🔍 Task Review: bcm-hil-phase1
═══════════════════════════════

Files affected: 6 files (+1245 / -89 lines)
Module: bcm_demo

Track A (AI Self-Check):
  ✅ [info]    bcm_door.c:12      文件头注释完整
  ✅ [info]    bcm_hil_runner.c:55  循环复杂度 < 10
  ⚠️  [minor]  bcm_light.c:88    函数参数 > 5 个 (建议拆分)

Track B (Auto-Review):
  ✅ [major]   MISRA Rule 8.4:   外部链接函数有声明
  ✅ [critical] 无安全未初始化变量
  ⚠️  [major]   bcm_wiper.c:34   HAL 返回值未检查
  ────────────────────────────────────────────────
  Pass: 3 | Fail: 0 | Warnings: 2

Result: ✅ PASS (no blocking items)
Evidence: .osh/evidence/review-bcm-hil-phase1.json
```

### 对比两次审查结果

```bash
$ yuleosh review diff review-v1.json review-v2.json

📊 Review Diff: v1 → v2
══════════════════════════
Fixed:   2 items
  ✅ bcm_light.c:88    参数拆分（5→3参数）
  ✅ bcm_wiper.c:34    HAL 返回值检查已添加
New:     0 items
Unchanged: 3 items
```

---

## Part 3：端到端 — 全流程串联（5 min）

### 完整工作流

```bash
# ── 第 1 步：需求 → 方案 ──
$ yuleosh plan "为 BCM 增加 CAN 通信诊断模块"
# → 输出 6 步骤方案（含工时、agent 分配、验证条件）

# ── 第 2 步：确认执行 ──
$ yuleosh plan --apply
# → 注入 CheckpointEngine，自动化流水线启动

# ── 第 3 步：Pipeline 状态监控 ──
$ yuleosh pipeline status

📊 Pipeline Status: agent-pipeline
  ✅  [ 1] Spec Analysis          0.3s  
  ✅  [ 2] Architecture Design    1.2s  
  ✅  [ 3] CAN DBC Import         0.8s  
  ✅  [ 4] Diagnostic SWC Gen     2.1s  
  ✅  [ 5] Auto-Review            1.5s  
  ✅  [ 6] MISRA Check            3.0s  
  ─────────────────────────────────────
  Status: ✅ all 6 steps passed

# ── 第 4 步：审查结果 ──
$ yuleosh review auto
# → 双轨审查输出，KG 影响分析

# ── 第 5 步：合规证据入库 ──
$ yuleosh ev check --save

📋 ASPICE Compliance Check
══════════════════════════
Standard: ASPICE v3.1 | Version: 3.1
Total Base Practices: 18

✅ Passed:  11  (61.1%)
⚠️ Partial:  3  (16.7%)
❌ Failed:   4  (22.2%)

📊 KG Data (Real Traceability):
  ├─ Total Nodes:      11,200
  ├─ Total Edges:      16,673
  ├─ implements Edges: 523
  ├─ validates Edges:  42
  └─ CI Snapshots:     6

Per-Layer Coverage:
  ├─ unit:        96 covers (SWE.4)
  ├─ integration: 28 covers (SWE.5)
  ├─ sil:         12 covers (SWE.5)
  └─ hil:          2 covers (SWE.5)

Report saved: .osh/compliance-report.md
```

---

## Part 4：Qoder vs yuleOSH 对比

| 功能 | Qoder | yuleOSH |
|:-----|:------|:--------|
| **Plan Agent** | ✅ /plan 命令，生成实施计划 | ✅ `yuleosh plan`，含 KG 上下文感知 + CheckpointEngine 注入 |
| **Code Review** | ✅ 综合代码审查 | ✅ 双轨审查（Track A 快速 + Track B 阻塞）+ MISRA 专项 |
| **追溯分析** | ❌ 无 | ✅ KG 影响分析（改了什么→影响了哪个需求→是否可追溯）|
| **合规证据** | ❌ 无 | ✅ ASPICE Compliance Checker + 证据包自动生成 |
| **Pipeline 编排** | ❌ 单步骤 | ✅ 30 步 CheckpointEngine + 任意点注入 + 断点续跑 |
| **KG 数据底座** | ❌ 无 | ✅ 11K 节点 / 16K 边，per-layer 追溯语义分离 |
| **多 Agent 分工** | ❌ 单 AI | ✅ 小克（编码）+ 小马（审查）+ 小明（编排）|

---

## 一键 Demo

```bash
# 最快体验路径
$ pip install yuleosh
$ yuleosh demo quick "写一个刹车灯控制"

🚀 Quick Demo: 写一个刹车灯控制

  Step 1: Ultra-Plan  ──→ 3秒出方案
  Step 2: Dev          ──→ 代码生成
  Step 3: Auto-Review  ──→ 双轨审查
  Step 4: MISRA Check  ──→ 合规验证
  Step 5: KG 入库      ──→ 追溯证据
  ──────────────────────────
  Done! See .osh/reports/
```

---

## 总结

```
yuleosh plan "一句话需求"  →  Ultra-Plan 出方案
yuleosh plan --apply       →  CheckpointEngine 自动执行
yuleosh review auto        →  双轨审查 + MISRA + KG 影响分析
yuleosh ev check --save    →  ASPICE 合规证据入库
```

从"一句话"到"合规审计证据"，全自动闭环。

---

*文档版本 1.0 | 2026-07-15 | yuleOSH v2.2.0*
